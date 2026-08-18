"""Style de graphiques aligné sur le design system de pythonrocks.academy.

Deux partis pris qui expliquent tout le reste du fichier.

**Sortie SVG, pas PNG.** Vectoriel, net à tout zoom, léger, et cohérent avec les autres
médias des articles. Surtout, `svg.fonttype = "none"` laisse le texte en balises `<text>`
plutôt qu'en tracés : le navigateur le rend avec les polices du site, le texte reste
sélectionnable, et le fichier ne transporte aucune fonte.

**Palette validée, pas choisie à l'œil.** Les trois teintes catégorielles viennent d'un jeu
vérifié par script contre *notre* surface (`#f7f5f0`) : bande de clarté, plancher de chroma,
séparation sous déficience de vision des couleurs en mode « toutes paires » (nuages de points
et petits multiples comparent toutes les paires, pas seulement les voisines). Résultat : ΔE
minimal 9,2 en deutan, 24,0 en vision normale.

Avertissement conservé du validateur : l'orange et l'aqua passent sous 3:1 de contraste avec
le fond. Ils ne sont donc **jamais** porteurs d'information seuls — toujours doublés d'une
étiquette directe. C'est une obligation, pas une préférence.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt

SURFACE = "#f7f5f0"  # --paper
INK = "#201d1a"  # --ink
MUTED = "#726c60"  # --muted
GRILLE = "#e3dfd8"  # --line aplati sur la surface : un ton au-dessus, jamais plus
ACCENT = "#1d3f8f"  # --accent, pour les séries uniques et les droites ajustées
CONTEXTE = "#b9b4aa"  # gris de mise en retrait (forme « emphase »)

# Créneaux catégoriels, dans un ordre FIXE. Un 4e créneau ne s'invente pas : on replie la
# queue dans « Autres » ou on passe en petits multiples.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]

POLICE = ["Public Sans", "system-ui", "Helvetica Neue", "Arial", "sans-serif"]


def appliquer_style():
    """Applique le style global. À appeler une fois avant de tracer."""
    mpl.rcParams.update(
        {
            "svg.fonttype": "none",
            "font.family": "sans-serif",
            "font.sans-serif": POLICE,
            "font.size": 11,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "text.color": INK,
            "axes.labelcolor": MUTED,
            "axes.edgecolor": GRILLE,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.titlecolor": INK,
            # Grille et axes : traits pleins d'un cheveu, jamais pointillés — un pointillé se
            # lit comme un seuil ou une projection alors que ce n'est qu'une grille.
            "axes.grid": True,
            "grid.color": GRILLE,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "axes.axisbelow": True,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "legend.frameon": False,
            "figure.constrained_layout.use": True,
        }
    )


def titrer(ax, titre, sous_titre=None):
    """Titre porteur de l'information, sous-titre pour l'unité ou la source.

    Le titre dit ce que le lecteur doit retenir, pas ce que le graphique contient :
    « la médiane ne bouge pas » plutôt que « longueur par décennie ».
    """
    ax.set_title(
        titre, loc="left", fontsize=13, fontweight="600", pad=32 if sous_titre else 10
    )
    if sous_titre:
        # `pad` réserve la hauteur du titre ; le sous-titre se pose juste au-dessus des axes.
        # Un écart trop faible les fait se chevaucher — matplotlib ne détecte pas la
        # collision, il faut la prévenir.
        ax.text(
            0,
            1.03,
            sous_titre,
            transform=ax.transAxes,
            fontsize=10,
            color=MUTED,
            va="bottom",
        )


def fr(valeur, decimales=2):
    """Nombre au format français : virgule décimale, espace fine comme séparateur."""
    texte = f"{valeur:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return texte


def enregistrer(fig, chemin):
    """Écrit le SVG et renvoie son poids en Ko."""
    from pathlib import Path

    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chemin, format="svg", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return chemin.stat().st_size / 1024
