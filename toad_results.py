import matplotlib.pyplot as plt
import numpy as np

# Dati di input
categories = ['Non confrontabili', 'Coerenti\n(tra confrontabili)', 'Incoerenti\n(tra confrontabili)']
values = [12, 25, 9]
colors = ['#ff9999', '#66b3ff', '#99ff99']

# Creazione della figura (ingrandita per dare più respiro ai testi)
plt.figure(figsize=(10, 6.5))

# Larghezza delle barre
bars = plt.bar(categories, values, color=colors, edgecolor='grey', width=0.45)

# Aggiunta dei valori sopra le barre con font molto grande (15)
for bar in bars:
    height = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2., height + 0.6,
             f'{height} ({height/46*100:.1f}%)',
             ha='center', va='bottom', fontsize=25, fontweight='bold')

# Personalizzazione degli assi e delle etichette con font grandi
plt.ylabel('Numero di Risultati', fontsize=25, labelpad=12, fontweight='bold')
plt.xticks(fontsize=25, fontweight='bold')
plt.yticks(fontsize=25)
plt.ylim(0, 31)
plt.grid(axis='y', linestyle='--', alpha=0.7)

plt.tight_layout()
plt.show()