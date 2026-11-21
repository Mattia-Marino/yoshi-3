
import matplotlib.pyplot as plt
import numpy as np

# Dati delle valutazioni
models = [
    "DeepSeek V4.1 Flash",
    "GPT-6",
    "Gemini",
    "Sonnet5.5"
]

coerente = [77, 67, 69, 65]
dubbio = [8, 24, 25, 11]
incoerente = [15, 9, 6, 24]

# Colori
color_coerente = "#4CAF50"
color_dubbio = "#D9D9D9"
color_incoerente = "#E57373"

# Creazione del grafico
fig, ax = plt.subplots(figsize=(10, 5.5))

y = np.arange(len(models))

# Barre impilate
ax.barh(
    y, coerente,
    color=color_coerente,
    label="Coerente"
)

ax.barh(
    y, dubbio,
    left=coerente,
    color=color_dubbio,
    label="Dubbio"
)

left_incoerente = np.array(coerente) + np.array(dubbio)

ax.barh(
    y, incoerente,
    left=left_incoerente,
    color=color_incoerente,
    label="Incoerente"
)

# Etichette percentuali
for i in range(len(models)):
    values = [coerente[i], dubbio[i], incoerente[i]]
    left = 0

    for value in values:
        if value >= 6:
            ax.text(
                left + value / 2,
                i,
                f"{value}%",
                ha="center",
                va="center",
                fontsize=20,
                color="black"
            )
        left += value

# Personalizzazione
ax.set_yticks(y)
ax.set_yticklabels(models, fontsize=20)
ax.set_xlim(0, 100)
ax.set_xlabel(
    "Percentuale delle valutazioni",
    fontsize=20,
    labelpad=10
)

ax.tick_params(axis="x", labelsize=12)
ax.tick_params(axis="y", length=0)

# Legenda
ax.legend(
    loc="lower center",
    bbox_to_anchor=(0.5, -0.27),
    ncol=3,
    frameon=False,
    fontsize=20
)

# Griglia
ax.grid(axis="x", linestyle="--", alpha=0.35)
ax.set_axisbelow(True)

# Ordine dall'alto verso il basso
ax.invert_yaxis()

# Rimozione dei bordi superflui
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)

plt.tight_layout()

# Esportazione ad alta risoluzione
plt.savefig(
    "llm_comparison.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()
