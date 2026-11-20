"""
Cerca nella cronologia git di ogni repository la PRIMA introduzione dei file:
  - CLAUDE.md
  - AGENTS.md
  - GEMINI.md
  - SKILL.md
  - copilot-instructions.md   (es. .github/copilot-instructions.md)

Matching case-insensitive sul nome del file, in qualunque sottocartella.
Per ogni repo viene registrata UNA sola riga: la PRIMA introduzione (T_1),
cioè il primo file tra tutti quelli target ad essere stato aggiunto.
Risultato scritto in results/first_ai_file_introductions.csv
(colonne: repository, file, data, commit, autore, percorso).
"""

import csv
import subprocess
from pathlib import Path

REPOS_DIR = Path(r"C:\Users\geppe\Desktop\Cloning_repo")
OUT_DIR = Path(r"C:\Users\geppe\Desktop\Progetto_Tamburri\yoshi-3\AI_agent_folder\results")
OUT_FILE = OUT_DIR / "adoption_events.csv"

TARGETS = {"claude.md", "agents.md", "gemini.md", "skill.md", "copilot-instructions.md"}


def repo_full_name(repo: Path):
    """Ritorna 'owner/repo' leggendo l'origin remoto; fallback sul nome cartella."""
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        url = p.stdout.strip()
    except subprocess.TimeoutExpired:
        url = ""
    if url:
        # forme: https://github.com/owner/repo.git | git@github.com:owner/repo.git
        s = url.rstrip("/")
        if s.endswith(".git"):
            s = s[:-4]
        s = s.replace("git@github.com:", "https://github.com/")
        parts = [x for x in s.split("/") if x]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
    return repo.name


def first_introductions(repo: Path):
    """Ritorna UNA tupla (basename, data, commit, autore, percorso): la PRIMA
    introduzione di uno qualsiasi dei file target nel repo (T_1)."""
    cmd = [
        "git", "-C", str(repo), "-c", "core.quotepath=false",
        "log", "HEAD", "--diff-filter=A", "--name-only",
        "--format=%x1e%H%x1f%aI%x1f%an",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=1800,
        )
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] {repo.name}")
        return None
    if proc.returncode != 0:
        print(f"  [ERRORE git] {repo.name}: {proc.stderr.strip()[:120]}")
        return None

    best = {}  # basename -> (data, commit, autore, percorso)
    cur = None  # (data, commit, autore)
    # NOTA: splitlines() spezzerebbe anche su \x1e (e' un separatore Unicode):
    # si usa lo split esplicito su "\n"
    for line in proc.stdout.split("\n"):
        if line.startswith("\x1e"):
            f = line[1:].split("\x1f")
            if len(f) == 3:
                cur = (f[1][:10], f[0], f[2])
            else:
                cur = None
        elif line.strip() and cur is not None:
            path = line.strip()
            base = path.split("/")[-1].lower()
            if base in TARGETS and base not in best:
                best[base] = (cur[0], cur[1], cur[2], path)

    if not best:
        return None
    # T_1 = prima introduzione assoluta tra tutti i file target del repo
    base, vals = min(best.items(), key=lambda kv: kv[1][0])
    return base, vals[0], vals[1], vals[2], vals[3]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    repos = sorted([p for p in REPOS_DIR.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    print(f"Trovate {len(repos)} cartelle")

    rows = []
    for i, repo in enumerate(repos, 1):
        print(f"[{i}/{len(repos)}] {repo.name} ...", flush=True)

        shallow = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--is-shallow-repository"],
            capture_output=True, text=True,
        )
        if shallow.stdout.strip() == "true":
            print(f"  [ATTENZIONE] {repo.name}: clone shallow (storica troncata!)")

        found = first_introductions(repo)
        full = repo_full_name(repo)
        if found is None:
            # repo senza alcun file target: solo il nome, come promemoria
            rows.append({
                "repository": full,
                "file": "", "data": "", "commit": "", "autore": "", "percorso": "",
            })
            continue
        base, date, commit, author, path = found
        rows.append({
            "repository": full,
            "file": path.split("/")[-1],
            "data": date,
            "commit": commit,
            "autore": author,
            "percorso": path,
        })

    with open(OUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["repository", "file", "data", "commit", "autore", "percorso"])
        w.writeheader()
        w.writerows(rows)

    print(f"\nScritto: {OUT_FILE} ({len(rows)} righe, {len(repos)} repository)")


if __name__ == "__main__":
    main()
