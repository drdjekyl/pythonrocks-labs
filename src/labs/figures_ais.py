"""Les deux figures de l'article sur l'appariement AIS.

Même parti pris que `figures_eda` : la figure est choisie par la *fonction* de la donnée.
  1. une population qui se décompose en issues  -> barres horizontales, emphase sur ce qui survit
  2. deux mesures qui devraient coïncider       -> nuage, bande de tolérance, aberrants nommés

Le scoring vient de `marine_cadastre.analyser` et n'est jamais réimplémenté ici : une figure
qui recalculerait ses propres chiffres finirait par diverger du texte de l'article. Le résultat
est mis en cache dans la couche gold, qui est faite exactement pour ça — reconstructible en une
commande, donc supprimable sans regret.

Sortie dans `figures/ais/`, à copier ensuite vers la vitrine.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from labs.marine_cadastre import TOLERANCE_M, analyser, charger_reference
from labs.viz import (
    ACCENT,
    CONTEXTE,
    INK,
    MUTED,
    appliquer_style,
    enregistrer,
    titrer,
)

RACINE = Path(__file__).resolve().parents[2]
CACHE = RACINE / "data" / "lac" / "gold" / "appariement.parquet"
SORTIE = RACINE / "figures" / "ais"
JOURS = ["2023-02-14", "2023-02-15", "2023-02-16"]

# Voir `figures_eda` : un SVG à viewBox fixe écrasé en CSS à 390px devient illisible, on
# régénère donc une variante pensée pour l'étroitesse.
MOBILE = False


def dim(large, etroit):
    """Choisit la valeur selon la variante en cours."""
    return etroit if MOBILE else large


def espace(n):
    """Séparateur de milliers français : une espace, pas une virgule."""
    return f"{int(n):,}".replace(",", " ")


def _plus_proche(candidats, longueur):
    """Longueur du candidat le plus proche, quand un nom désigne plusieurs yachts.

    Retenir le plus favorable plutôt qu'un candidat au hasard évite d'imputer à la méthode un
    écart qui ne viendrait que du tirage : si même le meilleur candidat est à cent mètres, le
    rejet ne se discute pas.
    """
    refs = [c["overall_length"] for c in candidats if pd.notna(c["overall_length"])]
    if not refs or pd.isna(longueur):
        return np.nan
    return min(refs, key=lambda r: abs(r - longueur))


def charger():
    """Le tableau des verdicts, un navire (MMSI) par ligne."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)

    _, scores = analyser(JOURS)
    reference = charger_reference()
    scores["longueur_catalogue"] = [
        _plus_proche(reference[cle], longueur)
        for cle, longueur in zip(scores["cle"], scores["Length"], strict=True)
    ]
    garde = scores[
        ["MMSI", "VesselName", "cle", "Length", "longueur_catalogue", "verdict"]
    ].reset_index(drop=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    garde.to_parquet(CACHE)
    return garde


# --------------------------------------------------------------------------- 1
def fig_entonnoir(scores):
    """Une population qui se décompose : barres horizontales, une seule teinte accentuée.

    Pas de barre empilée : quatre issues demanderaient quatre créneaux catégoriels, alors que
    la palette validée n'en compte que trois. L'emphase (accent + gris) dit d'ailleurs mieux ce
    qu'il faut retenir — ce qui survit contre ce qui tombe.
    """
    n = scores["verdict"].value_counts()
    total = int(n.sum())
    confirmes = int(n.get("confirme", 0))
    lignes = [
        ("Rejetés — longueur incompatible", int(n.get("longueur incompatible", 0)), CONTEXTE),
        ("Rejetés — type AIS non plaisance", int(n.get("type non plaisance", 0)), CONTEXTE),
        ("Écartés — longueur absente", int(n.get("longueur absente", 0)), CONTEXTE),
        ("Confirmés", confirmes, ACCENT),
    ]

    fig, ax = plt.subplots(figsize=dim((8.2, 4.0), (5.0, 4.6)))
    y = np.arange(len(lignes))
    valeurs = [v for _, v, _ in lignes]
    ax.barh(y, valeurs, color=[c for _, _, c in lignes], height=0.62)
    for i, (_, v, couleur) in enumerate(lignes):
        part = f"  ({v / total * 100:.0f} %)"
        ax.text(v + max(valeurs) * 0.015, i, espace(v) + part, va="center", fontsize=10,
                color=INK if couleur is ACCENT else MUTED,
                fontweight="600" if couleur is ACCENT else "normal")

    ax.set_yticks(y, [libelle for libelle, _, _ in lignes], fontsize=dim(11, 10))
    ax.invert_yaxis()
    ax.set_xlim(0, max(valeurs) * 1.18)
    ax.set_xlabel("Navires uniques (MMSI)")
    ax.grid(axis="y", visible=False)
    # Sous-titre court, sur une seule ligne : `titrer` ne renvoie pas à la ligne, et un texte
    # plus large que les axes fait déborder la boîte englobante à l'enregistrement.
    titrer(ax, "Cinq correspondances sur six sont fausses",
           dim(f"{espace(total)} navires nommés comme un yacht, trois journées de février 2023.",
               f"{espace(total)} navires nommés comme un yacht."))
    return fig


# --------------------------------------------------------------------------- 2
def fig_longueurs(scores):
    """Deux mesures qui devraient coïncider : nuage, bande de tolérance, aberrants nommés."""
    d = scores[scores["verdict"].isin(["confirme", "longueur incompatible"])]
    d = d.dropna(subset=["Length", "longueur_catalogue"])
    d = d[d["Length"] > 0]
    confirme = d[d["verdict"] == "confirme"]
    rejete = d[d["verdict"] == "longueur incompatible"]

    fig, ax = plt.subplots(figsize=dim((8.2, 5.6), (5.0, 5.4)))
    # Borne calée sur les données, pas sur un chiffre rond : rien n'est hors champ, et le
    # nuage occupe la figure au lieu de se tasser dans un coin.
    borne = 160
    xs = np.array([0.0, borne])
    # La bande d'abord, pour qu'elle passe sous les points.
    ax.fill_between(xs, xs - TOLERANCE_M, xs + TOLERANCE_M, color=ACCENT, alpha=0.16,
                    linewidth=0)
    ax.plot(xs, xs, color=CONTEXTE, linewidth=1.4)
    ax.scatter(rejete["longueur_catalogue"], rejete["Length"], s=13, alpha=0.5,
               color=CONTEXTE, linewidths=0, rasterized=True)
    ax.scatter(confirme["longueur_catalogue"], confirme["Length"], s=15, alpha=0.8,
               color=ACCENT, linewidths=0, rasterized=True)

    # Étiquettes directes plutôt qu'une légende : c'est la règle du style maison, et ici elle
    # libère en prime le coin haut-gauche, seul endroit où l'aberrant du haut peut s'annoter.
    ax.text(0.68, 0.80, f"Confirmés\nécart ≤ {TOLERANCE_M:.0f} m", transform=ax.transAxes,
            color=ACCENT, fontsize=dim(11, 12), fontweight="600", va="center")
    ax.text(0.02, 0.15, "Écartés sur\nla longueur", transform=ax.transAxes,
            color=MUTED, fontsize=dim(11, 12), va="center")

    # Les deux extrêmes, calculés et non choisis : un dans chaque sens, parce que la
    # coïncidence de noms joue aussi bien dans un sens que dans l'autre — une vedette qui
    # porte le nom d'un géant, et un géant qui porte celui d'un petit yacht.
    ecart = rejete["longueur_catalogue"] - rejete["Length"]
    for cas, decalage, ancrage in [
        (rejete.loc[ecart.idxmax()], (-16, 30), "right"),
        (rejete.loc[ecart.idxmin()], (18, -34), "left"),
    ]:
        ax.annotate(
            f"{cas['VesselName'].strip()} : {cas['Length']:.0f} m déclarés,"
            f"\n{cas['longueur_catalogue']:.0f} m au catalogue",
            xy=(cas["longueur_catalogue"], cas["Length"]),
            xytext=decalage, textcoords="offset points", ha=ancrage,
            fontsize=dim(10, 11), color=MUTED,
            arrowprops={"arrowstyle": "->", "color": CONTEXTE, "linewidth": 1.2})

    ax.set_xlim(0, borne)
    ax.set_ylim(0, borne)
    # Pas de contrainte d'aspect : une figure carrée sort deux fois plus étroite que les autres
    # après recadrage serré, et se retrouve donc agrandie d'autant par la vitrine (largeur
    # imposée à 900px), ce qui donnerait à ses étiquettes une taille sans rapport avec celles
    # de la figure voisine. La diagonale à 45° ne valait pas cette incohérence.
    ax.set_xlabel("Longueur au catalogue (m)")
    ax.set_ylabel("Longueur déclarée en AIS (m)")
    titrer(ax, "Un nom identique, deux navires sans rapport",
           dim("Un point par navire ; en cas d'homonymes, le candidat le plus proche.",
               "Homonymes : le candidat le plus proche."))
    return fig


def main():
    global MOBILE
    scores = None
    for mobile in (False, True):
        MOBILE = mobile
        scores = _produire(scores, mobile)
    return 0


def _produire(scores, mobile):
    appliquer_style()
    if mobile:
        import matplotlib as mpl

        mpl.rcParams.update({"font.size": 15, "axes.titlesize": 17})
    if scores is None:
        scores = charger()
    figures = [
        ("01-entonnoir", fig_entonnoir),
        ("02-longueurs", fig_longueurs),
    ]
    suffixe = "-mobile" if mobile else ""
    for nom, fabrique in figures:
        poids = enregistrer(fabrique(scores), SORTIE / f"{nom}{suffixe}.svg")
        print(f"  {nom}{suffixe:<8} {poids:6.0f} Ko")
    return scores


if __name__ == "__main__":
    sys.exit(main())
