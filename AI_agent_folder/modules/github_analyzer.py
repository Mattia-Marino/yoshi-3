"""
github_analyzer.py — metriche GitHub (PR, Issue, Review) sulle finestre T-6 / T+6.

Script separato e indipendente da git_analyzer.go: qui si usano le API REST di
GitHub (serve un token), non i clon locali.

Input:
  - results/adoption_events.csv  (T_1 per repo, colonna 'data')
  - results/git_metrics.csv      (stato delle finestre: usato per la selezione
                                  e per non ripetere controlli gia' eseguiti)
  - i clon in C:\\Users\\geppe\\Desktop\\Cloning_repo (elenco dei repository)

Finestre (coerenti con git_analyzer):
  pre  = [T_1 - 6 mesi, T_1)      (T_1 escluso)
  post = [T_1, T_1 + 6 mesi)      (T_1 incluso: il commit che introduce l'artefatto
                                   AI appartiene a T+6)
  bordi a mezzanotte UTC; tutte le date API sono UTC.

Regole temporali:
  - una PR/Issue e' "del periodo" solo se CREATA nella finestra;
    elementi creati prima non entrano nei conteggi anche se chiusi/uniti dopo;
  - le metriche di durata usano solo elementi creati nella finestra il cui evento
    conclusivo (chiusura/merge/primaa review) avviene entro la fine della finestra;
  - le review contano in base a submitted_at (una review inviata prima di T_1
    non viene attribuita a T+6).

Metriche (per ogni finestra, colonne *_pre e *_post):
  PR    : aperte, chiuse, merged, aperte alla fine, % merge (su chiuse),
          tempo medio di merge, contributori, media additions/deletions/totale;
  Issue : aperte, chiuse, tempo medio di chiusura, contributori,
          commenti medi, % chiusura (su aperte);
  Review: totale, reviewer distinti, review per PR (su PR create nella finestra),
          APPROVED, CHANGES_REQUESTED, tempo medio alla prima review.

Valori non calcolabili -> campo VUOTO (mai 0 al posto del mancante).

Limiti noti:
  - le review vengono scaricate per le PR attive durante la finestra (aggiornate
    entro la finestra): PR con zero attivita' nella finestra non possono aver
    ricevuto review nella finestra, quindi l'insieme e' completo per lo scopo;
  - le PR create nella finestra ma mai aggiornate dopo sono comunque inclusi
    (created_at <= updated_at).

Token: variabile d'ambiente GITHUB_TOKEN (o GH_TOKEN). Mai scritto nel codice.

Uso:
  python github_analyzer.py --dry-run          # solo selezione + stima richieste
  python github_analyzer.py                    # test completo su 5 repository
  python github_analyzer.py --n 5 --concurrency 2
  python github_analyzer.py --repo owner/a,owner/b
Output: results/github_metrics.csv
"""

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPOS_DIR = Path(r"C:\Users\geppe\Desktop\Cloning_repo")
RESULTS_DIR = Path(r"C:\Users\geppe\Desktop\Progetto_Tamburri\yoshi-3\AI_agent_folder\results")
EVENTS_FILE = RESULTS_DIR / "adoption_events.csv"
GIT_METRICS_FILE = RESULTS_DIR / "git_metrics.csv"
OUT_FILE = RESULTS_DIR / "github_metrics.csv"
CACHE_DIR = Path(r"C:\Users\geppe\Desktop\Progetto_Tamburri\yoshi-3\AI_agent_folder\cache\github")

API = "https://api.github.com"
WINDOW_MONTHS = 6
PER_PAGE = 100
MIN_RATE_REMAINING = 50      # soglia: sotto, si attende il reset
MAX_WAIT_RESET = 900         # secondi massimi di attesa per reset (poi si abortisce)
MAX_RETRIES = 4

# metriche nella ordine delle colonne del CSV
PR_METRICS = [
    "pr_aperte", "pr_chiuse", "pr_merged", "pr_aperte_alla_fine",
    "pr_pct_merge", "pr_tempo_medio_merge_giorni", "pr_contributori",
    "pr_media_add", "pr_media_del", "pr_media_tot",
]
ISSUE_METRICS = [
    "issue_aperte", "issue_chiuse", "issue_tempo_medio_chiusura_giorni",
    "issue_contributori", "issue_commenti_medi", "issue_pct_chiusura",
]
REVIEW_METRICS = [
    "review_totale", "review_reviewer_distinti", "review_per_pr",
    "review_approvate", "review_modifiche_richieste",
    "review_tempo_medio_prima_review_giorni",
]
METRICS = PR_METRICS + ISSUE_METRICS + REVIEW_METRICS

FIELDS = (
    ["repository", "t1", "stato", "pre_start", "pre_end", "post_start", "post_end"]
    + [f"{m}_{s}" for m in METRICS for s in ("pre", "post")]
    + ["richieste_api"]
)


# ---------------------------------------------------------------------- date

def add_months(d: date, n: int) -> date:
    """Come git_analyzer.add_months (divmod + clamp del giorno)."""
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    dim = 29 if (month == 2 and leap) else [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, dim))


def windows_for(t1: date):
    """Ritorna (pre_start, pre_end, post_start, post_end) come datetime UTC."""
    def midnight(d):
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    pre_start = midnight(add_months(t1, -WINDOW_MONTHS))
    post_end = midnight(add_months(t1, WINDOW_MONTHS))
    t1d = midnight(t1)
    return pre_start, t1d, t1d, post_end


def parse_ts(s):
    """'2026-04-17T12:34:56Z' -> datetime UTC; None/invalid -> None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def in_window(ts, start, end):
    """[start, end): start incluso, end escluso."""
    return ts is not None and start <= ts < end


def mean(vals):
    """Media arrotondata a 2 decimali; lista vuota -> None (campo vuoto)."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def fmt(v):
    """Valore per il CSV: None -> '' (mancante), mai 0 sostitutivo."""
    return "" if v is None else v


# ---------------------------------------------------------------------- HTTP

class RateLimitExceeded(Exception):
    pass


class GitHubClient:
    """Client REST con cache su disco, contatore richieste e rispetto rate limit."""

    def __init__(self, token, cache=True, dry_run=False):
        self.token = token
        self.cache_enabled = cache
        self.dry_run = dry_run
        self.lock = threading.Lock()
        self.requests = 0            # richieste API reali (cache esclusa)
        self.cache_hits = 0
        self.by_repo = {}            # repo -> richieste reali
        self.current_repo = "-"
        self.rate_remaining = None
        self.rate_reset = None
        self.errors = []
        self.abort = None          # motivo di interruzione per rate limit
        self._last_search = 0.0

    # --- contatori ---
    def _count(self):
        with self.lock:
            self.requests += 1
            self.by_repo[self.current_repo] = self.by_repo.get(self.current_repo, 0) + 1

    def _cache_path(self, url):
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return CACHE_DIR / (h + ".json")

    def _cache_read(self, url):
        if not self.cache_enabled:
            return None
        p = self._cache_path(url)
        if not p.exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)["body"]
        except Exception:
            return None

    def _cache_write(self, url, body):
        if not self.cache_enabled:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path(url).with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"url": url, "ts": datetime.now(timezone.utc).isoformat(), "body": body}, f)
            tmp.replace(self._cache_path(url))
        except Exception:
            pass

    def _update_rate(self, headers):
        try:
            rem = headers.get("X-RateLimit-Remaining")
            rst = headers.get("X-RateLimit-Reset")
            if rem is not None:
                self.rate_remaining = int(rem)
            if rst is not None:
                self.rate_reset = int(rst)
        except (TypeError, ValueError):
            pass

    def _wait_if_exhausted(self):
        if self.rate_remaining is None or self.rate_remaining > MIN_RATE_REMAINING:
            return
        wait = (self.rate_reset or int(time.time())) - int(time.time()) + 5
        if wait > MAX_WAIT_RESET:
            raise RateLimitExceeded(
                f"rate limit quasi esaurito (rimanenti={self.rate_remaining}), "
                f"reset tra {wait}s > {MAX_WAIT_RESET}s: interrotto per sicurezza"
            )
        print(f"  [RATE] {self.rate_remaining} richieste rimanenti, attendo {wait}s per il reset...")
        time.sleep(wait)
        self.rate_remaining = None

    def get(self, url, repo=None, is_search=False):
        """GET JSON. Ritorna il body; lancia RateLimitExceeded se non si puo' procedere."""
        cached = self._cache_read(url)
        if cached is not None:
            with self.lock:
                self.cache_hits += 1
            return cached

        if is_search:
            # limite search separato (30/min autenticati, 10/min anonimi): pacing
            with self.lock:
                gap = 7.0 if not self.token else 2.0
                wait = self._last_search + gap - time.time()
                self._last_search = max(time.time(), self._last_search + gap)
            if wait > 0:
                time.sleep(wait)

        self._wait_if_exhausted()

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "yoshi3-github-analyzer",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        last_err = None
        for attempt in range(MAX_RETRIES):
            self._count()
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self._update_rate(resp.headers)
                    body = json.loads(resp.read().decode("utf-8", "replace"))
                self._cache_write(url, body)
                return body
            except urllib.error.HTTPError as e:
                self._update_rate(e.headers)
                msg = ""
                try:
                    msg = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
                except Exception:
                    pass
                if e.code == 403 and "rate limit" in msg.lower():
                    # rate limit primario esaurito: attendi il reset
                    reset = int(e.headers.get("X-RateLimit-Reset") or time.time())
                    wait = reset - int(time.time()) + 5
                    if wait > MAX_WAIT_RESET:
                        raise RateLimitExceeded(f"rate limit esaurito, reset tra {wait}s")
                    print(f"  [RATE] 403 rate limit, attendo {wait}s...")
                    time.sleep(wait)
                    continue
                if e.code in (403, 429):
                    # secondary rate limit / throttling: Retry-After o backoff
                    ra = e.headers.get("Retry-After")
                    wait = int(ra) if ra and ra.isdigit() else min(60 * (attempt + 1), 180)
                    print(f"  [THROTTLE] HTTP {e.code}: {msg[:80]} -> attendo {wait}s")
                    time.sleep(wait)
                    continue
                if e.code >= 500:
                    time.sleep(2 ** attempt)
                    last_err = f"HTTP {e.code}: {msg[:120]}"
                    continue
                # errore 4xx definitivo (404, 422, ...)
                self.errors.append(f"{self.current_repo}: HTTP {e.code} {msg[:100]}")
                raise RuntimeError(f"HTTP {e.code}: {msg[:120]}")
            except urllib.error.URLError as e:
                last_err = str(e)[:120]
                time.sleep(2 ** attempt)
            except TimeoutError:
                last_err = "timeout"
                time.sleep(2 ** attempt)
        self.errors.append(f"{self.current_repo}: {last_err}")
        raise RuntimeError(f"richiesta fallita dopo {MAX_RETRIES} tentativi: {last_err}")

    def search_count(self, query):
        """total_count di una search (1 richiesta)."""
        q = urllib.parse.quote(query)
        url = f"{API}/search/issues?q={q}&per_page=1"
        body = self.get(url, is_search=True)
        return int(body.get("total_count", 0))


# ---------------------------------------------------------------------- fetch

def paginate(client, url_base, params, cutoff_iso, repo):
    """Pagina un endpoint con `since`/`sort=created` fino a superare il cutoff.

    - url_base: es. /repos/o/r/pulls  (params: state, sort, direction, since...)
    - cutoff_iso: data ISO; la paginazione si ferma quando la data di creazione
      dell'ultimo elemento della pagina e' < cutoff (gli elementi sono in ordine
      decrescente di creazione con sort=created&direction=desc).
    Ritorna la lista completa degli item.
    """
    items = []
    page = 1
    cutoff = parse_ts(cutoff_iso)
    while True:
        params = dict(params, per_page=PER_PAGE, page=page)
        qs = urllib.parse.urlencode(params)
        body = client.get(f"{API}{url_base}?{qs}", repo=repo)
        if not isinstance(body, list):
            raise RuntimeError(f"risposta inattesa da {url_base}: {type(body).__name__}")
        items.extend(body)
        if len(body) < PER_PAGE:
            break
        oldest = min((parse_ts(it.get("created_at")) for it in body if it.get("created_at")),
                     default=None)
        if oldest is None or (cutoff and oldest < cutoff):
            break
        page += 1
        if page > 500:  # sicurezza
            break
    return items


def fetch_listing(client, repo, since_iso):
    """Lista unica /issues?state=all&since=<since_iso> (issue + PR): tutto cio'
    che e' stato aggiornato da since.

    Copre tutti gli insiemi serviti:
      - issue create nella finestra: created >= inizio finestra => updated >= inizio;
      - PR create nella finestra: idem;
      - PR con attivita' nella finestra: una review (o qualsiasi modifica)
        aggiorna updated_at, quindi una PR reviewata nella finestra rientra.
    `since` e' un filtro lato server: la paginazione va a esaurimento
    (cutoff=None), ordinando per created desc (campo stabile, niente scatti)."""
    return paginate(
        client, f"/repos/{repo}/issues",
        {"state": "all", "sort": "created", "direction": "desc",
         "since": f"{since_iso}T00:00:00Z"},
        None, repo,
    )


def split_listing(items):
    """Separa la lista /issues in (PR, issue): le PR hanno la chiave 'pull_request'."""
    prs = [i for i in items if "pull_request" in i]
    issues = [i for i in items if "pull_request" not in i]
    return prs, issues


def active_for_reviews(prs, pre_start, post_end):
    """PR che possono aver ricevuto una review durante le finestre:
    create prima della fine di T+6 e ancora aperte (o chiuse) da almeno
    l'inizio di T-6. Le PR create nella finestra sono sempre incluse."""
    out = []
    for p in prs:
        created = parse_ts(p.get("created_at"))
        if created is None or created >= post_end:
            continue
        closed = parse_ts(p.get("closed_at"))
        if p.get("closed_at") and closed is not None and closed < pre_start:
            continue
        out.append(p)
    return out


def fetch_pull_detail(client, repo, number):
    """GET /pulls/{n}: serve per additions/deletions (non presenti nella lista)."""
    return client.get(f"{API}/repos/{repo}/pulls/{number}", repo=repo)


def fetch_reviews(client, repo, number):
    """Tutte le review di una PR (paginazione se > 100)."""
    out, page = [], 1
    while True:
        body = client.get(
            f"{API}/repos/{repo}/pulls/{number}/reviews?per_page={PER_PAGE}&page={page}",
            repo=repo,
        )
        if not isinstance(body, list):
            break
        out.extend(body)
        if len(body) < PER_PAGE:
            break
        page += 1
    return out


# ------------------------------------------------------------------ metriche

def pr_metrics(prs, details, start, end):
    """prs: PR create nella FINESTRA (già filtrate dal chiamante).
    details: {number: {additions, deletions}} per le PR create nella finestra."""
    n = len(prs)
    if n == 0:
        return {m: None for m in PR_METRICS}

    closed = [p for p in prs if in_window(parse_ts(p.get("closed_at")), start, end)]
    merged = [p for p in prs if in_window(parse_ts(p.get("merged_at")), start, end)]
    still_open = n - len(closed)   # create nella finestra, non chiuse entro la fine

    # tempo medio di merge: solo PR create qui e unite entro la fine della finestra
    merge_days = []
    for p in merged:
        c, m = parse_ts(p.get("created_at")), parse_ts(p.get("merged_at"))
        if c and m:
            merge_days.append((m - c).total_seconds() / 86400)

    adds = [details[p["number"]]["additions"] for p in prs
            if p.get("number") in details]
    dels = [details[p["number"]]["deletions"] for p in prs
            if p.get("number") in details]
    tots = [a + d for a, d in zip(adds, dels)]

    return {
        "pr_aperte": n,
        "pr_chiuse": len(closed),
        "pr_merged": len(merged),
        "pr_aperte_alla_fine": still_open,
        # denominatore: PR chiuse (merged e' sottoinsieme di chiuse)
        "pr_pct_merge": round(100.0 * len(merged) / len(closed), 2) if closed else None,
        "pr_tempo_medio_merge_giorni": mean(merge_days),
        "pr_contributori": len({(p.get("user") or {}).get("login") for p in prs}
                               - {None}),
        "pr_media_add": mean(adds),
        "pr_media_del": mean(dels),
        "pr_media_tot": mean(tots),
    }


def issue_metrics(issues, start, end):
    """issues: issue create nella FINESTRA (PR gia' escluse)."""
    n = len(issues)
    if n == 0:
        return {m: None for m in ISSUE_METRICS}

    closed = [i for i in issues if in_window(parse_ts(i.get("closed_at")), start, end)]
    close_days = []
    for i in closed:
        c, z = parse_ts(i.get("created_at")), parse_ts(i.get("closed_at"))
        if c and z:
            close_days.append((z - c).total_seconds() / 86400)

    return {
        "issue_aperte": n,
        "issue_chiuse": len(closed),
        "issue_tempo_medio_chiusura_giorni": mean(close_days),
        "issue_contributori": len({(i.get("user") or {}).get("login") for i in issues}
                                  - {None}),
        # media dei commenti su tutte le issue create nella finestra
        "issue_commenti_medi": mean([i.get("comments") or 0 for i in issues]),
        # denominatore: issue create nella finestra
        "issue_pct_chiusura": round(100.0 * len(closed) / n, 2),
    }


def review_metrics(reviews_by_pr, prs_created, start, end):
    """reviews_by_pr: {pr_number: [review...]}; reviews: inviate nella finestra
    (filtro su submitted_at, non sulla data della PR).
    prs_created: PR create nella finestra (per review/PR e prima review)."""
    in_win = []
    for num, revs in reviews_by_pr.items():
        for r in revs:
            if in_window(parse_ts(r.get("submitted_at")), start, end):
                in_win.append(r)

    n_prs = len(prs_created)
    if n_prs == 0 and not in_win:
        return {m: None for m in REVIEW_METRICS}

    # tempo alla prima review: PR create nella finestra con evento conclusivo
    # (prima review) entro la fine della finestra
    first_days = []
    for p in prs_created:
        revs = [parse_ts(r.get("submitted_at")) for r in reviews_by_pr.get(p["number"], [])]
        revs = sorted(t for t in revs if t and t < end)
        c = parse_ts(p.get("created_at"))
        if revs and c:
            first_days.append((revs[0] - c).total_seconds() / 86400)

    return {
        "review_totale": len(in_win),
        "review_reviewer_distinti": len({(r.get("user") or {}).get("login")
                                         for r in in_win} - {None}),
        # denominatore: PR create nella finestra
        "review_per_pr": round(len(in_win) / n_prs, 2) if n_prs else None,
        "review_approvate": sum(1 for r in in_win if r.get("state") == "APPROVED"),
        "review_modifiche_richieste": sum(1 for r in in_win
                                          if r.get("state") == "CHANGES_REQUESTED"),
        "review_tempo_medio_prima_review_giorni": mean(first_days),
    }


# ----------------------------------------------------------------- selezione

def load_events():
    """Chiave = nome cartella repo in minuscolo (come git_analyzer)."""
    events = {}
    with open(EVENTS_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("repository") or "").split("/")[-1].strip().lower()
            events[key] = row
    return events


def load_git_metrics():
    """Righe di git_metrics.csv indicizzate per nome cartella in minuscolo."""
    rows = {}
    if not GIT_METRICS_FILE.exists():
        return rows
    with open(GIT_METRICS_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("repository") or "").split("/")[-1].strip().lower()
            rows[key] = row
    return rows


def select_repos(events, gm_rows, n_target, today, explicit=None):
    """Selezione dei repository idonei.

    Criteri (tutti richiesti):
      1. T1 identificato in adoption_events.csv;
      2. presente in git_metrics.csv con stato 'ok' (=> finestra T+6 completa
         e controlli gia' eseguiti, non ripetuti);
      3. finestra T-6 completa: il clone esiste e la sua prima commit e'
         anteriore o uguale a T1 - 6 mesi;
      4. T1 non futuro.
    Ritorna (scelti, esclusi, idonei_non_scelti) con motivazioni.
    """
    folders = {p.name.lower(): p for p in REPOS_DIR.iterdir() if p.is_dir()} \
        if REPOS_DIR.is_dir() else {}

    candidates, excluded = [], []
    for key, ev in sorted(events.items(), key=lambda kv: kv[0]):
        full = ev.get("repository") or ""
        t1s = (ev.get("data") or "").strip()
        if not t1s:
            excluded.append((full, "nessun T1 (nessun file per agenti AI)"))
            continue
        gm = gm_rows.get(key)
        if gm is None:
            excluded.append((full, "assente da git_metrics.csv"))
            continue
        if (gm.get("stato") or "") != "ok":
            excluded.append((full, f"stato git_metrics = '{gm.get('stato')}' "
                                   "(finestra post incompleta)"))
            continue
        try:
            t1 = date.fromisoformat(t1s)
        except ValueError:
            excluded.append((full, f"data T1 non valida: {t1s}"))
            continue
        if t1 > today:
            excluded.append((full, "T1 nel futuro"))
            continue
        folder = folders.get(key)
        if folder is None:
            excluded.append((full, "clone locale non trovato"))
            continue
        # T-6 completa: prima commit del clone <= T1 - 6 mesi
        first = first_commit_date(folder)
        if first is None:
            excluded.append((full, "impossibile leggere la prima commit del clone"))
            continue
        if first > add_months(t1, -WINDOW_MONTHS):
            excluded.append((full, f"T-6 incompleta: clone inizia {first.isoformat()}, "
                                   f"finestra vorrebbe {add_months(t1, -WINDOW_MONTHS).isoformat()}"))
            continue
        candidates.append({
            "full": full, "folder": folder, "key": key, "t1": t1, "t1s": t1s,
            "first_commit": first,
        })

    if explicit:
        want = {w.strip().lower() for w in explicit if w.strip()}
        chosen = [c for c in candidates if c["full"].lower() in want]
        missing = want - {c["full"].lower() for c in chosen}
        for m in sorted(missing):
            excluded.append((m, "richiesto esplicitamente ma non idoneo"))
        return chosen, excluded, []

    # scelta deterministica: i primi n in ordine alfabetico tra gli idonei
    chosen = candidates[:n_target]
    not_chosen = [(c["full"], "idoneo ma non selezionato (oltre i %d)" % n_target)
                  for c in candidates[n_target:]]
    return chosen, excluded, not_chosen


def first_commit_date(folder: Path):
    """Data (solo giorno, UTC) della prima commit raggiungibile da HEAD.

    NOTA: `git log --reverse -1` applica il limite PRIMA del reverse e
    restituirebbe l'ultima commit: si usano i commit root (-max-parents=0)."""
    try:
        p = subprocess.run(
            ["git", "-C", str(folder), "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None
    if p.returncode != 0 or not p.stdout.strip():
        return None
    roots = p.stdout.split()
    dates = []
    for sha in roots:
        try:
            q = subprocess.run(
                ["git", "-C", str(folder), "show", "-s", "--format=%aI", sha],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            continue
        if q.returncode == 0 and q.stdout.strip():
            ts = parse_ts(q.stdout.strip())
            if ts:
                dates.append(ts.date())
    if not dates:
        return None
    return min(dates)


# ------------------------------------------------------------------ analisi

def iso(d: date) -> str:
    return d.isoformat()


def analyze_repo(client, cand, workers):
    """Analizza un repository su entrambe le finestre.
    Ritorna (riga_csv, note_errore)."""
    repo, t1 = cand["full"], cand["t1"]
    pre_start, pre_end, post_start, post_end = windows_for(t1)
    client.current_repo = repo
    client.abort = None
    req_before = client.by_repo.get(repo, 0)

    row = {
        "repository": repo, "t1": cand["t1s"], "stato": "ok",
        "pre_start": pre_start.date().isoformat(),
        "pre_end": pre_end.date().isoformat(),
        "post_start": post_start.date().isoformat(),
        "post_end": post_end.date().isoformat(),
    }
    notes = []

    # Lista unica (issue + PR) con `since` = inizio T-6: copre le PR/issue
    # create nelle finestre e le PR attive (e quindi reviewabili) in finestra.
    since_iso = pre_start.date().isoformat()

    try:
        listing = fetch_listing(client, repo, since_iso)
    except RateLimitExceeded as e:
        row["stato"] = f"interrotto: {e}"
        return row, str(e)
    except RuntimeError as e:
        row["stato"] = f"errore: {e}"
        return row, str(e)

    pulls, issues = split_listing(listing)

    # PR/issue create in ciascuna finestra
    pulls_pre = [p for p in pulls if in_window(parse_ts(p.get("created_at")), pre_start, pre_end)]
    pulls_post = [p for p in pulls if in_window(parse_ts(p.get("created_at")), post_start, post_end)]
    issues_pre = [i for i in issues if in_window(parse_ts(i.get("created_at")), pre_start, pre_end)]
    issues_post = [i for i in issues if in_window(parse_ts(i.get("created_at")), post_start, post_end)]

    # details: additions/deletions servono solo per le PR create nelle finestre
    # (1 richiesta a PR) -> stimabile; qui li scarichiamo in parallelo.
    nums = sorted({p["number"] for p in pulls_pre + pulls_post})
    details = {}
    missing_reviews = 0

    def _detail(num):
        try:
            d = fetch_pull_detail(client, repo, num)
            return num, {"additions": d.get("additions", 0), "deletions": d.get("deletions", 0)}
        except RateLimitExceeded as e:
            with client.lock:
                client.abort = client.abort or str(e)
            return num, None
        except RuntimeError:
            return num, None

    if nums:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for num, d in ex.map(_detail, nums):
                if d is not None:
                    details[num] = d
    if client.abort:
        row["stato"] = f"interrotto: {client.abort}"
        row["richieste_api"] = client.by_repo.get(repo, 0) - req_before
        return row, client.abort
    missing_details = len(nums) - len(details)
    if missing_details:
        notes.append(f"dettagli PR mancanti: {missing_details}/{len(nums)}")

    # reviews: 1 richiesta a PR (paginata). Servono per entrambe le finestre:
    # si considerano TUTTE le PR attive nella finestra (non solo quelle create
    # qui), per non perdere le review su PR vecchie ricevute in questo periodo.
    rev_nums = sorted({p["number"] for p in active_for_reviews(pulls, pre_start, post_end)})
    reviews_by_pr = {}

    def _reviews(num):
        try:
            return num, fetch_reviews(client, repo, num)
        except RateLimitExceeded as e:
            with client.lock:
                client.abort = client.abort or str(e)
            return num, None
        except RuntimeError:
            return num, None

    if rev_nums:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for num, revs in ex.map(_reviews, rev_nums):
                if revs is None:
                    missing_reviews += 1
                else:
                    reviews_by_pr[num] = revs
    if client.abort:
        row["stato"] = f"interrotto: {client.abort}"
        row["richieste_api"] = client.by_repo.get(repo, 0) - req_before
        return row, client.abort
    if missing_reviews:
        notes.append(f"review mancanti: {missing_reviews}/{len(rev_nums)}")

    # --- metriche per finestra ---
    for suffix, pulls_w, issues_w, s, e in (
        ("pre", pulls_pre, issues_pre, pre_start, pre_end),
        ("post", pulls_post, issues_post, post_start, post_end),
    ):
        pr_m = pr_metrics(pulls_w, details, s, e)
        is_m = issue_metrics(issues_w, s, e)
        rv_m = review_metrics(reviews_by_pr, pulls_w, s, e)
        for k, v in pr_m.items():
            row[f"{k}_{suffix}"] = fmt(v)
        for k, v in is_m.items():
            row[f"{k}_{suffix}"] = fmt(v)
        for k, v in rv_m.items():
            row[f"{k}_{suffix}"] = fmt(v)

    row["richieste_api"] = client.by_repo.get(repo, 0) - req_before
    if notes:
        row["stato"] = "ok con note: " + "; ".join(notes)
    return row, None


def estimate_requests(client, cand):
    """Stima le richieste per un repo usando 2 search (PR e issue nel range)."""
    repo = cand["full"]
    since = add_months(cand["t1"], -WINDOW_MONTHS).isoformat()
    until = add_months(cand["t1"], WINDOW_MONTHS).isoformat()
    q_pr = f"repo:{repo} type:pr created:{since}..{until}"
    q_is = f"repo:{repo} type:issue created:{since}..{until}"
    # PR attive nella finestra (per le review): create prima di T+6 e non
    # chiuse prima di T-6 -> approx via updated nel range
    q_act = f"repo:{repo} type:pr updated:{since}..{until}"
    n_pr = client.search_count(q_pr)
    n_is = client.search_count(q_is)
    n_act = client.search_count(q_act)
    # pagine della lista unica (/issues) + 1 detail per PR creata +
    # 1 reviews per PR attiva
    pages = -(-(n_pr + n_is) // PER_PAGE)
    est = pages + n_pr + n_act
    return n_pr, n_is, est, n_act


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Metriche GitHub (PR/Issue/Review) su T-6 / T+6")
    ap.add_argument("--n", type=int, default=5, help="quanti repository analizzare (default 5)")
    ap.add_argument("--repo", type=str, default="",
                    help="lista esplicita owner/name,owner/name (bypassa la selezione)")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="richieste parallele per repo (default 4; max 8)")
    ap.add_argument("--dry-run", action="store_true",
                    help="selezione + stima richieste, senza scaricare i dettagli")
    ap.add_argument("--by-size", action="store_true",
                    help="seleziona i repository a minor volume (stima le richieste "
                         "su una pool di candidati leggeri e prende i piu' piccoli)")
    ap.add_argument("--pool", type=int, default=20,
                    help="quanti candidati leggeri stimare con --by-size (default 20)")
    ap.add_argument("--no-cache", action="store_true", help="disabilita la cache su disco")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token and not args.dry_run:
        print("ERRORE: nessun token trovato. Imposta la variabile d'ambiente "
              "GITHUB_TOKEN (o GH_TOKEN) e riesegui.")
        return 1
    if not token:
        print("[AVVISO] nessun token: dry-run in anonimo (limite search 10/min). "
              "Per il test completo serve GITHUB_TOKEN.")
    workers = max(1, min(args.concurrency, 8))

    if not EVENTS_FILE.exists():
        print(f"ERRORE: manca {EVENTS_FILE}: esegui prima adoption_detector.py")
        return 1
    if not GIT_METRICS_FILE.exists():
        print(f"ERRORE: manca {GIT_METRICS_FILE}: esegui prima git_analyzer")
        return 1

    t_start = time.time()
    today = date.today()
    events = load_events()
    gm_rows = load_git_metrics()

    explicit = [x for x in args.repo.split(",") if x.strip()] if args.repo else None

    if explicit:
        chosen, excluded, not_chosen = select_repos(events, gm_rows, args.n, today, explicit)
        pool = chosen
    else:
        # tutti gli idonei, per poterli ordinare per volume
        all_ok, excluded, _ = select_repos(events, gm_rows, len(events), today, None)
        if args.by_size:
            # proxy locale gratuito: commits nella finestra pre (git_metrics.csv)
            def _commits(c):
                v = (gm_rows.get(c["key"], {}) or {}).get("commits_pre") or ""
                try:
                    return int(v)
                except ValueError:
                    return 10 ** 9
            ordered = sorted(all_ok, key=lambda c: (_commits(c), c["full"]))
            pool = ordered[:max(args.pool, args.n)]
            print(f"[by-size] pool stimata: {len(pool)} candidati leggeri "
                  f"(ordinati per commits_pre; proxy locale, nessuna richiesta)")
        else:
            ordered = sorted(all_ok, key=lambda c: c["full"])
            pool = ordered[:args.n]
        chosen = pool
        not_chosen = [(c["full"], "idoneo ma non selezionato (oltre i %d)" % args.n)
                      for c in all_ok if c not in pool]

    client = GitHubClient(token, cache=not args.no_cache)

    # ---- stima richieste (3 search per repo) ----
    print("\nSTIMA richieste API per repository (via search API):")
    est_by_repo = {}
    for c in pool:
        try:
            n_pr, n_is, est, n_act = estimate_requests(client, c)
        except (RuntimeError, RateLimitExceeded) as e:
            print(f"   {c['full']}: stima non disponibile ({e})")
            continue
        est_by_repo[c["full"]] = (n_pr, n_is, n_act, est)
        print(f"   {c['full']}: PR={n_pr} issue={n_is} PR_attive={n_act} -> ~{est} richieste "
              f"(pagine lista + detail PR + reviews PR attive)")

    if args.by_size and not explicit:
        # scelta finale: i n con la stima piu' bassa
        ordered = sorted(pool, key=lambda c: est_by_repo.get(c["full"], (0, 0, 0, 10 ** 9))[3])
        chosen = [c for c in ordered if c["full"] in est_by_repo][:args.n]

        def _why_not(c):
            est = est_by_repo.get(c["full"])
            if est is None:
                return "stima non disponibile"
            return f"idoneo ma fuori dalla selezione per volume (~{est[3]:,} richieste)"

        not_chosen = [(c["full"], _why_not(c)) for c in all_ok if c not in chosen]

    # ---- report selezione ----
    print("\n" + "=" * 70)
    print(f"Candidati idonei: {len(chosen) + len(not_chosen)} "
          f"(su {len(events)} repository con evento); scelti: {len(chosen)}")
    print("-" * 70)
    for i, c in enumerate(chosen, 1):
        pre_s, _, _, post_e = windows_for(c["t1"])
        est = est_by_repo.get(c["full"])
        est_txt = f"  stima=~{est[3]:,} richieste" if est else ""
        print(f"{i}. {c['full']}")
        print(f"   T1={c['t1s']}  finestra=[{pre_s.date()} .. {post_e.date()}]  "
              f"prima commit clone={c['first_commit']}{est_txt}")
        print("   idoneo perche': T1 presente, git_metrics stato=ok (T+6 completa), "
              "T-6 completa (clone piu' antico della finestra)")
    if excluded:
        print(f"\nEsclusi ({len(excluded)}):")
        for full, why in excluded[:15]:
            print(f"   - {full or '(senza nome)'}: {why}")
        if len(excluded) > 15:
            print(f"   ... e altri {len(excluded) - 15}")
    if not_chosen:
        print(f"\nIdonei non scelti: {len(not_chosen)} "
              f"(es. {', '.join(f for f, _ in not_chosen[:3])})")
    print("=" * 70)

    if not chosen:
        print("Nessun repository idoneo: interrotto.")
        return 1

    tot_est = sum(est_by_repo[c["full"]][3] for c in chosen if c["full"] in est_by_repo)
    print(f"\nTOTALE stimato per i {len(chosen)} scelti: ~{tot_est:,} richieste "
          f"(limite orario: 5000 autenticati)")
    if tot_est > 5000:
        print("[AVVISO] la stima supera il limite orario: con la cache il run puo' "
              "completarsi in piu' finestre di 1h, oppure usa --n piu' basso.")

    if args.dry_run:
        print("\n[dry-run] nessun dato scaricato. Esegui senza --dry-run per il test completo.")
        print(f"Richieste effettuate (solo stima): {client.requests}, "
              f"cache hit: {client.cache_hits}, tempo {time.time() - t_start:.1f}s")
        return 0

    # ---- analisi ----
    rows, errors = [], []
    for i, c in enumerate(chosen, 1):
        print(f"\n[{i}/{len(chosen)}] {c['full']} ...", flush=True)
        try:
            row, err = analyze_repo(client, c, workers)
        except RateLimitExceeded as e:
            row = {"repository": c["full"], "t1": c["t1s"], "stato": f"interrotto: {e}"}
            err = str(e)
        rows.append(row)
        if err:
            errors.append(f"{c['full']}: {err}")
        # salvataggio incrementale: non si perde nulla in caso di interruzione
        write_csv(rows)
        print(f"    stato={row.get('stato')}  richieste_repo={row.get('richieste_api')}  "
              f"totale_finora={client.requests}  rate_rimasto={client.rate_remaining}")
        if str(row.get("stato", "")).startswith("interrotto"):
            restanti = [x["full"] for x in chosen[i:]]
            print(f"    [STOP] rate limit esaurito: saltati {len(restanti)} repository "
                  f"rimanenti ({', '.join(restanti[:3])}...)")
            break

    # ---- report finale ----
    print("\n" + "=" * 70)
    print("REPORT TEST")
    print("=" * 70)
    print(f"{'repository':40} {'richieste':>10} {'stato':>12}")
    for r in rows:
        print(f"{r.get('repository', ''):40} {str(r.get('richieste_api', '-')):>10} "
              f"{str(r.get('stato', ''))[:12]:>12}")
    print("-" * 70)
    print(f"Repository analizzati      : {len(rows)} / {len(chosen)}")
    print(f"Richieste API totali       : {client.requests}")
    print(f"  per repository           : "
          + ", ".join(f"{k}={v}" for k, v in sorted(client.by_repo.items())))
    print(f"Cache hit (non richieste)  : {client.cache_hits}")
    if client.rate_remaining is not None:
        reset = datetime.fromtimestamp(client.rate_reset, tz=timezone.utc) \
            if client.rate_reset else None
        print(f"Rate limit residuo         : {client.rate_remaining}"
              + (f" (reset {reset:%H:%M UTC})" if reset else ""))
    if errors:
        print("Errori / dati non disponibili:")
        for e in errors:
            print(f"   - {e}")
    if client.errors:
        print("Errori HTTP registrati:")
        for e in client.errors[:10]:
            print(f"   - {e}")
    print(f"Tempo totale               : {time.time() - t_start:.1f}s")
    print(f"\nCSV: {OUT_FILE}")
    print("NOTA: eseguito solo il test sui repository sopra elencati; "
          "l'intero dataset NON e' stato analizzato.")
    return 0


def write_csv(rows):
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


if __name__ == "__main__":
    sys.exit(main())
