import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera gli istogrammi delle 4 metriche da Repositories2CSV.csv"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).with_name("Repositories2CSV.csv"),
        help="Percorso del file CSV (default: Repositories2CSV.csv nella stessa cartella)",
    )
    parser.add_argument("--bins", type=int, default=10, help="Numero di barre dell'istogramma")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Cartella output immagini (default: sottocartella 'output' nella cartella dello script)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Mostra il grafico a schermo oltre a salvarlo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.csv, sep=";", decimal=",")

    metrics = ["Geodispersion", "Formality", "Longevity", "Cohesion"]
    missing = [metric for metric in metrics if metric not in df.columns]
    if missing:
        cols = ", ".join(df.columns)
        raise ValueError(
            f"Mancano le colonne richieste: {', '.join(missing)}. Colonne disponibili: {cols}"
        )

    output_dir = args.output_dir or (Path(__file__).parent / "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []
    for metric in metrics:
        values = pd.to_numeric(df[metric], errors="coerce").dropna()
        if values.empty:
            raise ValueError(f"La colonna '{metric}' non contiene valori numerici validi")

        output_path = output_dir / f"histogram_{metric}.png"

        plt.figure(figsize=(9, 5))
        plt.hist(values, bins=args.bins, edgecolor="black")
        plt.title(f"Histogram - {metric}")
        plt.xlabel(metric)
        plt.ylabel("Frequenza")
        plt.grid(axis="y", alpha=0.25)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        if args.show:
            plt.show()
        plt.close()

        generated_files.append(output_path)

    print("Istogrammi salvati in:")
    for file_path in generated_files:
        print(f"- {file_path}")


if __name__ == "__main__":
    main()
