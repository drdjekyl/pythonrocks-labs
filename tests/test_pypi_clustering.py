"""Aucune de ces données n'est réelle -- les chiffres réels de la collecte du 2026-08-25 vivent
dans la docstring de `pypi_clustering.py`. Ces tests vérifient la mécanique : le volume passe
bien en log avant le reste, et le pipeline retrouve des groupes qu'on a délibérément rendus
triviaux à séparer -- un smoke test qui ne prétend rien démontrer sur le vrai jeu de données.
"""

import numpy as np
import pandas as pd
import pytest

from labs.pypi_clustering import (
    FEATURES_CLUSTERING,
    analyser,
    choisir_k,
    construire_pretraitement,
    matrice_design,
)


def test_matrice_design_ne_transforme_que_le_volume():
    df = pd.DataFrame(
        {
            "volume_recent": [0.0, np.e - 1],
            "variation_brute_pct": [10.0, -10.0],
            "variation_normalisee_pct": [5.0, -5.0],
            "age_jours": [100, 200],
            "recence_jours": [1, 2],
            "cadence_releases_an": [3.0, 4.0],
        }
    )
    X = matrice_design(df)
    assert list(X.columns) == list(FEATURES_CLUSTERING)
    assert X["volume_recent"].tolist() == pytest.approx(
        [0.0, 1.0]
    )  # log1p(0)=0, log1p(e-1)=1
    assert X["age_jours"].tolist() == [100, 200]  # inchangé


def _groupe(
    categorie: str, n: int, volume: float, variation: float, age: float, graine: int
):
    rng = np.random.default_rng(graine)
    return pd.DataFrame(
        {
            "package": [f"{categorie}_{i}" for i in range(n)],
            "categorie": categorie,
            "volume_recent": volume + rng.normal(0, volume * 0.01, n),
            "variation_brute_pct": variation + rng.normal(0, 0.5, n),
            "variation_normalisee_pct": variation + rng.normal(0, 0.5, n),
            "age_jours": age + rng.normal(0, 2, n),
            "recence_jours": 10 + rng.normal(0, 1, n),
            "cadence_releases_an": 5 + rng.normal(0, 0.2, n),
        }
    )


def _jeu_trois_groupes_separes() -> pd.DataFrame:
    """Trois groupes délibérément très éloignés sur volume/variation/âge -- pas un jeu réaliste,
    un cas où l'échec du pipeline serait un bug du code, pas une propriété des données."""
    return pd.concat(
        [
            _groupe("a", 6, volume=10.0, variation=-50.0, age=3000, graine=1),
            _groupe("b", 6, volume=100_000.0, variation=0.0, age=500, graine=2),
            _groupe("c", 6, volume=5_000_000.0, variation=80.0, age=100, graine=3),
        ],
        ignore_index=True,
    )


def test_analyser_retrouve_des_groupes_trivialement_separes():
    df = _jeu_trois_groupes_separes()
    resultat = analyser(df, n_clusters=3)

    assert resultat["ari"] >= 0.95
    assert resultat["nmi"] >= 0.95

    contingence = resultat["contingence"]
    # Chaque catégorie doit tomber presque entièrement dans une seule colonne (cluster).
    for _, ligne in contingence.iterrows():
        assert (ligne > 0).sum() == 1

    assert resultat["coords_acp"].shape == (18, 2)
    assert resultat["variance_expliquee"].shape == (2,)


def test_choisir_k_couvre_la_plage_demandee():
    df = _jeu_trois_groupes_separes()
    X_scaled = construire_pretraitement().fit_transform(matrice_design(df))
    grille = choisir_k(X_scaled, k_min=2, k_max=4)
    assert list(grille["k"]) == [2, 3, 4]
    assert (grille["silhouette"] <= 1.0).all()
    assert (grille["inertie"] > 0).all()
