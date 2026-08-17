"""Le plancher réglementaire : ce que MARPOL impose, pas ce que l'équipage fait.

Cette couche répond à une seule question par navire : quelles obligations environnementales
*certifiées* la réglementation lui impose-t-elle ? Les seuils viennent de MARPOL et des
conventions associées, tels que relevés dans le mémoire de M2 de l'auteur (chapitre 4).

**Obligation n'est pas comportement.** Un yacht sans certificat ISPP peut très bien disposer
d'un traitement des eaux usées à bord et vidanger à quai — la réglementation ne l'y oblige pas
en dessous du seuil, ce qui ne dit rien de ce qu'il fait réellement. Ce module calcule ce que
la loi *exige sur le papier*, jamais ce qui se passe en mer. Lire une sortie d'ici comme une
mesure de pollution réelle est un contresens. C'est pour rendre ce contresens difficile que les
fonctions et les champs ci-dessous parlent d'« obligations » et de « certificats », jamais de
« pollution » ou de « conformité ».

C'est aussi, précisément parce qu'elle ne fait qu'appliquer des seuils à des champs sans
estimer ni modéliser quoi que ce soit, la couche la plus solide de l'édifice : un résultat faux
ici serait une erreur d'arithmétique ou de seuil, jamais une approximation.

## Deux angles morts à ne pas dissimuler

1. **Le voyage international.** Plusieurs de ces obligations (IOPP, ISPP, IAPP, IEE, les deux
   certificats antifouling, le registre des ordures, l'ISM) ne s'appliquent, au sens strict de
   MARPOL/SOLAS, qu'aux navires engagés dans des voyages internationaux — une information que
   `cleaned_yachts` ne porte pas. Plutôt que de la deviner, `obligations_navire` l'expose comme
   un paramètre explicite, `voyage_international`, par défaut à `True` : ce catalogue est un
   inventaire de courtage/charter de superyachts, une population qui opère quasi systématique-
   ment au-delà des eaux nationales. C'est une hypothèse de modélisation assumée, pas une
   mesure — documentée ici plutôt que cachée dans une valeur par défaut muette. Le mettre à
   `False` ne fait pas basculer les obligations à `False` (ce serait deviner l'inverse) : la
   fonction renvoie alors un jeu d'obligations entièrement indéterminées (`None` partout), et
   le fait via le champ `voyage_international_suppose` du résultat, pour que l'hypothèse reste
   traçable sur chaque valeur produite, pas seulement dans la signature de l'appel.
2. **Le rejet d'hydrocarbures en exploitation.** MARPOL Annexe I limite le rejet des navires de
   400 GT et plus à 15 ppm, et seulement « en route ». C'est une condition d'exploitation en
   continu, pas un document qu'on détient une fois pour toutes — elle n'a donc pas sa place
   dans la table des obligations ci-dessous, et ce module ne la modélise pas comme telle.

## Données manquantes : jamais une supposition silencieuse

`gross_tonnage` (≈ 2 % du catalogue) et `number_of_guests` (≈ 10 %) sont parfois absents.
Une comparaison numérique naïve (`None > 15`) lèverait, et une comparaison pandas naïve sur une
colonne `float64` (`NaN > 15`) renvoie silencieusement `False` — soit exactement la supposition
qu'on refuse de faire ici. Le module utilise donc le dtype nullable `"boolean"` de pandas, dont
les opérateurs `&` / `|` / `~` implémentent nativement la logique à trois valeurs de Kleene :
une comparaison sur une valeur manquante produit une troisième valeur, l'indétermination
(`pd.NA` en interne, `None` dans `Obligations`), qui se propage — sauf quand l'autre branche
d'un `OU` suffit déjà à trancher (ex. : tonnage inconnu mais plus de 15 invités connus -> ISPP
s'applique quand même, l'inconnue sur le tonnage devient sans objet).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
CATALOGUE = RACINE / "data" / "yachts.parquet"

# --- Seuils, tels que relevés dans le mémoire (chapitre 4) --------------------------------

# IOPP, IAPP, IEE, AFS_CERTIFICATE — et une des deux branches de ISPP / GARBAGE_RECORD_BOOK
SEUIL_GT_CERTIFICATS = 400.0
SEUIL_GT_GARBAGE_MGMT_PLAN = 100.0
SEUIL_GT_ISM = 500.0
SEUIL_INVITES = 15  # strict : *plus de* 15, pas 15 compris
SEUIL_LONGUEUR_AFS_DECLARATION = 24.0  # strict : *plus de* 24 m, et *sous* 400 GT
SEUIL_LONGUEUR_MOUILLAGE_POSIDONIES = 24.0  # large : 24 m *ou plus*

OBLIGATIONS = (
    "IOPP",
    "ISPP",
    "IAPP",
    "IEE",
    "AFS_CERTIFICATE",
    "AFS_DECLARATION",
    "GARBAGE_MGMT_PLAN",
    "GARBAGE_RECORD_BOOK",
    "ISM",
)


@dataclass(frozen=True, slots=True)
class Obligations:
    """Le jeu des neuf obligations pour un navire, à trois valeurs chacune.

    `True` : le seuil est franchi, l'obligation s'applique. `False` : il ne l'est pas.
    `None` : indéterminé — une donnée nécessaire manque et aucune autre branche ne suffisait à
    trancher. `None` n'est ni un `True` ni un `False` optimiste : c'est un refus de deviner,
    à traiter comme tel par tout code qui consomme ce résultat.

    Encore une fois : ces champs décrivent une exigence documentaire, pas un état de fait sur
    l'eau. `IOPP=False` ne certifie pas que le navire pollue ; `IOPP=True` ne certifie pas
    qu'il détient réellement le certificat, seulement que la réglementation le lui impose.
    """

    IOPP: bool | None
    ISPP: bool | None
    IAPP: bool | None
    IEE: bool | None
    AFS_CERTIFICATE: bool | None
    AFS_DECLARATION: bool | None
    GARBAGE_MGMT_PLAN: bool | None
    GARBAGE_RECORD_BOOK: bool | None
    ISM: bool | None
    voyage_international_suppose: bool


def _scalaire(valeur: object) -> bool | None:
    """Convertit un booléen nullable pandas (`pd.NA` inclus) en `True` / `False` / `None`."""
    return None if pd.isna(valeur) else bool(valeur)


def _table(gt: pd.Series, longueur: pd.Series, invites: pd.Series) -> pd.DataFrame:
    """Le moteur : neuf colonnes à trois valeurs, seuils appliqués une seule fois.

    Vectorisé plutôt qu'écrit deux fois (une version scalaire, une version par lot) : la même
    logique sert `obligations_navire`, appelée sur une série d'un seul navire, et
    `repartir_obligations`, appelée sur le catalogue entier. Un seul endroit où les seuils sont
    écrits, un seul endroit où ils pourraient être faux.
    """
    gt = gt.astype("Float64")
    longueur = longueur.astype("Float64")
    invites = invites.astype("Float64")

    gt_certificats = gt >= SEUIL_GT_CERTIFICATS
    gt_garbage_plan = gt >= SEUIL_GT_GARBAGE_MGMT_PLAN
    gt_ism = gt >= SEUIL_GT_ISM
    invites_seuil = invites > SEUIL_INVITES
    longueur_seuil = longueur > SEUIL_LONGUEUR_AFS_DECLARATION

    return pd.DataFrame(
        {
            "IOPP": gt_certificats,
            "ISPP": gt_certificats | invites_seuil,
            "IAPP": gt_certificats,
            "IEE": gt_certificats,
            "AFS_CERTIFICATE": gt_certificats,
            "AFS_DECLARATION": longueur_seuil & ~gt_certificats,
            "GARBAGE_MGMT_PLAN": gt_garbage_plan | invites_seuil,
            "GARBAGE_RECORD_BOOK": gt_certificats | invites_seuil,
            "ISM": gt_ism,
        }
    )


def obligations_navire(
    gross_tonnage: float | None,
    overall_length: float | None,
    number_of_guests: float | None,
    year: float | None = None,
    *,
    voyage_international: bool = True,
) -> Obligations:
    """Les neuf obligations applicables à un navire, seuil par seuil.

    `year` est accepté pour décrire le navire au complet, comme demandé, mais n'intervient
    dans aucun seuil de la table du chapitre 4 : ce module n'invente pas de règle liée à
    l'année qui ne soit pas sourcée (certains textes MARPOL font dépendre des exigences de la
    date de pose de quille, mais ce n'est pas dans la table reçue — l'ajouter serait deviner).

    `voyage_international` : voir la docstring du module. Par défaut `True` (hypothèse
    documentée, pas une mesure) ; à `False`, toutes les obligations reviennent `None`
    plutôt que de deviner un comportement pour une flotte domestique non modélisée ici.
    """
    if not voyage_international:
        return Obligations(
            *([None] * len(OBLIGATIONS)), voyage_international_suppose=False
        )

    ligne = _table(
        pd.Series([gross_tonnage], dtype="Float64"),
        pd.Series([overall_length], dtype="Float64"),
        pd.Series([number_of_guests], dtype="Float64"),
    ).iloc[0]

    return Obligations(
        **{nom: _scalaire(ligne[nom]) for nom in OBLIGATIONS},
        voyage_international_suppose=True,
    )


def obligations_applicables(obligations: Obligations) -> frozenset[str]:
    """Le sous-ensemble des neuf noms dont l'obligation est confirmée (`True`)."""
    return frozenset(nom for nom in OBLIGATIONS if getattr(obligations, nom) is True)


def obligations_indeterminees(obligations: Obligations) -> frozenset[str]:
    """Le sous-ensemble des noms qu'on ne peut pas trancher, faute de donnée."""
    return frozenset(nom for nom in OBLIGATIONS if getattr(obligations, nom) is None)


def interdiction_mouillage_posidonies(overall_length: float | None) -> bool | None:
    """Arrêté mouillage Méditerranée : interdiction de mouiller sur herbier de posidonie.

    Arrêté cadre 123/2019 du préfet maritime de la Méditerranée, applicable aux navires de
    24 m et plus. Sur ce catalogue, `overall_length` ne descend jamais sous 26 m : l'indicateur
    vaut donc `True` pour l'intégralité des 9 407 navires. Ce n'est pas une erreur de calcul —
    c'est un résultat, tenant à la composition du catalogue (du courtage de superyachts, pas de
    petite plaisance), documenté ici plutôt que masqué en omettant la fonction.
    """
    if pd.isna(overall_length):
        return None
    return bool(overall_length >= SEUIL_LONGUEUR_MOUILLAGE_POSIDONIES)


def repartir_obligations(df: pd.DataFrame) -> pd.DataFrame:
    """La répartition des neuf obligations sur un catalogue de navires.

    Une ligne par obligation, trois colonnes de décompte (`applicable`, `non_applicable`,
    `indetermine`) et leurs pourcentages sur l'effectif total du `df` passé — dénominateur
    unique et constant, pour que les trois pourcentages d'une ligne totalisent 100 %.

    Voyage international supposé (voir le module) : cette fonction n'a pas de paramètre pour
    le désactiver, parce qu'un `repartir_obligations` sur une flotte majoritairement
    domestique n'aurait aucun sens avec les seuils de ce module — elle est écrite pour le
    catalogue de courtage/charter qu'est `cleaned_yachts`.
    """
    n = len(df)
    table = _table(df["gross_tonnage"], df["overall_length"], df["number_of_guests"])

    lignes = []
    for nom in OBLIGATIONS:
        colonne = table[nom]
        applicable = int(colonne.sum())  # `.sum()` ignore les `pd.NA`
        indetermine = int(colonne.isna().sum())
        non_applicable = n - applicable - indetermine
        lignes.append(
            {
                "obligation": nom,
                "applicable": applicable,
                "applicable_pct": applicable / n * 100,
                "non_applicable": non_applicable,
                "non_applicable_pct": non_applicable / n * 100,
                "indetermine": indetermine,
                "indetermine_pct": indetermine / n * 100,
            }
        )

    return pd.DataFrame(lignes).set_index("obligation")


def main() -> int:
    df = pd.read_parquet(CATALOGUE)
    repartition = repartir_obligations(df)

    print(f"{len(df)} navires — répartition des obligations réglementaires\n")
    for nom, ligne in repartition.iterrows():
        print(
            f"  {nom:22} applicable {ligne.applicable_pct:5.1f} %  "
            f"({int(ligne.applicable):>5}/{len(df)}) — "
            f"indéterminé {ligne.indetermine_pct:4.1f} %"
        )

    echappe = repartition.loc["ISPP"]
    n_echappe = int(echappe.non_applicable)
    print(
        f"\n  navires échappant à tout le bloc certifié (< {SEUIL_GT_CERTIFICATS:.0f} GT et "
        f"≤ {SEUIL_INVITES} invités, sans ambiguïté) : {n_echappe} "
        f"({n_echappe / len(df) * 100:.1f} %)"
    )

    mouillage = df["overall_length"].apply(interdiction_mouillage_posidonies)
    n_concernes = int(mouillage.fillna(False).sum())
    print(
        f"  interdiction de mouillage posidonies (arrêté 123/2019) : "
        f"{n_concernes}/{len(df)} navires concernés"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
