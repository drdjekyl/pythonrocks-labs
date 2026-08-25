"""Ingénierie de variables : du signal quotidien de `pypi_ecosystem.py` à une ligne par paquet.

## La découverte qui commande tout le reste : une variation brute ment

Sur les 181 jours observables, le trafic PyPI global a fortement augmenté : `certifi` — une
quasi-dépendance universelle, présente dans la quasi-totalité des installations — passe d'une
moyenne 7 jours de ~46,8 M/jour en tout début de période à ~64,8 M/jour en toute fin, soit
**+38,7 %** sur la collecte réelle du 2026-08-25 (`variation_brute_pct` de `certifi` lui-même).
Une lecture brute du `%change` d'un paquet classerait alors presque tout comme « montant » :
`requests` affiche +40,0 % et `numpy` +56,9 % en variation brute sur la même période, des
chiffres qui ne disent rien de leur position relative — ils disent surtout que PyPI dans son
ensemble a plus de trafic aujourd'hui qu'il y a six mois (plus de CI, plus de conteneurs
éphémères, plus d'installations automatisées). *(Note pour qui recouperait avec la recherche
préalable à ce module : une estimation plus grossière, sur un seul jour de part et d'autre plutôt
que sur une moyenne 7 jours, donnait environ +45,8 % pour `certifi` — la valeur qui fait foi est
celle-ci, +38,7 %, calculée par le code réellement exécuté avec la méthode que ce module
applique à tous les paquets, moyennes glissantes incluses.)*

Quelques repères réels de la collecte du 2026-08-25 (`variation_normalisee_pct`, triée) :
`anthropic` +125,1 %, `huggingface-hub` +101,9 %, `duckdb` +90,8 % et `tiktoken` +83,5 % en tête —
une vraie croissance relative, pas un effet de baseline. À l'inverse, `scikit-learn` (+1,6 %),
`requests` (+1,0 %) et `sqlalchemy` (-2,9 %) sont, une fois normalisés, quasiment plats — alors
que leur variation brute (respectivement +41,0 %, +40,0 %, +34,7 %) les ferait passer pour des
paquets en forte hausse. **`urllib3` confirme le piège identifié en amont de cette investigation** :
+34,5 % en brut, -3,0 % une fois normalisé — au niveau du baseline, ni en hausse ni en déclin.
L'intuition « `urllib3` remplacé par `httpx` » est fausse pour la part `urllib3` : `httpx`
progresse bien (+42,5 % normalisé), mais depuis une base beaucoup plus petite, sans manger la
part d'`urllib3`. En bas de classement, `ipaddress` (-53,9 %), `pathlib2` (-42,8 %) et
`tensorflow` (-41,9 %) sont les reculs relatifs les plus marqués de l'échantillon.

Ce module calcule donc **deux variations, jamais une seule** : `variation_brute_pct` (le
`%change` naïf) et `variation_normalisee_pct`, le même calcul appliqué au ratio
`téléchargements_paquet / téléchargements_certifi` plutôt qu'au volume brut — la part de trafic
« certifi-équivalent » qu'occupe le paquet, avant et après. C'est cette seconde variable qui porte
le signal éditorial : un paquet stable doit y rester proche de 0 %, qu'il soit gros (`numpy`) ou
petit. C'est aussi exactement l'angle pédagogique visé : choisir la bonne métrique selon le
contexte plutôt que prendre la première qui se présente.

## Lissage : moyennes mobiles 7 jours, jamais deux jours bruts

La saisonnalité hebdomadaire est réelle (creux week-end mesuré à ~30 % sur le trafic lié à la
CI) : comparer le premier et le dernier jour bruts de la fenêtre reviendrait à comparer un
dimanche à un mardi selon le hasard du calendrier. `variation_brute_pct` et
`variation_normalisee_pct` comparent donc la moyenne des 7 premiers jours à celle des 7
derniers, et `volume_recent` est cette même moyenne des 7 derniers jours plutôt qu'un seul jour
(qui aurait pu tomber un week-end).

## Cadence de release : indéterminée n'est pas zéro

`cadence_releases_an = n_releases / (durée_de_publication_en_années)`, où la durée de publication
va de la première à la dernière release **avec fichier** (voir `pypi_ecosystem.py`). Si cette
durée est nulle (une seule journée de publication, ou une seule release jamais suivie d'une
autre), la division n'a pas de sens : le module renvoie `None` (dtype nullable `Float64`) plutôt
que `0` ou une exception — logique à trois valeurs, comme partout ailleurs dans ce dépôt. Ce cas
ne s'est produit sur aucun des 51 paquets de la collecte réelle (le plus jeune, `tiktoken`, a
20 releases sur ~3,7 ans), mais le code ne suppose pas qu'il ne se produira jamais.

## Ce que ce module NE fait PAS

Il n'attache la catégorie (`etabli`/`montant`/`declinant`) qu'à titre de méta-donnée descriptive,
recopiée depuis `pypi_ecosystem.CATEGORIES` — jamais recalculée ni inférée ici. Le clustering
(`pypi_clustering.py`) ne doit JAMAIS la lire comme variable d'entrée ; elle n'existe dans le
Parquet de sortie que pour la comparaison a posteriori et pour servir de vérité terrain à la
classification (`pypi_classification.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from labs.pypi_ecosystem import BASELINE, CATEGORIES, RELEASES, TELECHARGEMENTS

RACINE = Path(__file__).resolve().parents[2]
SORTIE = RACINE / "data" / "pypi_features.parquet"

FENETRE_MOYENNE = (
    7  # jours -- lisse le creux week-end (~30 % sur le trafic lié à la CI)
)

COLONNES_FUITE = ("variation_brute_pct", "variation_normalisee_pct", "volume_recent")
"""Les trois colonnes qui encodent directement la variation de téléchargement -- exactement ce
qui a servi à poser `categorie` à la main. `pypi_classification.py` les exclut explicitement de
ses variables d'entrée pour ne pas se prédire elle-même."""


def _categorie(paquet: str) -> str:
    for nom, paquets in CATEGORIES.items():
        if paquet in paquets:
            return nom
    raise KeyError(f"{paquet!r} n'appartient à aucun groupe de CATEGORIES")


def _moyenne_bord(serie: pd.Series, fenetre: int, bord: str) -> float:
    """Moyenne des `fenetre` premiers (`bord='debut'`) ou derniers (`bord='fin'`) jours d'une
    série de téléchargements déjà triée par date croissante."""
    fragment = serie.iloc[:fenetre] if bord == "debut" else serie.iloc[-fenetre:]
    return float(fragment.mean())


def construire_features(
    telechargements: pd.DataFrame, releases: pd.DataFrame
) -> pd.DataFrame:
    """Une ligne par paquet : volume récent, deux variations, âge, récence, cadence, catégorie.

    Lève si les deux sources ne couvrent pas exactement le même ensemble de paquets plutôt que
    de produire silencieusement des lignes partielles pour l'écart.
    """
    paquets_dl = set(telechargements["package"].unique())
    paquets_rel = set(releases["package"].unique())
    if paquets_dl != paquets_rel:
        raise ValueError(
            "désaccord entre téléchargements et releases sur les paquets couverts : "
            f"{paquets_dl.symmetric_difference(paquets_rel)}"
        )
    if BASELINE not in paquets_dl:
        raise ValueError(
            f"le paquet de référence {BASELINE!r} est absent de la collecte"
        )

    par_paquet = {
        paquet: groupe.sort_values("date")
        for paquet, groupe in telechargements.groupby("package", observed=True)
    }
    releases_idx = releases.set_index("package")

    certifi_debut = _moyenne_bord(
        par_paquet[BASELINE]["downloads"], FENETRE_MOYENNE, "debut"
    )
    certifi_fin = _moyenne_bord(
        par_paquet[BASELINE]["downloads"], FENETRE_MOYENNE, "fin"
    )

    lignes = []
    for paquet, groupe in par_paquet.items():
        debut = _moyenne_bord(groupe["downloads"], FENETRE_MOYENNE, "debut")
        fin = _moyenne_bord(groupe["downloads"], FENETRE_MOYENNE, "fin")

        variation_brute_pct = (fin / debut - 1) * 100
        ratio_debut = debut / certifi_debut
        ratio_fin = fin / certifi_fin
        variation_normalisee_pct = (ratio_fin / ratio_debut - 1) * 100

        meta = releases_idx.loc[paquet]
        premiere = pd.Timestamp(meta["first_release"])
        derniere = pd.Timestamp(meta["last_release"])
        reference = pd.Timestamp(meta["reference_date"])

        duree_publication_jours = (derniere - premiere).days
        cadence_releases_an = (
            meta["n_releases"] / (duree_publication_jours / 365.25)
            if duree_publication_jours > 0
            else None
        )

        lignes.append(
            {
                "package": paquet,
                "categorie": _categorie(paquet),
                "volume_recent": fin,
                "variation_brute_pct": variation_brute_pct,
                "variation_normalisee_pct": variation_normalisee_pct,
                "age_jours": (reference - premiere).days,
                "recence_jours": (reference - derniere).days,
                "n_releases": int(meta["n_releases"]),
                "cadence_releases_an": cadence_releases_an,
            }
        )

    df = pd.DataFrame(lignes).sort_values("package").reset_index(drop=True)
    df["cadence_releases_an"] = df["cadence_releases_an"].astype("Float64")
    df["categorie"] = df["categorie"].astype("category")
    return df


def main() -> int:
    telechargements = pd.read_parquet(TELECHARGEMENTS)
    releases = pd.read_parquet(RELEASES)
    df = construire_features(telechargements, releases)

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SORTIE, index=False)

    print(f"{len(df)} paquets -> {SORTIE.name}\n")
    apercu = df[
        ["package", "categorie", "variation_brute_pct", "variation_normalisee_pct"]
    ].sort_values("variation_normalisee_pct", ascending=False)
    for _, ligne in apercu.iterrows():
        print(
            f"  {ligne.package:20} {ligne.categorie:10} "
            f"brute {ligne.variation_brute_pct:+7.1f} %   "
            f"vs certifi {ligne.variation_normalisee_pct:+7.1f} %"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
