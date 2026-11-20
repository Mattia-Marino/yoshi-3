"""
Secondo passo: metriche di attivita' attorno a T_1, con finestra T-6 / T+6
(sci mesi prima e sei mesi dopo la prima introduzione di un file per agenti).

Input:
  - results/adoption_events.csv  (T_1 per repo, colonna 'data')
  - i clone in C:\\Users\\geppe\\Desktop\\Cloning_repo

Finestre:
  pre  = [T_1 - 6 mesi, T_1)
  post = [T_1, T_1 + 6 mesi)
Se T_1 + 6 mesi e' futuro (rispetto a oggi), la finestra post non e' completa:
nello stato del repo viene scritto "periodo_post_incompleto" e le colonne
post restano vuote (nessun confronto non omogeneo tra repo).

Metriche (una riga per repo):
  - commits: tutti i commit raggiungibili dal branch principale (dedup per hash)
  - commit mensili: media su 6 mesi
  - contributori distinti: identita' git dell'autore (email in minuscolo,
    altrimenti nome in minuscolo)
  - contributori attivi mensili: media dei contributori con >=1 commit
    in ciascuno dei 6 slot mensili della finestra
  - righe aggiunte/rimosse: numstat dei commit NON-merge
  - top 1/3/5: quota % dei commit appartenenti ai contributori piu' attivi
  - release: tag il cui nome contiene una versione "x.y" (i tag puramente
    decorativi/non-versione non sono contati)
  - release mensili: media su 6 mesi

Esclusi al momento (da fare con API GitHub): PR, issue, review.
Output: results/git_metrics.csv
"""

import csv
import re
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

REPOS_DIR = Path(r"C:\Users\geppe\Desktop\Cloning_repo")
RESULTS_DIR = Path(r"C:\Users\geppe\Desktop\Progetto_Tamburri\yoshi-3\AI_agent_folder\results")
EVENTS_FILE = RESULTS_DIR / "adoption_events.csv"
OUT_FILE = RESULTS_DIR / "git_metrics.csv"

WINDOW_MONTHS = 6
SLACK_DAYS = 40  # margine su --since/--until (git filtra per data di commit, non di autore)
RELEASE_RE = re.compile(r"\d+\.\d+")  # tag tipo "v1.2.3", "release-2.0", "2026.08.1"

FIELDS = [
    "repository", "t1", "stato",
    "commits_pre", "commits_post",
    "commit_mensili_pre", "commit_mensili_post",
    "contributors_pre", "contributors_post",
    "contributors_attivi_mensili_pre", "contributors_attivi_mensili_post",
    "righe_aggiunte_pre", "righe_aggiunte_post",
    "righe_rimosse_pre", "righe_rimosse_post",
    "top1_contributor_pre", "top1_contributor_post",
    "top3_contributor_pre", "top3_contributor_post",
    "top5_contributor_pre", "top5_contributor_post",
    "release_pre", "release_post",
    "release_mensili_pre", "release_mensili_post",
]

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    dim = 29 if (month == 2 and leap) else _DAYS_IN_MONTH[month - 1]
    return date(year, month, min(d.day, dim))


def git(repo: Path, *args, timeout=3600):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def default_ref(repo: Path) -> str:
    """Branch principale: origin/HEAD se disponibile, altrimenti HEAD."""
    p = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if p.returncode == 0 and p.stdout.strip():
        return p.stdout.strip()
    return "HEAD"


def month_slots(t1: date, post: bool):
    """6 slot mensili consecutivi allineati a T_1.
    pre : [T1-6m, T1-5m) ... [T1-1m, T1)
    post: [T1, T1+1m) ... [T1+5m, T1+6m)"""
    slots = []
    for i in range(WINDOW_MONTHS):
        if post:
            s, e = add_months(t1, i), add_months(t1, i + 1)
        else:
            s, e = add_months(t1, -(WINDOW_MONTHS - i)), add_months(t1, -(WINDOW_MONTHS - 1 - i))
        slots.append((s, e))
    return slots


def collect_commits(repo: Path, ref: str, since: date, until: date):
    """Tutti i commit (inclusi i merge) nel range: [(identita', data_autore)]."""
    p = git(repo, "log", ref,
            f"--since={since.isoformat()}", f"--until={until.isoformat()}",
            "--format=%x1e%an%x1f%ae%x1f%aI")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:160])
    commits = []
    for line in p.stdout.split("\n"):
        if not line.startswith("\x1e"):
            continue
        f = line[1:].split("\x1f")
        if len(f) != 3:
            continue
        name, email, iso = f
        ident = email.strip().lower() if "@" in email else name.strip().lower()
        commits.append((ident, date.fromisoformat(iso[:10])))
    return commits


def collect_loc(repo: Path, ref: str, since: date, until: date):
    """Righe aggiunte/rimosse per commit, ESCLUSI i merge: [(data_autore, add, del)]."""
    p = git(repo, "log", ref, "--no-merges",
            f"--since={since.isoformat()}", f"--until={until.isoformat()}",
            "--numstat", "--format=%x1e%aI")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:160])
    out = []
    cur, add, dele = None, 0, 0
    for line in p.stdout.split("\n"):
        if line.startswith("\x1e"):
            if cur is not None:
                out.append((cur, add, dele))
            cur, add, dele = date.fromisoformat(line[1:11]), 0, 0
        elif line.strip() and cur is not None:
            f = line.split("\t")
            if len(f) == 3:
                if f[0] != "-":
                    add += int(f[0])
                if f[1] != "-":
                    dele += int(f[1])
    if cur is not None:
        out.append((cur, add, dele))
    return out


def collect_tags(repo: Path):
    """[(nome, data)] di tutti i tag (creatordate)."""
    p = git(repo, "for-each-ref", "--format=%(refname:short)|%(creatordate:iso-strict)", "refs/tags")
    if p.returncode != 0:
        return []
    tags = []
    for line in p.stdout.split("\n"):
        if "|" not in line:
            continue
        name, iso = line.split("|", 1)
        if len(iso) >= 10:
            try:
                tags.append((name, date.fromisoformat(iso[:10])))
            except ValueError:
                pass
    return tags


def window_stats(commits, loc, tags, bounds, slots):
    """Metriche per una finestra [start, end)."""
    s, e = bounds
    cs = [c for c in commits if s <= c[1] < e]
    n = len(cs)
    ids = Counter(c[0] for c in cs)

    def share(top):
        if n == 0:
            return ""
        return round(100.0 * sum(v for _, v in ids.most_common(top)) / n, 1)

    ls = [x for x in loc if s <= x[0] < e]
    actives = []
    for (ss, ee) in slots:
        actives.append(len({c[0] for c in commits if ss <= c[1] < ee}))

    releases = sum(1 for name, d in tags if s <= d < e and RELEASE_RE.search(name))

    return {
        "commits": n,
        "commit_mensili": round(n / WINDOW_MONTHS, 1),
        "contributors": len(ids),
        "contributors_attivi_mensili": round(sum(actives) / WINDOW_MONTHS, 1),
        "righe_aggiunte": sum(x[1] for x in ls),
        "righe_rimosse": sum(x[2] for x in ls),
        "top1_contributor": share(1),
        "top3_contributor": share(3),
        "top5_contributor": share(5),
        "release": releases,
        "release_mensili": round(releases / WINDOW_MONTHS, 2),
    }


def main():
    if not EVENTS_FILE.exists():
        raise SystemExit(f"Manca {EVENTS_FILE}: esegui prima adoption_detector.py")

    # t1 per cartella (chiave = nome cartella in minuscolo)
    events = {}
    with open(EVENTS_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("repository") or "").split("/")[-1].strip().lower()
            events[key] = row

    folders = sorted([p for p in REPOS_DIR.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    print(f"Trovate {len(folders)} cartelle")
    today = date.today()

    rows = []
    for i, repo in enumerate(folders, 1):
        ev = events.get(repo.name.lower(), {})
        full_name = ev.get("repository") or repo.name
        t1s = (ev.get("data") or "").strip()
        print(f"[{i}/{len(folders)}] {full_name} ...", flush=True)

        if not t1s:
            # nessun file per agenti: solo il nome, come in adoption_events.csv
            rows.append({k: "" for k in FIELDS} | {"repository": full_name})
            continue

        t1 = date.fromisoformat(t1s)
        pre_start = add_months(t1, -WINDOW_MONTHS)
        post_end = add_months(t1, WINDOW_MONTHS)
        post_complete = post_end <= today
        stato = "ok" if post_complete else "periodo_post_incompleto"

        since = pre_start - timedelta(days=SLACK_DAYS)
        until = (post_end if post_complete else t1) + timedelta(days=SLACK_DAYS)

        try:
            ref = default_ref(repo)
            commits = collect_commits(repo, ref, since, until)
            loc = collect_loc(repo, ref, since, until)
            tags = collect_tags(repo)
        except (RuntimeError, subprocess.TimeoutExpired) as ex:
            print(f"  [ERRORE] {full_name}: {ex}")
            rows.append({k: "" for k in FIELDS} |
                        {"repository": full_name, "t1": t1s, "stato": "errore_git"})
            continue

        pre = window_stats(commits, loc, tags, (pre_start, t1), month_slots(t1, post=False))
        row = {"repository": full_name, "t1": t1s, "stato": stato}
        for k, v in pre.items():
            row[f"{k}_pre"] = v

        if post_complete:
            post = window_stats(commits, loc, tags, (t1, post_end), month_slots(t1, post=True))
            for k, v in post.items():
                row[f"{k}_post"] = v
        else:
            for k in pre:
                row[f"{k}_post"] = ""

        rows.append(row)

    with open(OUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n_incomplete = sum(1 for r in rows if r.get("stato") == "periodo_post_incompleto")
    print(f"\nScritto: {OUT_FILE} ({len(rows)} righe, {n_incomplete} con periodo_post_incompleto)")


if __name__ == "__main__":
    main()
