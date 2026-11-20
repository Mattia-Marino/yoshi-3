from pathlib import Path
import subprocess
import sys

FILE_LISTA = Path(r"C:\Users\geppe\Desktop\Cloning_repo\toClone.txt")
CARTELLA_DESTINAZIONE = Path(r"C:\Users\geppe\Desktop\Cloning_repo")


def clona_repository() -> None:
    if not FILE_LISTA.is_file():
        print(f"Errore: file non trovato -> {FILE_LISTA}")
        sys.exit(1)

    CARTELLA_DESTINAZIONE.mkdir(parents=True, exist_ok=True)

    # Legge le righe ignorando righe vuote e commenti con '#'
    with FILE_LISTA.open("r", encoding="utf-8") as f:
        urls = [
            riga.strip()
            for riga in f
            if riga.strip() and not riga.strip().startswith("#")
        ]

    if not urls:
        print("Nessun URL trovato nel file.")
        return

    for url in urls:
        # Ricava il nome della cartella dall'URL (es. "repo" da ".../repo.git")
        nome_repo = url.rstrip("/").split("/")[-1]
        if nome_repo.endswith(".git"):
            nome_repo = nome_repo[:-4]

        cartella_repo = CARTELLA_DESTINAZIONE / nome_repo
        if cartella_repo.exists():
            print(f"[SALTO] '{nome_repo}' esiste già in {CARTELLA_DESTINAZIONE}")
            continue

        print(f"[CLONING] {url} -> {cartella_repo}")
        try:
            subprocess.run(
                ["git", "clone", url, str(cartella_repo)],
                check=True,
            )
            print(f"[OK] Completato: {nome_repo}\n")
        except subprocess.CalledProcessError as e:
            print(f"[ERRORE] Clona fallita per {url} (codice {e.returncode})\n")
        except FileNotFoundError:
            print(
                "Errore: 'git' non trovato nel PATH di sistema. Installa Git o aggiungilo alle variabili d'ambiente."
            )
            sys.exit(1)


if __name__ == "__main__":
    clona_repository()