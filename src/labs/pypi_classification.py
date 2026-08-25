"""Prédire établi / montant / déclinant sans jamais montrer au modèle une seule variable de
téléchargement.

`pypi_clustering.py` posait la question non supervisée. Celle-ci est supervisée et différente :
à partir des SEULES variables de cadence, d'âge et de récence — jamais `volume_recent`,
`variation_brute_pct` ni `variation_normalisee_pct`, qui sont *littéralement* ce qui a servi à
poser la catégorie à la main (voir `pypi_features.COLONNES_FUITE`) — peut-on prédire la
catégorie d'un paquet ? Le brancher sur les variables de téléchargement donnerait un classifieur
presque parfait par construction, une fuite triviale plutôt qu'un résultat. `FEATURES_CLASSIFICATION`
exclut ces trois colonnes explicitement, pas par omission.

## Le problème que pose n=51

51 paquets, 3 classes déséquilibrées (20 établis, 18 montants, 13 déclinants — ratio 1,5:1, pas
extrême, mais pas rien sur un aussi petit effectif). Un simple partage train/test tirerait un
jeu de test d'une dizaine de paquets : la variance d'une seule mesure y est énorme (une différence
d'un seul paquet mal classé change la précision de plusieurs points). Ce module utilise donc une
**validation croisée stratifiée à deux niveaux** : une boucle externe (`exterieur`, 5 plis) qui
mesure la performance, une boucle interne (`interieur`, 3 plis, via `GridSearchCV`) qui règle
l'hyperparamètre `C` de la régression logistique — chaque pli externe est évalué par un modèle
dont le réglage n'a jamais vu ses données, ce qu'un simple `GridSearchCV` unique sur tout le jeu
ne garantit pas (il resterait optimiste : le C choisi aurait vu les données mêmes sur lesquelles
on le juge). `cross_val_predict` réalise cette imbrication proprement : chaque prédiction vient
d'un modèle qui n'a jamais vu l'exemple qu'il prédit, ni pour l'entraînement ni pour le réglage.

## Le choix des métriques, pas juste l'exactitude

Sur 3 classes déséquilibrées, l'exactitude brute favorise la classe majoritaire et peut rester
haute même quand la classe minoritaire (`declinant`, 13/51) est mal reconnue. Ce module rapporte
donc `balanced_accuracy` (la moyenne du rappel par classe, insensible au déséquilibre) et le
F1 macro (moyenne non pondérée du F1 par classe) plutôt que l'exactitude seule, toujours
accompagnés d'un `DummyClassifier(strategy="stratified")` comme référence de hasard : un score
qui ne bat pas cette référence ne vaut rien, quel que soit son chiffre affiché isolément.

## Les chiffres réels (collecte et exécution du 2026-08-25)

**Balanced accuracy 0,656, F1 macro 0,657** — contre 0,305 et 0,299 pour le `DummyClassifier` de
référence : nettement mieux que le hasard (à trois classes équilibrées, le hasard vaudrait
0,333 ; le déséquilibre réel du jeu abaisse encore la référence empirique à 0,305). L'écart est
net, mais 0,656 reste loin d'un classifieur fiable — la lecture honnête est « la structure de
publication porte un vrai signal, insuffisant pour trancher seul ».

Meilleur hyperparamètre retenu sur un réglage final (tout le jeu, à titre descriptif) :
`C=0.1` — une régularisation forte, cohérente avec un jeu de 51 exemples pour seulement 3
variables : un modèle peu contraint sur-apprendrait presque immanquablement.

Matrice de confusion (lignes = vraie catégorie, colonnes = prédiction, agrégée sur les 5 plis
externes) :

```
           declinant  etabli  montant
declinant          5       6        2
etabli             4      15        1
montant            0       3       15
```

Rapport par classe : `montant` se prédit le mieux (précision 0,833, rappel 0,833) — un paquet
jeune à cadence soutenue se reconnaît structurellement. `etabli` suit (précision 0,625, rappel
0,750). **`declinant` est la classe la plus dure** (précision 0,556, rappel seulement 0,385) :
6 des 13 paquets déclinants sont prédits `etabli` — exactement la même confusion que révèle le
clustering non supervisé (cluster 1 ci-dessus, `pypi_clustering.py`) : un paquet en déclin garde
souvent l'âge et la cadence d'un projet mûr, seul son volume de téléchargement — délibérément
exclu des variables d'entrée ici — trahit le déclin. **Les deux méthodes convergent sur la même
limite structurelle**, ce qui renforce la confiance dans le résultat plutôt que de l'affaiblir :
ce n'est pas un artefact d'un seul modèle.

Voir `evaluer()` et `main()` pour rejouer ces chiffres — reproductibles à l'identique
(`RANDOM_STATE` fixe), à partir de `data/pypi_features.parquet`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from labs.pypi_features import COLONNES_FUITE
from labs.pypi_features import SORTIE as FEATURES

RACINE = Path(__file__).resolve().parents[2]

RANDOM_STATE = (
    20260825  # même graine que pypi_clustering.py, pour un pipeline reproductible
)

FEATURES_CLASSIFICATION = ("age_jours", "recence_jours", "cadence_releases_an")
assert not set(FEATURES_CLASSIFICATION) & set(COLONNES_FUITE), (
    "une variable de téléchargement s'est glissée dans les entrées du classifieur"
)

GRILLE_HYPERPARAMETRES = {"modele__C": [0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30, 100]}


def construire_pipeline() -> Pipeline:
    """Imputation médiane (défensive -- voir `pypi_features.py` sur `cadence_releases_an`),
    centrage-réduction, puis régression logistique multinomiale pondérée par l'effectif de
    chaque classe (`class_weight="balanced"`), pour ne pas laisser la classe majoritaire
    (`etabli`, 20/51) dominer l'optimisation."""
    return Pipeline(
        [
            ("imputation", SimpleImputer(strategy="median")),
            ("echelle", StandardScaler()),
            (
                "modele",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def evaluer(df: pd.DataFrame) -> dict:
    """Validation croisée imbriquée (5 plis externes, 3 plis internes pour `GridSearchCV`) et
    comparaison à un `DummyClassifier` de référence. Renvoie tout ce qu'il faut pour la
    synthèse : rapport par classe, matrice de confusion, métriques agrégées côté modèle et
    côté référence, et les hyperparamètres retenus par un réglage final sur l'ensemble du jeu
    (rapportés à titre descriptif -- ils ne sont pas ceux évalués par la boucle externe, dont le
    C optimal peut différer légèrement d'un pli à l'autre)."""
    X = df[list(FEATURES_CLASSIFICATION)]
    y = df["categorie"].astype(str).to_numpy()
    etiquettes = sorted(set(y))

    exterieur = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    interieur = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE)

    recherche = GridSearchCV(
        construire_pipeline(), GRILLE_HYPERPARAMETRES, cv=interieur, scoring="f1_macro"
    )
    y_predit = cross_val_predict(recherche, X, y, cv=exterieur)

    reference = DummyClassifier(strategy="stratified", random_state=RANDOM_STATE)
    y_predit_reference = cross_val_predict(reference, X, y, cv=exterieur)

    recherche_finale = GridSearchCV(
        construire_pipeline(), GRILLE_HYPERPARAMETRES, cv=interieur, scoring="f1_macro"
    )
    recherche_finale.fit(X, y)

    return {
        "etiquettes": etiquettes,
        "y_vrai": y,
        "y_predit": y_predit,
        "rapport": classification_report(
            y, y_predit, labels=etiquettes, output_dict=True, zero_division=0
        ),
        "matrice_confusion": confusion_matrix(y, y_predit, labels=etiquettes),
        "balanced_accuracy": balanced_accuracy_score(y, y_predit),
        "balanced_accuracy_reference": balanced_accuracy_score(y, y_predit_reference),
        "f1_macro": f1_score(y, y_predit, average="macro", zero_division=0),
        "f1_macro_reference": f1_score(
            y, y_predit_reference, average="macro", zero_division=0
        ),
        "meilleurs_hyperparametres": recherche_finale.best_params_,
    }


def main() -> int:
    df = pd.read_parquet(FEATURES)
    resultat = evaluer(df)

    print(f"variables d'entrée : {FEATURES_CLASSIFICATION}\n")
    print(
        f"balanced accuracy : {resultat['balanced_accuracy']:.3f}  "
        f"(référence hasard : {resultat['balanced_accuracy_reference']:.3f})"
    )
    print(
        f"F1 macro          : {resultat['f1_macro']:.3f}  "
        f"(référence hasard : {resultat['f1_macro_reference']:.3f})"
    )
    print(
        f"meilleur C (réglage final, tout le jeu) : {resultat['meilleurs_hyperparametres']}"
    )

    print("\nmatrice de confusion (lignes = vrai, colonnes = prédit) :")
    print(
        pd.DataFrame(
            resultat["matrice_confusion"],
            index=resultat["etiquettes"],
            columns=resultat["etiquettes"],
        )
    )

    print("\nrapport par classe :")
    rapport = pd.DataFrame(resultat["rapport"]).T
    print(rapport.to_string(float_format=lambda v: f"{v:.3f}"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
