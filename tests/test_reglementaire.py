"""Les cas limites qui font la valeur de la couche réglementaire.

Chaque seuil a son test au bord exact (399/400, 499/500, 99/100, 12/13, 15/16), plus le cas
qui distingue vraiment cette couche d'un simple `if` : les données manquantes, qui doivent
produire une troisième valeur (`None`) plutôt qu'une supposition silencieuse. Les seuils de
base viennent de la table du chapitre 4 du mémoire de M2 de l'auteur ; trois d'entre eux ont
été corrigés le 2026-08-21 après confrontation au texte primaire OMI (voir
`src/labs/reglementaire.py`) — les tests ci-dessous couvrent la version corrigée.
"""

import math

import pandas as pd
import pytest

from labs.reglementaire import (
    CATALOGUE,
    OBLIGATIONS,
    interdiction_mouillage_posidonies,
    obligations_applicables,
    obligations_indeterminees,
    obligations_navire,
    repartir_obligations,
)

# Un navire loin de tous les seuils, pour isoler une seule variable à la fois.
GT_NEUTRE = 50.0
LONGUEUR_NEUTRE = 20.0
INVITES_NEUTRE = 4


def navire(gt=GT_NEUTRE, longueur=LONGUEUR_NEUTRE, invites=INVITES_NEUTRE, **kw):
    return obligations_navire(gt, longueur, invites, **kw)


# --- 400 GT : IOPP / IAPP / IEE / AFS_CERTIFICATE ------------------------------------------


def test_399_gt_n_ouvre_pas_le_bloc_400():
    o = navire(gt=399.0)
    assert (o.IOPP, o.IAPP, o.IEE, o.AFS_CERTIFICATE) == (False, False, False, False)


def test_400_gt_pile_ouvre_le_bloc_400():
    o = navire(gt=400.0)
    assert (o.IOPP, o.IAPP, o.IEE, o.AFS_CERTIFICATE) == (True, True, True, True)


# --- 500 GT : ISM, et sa seconde voie indépendante (navire à passagers) --------------------


def test_499_gt_n_ouvre_pas_ism():
    assert navire(gt=499.0).ISM is False


def test_500_gt_pile_ouvre_ism():
    assert navire(gt=500.0).ISM is True


def test_12_invites_n_ouvre_pas_ism_meme_sous_500_gt():
    """SOLAS I/2(f) : un navire à passagers en transporte *plus de* douze, pas douze pile."""
    assert navire(gt=50.0, invites=12).ISM is False


def test_13_invites_ouvre_ism_meme_tres_sous_500_gt():
    """La seconde voie de SOLAS IX/2 §1.1, absente de la table du mémoire, ajoutée le
    2026-08-21 : contrairement aux navires de charge (§1.2/.3, "500 gross tonnage and
    upwards"), un navire à passagers relève du Code ISM sans aucun seuil de tonnage. Un yacht
    de 50 GT avec 13 invités reste soumis à l'ISM."""
    o = navire(gt=50.0, invites=13)
    assert o.ISM is True


def test_ism_invites_manquant_avec_gt_sous_500_reste_indetermine():
    assert navire(gt=50.0, invites=None).ISM is None


def test_ism_gt_manquant_mais_plus_de_12_invites_tranche_quand_meme():
    """Même court-circuit `OU` que pour ISPP/l'Annexe V : la voie passagers seule suffit."""
    assert navire(gt=None, invites=20).ISM is True


# --- 100 GT : GARBAGE_MGMT_PLAN -------------------------------------------------------------


def test_99_gt_n_ouvre_pas_le_plan_dechets():
    assert navire(gt=99.0).GARBAGE_MGMT_PLAN is False


def test_100_gt_pile_ouvre_le_plan_dechets():
    assert navire(gt=100.0).GARBAGE_MGMT_PLAN is True


# --- 15 invités : ISPP / GARBAGE_MGMT_PLAN / GARBAGE_RECORD_BOOK ---------------------------


def test_15_invites_n_ouvre_pas_ispp():
    """Le seuil ISPP (Annexe IV) est *plus de* 15, pas 15 compris."""
    o = navire(gt=50.0, invites=15)
    assert o.ISPP is False


def test_15_invites_pile_ouvre_le_plan_et_le_registre_mais_pas_ispp():
    """Le cas qui distingue les deux textes : Annexe IV (ISPP, « more than 15 persons »,
    strict) contre Annexe V (plan + registre, « 15 or more persons », inclusif). Confirmé
    contre le texte primaire OMI le 2026-08-21 (MEPC.201/62, MEPC.360/79) — un navire certifié
    pour EXACTEMENT 15 personnes doit le plan de gestion et le registre des ordures, pas
    l'ISPP."""
    o = navire(gt=50.0, invites=15)
    assert o.ISPP is False
    assert o.GARBAGE_MGMT_PLAN is True
    assert o.GARBAGE_RECORD_BOOK is True


def test_16_invites_ouvre_ispp_meme_sous_400_gt():
    """Le cas qui fait la valeur de la table : la voie « passagers » est indépendante de la
    voie « tonnage ». Un navire de 50 GT avec 16 invités reste sous ISPP."""
    o = navire(gt=50.0, invites=16)
    assert o.ISPP is True
    assert o.GARBAGE_RECORD_BOOK is True
    assert o.GARBAGE_MGMT_PLAN is True  # a fortiori, son seuil est plus bas (100 GT)


# --- AFS_DECLARATION : > 24 m ET < 400 GT ---------------------------------------------------


def test_afs_declaration_sous_400_gt_et_au_dessus_de_24_m():
    o = navire(gt=200.0, longueur=30.0)
    assert o.AFS_DECLARATION is True


def test_afs_declaration_absente_a_24_m_pile():
    """Seuil strict : *plus de* 24 m, 24 m pile n'y entre pas."""
    o = navire(gt=200.0, longueur=24.0)
    assert o.AFS_DECLARATION is False


def test_afs_declaration_absente_au_dessus_de_400_gt_meme_long():
    """Au-dessus de 400 GT, c'est AFS_CERTIFICATE qui s'applique, pas la déclaration."""
    o = navire(gt=450.0, longueur=60.0)
    assert o.AFS_CERTIFICATE is True
    assert o.AFS_DECLARATION is False


# --- Données manquantes : jamais une supposition silencieuse -------------------------------


def test_gt_manquant_laisse_le_bloc_400_indetermine():
    o = navire(gt=None, invites=4)
    assert (o.IOPP, o.IAPP, o.IEE, o.AFS_CERTIFICATE, o.ISM) == (None,) * 5


def test_gt_manquant_mais_plus_de_15_invites_tranche_quand_meme_ispp():
    """La branche `OU` qui suffit : pas besoin de connaître le tonnage si les invités seuls
    dépassent déjà 15. C'est le cas réel de 6 navires du catalogue (tonnage absent, invités
    connus et au-dessus de 15) — voir `test_reconcilie_avec_le_catalogue_reel`."""
    o = navire(gt=None, invites=20)
    assert o.ISPP is True
    assert o.GARBAGE_RECORD_BOOK is True
    assert o.GARBAGE_MGMT_PLAN is True


def test_gt_manquant_et_invites_sous_le_seuil_reste_indetermine():
    """Ici, à l'inverse, aucune branche ne tranche : `False OU indéterminé` = indéterminé."""
    o = navire(gt=None, invites=4)
    assert o.ISPP is None
    assert o.GARBAGE_RECORD_BOOK is None
    assert o.GARBAGE_MGMT_PLAN is None


def test_invites_manquant_avec_gt_sous_400_reste_indetermine():
    o = navire(gt=50.0, invites=None)
    assert o.ISPP is None  # `False OU indéterminé`


def test_invites_manquant_avec_gt_au_dessus_de_400_tranche_quand_meme():
    """L'inverse : le tonnage seul suffit, la donnée manquante devient sans objet."""
    o = navire(gt=450.0, invites=None)
    assert o.ISPP is True


def test_longueur_manquante_avec_gt_au_dessus_de_400_tranche_afs_declaration_a_false():
    """`ET` a lui aussi sa branche qui court-circuite : GT ≥ 400 signifie AFS_CERTIFICATE et
    non AFS_DECLARATION, quelle que soit la longueur."""
    o = navire(gt=450.0, longueur=None)
    assert o.AFS_DECLARATION is False


def test_longueur_manquante_avec_gt_sous_400_reste_indetermine():
    o = navire(gt=50.0, longueur=None)
    assert o.AFS_DECLARATION is None


def test_gt_manquant_avec_longueur_sous_24_m_tranche_afs_declaration_a_false():
    """Le même court-circuit `ET`, vu depuis l'autre inconnue : une longueur de 24 m ou moins,
    à elle seule, suffit à écarter la déclaration, tonnage ou pas."""
    o = navire(gt=None, longueur=20.0)
    assert o.AFS_DECLARATION is False


def test_gt_manquant_avec_longueur_au_dessus_de_24_m_reste_indetermine():
    """Ici, à l'inverse, la longueur ne suffit pas seule : il faut encore savoir si le navire
    est sous 400 GT pour trancher entre AFS_DECLARATION et AFS_CERTIFICATE."""
    o = navire(gt=None, longueur=30.0)
    assert o.AFS_DECLARATION is None


def test_toutes_donnees_manquantes_renvoie_indetermine_partout():
    o = navire(gt=None, longueur=None, invites=None)
    for nom in OBLIGATIONS:
        assert getattr(o, nom) is None, nom


def test_nan_pandas_est_traite_comme_une_valeur_manquante():
    """Une colonne `float64` sert des `NaN`, pas des `None` : les deux doivent produire le
    même indéterminé, sans quoi la fonction se comporte différemment appelée depuis un
    DataFrame ou depuis un test."""
    o = navire(gt=math.nan, invites=4)
    assert o.IOPP is None


# --- Le paramètre voyage_international, exposé et non deviné -------------------------------


def test_voyage_international_est_suppose_vrai_par_defaut():
    o = navire(gt=450.0)
    assert o.voyage_international_suppose is True
    assert o.IOPP is True  # le calcul normal s'applique


def test_voyage_international_a_false_indetermine_tout_plutot_que_deviner():
    """Passer `voyage_international=False` ne fait pas basculer les obligations à `False` —
    ce serait deviner l'inverse. Elles reviennent `None`, et l'hypothèse utilisée reste lisible
    sur le résultat lui-même via `voyage_international_suppose`."""
    o = navire(gt=450.0, voyage_international=False)
    assert o.voyage_international_suppose is False
    for nom in OBLIGATIONS:
        assert getattr(o, nom) is None, nom


def test_year_est_accepte_mais_n_influence_aucun_seuil():
    """Le navire est décrit par `year` comme demandé, mais aucun seuil de la table n'en
    dépend : deux navires identiques sauf par l'année obtiennent le même résultat."""
    ancien = obligations_navire(450.0, 60.0, 10, year=1990.0)
    recent = obligations_navire(450.0, 60.0, 10, year=2023.0)
    assert ancien == recent


# --- Les fonctions de commodité --------------------------------------------------------------


def test_obligations_applicables_ne_retient_que_les_true_confirmes():
    o = navire(gt=550.0, longueur=30.0, invites=20)
    applicables = obligations_applicables(o)
    assert applicables == {
        "IOPP",
        "ISPP",
        "IAPP",
        "IEE",
        "AFS_CERTIFICATE",
        "GARBAGE_MGMT_PLAN",
        "GARBAGE_RECORD_BOOK",
        "ISM",
    }
    # Au-dessus de 400 GT, c'est le certificat qui s'applique, pas la déclaration.
    assert "AFS_DECLARATION" not in applicables


def test_obligations_indeterminees_ne_retient_que_les_none():
    o = navire(gt=None, longueur=None, invites=None)
    assert obligations_indeterminees(o) == set(OBLIGATIONS)
    assert obligations_applicables(o) == set()


# --- L'arrêté mouillage Méditerranée --------------------------------------------------------


def test_mouillage_interdit_a_24_m_pile():
    """Seuil large ici, à la différence d'AFS_DECLARATION : *24 m ou plus*."""
    assert interdiction_mouillage_posidonies(24.0) is True


def test_mouillage_autorise_sous_24_m():
    assert interdiction_mouillage_posidonies(23.9) is False


def test_mouillage_indetermine_si_longueur_manquante():
    assert interdiction_mouillage_posidonies(None) is None
    assert interdiction_mouillage_posidonies(math.nan) is None


# --- La répartition sur un catalogue ---------------------------------------------------------


def test_repartir_obligations_denombre_les_trois_valeurs_par_obligation():
    df = pd.DataFrame(
        {
            "gross_tonnage": [200.0, 450.0, None, 600.0],
            "overall_length": [30.0, 60.0, 40.0, 80.0],
            "number_of_guests": [4, 10, 20, None],
        }
    )

    r = repartir_obligations(df)

    # IOPP : 200 -> False, 450 -> True, GT manquant -> indéterminé, 600 -> True
    assert r.loc["IOPP", "applicable"] == 2
    assert r.loc["IOPP", "non_applicable"] == 1
    assert r.loc["IOPP", "indetermine"] == 1
    assert r.loc["IOPP", "applicable_pct"] == pytest.approx(50.0)

    # ISPP : 200/4 -> False, 450/10 -> True, GT manquant/20 -> True (branche invités),
    # 600/invités manquant -> True (branche tonnage)
    assert r.loc["ISPP", "applicable"] == 3
    assert r.loc["ISPP", "indetermine"] == 0


def test_repartir_obligations_totalise_100_pour_cent_par_ligne():
    df = pd.DataFrame(
        {
            "gross_tonnage": [None, 50.0, 450.0],
            "overall_length": [30.0, 30.0, 30.0],
            "number_of_guests": [4, None, 4],
        }
    )
    r = repartir_obligations(df)
    totaux = r["applicable_pct"] + r["non_applicable_pct"] + r["indetermine_pct"]
    assert totaux.apply(lambda t: t == pytest.approx(100.0)).all()


# --- Le résultat sur le catalogue réel --------------------------------------------------------


def test_reconcilie_avec_le_catalogue_reel():
    """Compare aux chiffres du mémoire (9 218 navires ayant un tonnage connu). Un petit écart
    est attendu et volontaire, pas une erreur : le mémoire calculait ses pourcentages sur le
    seul sous-ensemble à tonnage connu, en traitant implicitement les invités manquants comme
    « pas plus de 15 ». Ce module traite les deux champs manquants honnêtement (indéterminé),
    sur l'effectif complet — d'où, par exemple, 1 820 ISPP confirmés ici contre 1 814 dans le
    mémoire : 6 navires sans tonnage connu ont malgré tout plus de 15 invités connus, ce que la
    méthode du mémoire ne pouvait pas voir puisqu'elle excluait d'emblée les tonnages manquants.
    """
    df = pd.read_parquet(CATALOGUE)
    assert len(df) == 9407

    r = repartir_obligations(df)

    assert r.loc["IOPP", "applicable"] == 1724
    assert r.loc["IAPP", "applicable"] == 1724
    assert r.loc["IEE", "applicable"] == 1724
    assert r.loc["AFS_CERTIFICATE", "applicable"] == 1724
    assert r.loc["ISPP", "applicable"] == 1820

    # GARBAGE_RECORD_BOOK et GARBAGE_MGMT_PLAN : mêmes seuils depuis MEPC.360(79) (2024-05-01),
    # donc même décompte -- 8 174, pas 1 820/8 172. Avant la correction du 2026-08-21, le
    # registre appliquait encore le seuil pré-2024 (400 GT au lieu de 100), d'où son ancien
    # compte proche de celui d'ISPP (1 820, même ordre de grandeur car même seuil GT) plutôt
    # que du plan de gestion. +2 sur le plan par rapport à l'ancien 8 172 : deux navires
    # certifiés pour EXACTEMENT 15 personnes, que le seuil strict >15 excluait à tort.
    assert r.loc["GARBAGE_RECORD_BOOK", "applicable"] == 8174
    assert r.loc["GARBAGE_MGMT_PLAN", "applicable"] == 8174

    # ISM : 926 -> 1 178 avec l'ajout de la voie « navire à passagers » (SOLAS IX/2 §1.1, sans
    # seuil GT) le 2026-08-21 -- 252 navires de moins de 500 GT mais transportant plus de 12
    # invités, invisibles de l'ancienne table qui ne testait que le tonnage.
    assert r.loc["ISM", "applicable"] == 1178

    # Navires échappant à tout le bloc certifié : le complément de ISPP.
    echappe = r.loc["ISPP", "non_applicable"]
    assert echappe == 6683

    mouillage = df["overall_length"].apply(interdiction_mouillage_posidonies)
    assert mouillage.eq(True).all()  # toutes les unités du catalogue font 24 m ou plus
