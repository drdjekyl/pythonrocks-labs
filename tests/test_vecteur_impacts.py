"""Tests du vecteur d'impacts : logique de calcul, cas limites, données manquantes.

Aucun accès réseau. Les valeurs de référence des régressions hôtelières sont recalculées
inline depuis les coefficients (des équations numérotées et lues directement dans le mémoire
source, pas depuis le tableau d'exemple 3.7 — voir la docstring du module pour pourquoi ce
tableau-là, lui, n'est pas fiable comme oracle : extraction PDF -> texte manifestement
désalignée sur les colonnes intermédiaires)."""

import math

import pandas as pd
import pytest

from labs.reglementaire import SEUIL_GT_CERTIFICATS, SEUIL_GT_GARBAGE_MGMT_PLAN
from labs.vecteur_impacts import (
    CATALOGUE,
    FACTEUR_CARBONE_CF,
    FLUX,
    RATIO_MASSIQUE_S_VERS_SO2,
    SEUIL_GT_CLASSE_HAUTE,
    TAUX_DECHETS_KG_PERS_JOUR,
    TAUX_EAUX_GRISES_L_PERS_JOUR,
    TAUX_EAUX_NOIRES_L_PERS_JOUR,
    ParametresModele,
    _flux_usage_interne_jamais_publier,
    carburant_g_par_jour,
    charge_hotel,
    classe_gt,
    correction_charge_sfc,
    decennie,
    facteur_charge_propulsion,
    flux_co2_g_par_jour,
    flux_dechets_kg_par_jour,
    flux_eaux_grises_l_par_jour,
    flux_eaux_noires_l_par_jour,
    flux_sox_g_par_jour,
    hors_domaine_hebergement,
    normaliser_gt_heure,
    normaliser_invite_nuit,
    personnes_a_bord,
    puissance_groupe_a,
    puissance_groupe_b,
    puissance_hotel_installee,
    puissance_propulsion_installee,
    puissance_stabilisateurs,
    repartition_tier_nox,
    resume_calculabilite,
    resume_par_cohorte,
    sfc_repli_imo2014,
    tier_nox_construction,
    type_coque,
)


def s(*valeurs) -> pd.Series:
    return pd.Series(list(valeurs), dtype="Float64")


# --- Charge hôtelière : groupes A, B, stabilisateurs ----------------------------------------


def test_puissance_groupe_a_gt_1000_reconcilie_avec_le_memoire():
    """111,44 kW à GT=1000 est la valeur donnée telle quelle dans le mémoire (table 3.7,
    colonne « installed power », seule valeur de cette table jugée fiable — voir la docstring
    du module)."""
    assert puissance_groupe_a(s(1000.0))[0] == pytest.approx(111.44, abs=1e-6)


def test_puissance_groupe_b_recalcule_depuis_l_equation_3_20():
    attendu = 5.063e-5 * 1000.0**2 + 0.1123 * 1000.0 - 20.53
    assert puissance_groupe_b(s(1000.0))[0] == pytest.approx(attendu)


def test_puissance_stabilisateurs_recalcule():
    assert puissance_stabilisateurs(s(1000.0))[0] == pytest.approx(
        0.02532 * 1000.0 + 16.5
    )


def test_puissance_hotel_installee_est_la_somme_des_trois_groupes():
    gt = s(500.0)
    attendu = (
        puissance_groupe_a(gt)[0]
        + puissance_groupe_b(gt)[0]
        + puissance_stabilisateurs(gt)[0]
    )
    assert puissance_hotel_installee(gt)[0] == pytest.approx(attendu)


def test_puissance_hotel_installee_gt_manquant_est_indetermine():
    assert puissance_hotel_installee(s(None))[0] is pd.NA


def test_charge_hotel_est_bornee_entre_0_et_1_sur_une_plage_de_gt():
    for gt in (30.0, 100.0, 500.0, 2000.0, 20000.0):
        for mode in ("navigation", "mouillage", "port"):
            charge = charge_hotel(s(gt), mode)[0]
            assert 0.0 <= charge <= 1.0, (gt, mode, charge)


def test_charge_hotel_mouillage_domine_par_les_stabilisateurs():
    """Au mouillage, le ratio d'usage des stabilisateurs (0,50) est le plus élevé des trois
    groupes — la charge hôtelière au mouillage doit donc être notablement plus haute qu'au
    port (ratios 0,06/0,03/0,25, tous plus bas)."""
    gt = s(500.0)
    assert charge_hotel(gt, "mouillage")[0] > charge_hotel(gt, "port")[0]


# --- Domaine de validité --------------------------------------------------------------------


def test_hors_domaine_sous_30_m():
    assert hors_domaine_hebergement(s(29.9))[0] == True  # noqa: E712 (booléen nullable numpy)


def test_dans_domaine_a_30_m_pile():
    assert hors_domaine_hebergement(s(30.0))[0] == False  # noqa: E712


def test_dans_domaine_a_180_m_pile():
    assert hors_domaine_hebergement(s(180.0))[0] == False  # noqa: E712


def test_hors_domaine_au_dessus_de_180_m():
    assert hors_domaine_hebergement(s(180.1))[0] == True  # noqa: E712


def test_hors_domaine_indetermine_si_longueur_manquante():
    assert hors_domaine_hebergement(s(None))[0] is pd.NA


# --- Propulsion : loi du cube ----------------------------------------------------------------


def test_facteur_charge_propulsion_cas_valide():
    # cruise=10, max=20 -> (0.5)^3 = 0.125
    assert facteur_charge_propulsion(s(10.0), s(20.0))[0] == pytest.approx(0.125)


def test_facteur_charge_propulsion_egal_a_max_donne_1():
    assert facteur_charge_propulsion(s(20.0), s(20.0))[0] == pytest.approx(1.0)


def test_facteur_charge_propulsion_cruise_superieur_a_max_est_indetermine():
    """10 cas réels sur le catalogue — une erreur de saisie manifeste, jamais pincée à 1,0
    silencieusement."""
    assert facteur_charge_propulsion(s(25.0), s(20.0))[0] is pd.NA


def test_facteur_charge_propulsion_vitesse_manquante_est_indetermine():
    assert facteur_charge_propulsion(s(None), s(20.0))[0] is pd.NA
    assert facteur_charge_propulsion(s(10.0), s(None))[0] is pd.NA


def test_facteur_charge_propulsion_max_nul_est_indetermine():
    assert facteur_charge_propulsion(s(10.0), s(0.0))[0] is pd.NA


def test_puissance_propulsion_installee_multiplie_par_le_nombre_de_moteurs():
    assert puissance_propulsion_installee(s(1000.0), s(2.0))[0] == pytest.approx(2000.0)


def test_puissance_propulsion_installee_nombre_de_moteurs_manquant():
    assert puissance_propulsion_installee(s(1000.0), s(None))[0] is pd.NA


# --- SFC : repli IMO 2014, injectable --------------------------------------------------------


def test_sfc_repli_avant_1983_inclus():
    assert sfc_repli_imo2014(s(1983.0))[0] == 225.0


def test_sfc_repli_1984_ouvre_le_palier_intermediaire():
    assert sfc_repli_imo2014(s(1984.0))[0] == 205.0


def test_sfc_repli_2000_encore_dans_le_palier_intermediaire():
    assert sfc_repli_imo2014(s(2000.0))[0] == 205.0


def test_sfc_repli_2001_ouvre_le_palier_recent():
    assert sfc_repli_imo2014(s(2001.0))[0] == 195.0


def test_sfc_repli_annee_manquante_est_indeterminee():
    assert sfc_repli_imo2014(s(None))[0] is pd.NA


def test_sfc_repli_nan_pandas_traite_comme_manquant():
    assert sfc_repli_imo2014(s(math.nan))[0] is pd.NA


def test_correction_charge_sfc_recalculee_depuis_la_formule():
    charge = 0.5
    attendu = 0.455 * charge**2 - 0.71 * charge + 1.287
    assert correction_charge_sfc(s(charge))[0] == pytest.approx(attendu)


def test_correction_charge_sfc_a_pleine_charge():
    attendu = 0.455 * 1.0 - 0.71 * 1.0 + 1.287
    assert correction_charge_sfc(s(1.0))[0] == pytest.approx(attendu)


# --- Constantes sourcées ----------------------------------------------------------------------


def test_facteur_carbone_cf():
    assert pytest.approx(3.206) == FACTEUR_CARBONE_CF


def test_ratio_massique_s_vers_so2_est_proche_de_2():
    """Masses atomiques IUPAC : S=32,06, SO2=64,06 -> ratio ~1,998, pas exactement 2 (S n'est
    pas un isotope pur)."""
    assert pytest.approx(1.998, abs=0.005) == RATIO_MASSIQUE_S_VERS_SO2


def test_taux_eaux_noires_recalcule_depuis_le_taux_epa():
    assert pytest.approx(8.4 * 3.785411784) == TAUX_EAUX_NOIRES_L_PERS_JOUR


def test_taux_eaux_grises_recalcule_depuis_le_taux_epa():
    assert pytest.approx(67.0 * 3.785411784) == TAUX_EAUX_GRISES_L_PERS_JOUR


def test_taux_dechets_recalcule_depuis_le_taux_epa():
    assert pytest.approx(2.0 * 0.45359237) == TAUX_DECHETS_KG_PERS_JOUR


# --- Carburant, CO2, SOx : propagation des indéterminations ----------------------------------


def _navire_complet(**overrides) -> pd.DataFrame:
    base = {
        "gross_tonnage": 500.0,
        "year": 2015.0,
        "main_eng_power": 1000.0,
        "main_eng_count": 2.0,
        "cruise_speed": 15.0,
        "max_speed": 20.0,
        "number_of_guests": 10.0,
        "number_of_crew": 8.0,
        "overall_length": 45.0,
        "vessel_hull_configuration": "Planning",
    }
    base.update(overrides)
    return pd.DataFrame({k: [v] for k, v in base.items()})


def test_carburant_par_jour_est_positif_pour_un_navire_complet():
    carburant = carburant_g_par_jour(_navire_complet())
    assert carburant[0] > 0


def test_carburant_indetermine_si_gt_manquant():
    carburant = carburant_g_par_jour(_navire_complet(gross_tonnage=None))
    assert carburant[0] is pd.NA


def test_carburant_indetermine_si_moteur_manquant():
    """Aucune moyenne partielle silencieuse : la propulsion manquante rend le total
    indéterminé, même si l'hôtellerie est parfaitement connue."""
    carburant = carburant_g_par_jour(_navire_complet(main_eng_power=None))
    assert carburant[0] is pd.NA


def test_carburant_indetermine_si_annee_manquante():
    carburant = carburant_g_par_jour(_navire_complet(year=None))
    assert carburant[0] is pd.NA


def test_flux_co2_est_le_carburant_fois_le_facteur_carbone():
    df = _navire_complet()
    co2 = flux_co2_g_par_jour(df)
    carburant = carburant_g_par_jour(df)
    assert co2[0] == pytest.approx(carburant[0] * FACTEUR_CARBONE_CF)


def test_flux_sox_utilise_le_soufre_injecte():
    df = _navire_complet()
    sox_defaut = flux_sox_g_par_jour(df)
    sox_eca = flux_sox_g_par_jour(df, ParametresModele(soufre_pct=0.10))
    # ECA (0,10 %) doit donner un cinquième du plafond mondial (0,50 %)
    assert sox_eca[0] == pytest.approx(sox_defaut[0] * (0.10 / 0.50))


def test_parametres_modele_sfc_injectable():
    """Le paramètre `sfc_base_g_par_kwh` est bien substituable — un repli constant maison
    donne un résultat différent du repli IMO par défaut."""
    df = _navire_complet()
    defaut = carburant_g_par_jour(df)
    repli_constant = ParametresModele(
        sfc_base_g_par_kwh=lambda year: pd.Series([100.0] * len(year), dtype="Float64")
    )
    autre = carburant_g_par_jour(df, repli_constant)
    assert defaut[0] != pytest.approx(autre[0])


# --- Eaux noires, eaux grises, déchets --------------------------------------------------------


def test_personnes_a_bord_additionne_invites_et_equipage():
    assert personnes_a_bord(s(10.0), s(8.0))[0] == 18.0


def test_personnes_a_bord_invites_manquants_est_indetermine():
    assert personnes_a_bord(s(None), s(8.0))[0] is pd.NA


def test_personnes_a_bord_equipage_manquant_est_indetermine():
    assert personnes_a_bord(s(10.0), s(None))[0] is pd.NA


def test_flux_eaux_noires_valeur():
    assert flux_eaux_noires_l_par_jour(s(10.0), s(8.0))[0] == pytest.approx(
        18.0 * TAUX_EAUX_NOIRES_L_PERS_JOUR
    )


def test_flux_eaux_grises_valeur():
    assert flux_eaux_grises_l_par_jour(s(10.0), s(8.0))[0] == pytest.approx(
        18.0 * TAUX_EAUX_GRISES_L_PERS_JOUR
    )


def test_flux_dechets_valeur():
    assert flux_dechets_kg_par_jour(s(10.0), s(8.0))[0] == pytest.approx(
        18.0 * TAUX_DECHETS_KG_PERS_JOUR
    )


# --- Tier NOx (diagnostic, pas une masse) -----------------------------------------------------


def test_tier_nox_avant_2000():
    assert tier_nox_construction(s(1999.0))[0] == "avant Tier I"


def test_tier_nox_2000_ouvre_tier_1():
    assert tier_nox_construction(s(2000.0))[0] == "I"


def test_tier_nox_2011_ouvre_tier_2():
    assert tier_nox_construction(s(2011.0))[0] == "II"


def test_tier_nox_2016_ouvre_tier_3_avec_reserve_eca():
    resultat = tier_nox_construction(s(2016.0))[0]
    assert resultat == "III (en ECA) / II (hors ECA)"


def test_tier_nox_annee_manquante_indetermine():
    assert tier_nox_construction(s(None))[0] is pd.NA


def test_repartition_tier_nox_totalise_l_effectif():
    df = pd.DataFrame({"year": [1990.0, 2005.0, 2013.0, 2020.0, None]})
    repartition = repartition_tier_nox(df)
    assert repartition["n"].sum() == len(df)


# --- Normalisation : invité-nuit et GT-heure ---------------------------------------------------


def test_normaliser_invite_nuit():
    assert normaliser_invite_nuit(s(1000.0), s(10.0))[0] == pytest.approx(100.0)


def test_normaliser_invite_nuit_invites_manquants():
    assert normaliser_invite_nuit(s(1000.0), s(None))[0] is pd.NA


def test_normaliser_invite_nuit_zero_invite_est_indetermine():
    assert normaliser_invite_nuit(s(1000.0), s(0.0))[0] is pd.NA


def test_normaliser_gt_heure():
    # 1000 / (GT=100 * 24h) = 1000/2400
    assert normaliser_gt_heure(s(1000.0), s(100.0))[0] == pytest.approx(1000.0 / 2400.0)


def test_normaliser_gt_heure_gt_manquant():
    assert normaliser_gt_heure(s(1000.0), s(None))[0] is pd.NA


# --- Cohortes : classe de GT, décennie, type de coque -------------------------------------------


def test_classe_gt_juste_sous_100():
    assert classe_gt(s(99.9))[0] == f"< {SEUIL_GT_GARBAGE_MGMT_PLAN:.0f} GT"


def test_classe_gt_a_100_pile():
    assert (
        classe_gt(s(100.0))[0]
        == f"{SEUIL_GT_GARBAGE_MGMT_PLAN:.0f}-{SEUIL_GT_CERTIFICATS:.0f} GT"
    )


def test_classe_gt_a_400_pile():
    assert (
        classe_gt(s(400.0))[0]
        == f"{SEUIL_GT_CERTIFICATS:.0f}-{SEUIL_GT_CLASSE_HAUTE:.0f} GT"
    )


def test_classe_gt_a_1000_pile():
    assert classe_gt(s(1000.0))[0] == f">= {SEUIL_GT_CLASSE_HAUTE:.0f} GT"


def test_classe_gt_manquant_est_indetermine():
    assert classe_gt(s(None))[0] == "indéterminé"


def test_decennie_arrondit_vers_le_bas():
    assert decennie(s(1997.0))[0] == "1990s"


def test_decennie_annee_manquante_est_indeterminee():
    assert decennie(s(None))[0] == "indéterminé"


def test_type_coque_remplit_les_manquants():
    serie = pd.Series(["Planning", None])
    resultat = type_coque(serie)
    assert resultat[0] == "Planning"
    assert resultat[1] == "indéterminé"


# --- Le calcul interne par navire : jamais de fuite nominative --------------------------------


def test_flux_usage_interne_ne_contient_ni_id_ni_name():
    df = _navire_complet()
    detail = _flux_usage_interne_jamais_publier(df)
    assert "id" not in detail.columns
    assert "name" not in detail.columns
    assert "description" not in detail.columns


def test_flux_usage_interne_toutes_les_colonnes_attendues():
    df = _navire_complet()
    detail = _flux_usage_interne_jamais_publier(df)
    for flux in FLUX:
        assert f"{flux}_par_jour" in detail.columns
        assert f"{flux}_invite_nuit" in detail.columns
        assert f"{flux}_gt_heure" in detail.columns


def test_flux_usage_interne_navire_incomplet_indetermine_uniquement_les_flux_concernes():
    """Un navire sans équipage connu : les flux liés aux personnes sont indéterminés, mais le
    CO2 (qui ne dépend pas des personnes) reste calculable."""
    df = _navire_complet(number_of_crew=None)
    detail = _flux_usage_interne_jamais_publier(df)
    assert detail["co2_par_jour"][0] > 0
    assert detail["eaux_noires_par_jour"][0] is pd.NA


# --- Sorties de résumé : sûres, jamais par navire ----------------------------------------------


def test_resume_calculabilite_sur_catalogue_synthetique():
    df = pd.concat(
        [_navire_complet(), _navire_complet(gross_tonnage=None)], ignore_index=True
    )
    resume = resume_calculabilite(df)
    assert resume.loc["co2", "n"] == 2
    assert resume.loc["co2", "n_calculable"] == 1
    assert resume.loc["co2", "pct_calculable"] == pytest.approx(50.0)


def test_resume_par_cohorte_n_perd_aucun_navire():
    df = pd.concat(
        [
            _navire_complet(gross_tonnage=50.0),
            _navire_complet(gross_tonnage=200.0),
            _navire_complet(gross_tonnage=None),
        ],
        ignore_index=True,
    )
    resume = resume_par_cohorte(df)
    # une ligne par cohorte x flux : la somme des `n` sur un seul flux couvre tout l'effectif
    sous = resume[resume["flux"] == "co2"]
    assert sous["n"].sum() == len(df)


def test_resume_par_cohorte_ne_contient_aucune_colonne_nominative():
    df = _navire_complet()
    resume = resume_par_cohorte(df)
    assert "id" not in resume.columns
    assert "name" not in resume.columns


def test_resume_par_cohorte_indetermine_va_dans_une_cohorte_visible():
    df = _navire_complet(gross_tonnage=None)
    resume = resume_par_cohorte(df)
    assert "indéterminé" in set(resume["classe_gt"])


# --- Le résultat sur le catalogue réel ----------------------------------------------------------


def test_reconcilie_avec_le_catalogue_reel():
    df = pd.read_parquet(CATALOGUE)
    assert len(df) == 9407

    calculabilite = resume_calculabilite(df)
    # CO2/SOx partagent le même dénominateur de calculabilité (même carburant sous-jacent).
    assert (
        calculabilite.loc["co2", "n_calculable"]
        == calculabilite.loc["sox", "n_calculable"]
    )
    assert calculabilite.loc["co2", "pct_calculable"] == pytest.approx(74.3, abs=0.1)
    # eaux/déchets partagent le même dénominateur (invités + équipage tous deux connus).
    assert (
        calculabilite.loc["eaux_noires", "n_calculable"]
        == calculabilite.loc["eaux_grises", "n_calculable"]
        == calculabilite.loc["dechets", "n_calculable"]
    )
    assert calculabilite.loc["eaux_noires", "pct_calculable"] == pytest.approx(
        82.8, abs=0.1
    )

    repartition = repartition_tier_nox(df)
    assert repartition["n"].sum() == len(df)

    resume = resume_par_cohorte(df)
    sous = resume[resume["flux"] == "co2"]
    assert sous["n"].sum() == len(df)
