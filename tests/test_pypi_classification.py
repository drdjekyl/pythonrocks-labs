"""Aucune de ces données n'est réelle -- les chiffres réels de la collecte du 2026-08-25 vivent
dans la docstring de `pypi_classification.py`. Ces tests couvrent la mécanique : l'absence de
fuite et la capacité du pipeline à apprendre quand les groupes sont, par construction, faciles à
séparer sur les trois variables autorisées.
"""

import numpy as np
import pandas as pd

from labs.pypi_classification import (
    FEATURES_CLASSIFICATION,
    construire_pipeline,
    evaluer,
)
from labs.pypi_features import COLONNES_FUITE


def test_features_classification_exclut_toute_colonne_de_fuite():
    assert not set(FEATURES_CLASSIFICATION) & set(COLONNES_FUITE)


def test_construire_pipeline_a_les_trois_etapes_attendues():
    pipeline = construire_pipeline()
    assert list(pipeline.named_steps) == ["imputation", "echelle", "modele"]


def _groupe(
    categorie: str, n: int, age: float, recence: float, cadence: float, graine: int
):
    rng = np.random.default_rng(graine)
    return pd.DataFrame(
        {
            "package": [f"{categorie}_{i}" for i in range(n)],
            "categorie": categorie,
            "age_jours": age + rng.normal(0, 20, n),
            "recence_jours": np.clip(recence + rng.normal(0, 5, n), 0, None),
            "cadence_releases_an": np.clip(cadence + rng.normal(0, 0.3, n), 0.01, None),
        }
    )


def _jeu_trois_groupes_separes() -> pd.DataFrame:
    """10 paquets synthétiques par catégorie, séparés sans ambiguïté sur les trois variables
    autorisées -- contrairement au vrai jeu de 51 paquets, où `declinant` se confond avec
    `etabli` (voir la docstring du module). Un échec ici serait un bug du pipeline, pas une
    propriété honnête des données."""
    return pd.concat(
        [
            _groupe("montant", 10, age=500, recence=5, cadence=50, graine=1),
            _groupe("etabli", 10, age=4000, recence=30, cadence=10, graine=2),
            _groupe("declinant", 10, age=4000, recence=2000, cadence=1, graine=3),
        ],
        ignore_index=True,
    )


def test_evaluer_apprend_nettement_mieux_que_le_hasard_sur_des_groupes_separes():
    df = _jeu_trois_groupes_separes()
    resultat = evaluer(df)

    assert resultat["balanced_accuracy"] >= 0.8
    assert resultat["balanced_accuracy"] > resultat["balanced_accuracy_reference"]
    assert resultat["f1_macro"] >= 0.8
    assert set(resultat["etiquettes"]) == {"montant", "etabli", "declinant"}
    assert "modele__C" in resultat["meilleurs_hyperparametres"]
    assert resultat["matrice_confusion"].shape == (3, 3)
