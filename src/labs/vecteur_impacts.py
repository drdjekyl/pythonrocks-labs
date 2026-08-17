"""Le vecteur d'impacts environnementaux, flux par flux, par invité-nuit et par GT-heure.

Ce module corrige deux défauts démontrés de l'état de l'art (SEA Index, YETI/ISO TS 23099) :
ils ne couvrent que l'air (CO2e, NOx, PM) et ignorent les rejets marins, et ils normalisent
par le tonnage brut — ce qui récompense mécaniquement le fait de construire plus de volume à
service constant. **Le livrable ici est le vecteur, flux par flux, jamais un score unique.**
L'agrégation en un scalaire exige des facteurs de caractérisation ACV publiés et une analyse
de sensibilité : c'est une tâche distincte, hors périmètre.

**Ce que ce module calcule N'EST PAS un « score environnemental ».** C'est un proxy
d'intensité de conception, dérivé de régressions statistiques et d'un profil d'exploitation
unique appliqué à toute la flotte — jamais une mesure de pollution réelle ni une attestation
réglementaire. Un modèle produit un estimateur, un référentiel produit une attestation : ne
jamais confondre les deux dans le nom d'une variable, une docstring, ou une sortie.

**Aucune sortie nominative.** Les fonctions qui exposent un résultat par navire portent un
nom qui le dit explicitement et leur docstring interdit la publication telle quelle (voir
`_flux_usage_interne_jamais_publier`). Les sorties publiques se font par cohortes (classe de
GT x décennie x type de coque), jamais par navire nommé.

## Le profil d'exploitation (ISO/TS 23099, approuvée le 3 février 2026)

10 % en navigation, 34 % au mouillage, 56 % au port. **Profil unique pour toute la flotte**
— une limite connue de la norme, reprise telle quelle ici, pas corrigée : un yacht de charter
méditerranéen et un yacht qui ne quitte jamais son port d'attache reçoivent le même profil
temporel, faute de mieux. `PROFIL_TEMPOREL` ci-dessous.

## La charge hôtelière : seulement 3 groupes sur 11, et c'est un choix assumé

Les régressions de van Eesteren Barros (TU Delft, 2022, mémoire de M2 — le travail de fond de
YETI) donnent la puissance installée de 11 groupes EEDI (A à M) + stabilisateurs, mais 7 de
ces 11 groupes (C, D, E, F, G, H, I) dépendent de la « interior space » (surface intérieure
guests + crew) ou de la longueur de flottaison (L, M) — deux grandeurs absentes du catalogue.
Seuls les groupes **A** (coque, pont, navigation, sécurité), **B** hors stabilisateurs
(propulsion, auxiliaires de service) et les **stabilisateurs** se dérivent du seul tonnage
brut (GT), avec un excellent ajustement (r = 0,98 / 0,91 / 0,98 respectivement) :

    P_A    = 0,1004 * GT + 11,04                              (r = 0,98, éq. 3.19)
    P_B    = 5,063e-5 * GT^2 + 0,1123 * GT - 20,53             (éq. 3.20, r = 0,91)
    P_STAB = 0,02532 * GT + 16,5                               (r = 0,98)

**Conséquence assumée et documentée : la « charge hôtelière » calculée ici est une
SOUS-ESTIMATION substantielle de la consommation hôtelière réelle.** Le groupe F (HVAC) est,
d'après le mémoire lui-même, l'un des postes de consommation les plus lourds d'un yacht — il
n'est pas dans ce calcul. Ni l'éclairage (I), ni les prises/agréments (H), ni les besoins
d'eau chaude/douce liés aux cabines (C, D, E). Le CO2 et le SOx produits ici couvrent donc
structurellement (coque/pont/sécurité + propulsion/auxiliaires + stabilisation), pas la
totalité de la demande électrique embarquée — une liste courte et sourcée plutôt qu'une
liste complète et bricolée, comme demandé.

Domaine de validité déclaré par le mémoire : yachts de 30 à 180 m. 34,9 % du catalogue est
sous 30 m (`overall_length` va de 26 à 180,61 m) : ces navires sont marqués
`hors_domaine_hebergement=True`, jamais exclus ni recalculés — voir `hors_domaine_hebergement`.

Les trois modes YETI (anchor / harbor / sailing) correspondent terme à terme aux trois modes
ISO/TS 23099 (mouillage / port / navigation) : même trichotomie opérationnelle, deux
vocabulaires. C'est une équivalence assumée, pas mesurée, documentée ici plutôt que cachée
dans un dictionnaire silencieux.

## Propulsion : la loi du cube, pas une charge inventée

`main_eng_power` (kW, déjà en kW pour la totalité du catalogue — aucune conversion d'unité,
voir `registres_classe`/le README) est une valeur **par moteur** (le nom du champ est au
singulier, et un champ `main_eng_count` distinct existe) : la puissance installée de
propulsion est `main_eng_power * main_eng_count`. C'est une lecture du schéma, pas une mesure
— documentée comme telle.

Pour estimer la charge réellement tirée en navigation (nécessaire à la correction SFOC), ce
module utilise la **loi du cube** (loi de l'Amirauté / *propeller law*) :

    charge = (cruise_speed / max_speed)^3, plafonnée à 1,0

Ce n'est pas un facteur inventé : c'est la méthode standard des inventaires d'émissions
portuaires (ENTEC, reprise et endorsée par l'USEPA — cf. USEPA, *Current Methodologies in
Preparing Mobile Source Port-Related Emission Inventories*, 2009 ; ENTEC, *Ship Emissions
Inventory Update*, 2002) en l'absence de mesure directe de charge moteur, et c'est déjà la
relation utilisée par `figures_eda.py` dans ce même dépôt (`k = main_eng_power / max_speed**3`)
pour ajuster la même relation vitesse-puissance sur ce catalogue. Elle a ses limites connues
(un yacht à coque planante a un « hump » de résistance que le cube pur ne capture pas) — non
corrigées ici, documentées comme telle. Sur les 7 708 navires où `cruise_speed` et
`max_speed` sont tous deux connus, 10 ont `cruise_speed > max_speed` (erreur de saisie
manifeste) : ces 10 sont traités comme indéterminés, jamais silencieusement pincés à 1,0.

## SFC : paramètre injectable, repli sourcé Third IMO GHG Study 2014, Table 49

Le référentiel de consommation spécifique sourcé vit sur une branche non mergée d'un autre
dépôt — non consommé ici, comme demandé. La SFC de base est un **paramètre injectable**
(`ParametresModele.sfc_base_g_par_kwh`), avec pour valeur par défaut le repli de la Third IMO
GHG Study 2014, Table 49 (SFOC par âge et type de moteur — HSD, moteur rapide, quasi
exclusif sur ce catalogue) : avant 1983 -> 225 g/kWh, 1984-2000 -> 205, après 2001 -> 195
(`sfc_repli_imo2014`). La correction de charge du même document,
`SFOC(charge) = SFOC_base * (0,455*charge^2 - 0,71*charge + 1,287)`, s'applique toujours
(`correction_charge_sfc`) — elle n'est pas substituable, elle vient du même document que le
repli par défaut.

## Facteur carbone

`C_F = 3,206` t CO2 / t de carburant pour le gazole marin (MDO/MGO — le carburant quasi
universel des yachts privés, contrairement aux HFO des porte-conteneurs), résolution OMI
MEPC.364(79) § 2.2.1.

## Les flux implémentés, et leur source

- **CO2** (`flux_co2_g_par_jour`) : puissance x facteur de charge par mode x SFC x C_F.
  Propulsion en navigation seulement ; hôtellerie (groupes A, B, stabilisateurs) sur les
  trois modes. Le flux le plus solide de ce module.
- **SOx** (`flux_sox_g_par_jour`) : dérivé du même carburant brûlé que le CO2. Teneur en
  soufre prise au **plafond réglementaire mondial** (0,50 % m/m, en vigueur depuis le
  1er janvier 2020 — Directive (UE) 2016/802, art. 6 § 1 b), qui transpose MARPOL Annexe VI
  règle 14 ; https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016L0802,
  consulté le 2026-08-17), pas une mesure de carburant réellement embarqué — exactement le
  même principe que le « plancher réglementaire » de `reglementaire.py` : ce que la
  réglementation autorise au maximum, pas ce qui se passe en mer. Conversion massique
  S -> SO2 par stœchiométrie (masses atomiques standard IUPAC : S = 32,06 ; O = 16,00 ;
  SO2 = 64,06 ; ratio = 64,06 / 32,06 ≈ 1,998), pas un facteur métier — de la chimie de base,
  vérifiable indépendamment de toute institution.
- **Eaux noires** (`flux_eaux_noires_l_par_jour`) et **eaux grises**
  (`flux_eaux_grises_l_par_jour`) : taux par personne et par jour, source primaire retrouvée
  (le mémoire cite « Oceana 2008 » sans préciser l'unité de temps — remontée jusqu'à la
  source primaire comme demandé). La source réelle est le rapport EPA842-R-07-005,
  *Cruise Ship Discharge Assessment Report*, US EPA, 29 décembre 2008 (souvent relayé par
  Oceana) :
  https://19january2017snapshot.epa.gov/sites/production/files/2015-11/documents/cruise_ship_discharge_assessment_report.pdf
  — § 2.1, p. 2-1 : « Average reported sewage generation rates were [...] 8.4 gallons/day/
  person » (eaux noires) ; § 3.1, p. 3-2 : « Average graywater generation rates were [...]
  67 gallons/day/person » (eaux grises). Les deux sont des moyennes déclarées lors de
  l'enquête EPA 2004 sur 29 navires de croisière en Alaska — pas mesurées sur ce catalogue de
  yachts privés, une extrapolation de population documentée comme telle (des paquebots de
  croisière vers des yachts privés, faute d'étude équivalente sur les yachts).
- **Déchets** (`flux_dechets_kg_par_jour`) : même rapport EPA842-R-07-005, § 5.1, p. 5-3,
  citant CELB (2003) : « each cruise ship passenger generates **at least** two pounds of
  non-hazardous solid waste per day » — un **plancher**, pas une moyenne, conservé comme tel
  (le taux réel est vraisemblablement supérieur, jamais inférieur).
- **NOx** (`tier_nox_construction`, `repartition_tier_nox`) : **implémenté partiellement**.
  Le Tier OMI (I/II/III) est déduit de `year` via les dates de construction de MARPOL Annexe
  VI règle 13 (source imo.org, « Nitrogen Oxides (NOx) – Regulation 13 »,
  https://www.imo.org/en/OurWork/Environment/Pages/Nitrogen-oxides-(NOx)-%E2%80%93-Regulation-13.aspx,
  consulté le 2026-08-17, imo.org répondant cette fois — pas DieselNet). Mais **aucune masse
  de NOx n'est calculée** : la limite en g/kWh dépend du régime nominal du moteur (n, tr/min
  — courbe à trois segments selon n < 130 / 130 <= n < 2000 / n >= 2000, valeurs dans
  `LIMITES_NOX_TIER`), un champ **totalement absent** du catalogue (pas dans la liste des
  taux de remplissage fournie, et absent du schéma vérifié). Assumer un régime (ex. « HSD
  -> n >= 2000 ») aurait été exactement le type de supposition interdite ici : le Tier est
  exposé comme diagnostic à part (`repartition_tier_nox`), jamais fondu dans le vecteur de
  flux numériques.

## Flux écartés de v1, et pourquoi

- **PM** : MARPOL Annexe VI règle 14 (imo.org, même page que ci-dessus, section SOx/PM)
  confirme explicitement l'absence de limite numérique PM — le PM y est traité comme un
  co-bénéfice du plafond soufre, pas comme un flux à seuil propre. Des facteurs d'émission
  PM empiriques existent (Third IMO GHG Study 2014, Table 44 ; Fourth IMO GHG Study 2020,
  Table 53, référencés par plusieurs sources secondaires), mais je n'ai pas pu accéder à ces
  tables primaires ni vérifier leurs valeurs exactes dans le temps imparti à cette tâche —
  publier un chiffre retrouvé uniquement via un résumé tiers aurait été exactement le
  contournement que la consigne interdit (le précédent DieselNet sur le NOx). Écarté de v1,
  documenté plutôt que bricolé.
- **Antifouling** : demanderait une surface mouillée (non dérivable proprement du seul GT/
  longueur sans inventer un coefficient de forme de coque) et un taux de lessivage
  (leaching rate) par type de revêtement — ni l'un ni l'autre sourcé dans le temps imparti.
  Écarté.
- **Ancrage** : un risque, pas un flux continu — le mémoire lui-même le traite à part. Tous
  les navires du catalogue font >= 24 m (`overall_length` min = 26 m) donc relèvent de
  l'arrêté mouillage Méditerranée, déjà couvert par
  `labs.reglementaire.interdiction_mouillage_posidonies` : pas dupliqué ici.

## Données manquantes : jamais une supposition silencieuse

Comme dans `reglementaire.py`, tout est vectorisé en dtypes nullables pandas (`"Float64"`,
`"boolean"`) dont les opérateurs arithmétiques et `&`/`|`/`~` propagent nativement `pd.NA` —
un flux dont une entrée manque devient indéterminé, jamais un zéro ou une moyenne silencieuse.
`number_of_guests` manque sur ~10 % du catalogue : aucun flux n'invente « zéro invité » par
défaut. Les eaux/déchets exigent **à la fois** `number_of_guests` et `number_of_crew` (pas de
repli sur l'un ou l'autre seul) — voir `personnes_a_bord`.

Piège pandas rencontré et évité partout dans ce module : `Series.mask(cond, valeur)` avec un
`cond` `"boolean"` contenant `pd.NA` traite l'entrée `NA` comme vraie (elle assigne `valeur`
là où on veut `NA` !) — comportement inverse de `Series.where(cond)`, qui lui traite
correctement `NA` comme « pas vrai ». Toute affectation catégorielle ici utilise donc
`.mask(cond.fillna(False), valeur)` explicitement ; tout masquage à `NA` utilise `.where(cond)`
nu (sans argument `other`), jamais l'inverse.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from labs.reglementaire import SEUIL_GT_CERTIFICATS, SEUIL_GT_GARBAGE_MGMT_PLAN

RACINE = Path(__file__).resolve().parents[2]
CATALOGUE = RACINE / "data" / "yachts.parquet"

# --- Profil d'exploitation (ISO/TS 23099, approuvée le 2026-02-03) -------------------------

MODES = ("navigation", "mouillage", "port")
PROFIL_TEMPOREL = {"navigation": 0.10, "mouillage": 0.34, "port": 0.56}  # somme = 1,0
HEURES_PAR_JOUR = 24.0

# --- Domaine de validité déclaré des régressions hôtelières (van Eesteren Barros, 2022) ----

DOMAINE_LONGUEUR_MIN_M = 30.0
DOMAINE_LONGUEUR_MAX_M = 180.0

# --- Charge hôtelière : groupes A, B (hors stabilisateurs), stabilisateurs -----------------
# Van Eesteren Barros, F. (2022). Mémoire de M2, TU Delft — chapitre 3 (méthodologie YETI).
# Coefficients relevés directement des équations numérotées (3.19), (3.20), et de la valeur
# citée dans la tâche pour les stabilisateurs (r = 0,98 pour les trois).

GROUPES_HOTEL_RETENUS = ("A", "B", "stabilisateurs")


def puissance_groupe_a(gt: pd.Series) -> pd.Series:
    """Coque, pont, navigation, sécurité (éq. 3.19, r = 0,98)."""
    gt = gt.astype("Float64")
    return 0.1004 * gt + 11.04


def puissance_groupe_b(gt: pd.Series) -> pd.Series:
    """Propulsion, auxiliaires de service, hors stabilisateurs (éq. 3.20, r = 0,91)."""
    gt = gt.astype("Float64")
    return 5.063e-5 * gt**2 + 0.1123 * gt - 20.53


def puissance_stabilisateurs(gt: pd.Series) -> pd.Series:
    """Stabilisateurs (r = 0,98 avec le GT — la plus forte corrélation du mémoire)."""
    gt = gt.astype("Float64")
    return 0.02532 * gt + 16.5


def puissance_hotel_installee(gt: pd.Series) -> pd.Series:
    """Puissance installée totale des 3 groupes retenus (kW) — PAS la puissance hôtelière
    totale du navire : HVAC, éclairage, agréments en sont exclus, voir la docstring du
    module."""
    return (
        puissance_groupe_a(gt) + puissance_groupe_b(gt) + puissance_stabilisateurs(gt)
    )


# Ratios d'usage par mode (part de la puissance installée réellement tirée), table 3.6
# (groupes A, B) et table 3.8 (stabilisateurs) du mémoire. Les modes YETI anchor/harbor/
# sailing correspondent terme à terme à mouillage/port/navigation — voir la docstring.
RATIOS_USAGE = {
    "A": {"navigation": 0.08, "mouillage": 0.15, "port": 0.06},
    "B": {"navigation": 0.17, "mouillage": 0.09, "port": 0.03},
    "stabilisateurs": {"navigation": 0.51, "mouillage": 0.50, "port": 0.25},
}


def puissance_hotel_utilisee(gt: pd.Series, mode: str) -> pd.Series:
    """Puissance hôtelière réellement tirée (kW) dans `mode`."""
    r = RATIOS_USAGE
    return (
        puissance_groupe_a(gt) * r["A"][mode]
        + puissance_groupe_b(gt) * r["B"][mode]
        + puissance_stabilisateurs(gt) * r["stabilisateurs"][mode]
    )


def charge_hotel(gt: pd.Series, mode: str) -> pd.Series:
    """Fraction de la puissance hôtelière installée réellement tirée dans `mode` — le
    « charge » utilisé pour la correction SFOC de la génération électrique servant
    l'hôtellerie."""
    installee = puissance_hotel_installee(gt)
    return (puissance_hotel_utilisee(gt, mode) / installee).clip(upper=1.0)


def hors_domaine_hebergement(overall_length: pd.Series) -> pd.Series:
    """`True` si `overall_length` sort du domaine de validité déclaré (30-180 m) des
    régressions hôtelières — ces navires ne sont PAS exclus du calcul, seulement marqués
    comme extrapolés hors domaine. `None`/`pd.NA` si `overall_length` est inconnue."""
    longueur = overall_length.astype("Float64")
    dans_domaine = (longueur >= DOMAINE_LONGUEUR_MIN_M) & (
        longueur <= DOMAINE_LONGUEUR_MAX_M
    )
    return ~dans_domaine


# --- Propulsion : loi du cube (voir la docstring du module) --------------------------------


def facteur_charge_propulsion(
    cruise_speed: pd.Series, max_speed: pd.Series
) -> pd.Series:
    """`(cruise_speed / max_speed)^3`, plafonné à 1,0 — la charge moteur estimée en
    navigation. `NA` si l'une des deux vitesses manque, si `max_speed <= 0`, ou si
    `cruise_speed > max_speed` (10 cas réels sur le catalogue, une erreur de saisie
    manifeste plutôt qu'un signal physique — jamais pincée silencieusement à 1,0)."""
    cruise = cruise_speed.astype("Float64")
    maxi = max_speed.astype("Float64")
    valide = (maxi > 0) & (cruise > 0) & (cruise <= maxi)
    ratio = ((cruise / maxi) ** 3).clip(upper=1.0)
    return ratio.where(valide)


def puissance_propulsion_installee(
    main_eng_power: pd.Series, main_eng_count: pd.Series
) -> pd.Series:
    """`main_eng_power` (kW, par moteur) x `main_eng_count` — voir la docstring du module
    pour l'hypothèse de lecture du schéma."""
    return main_eng_power.astype("Float64") * main_eng_count.astype("Float64")


# --- SFC : repli sourcé, injectable (Third IMO GHG Study 2014, Table 49) -------------------


def sfc_repli_imo2014(year: pd.Series) -> pd.Series:
    """SFOC de base (g/kWh) par âge du moteur, moteur HSD (rapide) — Third IMO GHG Study
    2014, Table 49. Avant 1983 inclus -> 225 ; 1984-2000 inclus -> 205 ; 2001 et après ->
    195. `NA` si `year` est inconnue."""
    year = year.astype("Float64")
    sfc = pd.Series(pd.NA, index=year.index, dtype="Float64")
    sfc = sfc.mask((year <= 1983).fillna(False), 225.0)
    sfc = sfc.mask(((year >= 1984) & (year <= 2000)).fillna(False), 205.0)
    sfc = sfc.mask((year >= 2001).fillna(False), 195.0)
    return sfc


def correction_charge_sfc(charge: pd.Series) -> pd.Series:
    """`SFOC(charge) = SFOC_base * (0,455*charge^2 - 0,71*charge + 1,287)` — Third IMO GHG
    Study 2014, même table. Toujours appliquée, non substituable (voir docstring du
    module)."""
    charge = charge.astype("Float64")
    return 0.455 * charge**2 - 0.71 * charge + 1.287


# --- Facteur carbone (MEPC.364(79) § 2.2.1) -------------------------------------------------

FACTEUR_CARBONE_CF = 3.206  # t CO2 / t de carburant, gazole marin (MDO/MGO)


@dataclass(frozen=True, slots=True)
class ParametresModele:
    """Paramètres injectables du calcul carburant — permet de substituer un référentiel SFC
    sourcé (ex. celui qui vit sur une branche non mergée d'un autre dépôt, volontairement
    non consommé ici) sans toucher à la logique de calcul elle-même."""

    sfc_base_g_par_kwh: Callable[[pd.Series], pd.Series] = sfc_repli_imo2014
    soufre_pct: float = 0.50  # plafond réglementaire mondial, voir docstring du module


# Singleton par défaut — évite un appel de constructeur dans une signature (B008), et il n'y
# a qu'un seul jeu de paramètres par défaut à faire vivre.
_PARAMETRES_PAR_DEFAUT = ParametresModele()


def carburant_g_par_jour(
    df: pd.DataFrame, parametres: ParametresModele = _PARAMETRES_PAR_DEFAUT
) -> pd.Series:
    """Carburant total brûlé par jour (g) : hôtellerie (groupes A, B, stabilisateurs) sur les
    trois modes + propulsion en navigation seulement. `NA` si un seul terme requis manque —
    jamais une somme partielle silencieuse (voir la docstring du module)."""
    gt = df["gross_tonnage"]
    year = df["year"]
    sfc_base = parametres.sfc_base_g_par_kwh(year)

    total = pd.Series(0.0, index=df.index, dtype="Float64")
    for mode in MODES:
        heures = HEURES_PAR_JOUR * PROFIL_TEMPOREL[mode]
        charge = charge_hotel(gt, mode)
        sfc_mode = sfc_base * correction_charge_sfc(charge)
        total = total + puissance_hotel_utilisee(gt, mode) * heures * sfc_mode

    puissance_prop = puissance_propulsion_installee(
        df["main_eng_power"], df["main_eng_count"]
    )
    charge_prop = facteur_charge_propulsion(df["cruise_speed"], df["max_speed"])
    sfc_prop = sfc_base * correction_charge_sfc(charge_prop)
    heures_nav = HEURES_PAR_JOUR * PROFIL_TEMPOREL["navigation"]
    total = total + puissance_prop * charge_prop * heures_nav * sfc_prop

    return total


def flux_co2_g_par_jour(
    df: pd.DataFrame, parametres: ParametresModele = _PARAMETRES_PAR_DEFAUT
) -> pd.Series:
    """CO2 (g/jour) = carburant brûlé x facteur carbone. Le flux le plus solide du module."""
    return carburant_g_par_jour(df, parametres) * FACTEUR_CARBONE_CF


RATIO_MASSIQUE_S_VERS_SO2 = (
    64.06 / 32.06
)  # masses atomiques IUPAC : S=32,06 ; SO2=32,06+2*16,00


def flux_sox_g_par_jour(
    df: pd.DataFrame, parametres: ParametresModele = _PARAMETRES_PAR_DEFAUT
) -> pd.Series:
    """SOx (g SO2/jour), dérivé du même carburant que le CO2, au plafond réglementaire de
    soufre (`parametres.soufre_pct`, pas une mesure du carburant réellement embarqué — voir
    la docstring du module)."""
    carburant = carburant_g_par_jour(df, parametres)
    masse_soufre = carburant * (parametres.soufre_pct / 100.0)
    return masse_soufre * RATIO_MASSIQUE_S_VERS_SO2


# --- Eaux noires, eaux grises, déchets : taux par personne et par jour (EPA842-R-07-005) ---

GALLON_US_EN_LITRES = 3.785411784
LIVRE_EN_KG = 0.45359237

TAUX_EAUX_NOIRES_L_PERS_JOUR = 8.4 * GALLON_US_EN_LITRES  # EPA842-R-07-005, §2.1, p.2-1
TAUX_EAUX_GRISES_L_PERS_JOUR = (
    67.0 * GALLON_US_EN_LITRES
)  # EPA842-R-07-005, §3.1, p.3-2
TAUX_DECHETS_KG_PERS_JOUR = (
    2.0 * LIVRE_EN_KG
)  # EPA842-R-07-005, §5.1, p.5-3, citant CELB 2003
# — un plancher (« at least »), pas une moyenne.


def personnes_a_bord(guests: pd.Series, crew: pd.Series) -> pd.Series:
    """Invités + équipage. Exige les DEUX champs — pas de repli sur l'un seul si l'autre
    manque, cohérent avec le refus de supposition silencieuse du module."""
    return guests.astype("Float64") + crew.astype("Float64")


def flux_eaux_noires_l_par_jour(guests: pd.Series, crew: pd.Series) -> pd.Series:
    return personnes_a_bord(guests, crew) * TAUX_EAUX_NOIRES_L_PERS_JOUR


def flux_eaux_grises_l_par_jour(guests: pd.Series, crew: pd.Series) -> pd.Series:
    return personnes_a_bord(guests, crew) * TAUX_EAUX_GRISES_L_PERS_JOUR


def flux_dechets_kg_par_jour(guests: pd.Series, crew: pd.Series) -> pd.Series:
    return personnes_a_bord(guests, crew) * TAUX_DECHETS_KG_PERS_JOUR


# --- NOx : Tier OMI par année de construction, JAMAIS converti en masse (voir docstring) ---

# Seuils en g/kWh, n = régime nominal du moteur (tr/min). Source : imo.org, « Nitrogen
# Oxides (NOx) – Regulation 13 »,
# https://www.imo.org/en/OurWork/Environment/Pages/Nitrogen-oxides-(NOx)-%E2%80%93-Regulation-13.aspx
# consulté le 2026-08-17. Exposé pour documentation/référence — n est absent à 100 % du
# catalogue, donc jamais appliqué (voir docstring du module).
LIMITES_NOX_TIER = {
    "I": {"n<130": 17.0, "n>=2000": 9.8},  # 130<=n<2000 : 45,0 * n^-0.2
    "II": {"n<130": 14.4, "n>=2000": 7.7},  # 130<=n<2000 : 44,0 * n^-0.23
    "III": {"n<130": 3.4, "n>=2000": 2.0},  # 130<=n<2000 : 9,0 * n^-0.2 ; ECA seulement
}


def tier_nox_construction(year: pd.Series) -> pd.Series:
    """Le Tier OMI déduit uniquement de l'année de construction (MARPOL Annexe VI règle 13) :
    Tier I >= 2000, Tier II >= 2011, Tier III >= 2016. Tier III ne s'applique qu'en zone ECA
    (NECA) — une information absente du catalogue (même angle mort que
    `voyage_international` dans `reglementaire.py`) : les navires post-2016 sont donc
    étiquetés en indiquant que Tier II s'applique de toute façon hors ECA, jamais un Tier III
    asséné comme certain. `NA` si `year` est inconnue."""
    year = year.astype("Float64")
    tier = pd.Series(pd.NA, index=year.index, dtype="object")
    tier = tier.mask((year < 2000).fillna(False), "avant Tier I")
    tier = tier.mask(((year >= 2000) & (year < 2011)).fillna(False), "I")
    tier = tier.mask(((year >= 2011) & (year < 2016)).fillna(False), "II")
    tier = tier.mask((year >= 2016).fillna(False), "III (en ECA) / II (hors ECA)")
    return tier


def repartition_tier_nox(df: pd.DataFrame) -> pd.DataFrame:
    """Décompte du Tier OMI applicable sur le catalogue — diagnostic à part, jamais fondu
    dans le vecteur de flux numériques (voir la docstring du module)."""
    n = len(df)
    tier = tier_nox_construction(df["year"]).fillna("indéterminé")
    compte = tier.value_counts()
    resultat = compte.rename("n").to_frame()
    resultat["pct"] = resultat["n"] / n * 100
    return resultat


# --- Normalisation : invité-nuit et GT-heure, toujours les deux ---------------------------


def normaliser_invite_nuit(valeur_par_jour: pd.Series, guests: pd.Series) -> pd.Series:
    """`valeur_par_jour / number_of_guests` — `NA` si `guests` est inconnu ou <= 0."""
    g = guests.astype("Float64")
    resultat = valeur_par_jour / g
    return resultat.where(g > 0)


def normaliser_gt_heure(valeur_par_jour: pd.Series, gt: pd.Series) -> pd.Series:
    """`valeur_par_jour / (gross_tonnage * 24h)` — `NA` si `gt` est inconnu ou <= 0."""
    heures_gt = gt.astype("Float64") * HEURES_PAR_JOUR
    resultat = valeur_par_jour / heures_gt
    return resultat.where(heures_gt > 0)


# --- Cohortes : classe de GT x décennie x type de coque ------------------------------------

# Seuil pragmatique, PAS réglementaire (contrairement à 100/400 GT, repris de
# `reglementaire.py` pour rester cohérent avec le reste du dépôt) : ~p92 du catalogue, ajouté
# pour ne pas noyer les grands yachts dans une seule classe « >= 400 GT » écrasée par l'écart
# type réel (GT va de 21 à 20 361, très asymétrique).
SEUIL_GT_CLASSE_HAUTE = 1000.0

INDETERMINE = "indéterminé"


def classe_gt(gt: pd.Series) -> pd.Series:
    gt = gt.astype("Float64")
    classe = pd.Series(pd.NA, index=gt.index, dtype="object")
    classe = classe.mask(
        (gt < SEUIL_GT_GARBAGE_MGMT_PLAN).fillna(False),
        f"< {SEUIL_GT_GARBAGE_MGMT_PLAN:.0f} GT",
    )
    classe = classe.mask(
        ((gt >= SEUIL_GT_GARBAGE_MGMT_PLAN) & (gt < SEUIL_GT_CERTIFICATS)).fillna(
            False
        ),
        f"{SEUIL_GT_GARBAGE_MGMT_PLAN:.0f}-{SEUIL_GT_CERTIFICATS:.0f} GT",
    )
    classe = classe.mask(
        ((gt >= SEUIL_GT_CERTIFICATS) & (gt < SEUIL_GT_CLASSE_HAUTE)).fillna(False),
        f"{SEUIL_GT_CERTIFICATS:.0f}-{SEUIL_GT_CLASSE_HAUTE:.0f} GT",
    )
    classe = classe.mask(
        (gt >= SEUIL_GT_CLASSE_HAUTE).fillna(False),
        f">= {SEUIL_GT_CLASSE_HAUTE:.0f} GT",
    )
    return classe.fillna(INDETERMINE)


def decennie(year: pd.Series) -> pd.Series:
    year = year.astype("Float64")
    base = year // 10 * 10
    resultat = pd.Series(pd.NA, index=year.index, dtype="object")
    connu = base.notna()
    resultat.loc[connu] = base[connu].astype("Int64").astype(str) + "s"
    return resultat.fillna(INDETERMINE)


def type_coque(vessel_hull_configuration: pd.Series) -> pd.Series:
    return vessel_hull_configuration.fillna(INDETERMINE)


# --- Le calcul par navire : USAGE INTERNE UNIQUEMENT, ne jamais publier tel quel -----------

FLUX = ("co2", "sox", "eaux_noires", "eaux_grises", "dechets")
UNITES_FLUX = {
    "co2": "g",
    "sox": "g",
    "eaux_noires": "L",
    "eaux_grises": "L",
    "dechets": "kg",
}


def _flux_usage_interne_jamais_publier(
    df: pd.DataFrame, parametres: ParametresModele = _PARAMETRES_PAR_DEFAUT
) -> pd.DataFrame:
    """Le vecteur d'impacts PAR NAVIRE, indexé comme `df`. **USAGE INTERNE UNIQUEMENT.**

    NE JAMAIS publier ce résultat tel quel : joint à `df` par son index, il reconstitue un
    classement de navires nommés — exactement ce que ce projet interdit (voir la docstring du
    module et l'aggregation par cohortes, la seule sortie publique légitime,
    `resume_par_cohorte`). Cette fonction ne retourne ni `id` ni `name` ni `description`, mais
    son index seul suffit à la ré-identification si l'appelant la rejoint négligemment à `df`.
    """
    gt = df["gross_tonnage"]
    guests = df["number_of_guests"]
    crew = df["number_of_crew"]

    flux_valeurs = {
        "co2": flux_co2_g_par_jour(df, parametres),
        "sox": flux_sox_g_par_jour(df, parametres),
        "eaux_noires": flux_eaux_noires_l_par_jour(guests, crew),
        "eaux_grises": flux_eaux_grises_l_par_jour(guests, crew),
        "dechets": flux_dechets_kg_par_jour(guests, crew),
    }

    resultat = pd.DataFrame(index=df.index)
    for nom, valeur in flux_valeurs.items():
        resultat[f"{nom}_par_jour"] = valeur
        resultat[f"{nom}_invite_nuit"] = normaliser_invite_nuit(valeur, guests)
        resultat[f"{nom}_gt_heure"] = normaliser_gt_heure(valeur, gt)

    resultat["hors_domaine_hebergement"] = hors_domaine_hebergement(
        df["overall_length"]
    )
    resultat["classe_gt"] = classe_gt(gt)
    resultat["decennie"] = decennie(df["year"])
    resultat["type_coque"] = type_coque(df["vessel_hull_configuration"])
    return resultat


def _quantiles_ou_none(
    serie: pd.Series,
) -> tuple[float | None, float | None, float | None]:
    serie = serie.dropna()
    if len(serie) == 0:
        return (None, None, None)
    return (
        float(serie.quantile(0.25)),
        float(serie.quantile(0.5)),
        float(serie.quantile(0.75)),
    )


def resume_calculabilite(
    df: pd.DataFrame, parametres: ParametresModele = _PARAMETRES_PAR_DEFAUT
) -> pd.DataFrame:
    """Une ligne par flux : combien de navires calculables, combien indéterminés, sur
    l'ensemble du catalogue passé. Sortie sûre — aucune colonne par navire."""
    detail = _flux_usage_interne_jamais_publier(df, parametres)
    n = len(df)
    lignes = []
    for flux in FLUX:
        n_calc = int(detail[f"{flux}_par_jour"].notna().sum())
        lignes.append(
            {
                "flux": flux,
                "unite": UNITES_FLUX[flux],
                "n": n,
                "n_calculable": n_calc,
                "pct_calculable": n_calc / n * 100,
                "n_indetermine": n - n_calc,
                "pct_indetermine": (n - n_calc) / n * 100,
            }
        )
    return pd.DataFrame(lignes).set_index("flux")


def resume_par_cohorte(
    df: pd.DataFrame, parametres: ParametresModele = _PARAMETRES_PAR_DEFAUT
) -> pd.DataFrame:
    """La sortie publique légitime : une ligne par (classe de GT, décennie, type de coque,
    flux), jamais par navire. Pour chaque cohorte x flux : effectif, calculabilité, et la
    distribution (p25/médiane/p75) des deux normalisations — invité-nuit et GT-heure — pour
    que leur comparaison soit directement lisible, cohorte par cohorte."""
    detail = _flux_usage_interne_jamais_publier(df, parametres)

    lignes = []
    for (cgt, dec, coque), sous in detail.groupby(
        ["classe_gt", "decennie", "type_coque"]
    ):
        n = len(sous)
        for flux in FLUX:
            n_calc = int(sous[f"{flux}_par_jour"].notna().sum())
            inv_p25, inv_med, inv_p75 = _quantiles_ou_none(sous[f"{flux}_invite_nuit"])
            gt_p25, gt_med, gt_p75 = _quantiles_ou_none(sous[f"{flux}_gt_heure"])
            lignes.append(
                {
                    "classe_gt": cgt,
                    "decennie": dec,
                    "type_coque": coque,
                    "flux": flux,
                    "n": n,
                    "n_calculable": n_calc,
                    "pct_calculable": n_calc / n * 100,
                    "n_indetermine": n - n_calc,
                    "pct_indetermine": (n - n_calc) / n * 100,
                    "invite_nuit_p25": inv_p25,
                    "invite_nuit_mediane": inv_med,
                    "invite_nuit_p75": inv_p75,
                    "gt_heure_p25": gt_p25,
                    "gt_heure_mediane": gt_med,
                    "gt_heure_p75": gt_p75,
                }
            )
    return pd.DataFrame(lignes)


def main() -> int:
    df = pd.read_parquet(CATALOGUE)

    print(f"{len(df)} navires — calculabilité par flux (vecteur d'impacts)\n")
    calculabilite = resume_calculabilite(df)
    for flux, ligne in calculabilite.iterrows():
        print(
            f"  {flux:14} ({ligne.unite}/jour)  calculable {ligne.pct_calculable:5.1f} % "
            f"({int(ligne.n_calculable):>5}/{len(df)})"
        )

    print("\nrépartition Tier NOx (année de construction, MARPOL Annexe VI règle 13) :")
    print(repartition_tier_nox(df).to_string())

    detail = _flux_usage_interne_jamais_publier(df)
    print("\ncomparaison invité-nuit vs GT-heure (corrélation de rang) :")
    for flux in FLUX:
        sous = detail[[f"{flux}_invite_nuit", f"{flux}_gt_heure"]].dropna()
        if len(sous) > 1:
            # Spearman = Pearson sur les rangs — évite une dépendance scipy pour un seul
            # nombre de digest.
            rho = (
                sous[f"{flux}_invite_nuit"]
                .astype(float)
                .rank()
                .corr(sous[f"{flux}_gt_heure"].astype(float).rank())
            )
            print(f"  {flux:14} rho = {rho:6.3f}  (n = {len(sous)})")

    hors_domaine = detail["hors_domaine_hebergement"]
    print(
        f"\nhors domaine de validité hôtellerie (<30 m ou >180 m) : "
        f"{int(hors_domaine.sum())}/{int(hors_domaine.notna().sum())} navires connus"
    )

    cohortes = resume_par_cohorte(df)
    print(
        f"\n{len(cohortes)} lignes cohorte x flux (classe GT x décennie x type de coque x flux)"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
