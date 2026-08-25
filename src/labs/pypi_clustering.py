"""Les trois catégories pressenties ressortent-elles d'un K-Means qui ne les a jamais vues ?

C'est la question éditoriale de ce module. `pypi_ecosystem.CATEGORIES` classe les 51 paquets à
la main (« établi », « montant », « déclinant »), en lisant directement les chiffres. Ce module
ne lui montre jamais cette étiquette : il tourne un K-Means non supervisé sur les six variables
de `pypi_features.construire_features`, et ne consulte la catégorie qu'une fois les clusters déjà
posés — pour comparer, pas pour apprendre. C'est le sens même de « non supervisé » : lui donner la
catégorie en entrée transformerait l'exercice en classification déguisée, exactement ce que
`pypi_classification.py` fait déjà, explicitement, à côté.

## Pourquoi le volume passe en log avant tout le reste

`volume_recent` s'étend sur plus de quatre ordres de grandeur (de quelques dizaines de milliers de
téléchargements/jour pour les paquets les plus confidentiels de l'échantillon à plus de
60 millions/jour pour `certifi`). Un K-Means sur des unités brutes serait dominé presque
entièrement par cette seule variable, quel que soit le poids réel des cinq autres après mise à
l'échelle — `np.log1p` compresse cette étendue avant que `StandardScaler` n'intervienne.

## Le résultat réel (collecte et exécution du 2026-08-25), honnêtement

**k=3 est objectivement le meilleur choix parmi k=2..6** au score de silhouette (0,407 contre
0,351 en k=2, 0,369 en k=4, 0,352 en k=5, 0,386 en k=6) — ce n'est pas qu'un choix de confort
pour comparer à trois catégories pressenties, la géométrie des données le confirme d'elle-même.
L'ACP à 2 composantes retient 76,0 % de la variance (54,1 % + 21,9 %), une projection qui reste
fidèle sans être totale.

Mais **le K-Means ne retrouve qu'imparfaitement les trois catégories pressenties** : Adjusted
Rand Index 0,575, Normalized Mutual Info 0,658 — un accord réel et net (loin de 0, qui serait le
hasard), mais loin de 1 (une correspondance parfaite). La table de contingence explique pourquoi :

```
cluster                0   1  2
categorie_pressentie
declinant              0   9  4
etabli                 0  20  0
montant               17   1  0
```

- **Cluster 0 (17 paquets) est un cluster « montant » quasi pur** : 17 des 18 paquets montants
  (seul `mypy` en manque — son âge et sa cadence, sur PyPI depuis 2009, ressemblent structurellement
  à un outil mûr, malgré une croissance de trafic réelle). Ce cluster se sépare proprement, sans
  ambiguïté.
- **Cluster 1 (33 paquets) mélange les 20 établis avec 9 des 13 déclinants** (`flake8`, `flask`,
  `keras`, `mock`, `pytz`, `setuptools`, `simplejson`, `tensorflow`, `tox`) plus `mypy`. Ces neuf
  paquets déclinants ont un âge, une récence et une cadence de publication qui ressemblent
  encore à ceux d'un projet établi — ils reçoivent encore des releases, ils existent depuis
  longtemps ; seul leur volume de téléchargement recule, une information que ce clustering voit
  bien (elle fait partie des 6 variables) mais qui ne suffit pas à elle seule à les séparer d'un
  établi sur les 5 autres axes.
- **Cluster 2 (4 paquets) isole les paquets réellement obsolètes** : `enum34`, `ipaddress`,
  `nose`, `pathlib2` — des rétroportages ou outils rendus caducs par leur intégration à la
  bibliothèque standard ou leur remplacement (unittest/pytest pour `nose`), reconnaissables à un
  âge ancien conjugué à une récence extrême (plus aucune release depuis des années).

**La lecture honnête** : le clustering distingue nettement « en forte croissance récente » du
reste, mais ne sépare **pas** « établi et stable » de « en déclin mais encore actif » — ces deux
profils se ressemblent sur l'âge/la récence/la cadence, ils ne se distinguent que par la
tendance de téléchargement elle-même (une des 6 variables, pas la seule). Seul le déclin le plus
extrême (plus aucune activité de publication depuis des années) forme un troisième groupe net.
L'hypothèse de départ en trois groupes nets ne survit donc pas telle quelle : la réalité a deux
frontières nettes (montant vs le reste ; obsolète vs le reste) et une frontière floue (établi vs
déclinant modéré), pas trois groupes également séparables.

Voir `resultats_reels()` plus bas pour rejouer ces chiffres — reproductibles à l'identique
(`RANDOM_STATE` fixe), à partir de `data/pypi_features.parquet`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    adjusted_rand_score,
    normalized_mutual_info_score,
    silhouette_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from labs.pypi_features import SORTIE as FEATURES

RACINE = Path(__file__).resolve().parents[2]

RANDOM_STATE = (
    20260825  # date de la collecte réelle, même convention que `echantillon()` ailleurs
)
N_CLUSTERS = 3  # pour la comparaison directe avec les 3 catégories pressenties -- voir choisir_k()

FEATURES_CLUSTERING = (
    "volume_recent",
    "variation_brute_pct",
    "variation_normalisee_pct",
    "age_jours",
    "recence_jours",
    "cadence_releases_an",
)


def matrice_design(df: pd.DataFrame) -> pd.DataFrame:
    """Les six variables du clustering, volume en log (voir la docstring du module)."""
    X = df[list(FEATURES_CLUSTERING)].copy()
    X["volume_recent"] = np.log1p(X["volume_recent"])
    return X


def construire_pretraitement() -> Pipeline:
    """Imputation médiane puis centrage-réduction -- l'imputation ne joue aucun rôle sur la
    collecte réelle (zéro valeur manquante sur les 51 paquets), mais un `cadence_releases_an`
    indéterminé (voir `pypi_features.py`) ne doit jamais faire échouer silencieusement le
    pipeline sur une future extension de l'échantillon."""
    return Pipeline(
        [
            ("imputation", SimpleImputer(strategy="median")),
            ("echelle", StandardScaler()),
        ]
    )


def choisir_k(X_scaled: np.ndarray, k_min: int = 2, k_max: int = 6) -> pd.DataFrame:
    """Score de silhouette et inertie pour k=2..6 -- objective le choix de `N_CLUSTERS` plutôt
    que de le décider à l'œil. Un k qui maximise la silhouette mais diffère de 3 n'est pas
    ignoré : voir la synthèse en tête de module pour ce que donne la collecte réelle."""
    lignes = []
    for k in range(k_min, k_max + 1):
        modele = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(
            X_scaled
        )
        lignes.append(
            {
                "k": k,
                "silhouette": silhouette_score(X_scaled, modele.labels_),
                "inertie": modele.inertia_,
            }
        )
    return pd.DataFrame(lignes)


def analyser(df: pd.DataFrame, n_clusters: int = N_CLUSTERS) -> dict:
    """Prétraite, cluster, projette en 2D par ACP, puis compare a posteriori aux catégories
    pressenties. Renvoie tout ce qu'il faut pour écrire la synthèse ou tracer une figure --
    jamais la catégorie en entrée du K-Means lui-même."""
    pretraitement = construire_pretraitement()
    X_scaled = pretraitement.fit_transform(matrice_design(df))

    grille_k = choisir_k(X_scaled)

    modele = KMeans(n_clusters=n_clusters, n_init=10, random_state=RANDOM_STATE).fit(
        X_scaled
    )
    clusters = modele.labels_

    acp = PCA(n_components=2, random_state=RANDOM_STATE)
    coords = acp.fit_transform(X_scaled)

    categories = df["categorie"].astype(str).to_numpy()
    contingence = pd.crosstab(
        pd.Series(categories, name="categorie_pressentie"),
        pd.Series(clusters, name="cluster"),
    )

    return {
        "grille_k": grille_k,
        "clusters": clusters,
        "contingence": contingence,
        "ari": adjusted_rand_score(categories, clusters),
        "nmi": normalized_mutual_info_score(categories, clusters),
        "coords_acp": coords,
        "variance_expliquee": acp.explained_variance_ratio_,
        "packages": df["package"].to_numpy(),
    }


def resultats_reels() -> None:
    """Rejoue l'analyse sur `data/pypi_features.parquet` et imprime les chiffres exacts -- ce
    que `main()` fait aussi, en plus verbeux. Nommé à part pour qu'un futur article puisse
    l'importer sans dépendre de `sys.argv`."""
    df = pd.read_parquet(FEATURES)
    resultat = analyser(df)

    print("silhouette par k :")
    print(
        resultat["grille_k"].to_string(index=False, float_format=lambda v: f"{v:.3f}")
    )

    print(
        f"\nvariance expliquée par les 2 composantes ACP : {resultat['variance_expliquee']}"
    )
    print(f"  total : {resultat['variance_expliquee'].sum():.1%}")

    print(
        f"\nAdjusted Rand Index (clusters vs catégories pressenties) : {resultat['ari']:.3f}"
    )
    print(
        f"Normalized Mutual Info                                   : {resultat['nmi']:.3f}"
    )

    print("\ntable de contingence (catégorie pressentie x cluster K-Means) :")
    print(resultat["contingence"])


def main() -> int:
    resultats_reels()
    return 0


if __name__ == "__main__":
    sys.exit(main())
