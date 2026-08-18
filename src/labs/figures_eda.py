"""Les cinq figures de l'article d'exploration du catalogue de yachts.

Chaque figure est choisie par la *fonction* de la donnée, pas par habitude :
  1. deux séries à distinguer    -> lignes, étiquetées directement
  2. une relation + un modèle    -> nuage en emphase (1 teinte + gris)
  3. un piège méthodologique     -> petits multiples, la pente locale contre la globale
  4. des magnitudes ordonnées    -> barres horizontales, une seule teinte
  5. une distribution            -> histogramme

Sortie dans `figures/`, à copier ensuite vers la vitrine.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from labs.viz import (
    ACCENT,
    CONTEXTE,
    INK,
    MUTED,
    SERIES,
    SURFACE,
    appliquer_style,
    enregistrer,
    fr,
    titrer,
)

RACINE = Path(__file__).resolve().parents[2]
DONNEES = RACINE / "data" / "yachts.parquet"
SORTIE = RACINE / "figures"

# Variante mobile. Une revue visuelle sur écran réel a montré qu'un SVG à viewBox fixe,
# simplement écrasé en CSS à 390px, voyait sa police interne de 11px tomber sous 5px
# effectifs — illisible. On régénère donc des figures pensées pour l'étroitesse : moins
# larges, police plus grande, et panneaux empilés au lieu d'être juxtaposés.
MOBILE = False


def dim(large, etroit):
    """Choisit la valeur selon la variante en cours."""
    return etroit if MOBILE else large


def espace(n):
    """Séparateur de milliers français : une espace, pas une virgule."""
    return f"{int(n):,}".replace(",", "\u202f")


def charger():
    return pd.read_parquet(DONNEES)


def pente_log(d, xc, yc):
    """Exposant d'une loi de puissance, ajusté en log-log."""
    d = d[[xc, yc]].dropna()
    d = d[(d[xc] > 0) & (d[yc] > 0)]
    x, y = np.log(d[xc].to_numpy()), np.log(d[yc].to_numpy())
    pente, ordonnee = np.polyfit(x, y, 1)
    return pente, ordonnee, len(d)


# --------------------------------------------------------------------------- 1
def fig_decennies(df):
    """Deux séries à distinguer : médiane plate, maximum qui double."""
    d = df[df.year.between(1950, 2019)].copy()  # 2020 exclue : décennie incomplète
    d["dec"] = (d.year // 10 * 10).astype(int)
    g = d.groupby("dec")["overall_length"].agg(["median", "max"])

    fig, ax = plt.subplots(figsize=dim((8.2, 4.4), (5.0, 4.6)))
    ax.plot(
        g.index,
        g["max"],
        color=SERIES[1],
        linewidth=2,
        marker="o",
        markersize=5,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
        label="Le plus grand",
    )
    ax.plot(
        g.index,
        g["median"],
        color=SERIES[0],
        linewidth=2,
        marker="o",
        markersize=5,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
        label="Médiane de la flotte",
    )

    # Étiquettes directes en bout de courbe : obligatoires, l'orange passe sous 3:1.
    for serie, couleur, texte in [
        ("max", SERIES[1], "Le plus grand"),
        ("median", SERIES[0], "Médiane"),
    ]:
        ax.annotate(
            f"{texte}\n{g[serie].iloc[-1]:.0f} m",
            xy=(g.index[-1], g[serie].iloc[-1]),
            xytext=(10, 0),
            textcoords="offset points",
            color=couleur,
            fontsize=10,
            fontweight="600",
            va="center",
        )

    ax.set_xlim(1945, 2028)
    ax.set_ylim(0, 200)
    ax.set_ylabel("Longueur hors-tout (m)")
    ax.set_xticks(g.index)
    ax.set_xticklabels([str(a) for a in g.index])
    titrer(
        ax,
        "La flotte ne grandit pas — son sommet s'étire",
        "Longueur hors-tout par décennie de lancement. La décennie 2020, incomplète, est exclue.",
    )
    return fig


# --------------------------------------------------------------------------- 2
def fig_loi_echelle(df):
    """Une relation contre un modèle : emphase, une teinte + gris."""
    d = df[["overall_length", "gross_tonnage"]].dropna()
    d = d[(d.overall_length > 0) & (d.gross_tonnage > 0)]
    pente, ordonnee, n = pente_log(d, "overall_length", "gross_tonnage")

    fig, ax = plt.subplots(figsize=dim((8.2, 5.0), (5.0, 5.2)))
    # Nuage rastérisé : 9 218 cercles vectoriels pèseraient plus d'un mégaoctet.
    # Les axes, la grille et le texte restent vectoriels.
    ax.scatter(
        d.overall_length,
        d.gross_tonnage,
        s=7,
        alpha=0.16,
        color=ACCENT,
        linewidths=0,
        rasterized=True,
    )

    xs = np.linspace(d.overall_length.min(), d.overall_length.max(), 100)
    ax.plot(
        xs,
        np.exp(ordonnee) * xs**pente,
        color=ACCENT,
        linewidth=2,
        label=f"Mesuré : le tonnage suit L puissance {fr(pente)}",
    )
    # Référence théorique : le pointillé est ici légitime, il marque un modèle et non
    # une grille. Calé sur la médiane pour rester comparable.
    ancre = d.overall_length.median()
    k = d.gross_tonnage.median() / ancre**3
    ax.plot(
        xs,
        k * xs**3,
        color=CONTEXTE,
        linewidth=2,
        linestyle="--",
        label="Similitude géométrique parfaite : L³",
    )

    ax.set_xscale("log")
    ax.set_yscale("log")
    # Graduations en valeurs lisibles : « 3 × 10¹ » ne parle à personne hors d'un article
    # de physique, alors que « 30 » se lit sans effort.
    ax.set_xticks([30, 40, 60, 80, 100, 150])
    ax.set_yticks([100, 300, 1000, 3000, 10000])
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{int(v):,}".replace(",", " "))
    )
    ax.minorticks_off()
    ax.set_xlabel("Longueur hors-tout (m), échelle logarithmique")
    ax.set_ylabel("Tonnage brut (GT), échelle logarithmique")
    ax.legend(loc="upper left", fontsize=10, labelcolor=INK)
    # Le séparateur de milliers se pose sur le seul nombre concerné : un `.replace`
    # global écraserait aussi la virgule décimale de l'exposant.
    titrer(
        ax,
        "Un yacht deux fois plus long n'est pas huit fois plus gros",
        f"{n:,}".replace(",", " ")
        + f" navires. L'exposant mesuré vaut {fr(pente)}, pas 3.",
    )
    return fig


# --------------------------------------------------------------------------- 3
def fig_piege_v3(df):
    """Le pivot : la pente globale n'est pas la pente locale."""
    d = df[["overall_length", "max_speed", "main_eng_power"]].dropna()
    # Bornes de plausibilité, énoncées plutôt que subies : aucun yacht de cette taille ne
    # dépasse 60 nœuds, et une motorisation sous 50 kW est une erreur de saisie. Sans ce
    # filtre, une poignée de points impossibles tire les ajustements.
    d = d[d.max_speed.between(5, 60) & (d.main_eng_power >= 50)]
    # La pente toutes tailles confondues sert la légende de l'article, pas la figure.
    print(
        f"    (pente globale {pente_log(d, 'max_speed', 'main_eng_power')[0]:.2f}, "
        f"n={len(d)})"
    )

    bandes = [(26, 40, "26–40 m"), (40, 60, "40–60 m"), (60, 200, "60 m et plus")]
    # Juxtaposés, les trois panneaux font tomber le plus petit label à ~2,7px sur mobile.
    # Empilés, chacun retrouve toute la largeur disponible.
    fig, axes = plt.subplots(
        *dim((1, 3), (3, 1)),
        figsize=dim((11.5, 4.6), (5.0, 9.6)),
        sharex=True,
        sharey=True,
    )

    for ax, (bas, haut, nom), couleur in zip(axes, bandes, SERIES, strict=True):
        sous = d[d.overall_length.between(bas, haut)]
        pente, ordonnee, n = pente_log(sous, "max_speed", "main_eng_power")
        ax.scatter(
            sous.max_speed,
            sous.main_eng_power,
            s=9,
            alpha=0.28,
            color=couleur,
            linewidths=0,
            rasterized=True,
        )
        # La droite s'arrête où sont les données : la prolonger jusqu'aux extrêmes
        # donnerait une fausse impression de portée.
        bas_x, haut_x = sous.max_speed.quantile([0.01, 0.99])
        xs = np.linspace(bas_x, haut_x, 50)
        ax.plot(xs, np.exp(ordonnee) * xs**pente, color=couleur, linewidth=2)
        # La pente attendue par la physique, ancrée sur la même médiane.
        k = sous.main_eng_power.median() / sous.max_speed.median() ** 3
        ax.plot(xs, k * xs**3, color=CONTEXTE, linewidth=1.6, linestyle="--")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{nom}\n", loc="left", fontsize=11, fontweight="600", color=INK)
        ax.text(
            0,
            1.005,
            f"pente {fr(pente)} · n={espace(n)}",
            transform=ax.transAxes,
            fontsize=10,
            color=couleur,
            fontweight="600",
            va="bottom",
        )
        # Graduations explicites : l'échelle log par défaut empile « 3 × 10¹ » et
        # « 4 × 10¹ » jusqu'à les rendre illisibles sur des panneaux étroits.
        ax.set_xticks([10, 15, 20, 30, 45])
        ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
        ax.minorticks_off()
        if not MOBILE or ax is axes[-1]:
            ax.set_xlabel("Vitesse max (nœuds)")

    # Un seul libellé d'axe Y : répété sur trois panneaux empilés, il mange la largeur
    # qu'on vient justement de leur rendre.
    (axes[1] if MOBILE else axes[0]).set_ylabel("Puissance moteur (kW)")
    axes[2].annotate(
        "v³ attendu", xy=(0.62, 0.9), xycoords="axes fraction", fontsize=10, color=MUTED
    )
    # Un seul titre, géré par matplotlib : `bbox_inches="tight"` recadre la figure après
    # coup, donc tout texte posé en coordonnées figure se retrouve décalé. Le chiffre de la
    # pente globale vit dans la légende de la figure, côté article — c'est sa place.
    fig.suptitle(
        dim(
            "À taille contrainte, la pente monte — sans jamais atteindre 3",
            "La pente monte,\nsans jamais atteindre 3",
        ),
        x=0.02 if MOBILE else 0.075,
        ha="left",
        fontsize=dim(13, 16),
        fontweight="600",
        color=INK,
    )
    return fig


# --------------------------------------------------------------------------- 4
def fig_chantiers(df):
    """Magnitudes ordonnées : une seule teinte. Un dégradé re-encoderait la longueur."""
    b = df.builder.dropna().value_counts()
    top = b.head(8)[::-1]
    autres = int(b.iloc[8:].sum())
    part_top = top.sum() / b.sum() * 100

    fig, ax = plt.subplots(figsize=dim((8.2, 4.6), (5.0, 5.4)))
    etiquettes = [f"Autres ({espace(len(b) - 8)} chantiers)", *top.index]
    valeurs = [autres, *top.to_numpy()]
    ax.barh(etiquettes, valeurs, color=[CONTEXTE] + [ACCENT] * len(top), height=0.68)
    for i, v in enumerate(valeurs):
        ax.text(v + autres * 0.012, i, espace(v), va="center", fontsize=10, color=MUTED)

    ax.set_xlim(0, autres * 1.14)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: espace(int(v))))
    ax.set_xlabel("Nombre de navires au catalogue")
    ax.grid(axis="y", visible=False)
    titrer(
        ax,
        f"Un marché fragmenté : {espace(len(b))} chantiers, aucun dominant",
        f"Les huit premiers ne pèsent que {part_top:.0f} % du catalogue.",
    )
    return fig


# --------------------------------------------------------------------------- 5
def fig_biais(df):
    """Une distribution — et une coupure qui saute aux yeux."""
    fig, ax = plt.subplots(figsize=dim((8.2, 4.0), (5.0, 4.2)))
    ax.hist(
        df.overall_length,
        bins=np.arange(0, 190, 2.5),
        color=ACCENT,
        edgecolor=SURFACE,
        linewidth=0.8,
    )
    ax.axvline(26, color=SERIES[1], linewidth=2)
    ax.annotate(
        "Aucun navire sous 26 m",
        xy=(26, ax.get_ylim()[1] * 0.82),
        xytext=(34, ax.get_ylim()[1] * 0.82),
        fontsize=10,
        color=SERIES[1],
        fontweight="600",
        va="center",
        arrowprops={"arrowstyle": "->", "color": SERIES[1], "linewidth": 1.4},
    )
    au_dela = int((df.overall_length > 120).sum())
    ax.set_xlim(0, 120)
    ax.text(
        0.985,
        0.62,
        f"+ {au_dela} navires\nau-delà de 120 m",
        transform=ax.transAxes,
        ha="right",
        fontsize=10,
        color=MUTED,
    )
    ax.set_xlabel("Longueur hors-tout (m)")
    ax.set_ylabel("Nombre de navires")
    ax.grid(axis="x", visible=False)
    titrer(
        ax,
        "Ce catalogue n'est pas un recensement",
        "La coupure nette à 26 m est une décision éditoriale du courtier, pas un fait maritime.",
    )
    return fig


def main():
    global MOBILE
    df = None
    for mobile in (False, True):
        MOBILE = mobile
        df = _produire(df, mobile)
    return 0


def _produire(df, mobile):
    appliquer_style()
    if mobile:
        # Police relative plus grande : la figure sera affichée plus étroite.
        import matplotlib as mpl

        mpl.rcParams.update({"font.size": 15, "axes.titlesize": 17})
    if df is None:
        df = charger()
    figures = [
        ("01-decennies", fig_decennies),
        ("02-loi-echelle", fig_loi_echelle),
        ("03-piege-v3", fig_piege_v3),
        ("04-chantiers", fig_chantiers),
        ("05-biais-selection", fig_biais),
    ]
    suffixe = "-mobile" if mobile else ""
    total = 0
    for nom, fabrique in figures:
        poids = enregistrer(fabrique(df), SORTIE / f"{nom}{suffixe}.svg")
        total += poids
        print(f"  {nom}{suffixe:<8} {poids:6.0f} Ko")
    print(f"  total{'(mobile)' if mobile else '':>16} {total:6.0f} Ko")
    return df


if __name__ == "__main__":
    sys.exit(main())
