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
    conclusivo (chiusura/merge/prima review) avviene entro la fine della finestra;
  - le review contano in base a submitted_at (una review inviata prima di T_1
    non viene attribuita a T+6).

Metriche (esattamente 14, per ogni finestra, colonne *_pre e *_post):
  PR    (5): pr_aperte, pr_merged, pr_pct_merge (merged / PR create e chiuse
             entro la fine della finestra), pr_tempo_medio_merge_giorni,
             pr_contributori;
  Issue (5): issue_aperte, issue_chiuse, issue_tempo_medio_chiusura_giorni,
             issue_contributori, issue_pct_chiusura (chiuse / create);
  Review(4): review_totale, review_reviewer_distinti, review_approvate,
             review_tempo_medio_prima_review_giorni.

Zero vs mancante:
  - 0  = metrica calcolata correttamente e nessun evento;
  - '' = non calcolabile (media senza elementi, percentuale con denominatore
         zero) oppure dati non recuperati in modo completo (stato 'parziale').

Strategia di recupero (REST, completezza storica privilegiata):
  - issue/PR create: GET /issues?state=all&sort=created&since=<T-6>,
    paginato fino a created_at < T-6 (l'ordinamento discendente su created
    garantisce di vedere tutti gli elementi creati nella finestra);
  - PR candidate (metriche PR + review): GET /pulls?state=open a esaurimento
    UNITO A GET /pulls?state=closed&sort=updated&direction=desc paginato fino
    a updated_at < inizio T-6. Una PR che poteva ricevere review durante le
    finestre doveva essere APERTA in quel periodo: se e' ancora aperta e'
    nella prima lista; se e' chiusa ora, la chiusura finale e' avvenuta dopo
    l'inizio della finestra e la chiusura e' essa stessa un aggiornamento
    (updated_at >= closed_at), quindi rientra nella seconda lista.
    NON si usa updated_at <= fine T+6: escluderebbe PR reviewate nella
    finestra e poi aggiornate successivamente;
  - le review si scaricano solo per le PR candidate (1 richiesta a PR,
    paginata). Non si usano GET /pulls/{number}: i dettagli
    additions/deletions non servono per le 14 metriche.
  - paginazione: sui repository grandi (es. apache/airflow) l'API REST
    risponde HTTP 422 'Pagination with the page parameter is not supported
    for large datasets, please use cursor based pagination (after/before)':
    paginate() parte con l'URL storico page=1 (compatibilita' cache), segue
    l'header Link (cursore `after` preferito a `next`) e, di fronte al 422,
    riparte da capo SENZA il parametro `page` seguendo i cursori, azzerando
    l'elenco accumulato (nessun duplicato, nessuna omissione). Se anche i
    cursori vengono rifiutati viene lanciato errore: l'elenco non recuperato
    non viene mai presentato come completo.

Limiti metodologici (documentati, non eliminabili con le API REST):
  - vale l'ipotesi di piattaforma "una PR puo' ricevere review solo se
    aperta": se non valdesse, esisterebbero PR chiuse prima di T-6 con
    review inviate nella finestra e non verrebbero recuperate;
  - non esiste un endpoint "review inviate in un intervallo": ogni PR
    candidate va interrogata singolarmente. Se il recupero delle review di
    una PR fallisce, le 4 metriche review della finestra in cui quella PR
    era aperta restano VUOTE e lo stato diventa 'parziale': non vengono mai
    presentate come complete. Le metriche PR/Issue restano valide se il loro
    recupero e' corretto;
  - l'ordinamento delle liste e' stabile su created/updated: un numero di
    pagine oltre MAX_PAGES genera errore (mai un elenco troncato presentato
    come completo).

Robustezza della connessione (GitHubClient.get):
  - interruzioni temporanee (RemoteDisconnected, ConnectionResetError,
    TimeoutError, URLError con motivo di rete): max 5 tentativi complessivi
    con backoff progressivo 2, 4, 8, 16, 30 s;
  - se tutti falliscono viene lanciato RuntimeError -> analyze_repo marca
    'parziale'/'errore': una richiesta fallita non e' mai una risposta vuota
    (recupero review fallito = 4 metriche review vuote, mai 0);
  - HTTP 403/429, 5xx e rate limit: gestione invariata;
  - gli URL gia' presenti in cache valida non vengono richiesti di nuovo.

Token: variabile d'ambiente GITHUB_TOKEN, GH_TOKEN o YOSHI_GH_TOKEN.
Mai scritto nel codice.

Uso:
  python github_analyzer.py --dry-run                  # solo stima richieste
  python github_analyzer.py --repo owner/name          # test su un repository
  python github_analyzer.py --repo owner/a,owner/b     # test su piu' repository
  python github_analyzer.py --n 3                      # primi 3 idonei
Output: results/github_metrics.csv
"""

import argparse
import csv
import hashlib
import http.client
import json
import os
import re
import ssl
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
MAX_PAGES = 5000             # oltre: la paginazione e' un errore, mai un troncamento

# Interruzioni temporanee della connessione (RemoteDisconnected durante una
# GET): massimo 5 tentativi complessivi con backoff progressivo di
# 2, 4, 8, 16 e 30 secondi. Gli errori HTTP (403/429/5xx) e il rate limit
# restano gestiti come prima (MAX_RETRIES).
MAX_TRANSIENT_ATTEMPTS = 5
TRANSIENT_BACKOFF = (2, 4, 8, 16, 30)   # secondi, un valore per tentativo

# esattamente 14 metriche, nell'ordine delle colonne del CSV
PR_METRICS = [
    "pr_aperte", "pr_merged", "pr_pct_merge",
    "pr_tempo_medio_merge_giorni", "pr_contributori",
]
ISSUE_METRICS = [
    "issue_aperte", "issue_chiuse", "issue_tempo_medio_chiusura_giorni",
    "issue_contributori", "issue_pct_chiusura",
]
REVIEW_METRICS = [
    "review_totale", "review_reviewer_distinti", "review_approvate",
    "review_tempo_medio_prima_review_giorni",
]
METRICS = PR_METRICS + ISSUE_METRICS + REVIEW_METRICS

FIELDS = (
    ["repository", "t1", "stato", "pre_start", "pre_end", "post_start", "post_end"]
    + [f"{m}_{s}" for m in METRICS for s in ("pre", "post")]
    + ["richieste_api", "cache_hit"]
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


class CursorPaginationRequired(Exception):
    """HTTP 422 'Pagination with the page parameter is not supported for large
    datasets, please use cursor based pagination (after/before)'.

    Sollevata dal client quando l'API rifiuta la paginazione con `page`:
    il chiamante (paginate) riparte con la paginazione a cursori. Non e' un
    errore definitivo di recupero: e' un invito a cambiare modalita'."""


def parse_link_header(header):
    """Header Link RFC 5988 -> {rel: url}. Esempio di risposta GitHub:
    '<...&after=abc>; rel="after", <...&page=3>; rel="next"'."""
    out = {}
    if not header:
        return out
    for part in str(header).split(","):
        m = re.search(r'<([^>]+)>\s*;\s*rel="([^"]+)"', part)
        if m:
            out[m.group(2)] = m.group(1)
    return out


# Interruzioni temporanee della connessione: si riprova con backoff.
# (http.client.RemoteDisconnected e' una sottoclasse di ConnectionResetError,
#  ma viene nominato esplicitamente per chiarezza.)
TRANSIENT_NET_ERRORS = (
    http.client.RemoteDisconnected,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
    BrokenPipeError,
    TimeoutError,             # include socket.timeout (alias in Python 3.10+)
)

# cattura completa delle eccezioni di rete/gestite dal client
NETWORK_CATCH = (urllib.error.URLError,) + TRANSIENT_NET_ERRORS


def is_transient_network_error(exc):
    """True se `exc` e' un'interruzione TEMPORANEA della connessione.

    Distingue i veri errori transitori da URLError con motivo non di rete
    (es. errori TLS/certificati o motivi arbitrari): questi ultimi non
    vengono riprovati, perch'equale ripetere la stessa richiesta."""
    if isinstance(exc, TRANSIENT_NET_ERRORS):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TRANSIENT_NET_ERRORS):
            return True
        if isinstance(reason, ssl.SSLError):
            return False        # certificati/TLS: non transitorio
        if isinstance(reason, OSError):
            return True         # DNS, refused, reset, timeout generici
        return False            # motivo non di rete: non transitorio
    return False


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
        self.cache_by_repo = {}      # repo -> cache hit
        self.by_kind = {}            # tipologia dato -> richieste reali
        self.cache_by_kind = {}      # tipologia dato -> cache hit
        self.current_repo = "-"
        self.rate_remaining = None
        self.rate_reset = None
        self.errors = []
        self.abort = None          # motivo di interruzione per rate limit
        self._last_search = 0.0

    # --- contatori ---
    def _count(self, kind="altro"):
        with self.lock:
            self.requests += 1
            self.by_repo[self.current_repo] = self.by_repo.get(self.current_repo, 0) + 1
            self.by_kind[kind] = self.by_kind.get(kind, 0) + 1

    def _cache_path(self, url):
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return CACHE_DIR / (h + ".json")

    def _cache_read(self, url):
        """Entry di cache {url, ts, body, link?} oppure None.

        `link` (header Link della risposta) e' presente solo nelle entry
        scritte dalla versione corrente: le entry vecchie lo hanno assente
        e paginate provvede a rifare la richiesta quando serve il header."""
        if not self.cache_enabled:
            return None
        p = self._cache_path(url)
        if not p.exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                entry = json.load(f)
            if isinstance(entry, dict) and "body" in entry:
                return entry
            return None
        except Exception:
            return None

    def _cache_write(self, url, body, link=None):
        if not self.cache_enabled:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path(url).with_suffix(".tmp")
            entry = {"url": url, "ts": datetime.now(timezone.utc).isoformat(),
                     "body": body}
            if link:
                entry["link"] = link
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(entry, f)
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

    def get(self, url, repo=None, is_search=False, kind="altro",
            want_link=False, force=False):
        """GET JSON. Ritorna il body; con want_link=True ritorna (body, header Link).

        - force=True: salta la lettura da cache (serve a paginate per ottenere
          l'header Link di una pagina cachata senza header);
        - se l'URL e' gia' presente in cache con dati validi, la richiesta di
          rete non viene ripetuta (nessun retry, nessun contatore richieste);
        - HTTP 422 'cursor based pagination' -> CursorPaginationRequired
          (vedi paginate: riparte senza il parametro `page`);
        - interruzioni temporanee della connessione (RemoteDisconnected,
          ConnectionResetError, TimeoutError, URLError con motivo di rete):
          fino a MAX_TRANSIENT_ATTEMPTS=5 tentativi complessivi con backoff
          progressivo TRANSIENT_BACKOFF (2, 4, 8, 16, 30 s). Se tutti
          falliscono viene lanciato RuntimeError, gestito da analyze_repo
          (stato 'parziale'/'errore'): la richiesta fallita NON viene mai
          interpretata come risposta vuota;
        - HTTP 403/429, 5xx e rate limit: gestione invariata.

        Lancia RateLimitExceeded se non si puo' procedere."""
        if not force:
            entry = self._cache_read(url)
            if entry is not None:
                with self.lock:
                    self.cache_hits += 1
                    self.cache_by_kind[kind] = self.cache_by_kind.get(kind, 0) + 1
                    self.cache_by_repo[self.current_repo] = \
                        self.cache_by_repo.get(self.current_repo, 0) + 1
                body = entry.get("body")
                return (body, entry.get("link")) if want_link else body

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
        http_attempt = 0      # tentativi per gli errori HTTP (403/429/5xx)
        transient_tries = 0   # interruzioni temporanee della connessione
        while http_attempt < MAX_RETRIES:
            self._count(kind)
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self._update_rate(resp.headers)
                    link = resp.headers.get("Link") or resp.headers.get("link")
                    body = json.loads(resp.read().decode("utf-8", "replace"))
                self._cache_write(url, body, link)
                return (body, link) if want_link else body
            except urllib.error.HTTPError as e:
                # --- gestione HTTP invariata (403 rate limit, 403/429,
                #     5xx, 4xx definitivi) ---
                self._update_rate(e.headers)
                msg = ""
                try:
                    msg = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
                except Exception:
                    pass
                if e.code == 422 and "cursor based pagination" in msg.lower():
                    # dataset troppo grande per `page`: paginate riparte con i cursori
                    raise CursorPaginationRequired(msg or "cursor based pagination")
                if e.code == 403 and "rate limit" in msg.lower():
                    # rate limit primario esaurito: attendi il reset
                    reset = int(e.headers.get("X-RateLimit-Reset") or time.time())
                    wait = reset - int(time.time()) + 5
                    if wait > MAX_WAIT_RESET:
                        raise RateLimitExceeded(f"rate limit esaurito, reset tra {wait}s")
                    print(f"  [RATE] 403 rate limit, attendo {wait}s...")
                    time.sleep(wait)
                    http_attempt += 1
                    continue
                if e.code in (403, 429):
                    # secondary rate limit / throttling: Retry-After o backoff
                    ra = e.headers.get("Retry-After")
                    wait = int(ra) if ra and ra.isdigit() else min(60 * (http_attempt + 1), 180)
                    print(f"  [THROTTLE] HTTP {e.code}: {msg[:80]} -> attendo {wait}s")
                    time.sleep(wait)
                    http_attempt += 1
                    continue
                if e.code >= 500:
                    time.sleep(2 ** http_attempt)
                    last_err = f"HTTP {e.code}: {msg[:120]}"
                    http_attempt += 1
                    continue
                # errore 4xx definitivo (404, 422, ...)
                self.errors.append(f"{self.current_repo}: HTTP {e.code} {msg[:100]}")
                raise RuntimeError(f"HTTP {e.code}: {msg[:120]}")
            except NETWORK_CATCH as e:
                # --- interruzioni temporanee della connessione ---
                if not is_transient_network_error(e):
                    # URLError con motivo non di rete (es. TLS/certificati):
                    # ripetere la stessa richiesta non serve
                    self.errors.append(f"{self.current_repo}: {e}")
                    raise RuntimeError(
                        f"richiesta fallita (errore non transitorio): {e}") from e
                transient_tries += 1
                last_err = f"{type(e).__name__}: {e}"[:120]
                # backoff progressivo: 2, 4, 8, 16, 30 secondi
                time.sleep(TRANSIENT_BACKOFF[
                    min(transient_tries, len(TRANSIENT_BACKOFF)) - 1])
                if transient_tries >= MAX_TRANSIENT_ATTEMPTS:
                    # tutti i tentativi esauriti: errore gestibile da
                    # analyze_repo (stato parziale/errore, mai 'ok')
                    self.errors.append(f"{self.current_repo}: {last_err}")
                    raise RuntimeError(
                        f"connessione interrotta dopo {MAX_TRANSIENT_ATTEMPTS} "
                        f"tentativi: {last_err}") from e
                continue
        self.errors.append(f"{self.current_repo}: {last_err}")
        raise RuntimeError(f"richiesta fallita dopo {MAX_RETRIES} tentativi: {last_err}")

    def search_count(self, query):
        """total_count di una search (1 richiesta)."""
        q = urllib.parse.quote(query)
        url = f"{API}/search/issues?q={q}&per_page=1"
        body = self.get(url, is_search=True, kind="search (stima)")
        return int(body.get("total_count", 0))


# ---------------------------------------------------------------------- fetch

def paginate(client, url_base, params, cutoff_iso, repo, kind="lista PR+Issue",
             field="created_at"):
    """Pagina un endpoint in ordine DECRESCENTE su `field` fino al cutoff.

    Strategia di paginazione (gestisce l'errore HTTP 422 dei repository
    grandi: 'Pagination with the page parameter is not supported for large
    datasets, please use cursor based pagination (after/before)'):

    1. si parte con l'URL storico `page=1` (stessa identica stringa delle
       precedenti esecuzioni => la cache su disco continua a valere);
    2. la richiesta successiva segue l'header Link: ha la precedenza il
       cursore `after` (paginazione cursor, nessun parametro `page`), poi
       `next` (paginazione classica `page`, per gli endpoint/casi che la
       supportano ancora);
    3. se l'API risponde 422 'cursor based pagination' (dataset grande),
       l'intera paginazione RIPARTE da capo SENZA il parametro `page`,
       seguendo i cursori `after`: l'elenco accumulato viene azzerato, quindi
       non possono nascere duplicati ne' omissioni;
    4. se il rifiuto dei cursori persiste, o si supera MAX_PAGES, o la
       risposta non e' una lista, si lancia l'errore: un elenco parziale non
       viene mai restituito come completo (il chiamante marca 'parziale').

    Cache: l'header Link di ogni pagina viene salvato in cache; per le entry
    vecchie (senza header) che contengono una pagina piena, la richiesta viene
    rifatta una volta in rete per recuperare l'header e poter proseguire.

    Deduplica per `id` su tutte le pagine (e dopo ogni ripartenza).
    - cutoff_iso: alla prima occorrenza con field < cutoff la paginazione si
      ferma (ordinamento discendente: tutto cio' che serve e' gia' stato visto);
    - cutoff_iso=None: paginazione a esaurimento.
    """
    base_qs = urllib.parse.urlencode(dict(params, per_page=PER_PAGE))
    cutoff = parse_ts(cutoff_iso)
    cursor_mode = False

    while True:                      # loop di ripartenza (solo su 422 cursor)
        items, seen = [], set()      # azzera: mai duplicati dopo un restart
        url = (f"{API}{url_base}?{base_qs}" if cursor_mode
               else f"{API}{url_base}?{base_qs}&page=1")
        n_pages = 0
        try:
            while True:
                n_pages += 1
                if n_pages > MAX_PAGES:
                    raise RuntimeError(
                        f"paginazione oltre {MAX_PAGES} pagine su {url_base}: "
                        "elenco non completo")
                body, link = client.get(url, repo=repo, kind=kind, want_link=True)
                if not isinstance(body, list):
                    raise RuntimeError(
                        f"risposta inattesa da {url_base}: {type(body).__name__}")
                # entry di cache senza header Link ma pagina piena: serve il
                # header per sapere se ci sono altre pagine -> rifai in rete
                if link is None and len(body) >= PER_PAGE:
                    body, link = client.get(url, repo=repo, kind=kind,
                                            want_link=True, force=True)
                    if not isinstance(body, list):
                        raise RuntimeError(
                            f"risposta inattesa da {url_base}: {type(body).__name__}")

                stop = False
                for it in body:
                    if cutoff is not None:
                        ts = parse_ts(it.get(field))
                        if ts is not None and ts < cutoff:
                            stop = True      # ordinamento discendente: il resto
                            break            # e' piu' vecchio del cutoff
                    key = it.get("id")
                    if key is None:
                        key = (it.get("url"), it.get("number"))
                    if key in seen:
                        continue             # nessun duplicato tra pagine
                    seen.add(key)
                    items.append(it)

                if stop or len(body) < PER_PAGE:
                    return items
                links = parse_link_header(link)
                nxt = links.get("after") or links.get("next")
                if nxt is None:
                    # nessun Link successivo: ultima pagina (GitHub omite
                    # l'header quando non ci sono altri risultati)
                    return items
                url = nxt
        except CursorPaginationRequired:
            if cursor_mode:
                # anche senza `page` l'API rifiuta: elenco non recuperabile
                raise RuntimeError(
                    f"paginazione cursor rifiutata da {url_base}: "
                    "elenco non recuperato")
            cursor_mode = True
            continue               # riparte da capo senza `page`, senza duplicati


def fetch_issues_listing(client, repo, since_iso):
    """Issue + PR create da `since` (GET /issues, sort=created, since=updated).

    `since` filtra su updated_at ed e' innocuo ai nostri fini: ogni elemento
    creato dopo `since` ha updated_at >= created_at >= since, quindi resta
    inclusa; la paginazione si ferma a created_at < since, dove gli elementi
    utili (creati nelle finestre) sono esauriti. Gli URL sono identici a
    quelli della precedente esecuzione => compatibilita' della cache.
    Su repository grandi l'endpoint rifiuta il parametro `page` (HTTP 422):
    paginate() ripiega automaticamente sulla paginazione a cursori `after`
    (vedi la docstring di paginate). Un errore di recupero resta un errore:
    qui non viene mai restituito un elenco parziale.
    Dato l'elenco, le metriche PR/Issue si filtrano su created_at."""
    return paginate(
        client, f"/repos/{repo}/issues",
        {"state": "all", "sort": "created", "direction": "desc",
         "since": f"{since_iso}T00:00:00Z"},
        f"{since_iso}T00:00:00Z", repo, kind="lista issue+PR",
        field="created_at",
    )


def fetch_pulls_open(client, repo):
    """Tutte le PR ancora aperte (a esaurimento)."""
    return paginate(client, f"/repos/{repo}/pulls", {"state": "open"},
                    None, repo, kind="lista PR aperte", field="created_at")


def fetch_pulls_closed_recent(client, repo, since_iso):
    """PR chiuse con updated_at >= inizio T-6 (sort=updated desc, cutoff su
    updated_at).

    Copre le PR che erano aperte durante le finestre e poi chiuse: la loro
    chiusura finale e' >= inizio finestra e la chiusura e' essa stessa un
    aggiornamento, quindi updated_at >= closed_at >= inizio finestra.
    NON si filtra su updated_at <= fine finestra: una PR reviewata in
    finestra e poi riaggiornata deve restare inclusa."""
    return paginate(
        client, f"/repos/{repo}/pulls",
        {"state": "closed", "sort": "updated", "direction": "desc"},
        f"{since_iso}T00:00:00Z", repo, kind="lista PR chiuse",
        field="updated_at",
    )


def fetch_pull_candidates(client, repo, since_iso):
    """Insieme completo delle PR che potevano ricevere review nelle finestre:
    (aperte ora) UNIONE (chiuse con aggiornamento recente), dedotte per
    number. E' anche il superset delle PR create nelle finestre (una PR creata
    dopo T-6 ha updated_at >= created_at >= T-6 e rientra in una delle due
    liste)."""
    by_num = {}
    for p in fetch_pulls_open(client, repo):
        if p.get("number") is not None:
            by_num[p["number"]] = p
    for p in fetch_pulls_closed_recent(client, repo, since_iso):
        by_num.setdefault(p.get("number"), p)
    return list(by_num.values())


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


def fetch_reviews(client, repo, number):
    """Tutte le review di una PR (paginazione se > 100).

    Solleva RuntimeError se la risposta non e' una lista o se la paginazione
    supera MAX_PAGES: un elenco parziale non deve mai essere trattato come
    completo (il chiamante lascia vuote le metriche review della finestra)."""
    out, page = [], 1
    while True:
        body = client.get(
            f"{API}/repos/{repo}/pulls/{number}/reviews?per_page={PER_PAGE}&page={page}",
            repo=repo, kind="review",
        )
        if not isinstance(body, list):
            raise RuntimeError(f"risposta inattesa dalle review della PR #{number}")
        out.extend(body)
        if len(body) < PER_PAGE:
            return out
        page += 1
        if page > MAX_PAGES:
            raise RuntimeError(f"review della PR #{number}: paginazione oltre "
                               f"{MAX_PAGES} pagine (elenco non completo)")


# ------------------------------------------------------------------ metriche

def _distinct_authors(items):
    """Conteggio autori/reviewer distinti: chiave = user.id, in alternativa
    user.login (coerente su tutte le metriche). Utenti senza identificativo
    non sono conteggiati (dato non attribuibile, non inventato)."""
    keys = set()
    for it in items:
        u = it.get("user") or {}
        k = u.get("id") if u.get("id") is not None else u.get("login")
        if k is not None:
            keys.add(k)
    return len(keys)


def pr_metrics(prs_created, start, end):
    """prs_created: PR CREATE nella finestra (filtrate dal chiamante su
    created_at; start incluso, end escluso).

    0 = conteggio corretto senza eventi; None = non calcolabile."""
    n = len(prs_created)
    # chiuse/merged entro la fine della finestra (created >= start, quindi
    # closed_at/merged_at in [start, end) equivale a < end)
    closed = [p for p in prs_created
              if in_window(parse_ts(p.get("closed_at")), start, end)]
    merged = [p for p in prs_created
              if in_window(parse_ts(p.get("merged_at")), start, end)]

    # tempo medio: solo PR effettivamente merged entro la fine della finestra
    merge_days = []
    for p in merged:
        c, m = parse_ts(p.get("created_at")), parse_ts(p.get("merged_at"))
        if c and m:
            merge_days.append((m - c).total_seconds() / 86400)

    return {
        "pr_aperte": n,
        "pr_merged": len(merged),
        # denominatore: PR create nella finestra e chiuse entro la fine della
        # finestra (merged e' sottoinsieme di chiuse: merged_at implica closed_at)
        "pr_pct_merge": (round(100.0 * len(merged) / len(closed), 2)
                         if closed else None),
        "pr_tempo_medio_merge_giorni": mean(merge_days),
        "pr_contributori": _distinct_authors(prs_created),
    }


def issue_metrics(issues_created, start, end):
    """issues_created: issue CREATE nella finestra (PR gia' escluse)."""
    n = len(issues_created)
    closed = [i for i in issues_created
              if in_window(parse_ts(i.get("closed_at")), start, end)]
    # tempo medio: solo issue effettivamente chiuse entro la fine della finestra
    close_days = []
    for i in closed:
        c, z = parse_ts(i.get("created_at")), parse_ts(i.get("closed_at"))
        if c and z:
            close_days.append((z - c).total_seconds() / 86400)

    return {
        "issue_aperte": n,
        "issue_chiuse": len(closed),
        "issue_tempo_medio_chiusura_giorni": mean(close_days),
        "issue_contributori": _distinct_authors(issues_created),
        # denominatore: TUTTE le issue create nella finestra
        "issue_pct_chiusura": (round(100.0 * len(closed) / n, 2)
                               if n else None),
    }


def review_metrics(reviews_by_pr, prs_created, start, end):
    """reviews_by_pr: {pr_number: [review...]} per le PR candidate, con
    recupero COMPLETO (il chiamante non chiama questa funzione se qualcosa e'
    mancato); prs_created: PR create nella finestra (per la prima review).

    Le review contano per submitted_at nella finestra, indipendentemente
    dalla data della PR di appartenenza (una PR aperta prima di T-6 puo'
    ricevere review in T-6/T+6)."""
    in_win = []
    for revs in reviews_by_pr.values():
        for r in revs:
            if in_window(parse_ts(r.get("submitted_at")), start, end):
                in_win.append(r)

    reviewers = set()
    for r in in_win:
        u = r.get("user") or {}
        k = u.get("id") if u.get("id") is not None else u.get("login")
        if k is not None:
            reviewers.add(k)

    # prima review: solo PR create nella finestra, prima review successiva alla
    # creazione e precedente alla fine della finestra
    first_days = []
    for p in prs_created:
        c = parse_ts(p.get("created_at"))
        num = p.get("number")
        if not c or num is None:
            continue
        revs = sorted(
            t for t in (parse_ts(r.get("submitted_at"))
                        for r in reviews_by_pr.get(num, []))
            if t is not None and c < t < end
        )
        if revs:
            first_days.append((revs[0] - c).total_seconds() / 86400)

    return {
        "review_totale": len(in_win),
        "review_reviewer_distinti": len(reviewers),
        # solo review inviate nella finestra
        "review_approvate": sum(1 for r in in_win
                                if r.get("state") == "APPROVED"),
        "review_tempo_medio_prima_review_giorni": mean(first_days),
    }


# ----------------------------------------------------------------- selezione

def load_events():
    """Chiave = owner/repository completo in minuscolo (evita collisioni tra
    repository omonimi di owner diversi)."""
    events = {}
    with open(EVENTS_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            full = (row.get("repository") or "").strip()
            events[full.lower()] = row
    return events


def load_git_metrics():
    """Righe di git_metrics.csv indicizzate per owner/repository completo."""
    rows = {}
    if not GIT_METRICS_FILE.exists():
        return rows
    with open(GIT_METRICS_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            full = (row.get("repository") or "").strip()
            rows[full.lower()] = row
    return rows


def normalize_repo_url(url):
    """Qualsiasi forma di URL git -> 'owner/repository' minuscolo, o None."""
    u = (url or "").strip()
    # https://github.com/owner/repo(.git) | git@github.com:owner/repo(.git)
    # ssh://git@github.com/owner/repo(.git) | git://github.com/owner/repo.git
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", u)
    if not m:
        return None
    cand = m.group(1).strip().lower()
    return cand if cand.count("/") == 1 else None


def clone_remote_repo(folder):
    """owner/repository (minuscolo) del remote origin del clone, o None."""
    try:
        p = subprocess.run(
            ["git", "-C", str(folder), "remote", "get-url", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if p.returncode != 0 or not p.stdout.strip():
        return None
    return normalize_repo_url(p.stdout.strip())


def verify_clones(chosen):
    """La cartella del clone si chiama come il repo finale, ma owner diversi
    possono avere nomi omonimi: si confronta il remote origin per essere sicuri
    che il clone sia davvero il repository richiesto.

    Ritorna (tenuti, esclusioni); se il remote non e' leggibile si accetta
    con un avviso stampato (identita' non verificabile)."""
    kept, extra = [], []
    for c in chosen:
        full = (c["full"] or "").strip()
        if "/" not in full:
            # riga senza owner nel CSV: non confrontabile, si accetta com'e'
            print(f"  [AVVISO] {full or '(senza nome)'}: riga senza owner/"
                  "repository, clone non verificabile")
            kept.append(c)
            continue
        remote = clone_remote_repo(c["folder"])
        if remote is None:
            print(f"  [AVVISO] {full}: remote del clone '{c['folder'].name}' "
                  "non leggibile: identita' non verificata")
            kept.append(c)
        elif remote != full.lower():
            extra.append((full,
                          f"clone '{c['folder'].name}' appartiene a {remote} "
                          "(omonimia risolta tramite remote origin)"))
        else:
            kept.append(c)
    return kept, extra


def select_repos(events, gm_rows, n_target, today, explicit=None):
    """Selezione dei repository idonei.

    Criteri (tutti richiesti):
      1. T1 identificato in adoption_events.csv;
      2. presente in git_metrics.csv con stato 'ok' (=> finestra T+6 completa
         e controlli gia' eseguiti, non ripetuti), associato per owner/name;
      3. finestra T-6 completa: il clone esiste e la sua prima commit e'
         anteriore o uguale a T1 - 6 mesi;
      4. T1 non futuro;
      5. il clone locale corrisponde al repository (remote origin), per
         risolvere le omonimie tra owner diversi.
    L'ordine di scelta, senza --repo, e' quello di adoption_events.csv.
    Ritorna (scelti, esclusi, idonei_non_scelti) con motivazioni.
    """
    folders = {p.name.lower(): p for p in REPOS_DIR.iterdir() if p.is_dir()} \
        if REPOS_DIR.is_dir() else {}

    candidates, excluded = [], []
    for key, ev in events.items():          # key = owner/repository completo
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
        # cartella del clone = nome finale del repo (l'identita' si verifica
        # poi con il remote origin, vedi verify_clones)
        folder_name = key.split("/")[-1].strip()
        folder = folders.get(folder_name.lower())
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
        kept, extra = verify_clones(chosen)
        excluded.extend(extra)
        return kept, excluded, []

    # scelta deterministica: i primi n nell'ordine di adoption_events.csv
    chosen = candidates[:n_target]
    not_chosen = [(c["full"], "idoneo ma non selezionato (oltre i %d)" % n_target)
                  for c in candidates[n_target:]]
    kept, extra = verify_clones(chosen)
    excluded.extend(extra)
    return kept, excluded, not_chosen


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


def windows_open_for(pr, pre_start, pre_end, post_start, post_end):
    """Finestre durante le quali la PR era aperta (=> poteva ricevere review).

    created < fine finestra e (mai chiusa oppure chiusa >= inizio finestra):
    closed_at e' l'ultima chiusura, quindi se e' < inizio finestra la PR era
    gia' chiusa quando la finestra e' cominciata (non ha potuto riceverci
    review); se e' nulla o >= inizio, in qualche istante della finestra era
    aperta."""
    created = parse_ts(pr.get("created_at"))
    if created is None:
        return []
    closed = parse_ts(pr.get("closed_at")) if pr.get("closed_at") else None
    out = []
    if created < pre_end and (closed is None or closed >= pre_start):
        out.append("pre")
    if created < post_end and (closed is None or closed >= post_start):
        out.append("post")
    return out


def analyze_repo(client, cand, workers):
    """Analizza un repository su entrambe le finestre (14 metriche x 2).
    Ritorna (riga_csv, errore_o_nota_o_None)."""
    repo, t1 = cand["full"], cand["t1"]
    pre_start, pre_end, post_start, post_end = windows_for(t1)
    client.current_repo = repo
    client.abort = None
    req_before = client.by_repo.get(repo, 0)
    cache_before = client.cache_by_repo.get(repo, 0)

    row = {
        "repository": repo, "t1": cand["t1s"], "stato": "ok",
        "pre_start": pre_start.date().isoformat(),
        "pre_end": pre_end.date().isoformat(),
        "post_start": post_start.date().isoformat(),
        "post_end": post_end.date().isoformat(),
    }
    notes = []    # dati mancanti/incompleti -> stato 'parziale'
    errors = []   # elenchi non recuperati -> 'parziale' (o 'errore' se tutti)
    issues = None # issue create da T-6 in poi (da /issues); None = mancante
    pulls = None  # PR candidate (aperte ∪ chiuse recenti); None = mancante
    since_iso = pre_start.date().isoformat()

    def finish(stato=None):
        """Chiude la riga: conteggi e stato. 'ok' SOLO se tutto e' completo."""
        row["richieste_api"] = client.by_repo.get(repo, 0) - req_before
        row["cache_hit"] = client.cache_by_repo.get(repo, 0) - cache_before
        prob = "; ".join(notes + errors)
        if stato:
            row["stato"] = stato
        elif issues is None and pulls is None:
            row["stato"] = "errore: " + (prob or "nessun dato recuperato")
        elif prob:
            row["stato"] = "parziale: " + prob
        else:
            row["stato"] = "ok"
        err = client.abort or prob
        if not err and stato:
            err = stato
        return row, err

    # ---- 1) issue create da T-6 in poi (le PR si recuperano da /pulls) ----
    try:
        listing = fetch_issues_listing(client, repo, since_iso)
        issues = split_listing(listing)[1]      # [1] = elementi senza 'pull_request'
    except RateLimitExceeded as e:
        return finish(f"interrotto: {e}")
    except (RuntimeError, OSError) as e:
        # OSError: interruzione di connessione non convertita dal client ->
        # mai trattata come assenza di issue (colonne vuote + stato parziale)
        errors.append(f"elenco issue non recuperato: {e}")
    if client.abort:
        return finish(f"interrotto: {client.abort}")

    # ---- 2) PR candidate: aperte ora ∪ chiuse con aggiornamento recente ----
    # (superset sia delle PR create nelle finestre sia di quelle che hanno
    #  potuto ricevere review durante T-6/T+6; vedi docstring e fetch_pull_candidates)
    try:
        pulls = fetch_pull_candidates(client, repo, since_iso)
    except RateLimitExceeded as e:
        return finish(f"interrotto: {e}")
    except (RuntimeError, OSError) as e:
        # idem: un errore di rete non e' un elenco PR vuoto
        errors.append(f"elenco PR non recuperato: {e}")
    if client.abort:
        return finish(f"interrotto: {client.abort}")

    # PR aperte almeno un istante in [T-6, T+6)
    active = active_for_reviews(pulls, pre_start, post_end) \
        if pulls is not None else None

    # ---- 3) review: 1 richiesta a PR candidate, in parallelo ----
    reviews_by_pr = {}
    failed_reviews = []
    if active is not None:
        rev_nums = sorted({p["number"] for p in active
                           if p.get("number") is not None})

        def _reviews(num):
            try:
                return num, fetch_reviews(client, repo, num)
            except RateLimitExceeded as e:
                with client.lock:
                    client.abort = client.abort or str(e)
                return num, None
            except (RuntimeError, OSError):
                # recupero fallito (dopo i retry del client): la PR finisce in
                # failed_reviews -> 4 metriche review vuote + stato parziale,
                # MAI una lista di review vuota considerata valida
                return num, None

        if rev_nums:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for num, revs in ex.map(_reviews, rev_nums):
                    if revs is None:
                        failed_reviews.append(num)
                    else:
                        reviews_by_pr[num] = revs
        if client.abort:
            return finish(f"interrotto: {client.abort}")
        if failed_reviews:
            # una PR il cui recupero e' fallito rende incompleta ogni finestra
            # in cui quella PR era aperta: le 4 metriche review di quella
            # finestra restano VUOTE (mai presentate come complete)
            notes.append(f"review non recuperate per {len(failed_reviews)} PR "
                         f"candidate (su {len(rev_nums)}): metriche review "
                         "delle finestre interessate lasciate vuote")

    # completezza review per finestra
    review_ok = {"pre": True, "post": True}
    if active is None:
        review_ok = {"pre": False, "post": False}
    elif failed_reviews:
        failed_set = set(failed_reviews)
        for p in active:
            if p.get("number") in failed_set:
                for w in windows_open_for(p, pre_start, pre_end,
                                          post_start, post_end):
                    review_ok[w] = False

    # ---- 4) metriche per finestra ----
    for suffix, s, e in (("pre", pre_start, pre_end),
                         ("post", post_start, post_end)):
        prs_w = ([p for p in active
                  if in_window(parse_ts(p.get("created_at")), s, e)]
                 if active is not None else None)
        issues_w = ([i for i in issues
                     if in_window(parse_ts(i.get("created_at")), s, e)]
                    if issues is not None else None)

        groups = [
            pr_metrics(prs_w, s, e) if prs_w is not None else None,
            issue_metrics(issues_w, s, e) if issues_w is not None else None,
            review_metrics(reviews_by_pr, prs_w, s, e)
            if (review_ok[suffix] and prs_w is not None) else None,
        ]
        for g in groups:
            if g is None:
                continue        # colonne lasciate vuote = dato mancante
            for k, v in g.items():
                row[f"{k}_{suffix}"] = fmt(v)

    return finish()


def estimate_requests(client, cand):
    """Stima le richieste per un repo con la strategia definita nella docstring.

    - 2 search: PR e issue create nel range (stime per la selezione/report);
    - pagine dell'elenco /issues (issue create da T-6 in poi);
    - pagine di /pulls?state=open (a esaurimento) + /pulls?state=closed
      (fino a updated_at < T-6): i PR candidate per le review;
    - 1 richiesta di review per PR aperta almeno un istante in T-6/T+6.
    Nessuna richiesta di dettaglio /pulls/{n}: non serve per le 14 metriche."""
    repo = cand["full"]
    since = add_months(cand["t1"], -WINDOW_MONTHS).isoformat()
    until = add_months(cand["t1"], WINDOW_MONTHS).isoformat()
    q_pr = f"repo:{repo} type:pr created:{since}..{until}"
    q_is = f"repo:{repo} type:issue created:{since}..{until}"
    # PR candidate per le review: aperte ora (tutte le PR mai aperte) UNIONE
    # chiuse con updated_at >= T-6 -> approx con updated:>=T-6 (sovrastima
    # moderata, va bene per una stima)
    q_act = f"repo:{repo} type:pr updated:>={since}"
    n_pr = client.search_count(q_pr)
    n_is = client.search_count(q_is)
    n_act = client.search_count(q_act)
    # pagine elenco issue + pagine liste PR (open a esaurimento + closed
    # recenti, sovrapposte in parte) + 1 reviews per PR attiva
    pages_issues = -(-(n_pr + n_is) // PER_PAGE)
    pages_pulls = -(-n_pr // PER_PAGE) + -(-(n_act) // PER_PAGE)
    est = pages_issues + pages_pulls + n_act
    return n_pr, n_is, est, n_act


# --------------------------------------------------------------------- main

# --------------------------------------------------------------- batch --
def read_existing_rows():
    """Legge results/github_metrics.csv esistente (se presente).

    Ritorna (rows, ok_repos): tutte le righe gia' raccolte e l'insieme dei
    repository DISTINTI (owner/repo) con stato esattamente 'ok'. Le righe
    parziali/in errore possono essere ritentate; quelle 'ok' non vengono
    mai rianalizzate e contano nel target."""
    if not OUT_FILE.exists():
        return [], set()
    rows, index = [], {}
    try:
        with open(OUT_FILE, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = (r.get("repository") or "").strip()
                if not key:
                    continue
                if key in index:
                    # difetto preesistente: UNA sola riga per repository,
                    # preferendo lo stato 'ok' (nessun risultato valido perso)
                    i = index[key]
                    if (str(r.get("stato", "")).strip() == "ok"
                            and str(rows[i].get("stato", "")).strip() != "ok"):
                        rows[i] = r
                    continue
                index[key] = len(rows)
                rows.append(r)
    except (OSError, csv.Error) as e:
        print(f"[AVVISO] impossibile leggere {OUT_FILE}: {e} -> parto da zero",
              flush=True)
        return [], set()
    ok = {r["repository"].strip() for r in rows
          if str(r.get("stato", "")).strip() == "ok"}
    return rows, ok


def upsert_row(rows, new_row):
    """Inserisce o aggiorna la riga di new_row['repository'] in `rows`.

    - una riga esistente con stato 'ok' NON viene mai sovrascritta da un
      risultato parziale/in errore e non vengono create righe duplicate;
    - ogni altra combinazione aggiorna la riga esistente in place (retry).
    Ritorna True se new_row e' stata effettivamente scritta."""
    repo = (new_row.get("repository") or "").strip()
    new_ok = str(new_row.get("stato", "")).strip() == "ok"
    idxs = [i for i, r in enumerate(rows)
            if (r.get("repository") or "").strip() == repo]
    if not idxs:
        rows.append(new_row)             # nessuna riga esistente: nessun rischio
        return True                      # di duplicato (chiave assente)
    # collasso di eventuali duplicati preesistenti (si tiene la prima riga)
    for j in reversed(idxs[1:]):
        del rows[j]
    if str(rows[idxs[0]].get("stato", "")).strip() == "ok" and not new_ok:
        return False                     # mai un 'ok' sovrascritto da peggio
    rows[idxs[0]] = new_row              # retry/aggiornamento in place
    return True


def run_batch(client, events, gm_rows, args, workers, t_start, today, explicit):
    """Modalita' batch sequenziale (--batch): UN repository alla volta, senza
    alcuna analisi concorrente tra repository, fino a raggiungere
    --target-success repository distinti con stato 'ok' nel CSV.

    - legge results/github_metrics.csv all'avvio: i repository gia' 'ok'
      (es. i 10 gia' presenti) contano nel target solo se ANCORA idonei
      secondo select_repos() e non vengono rianalizzati;
    - i repository parziali/in errore vengono ritentati e la loro riga
      aggiornata in place (mai duplicata, mai un 'ok' sovrascritto);
    - un errore di rete imprevisto su un repository viene registrato come
      'errore' e il batch prosegue con il successivo; solo il rate limit
      esaurito (RateLimitExceeded / stato 'interrotto') arresta il batch;
    - criteri di selezione, metriche, finestre e struttura CSV invariati;
    - salvataggio incrementale del CSV dopo ogni repository (scrittura
      atomica: nessuna perdita in caso di interruzione);
    - log leggibili con flush=True prima e dopo ogni analisi.
    Ritorna 0 se il target e' raggiunto, 1 altrimenti."""
    target = max(1, args.target_success)
    rows, ok_set = read_existing_rows()

    # ---- selezione: identici criteri della modalita' singola ----
    # idoneita' calcolata SENZA filtro --repo, per validare anche i
    # risultati 'ok' gia' raccolti al di fuori dell'eventuale lista esplicita
    idonei, excluded, _ = select_repos(events, gm_rows, len(events),
                                        today, None)
    eligible = {c["full"] for c in idonei}
    if explicit:
        # --repo restringe i NUOVI lavori, non il merito dei risultati ok
        want = {w.strip().lower() for w in explicit if w.strip()}
        scope = [c for c in idonei if c["full"].lower() in want]
        for name in sorted(want - {c["full"].lower() for c in scope}):
            excluded.append((name, "richiesto esplicitamente ma non idoneo"))
    else:
        scope = idonei

    # un risultato 'ok' del CSV conta nel target SOLO se il repository e'
    # ancora idoneo secondo select_repos(); altrimenti resta nel CSV (non si
    # eliminano risultati) ma non viene conteggiato
    ok_valid = {r for r in ok_set if r in eligible}
    stale_ok = ok_set - ok_valid
    todo = [c for c in scope if c["full"] not in ok_set]
    done = len(ok_valid)

    print("=" * 60, flush=True)
    print(f"AVANZAMENTO BATCH: {done}/{target} repository validi", flush=True)
    print(f"Repository già completati: {done}", flush=True)
    print(f"Repository ancora da completare: {max(0, target - done)}",
          flush=True)
    print("=" * 60, flush=True)
    if stale_ok:
        print(f"[NOTA] {len(stale_ok)} risultati 'ok' nel CSV non sono piu' "
              "idonei: conservati ma NON conteggiati nel target "
              f"({', '.join(sorted(stale_ok)[:3])}"
              f"{', ...' if len(stale_ok) > 3 else ''}).", flush=True)
    if excluded:
        print(f"Esclusi dai criteri di idoneita': {len(excluded)}", flush=True)
    if done >= target:
        print(f"Target gia' raggiunto ({done}/{target}): "
              "nessuna analisi da eseguire.", flush=True)
        return 0
    if not todo:
        print(f"Nessun repository idoneo mancante: raggiunti {done}/{target} "
              "(pool esaurito).", flush=True)
        return 1
    if args.dry_run:
        print(f"\n[dry-run] verrebbero analizzati {min(len(todo), target - done)} "
              f"repository (ordine di adoption_events.csv):", flush=True)
        for i, c in enumerate(todo[:target - done], done + 1):
            print(f"   [{i}/{target}] {c['full']}  T1={c['t1s']}", flush=True)
        print("[dry-run] nessun dato scaricato.", flush=True)
        return 0
    if workers > 1:
        print(f"[AVVISO] batch con --concurrency {workers}: le richieste "
              "interne restano parallele; i repository sono comunque "
              "elaborati uno alla volta.", flush=True)

    processed, stop_reason = 0, None
    for c in todo:
        done = len(ok_valid)            # conta solo 'ok' distinti e idonei
        if done >= target:
            break
        slot = done + 1                 # es. [11/40] con 10 gia' ok
        print(f"\n[{slot}/{target}] INIZIO ANALISI: {c['full']}", flush=True)
        print(f"T1: {c['t1s']}", flush=True)
        print("Stato: analisi in corso...", flush=True)
        t0 = time.time()
        try:
            row, err = analyze_repo(client, c, workers)
        except RateLimitExceeded as e:
            # rate limit esaurito: ARRESTO del batch (come in modalita' singola)
            row = {"repository": c["full"], "t1": c["t1s"],
                   "stato": f"interrotto: {e}"}
            err = str(e)
        except (RuntimeError, OSError) as e:
            # errore di rete non previsto sfuggito ad analyze_repo
            # (RemoteDisconnected, ConnectionResetError, TimeoutError, ...):
            # registro il repository come fallito e passo al successivo,
            # il batch NON si interrompe
            row = {"repository": c["full"], "t1": c["t1s"],
                   "stato": f"errore: {e}"}
            err = str(e)
        except Exception as e:
            # rete di sicurezza: nessun errore imprevisto puo' interrompere
            # l'intero batch (KeyboardInterrupt/SystemExit restano liberi)
            row = {"repository": c["full"], "t1": c["t1s"],
                   "stato": f"errore: {type(e).__name__}: {e}"}
            err = str(e)
        processed += 1
        stato = str(row.get("stato", ""))
        written = upsert_row(rows, row)
        write_csv(rows)                 # salvataggio incrementale e sicuro
        if stato == "ok":
            ok_valid.add(c["full"])
            print(f"\n[{slot}/{target}] COMPLETATA: {c['full']}", flush=True)
            print("Esito: OK", flush=True)
            print(f"Repository validi: {len(ok_valid)}/{target}", flush=True)
        else:
            esito = ("parziale" if stato.startswith("parziale")
                     else "errore" if stato.startswith("errore")
                     else stato)
            motivo = err or stato or "motivo non disponibile"
            print(f"\n[{slot}/{target}] ANALISI NON COMPLETATA: {c['full']}",
                  flush=True)
            print(f"Esito: {esito}", flush=True)
            print(f"Motivo: {motivo}", flush=True)
            print(f"[{slot}/{target}] Il repository non viene conteggiato "
                  f"tra i {target} validi.", flush=True)
            print("Passaggio al repository successivo...", flush=True)
            if not written:
                print("   (riga 'ok' esistente preservata)", flush=True)
        print(f"    richieste_repo={row.get('richieste_api')}  "
              f"cache_hit_repo={row.get('cache_hit')}  "
              f"totale={client.requests}  rate_rimasto={client.rate_remaining}"
              f"  tempo={time.time() - t0:.1f}s", flush=True)
        if stato.startswith("interrotto"):
            stop_reason = stato        # rate limit: stop (come in modalita' singola)
            break

    # ---- riepilogo finale (sul CSV, repository distinti) ----
    status_by_repo = {}
    for r in rows:
        status_by_repo[(r.get("repository") or "").strip()] = \
            str(r.get("stato", "")).strip()
    # conteggiati solo gli 'ok' DISTINCTI che sono ancora idonei
    n_ok = sum(1 for k, v in status_by_repo.items()
               if v == "ok" and k in eligible)
    n_ok_csv = sum(1 for v in status_by_repo.values() if v == "ok")
    n_parz = sum(1 for v in status_by_repo.values() if v.startswith("parziale"))
    n_ko = sum(1 for v in status_by_repo.values()
               if v and v != "ok" and not v.startswith("parziale"))
    mancanti = max(0, target - n_ok)

    print("\n" + "=" * 60, flush=True)
    print("RIEPILOGO BATCH", flush=True)
    print("=" * 60, flush=True)
    print(f"Repository validi (ok)    : {n_ok}/{target}", flush=True)
    if n_ok_csv != n_ok:
        print(f"  (di cui {n_ok_csv - n_ok} 'ok' nel CSV non piu' idonei: "
              "conservati, non conteggiati)", flush=True)
    print(f"Parziali                  : {n_parz}", flush=True)
    print(f"Falliti / interrotti      : {n_ko}", flush=True)
    print(f"Ancora mancanti vs target : {mancanti}", flush=True)
    print(f"Analizzati in questa sessione: {processed}", flush=True)
    print(f"Richieste API totali      : {client.requests} "
          f"(cache hit {client.cache_hits})", flush=True)
    if stop_reason:
        print(f"Interrotto                : {stop_reason}", flush=True)
    if client.rate_remaining is not None:
        print(f"Rate limit residuo        : {client.rate_remaining}", flush=True)
    print(f"Tempo totale              : {time.time() - t_start:.1f}s",
          flush=True)
    print(f"CSV: {OUT_FILE}", flush=True)
    return 0 if n_ok >= target else 1


def main():
    ap = argparse.ArgumentParser(description="Metriche GitHub (PR/Issue/Review) su T-6 / T+6")
    ap.add_argument("--n", type=int, default=1, help="quanti repository analizzare (default 1)")
    ap.add_argument("--repo", type=str, default="",
                    help="lista esplicita owner/name,owner/name (bypassa la selezione)")
    ap.add_argument("--batch", action="store_true",
                    help="modalita' batch sequenziale: un repository alla volta, "
                         "fino a --target-success repository con stato 'ok' nel "
                         "CSV (quelli gia' ok non vengono rianalizzati)")
    ap.add_argument("--target-success", type=int, default=40,
                    help="target totale di repository validi 'ok' nel CSV "
                         "(default 40; include quelli gia' analizzati)")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="richieste parallele per repo (default 4; max 8; "
                         "in batch usa tipicamente 1)")
    ap.add_argument("--dry-run", action="store_true",
                    help="selezione + stima richieste, senza scaricare i dati")
    ap.add_argument("--no-cache", action="store_true", help="disabilita la cache su disco")
    args = ap.parse_args()

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
             or os.environ.get("YOSHI_GH_TOKEN") or "")
    if not token and not args.dry_run:
        print("ERRORE: nessun token trovato. Imposta la variabile d'ambiente "
              "GITHUB_TOKEN (o GH_TOKEN / YOSHI_GH_TOKEN) e riesegui.")
        return 1
    if not token:
        print("[AVVISO] nessun token: dry-run in anonimo (limite search 10/min). "
              "Per il test completo serve un token.")
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

    client = GitHubClient(token, cache=not args.no_cache)

    if args.batch:
        # modalita' batch sequenziale: un repository alla volta, con lettura
        # del CSV esistente (i repository gia' 'ok' non vengono rianalizzati)
        return run_batch(client, events, gm_rows, args, workers,
                         t_start, today, explicit)

    if explicit:
        chosen, excluded, not_chosen = select_repos(events, gm_rows, args.n, today, explicit)
    else:
        # senza --repo: i primi args.n idonei NELL'ORDINE DI adoption_events.csv
        # (nessun ordinamento alfabetico ne per volume)
        all_ok, excluded, _ = select_repos(events, gm_rows, len(events), today, None)
        chosen = all_ok[:args.n]
        not_chosen = [(c["full"], "idoneo ma non selezionato (oltre i %d)" % args.n)
                      for c in all_ok[args.n:]]
    pool = chosen

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
        print(f"   {c['full']}: PR={n_pr} issue={n_is} PR_candidate_review={n_act} "
              f"-> ~{est} richieste "
              f"(pagine elenco issue + pagine liste PR + reviews PR candidate)")

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
    # le righe gia' raccolte (es. i 10 risultati 'ok') vengono preservate:
    # il CSV si aggiorna in place (upsert), mai ripartito da zero
    rows, _pre_ok = read_existing_rows()
    session, errors = [], []
    for i, c in enumerate(chosen, 1):
        print(f"\n[{i}/{len(chosen)}] {c['full']} ...", flush=True)
        try:
            row, err = analyze_repo(client, c, workers)
        except RateLimitExceeded as e:
            row = {"repository": c["full"], "t1": c["t1s"], "stato": f"interrotto: {e}"}
            err = str(e)
        upsert_row(rows, row)      # mai riga duplicata, mai 'ok' sovrascritto
        session.append(row)
        if err:
            errors.append(f"{c['full']}: {err}")
        # salvataggio incrementale: non si perde nulla in caso di interruzione
        write_csv(rows)
        print(f"    stato={row.get('stato')}  richieste_repo={row.get('richieste_api')}  "
              f"cache_hit_repo={row.get('cache_hit')}  "
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
    print(f"{'repository':40} {'richieste':>10} {'cache_hit':>10} {'stato':>12}")
    for r in session:
        print(f"{r.get('repository', ''):40} {str(r.get('richieste_api', '-')):>10} "
              f"{str(r.get('cache_hit', '-')):>10} {str(r.get('stato', ''))[:12]:>12}")
    print("-" * 70)
    print(f"Repository analizzati      : {len(session)} / {len(chosen)}")
    print(f"Richieste API totali       : {client.requests}")
    print(f"  per repository           : "
          + ", ".join(f"{k}={v}" for k, v in sorted(client.by_repo.items())))
    print(f"  per tipologia di dato    :")
    for k in sorted(set(client.by_kind) | set(client.cache_by_kind)):
        real = client.by_kind.get(k, 0)
        hit = client.cache_by_kind.get(k, 0)
        print(f"     {k:24} richieste={real:<6} cache_hit={hit:<6} totale_dati={real + hit}")
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
    """Scrive il CSV completo (37 colonne, stesso schema di prima).

    Scrittura atomica: prima su file temporaneo, poi sostituzione con
    os.replace, cosi' un'interruzione non puo' mai lasciare un CSV parziale
    o distruggere i risultati gia' raccolti."""
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, OUT_FILE)


if __name__ == "__main__":
    sys.exit(main())
