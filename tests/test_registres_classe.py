"""Les cas qui font la valeur de cette couche : décomposition des notations, confirmation par
second champ, distinction non-trouvé / trouvé-mais-vide, et politesse.

Aucun test ne touche le réseau : les réponses des trois registres sont rejouées telles qu'elles
ont été observées en vrai (voir la docstring du module pour la provenance de chaque exemple).
"""

import httpx
import pytest

from labs.registres_classe import (
    ClientEspace,
    Correspondance,
    DomaineIndisponible,
    apparier_dnv,
    apparier_lr,
    apparier_rina,
    confirmer,
    decomposer_notation,
    dnv_extraire_candidats,
    dnv_extraire_details,
    echantillon,
    lr_extraire_candidats,
    rina_extraire_candidats,
)

# --- Décomposition des notations : le cas qui distingue ce module d'un simple .split() -----


def test_notation_vide_donne_un_tuple_vide():
    assert decomposer_notation("") == ()


def test_notation_absente_donne_un_tuple_vide():
    assert decomposer_notation(None) == ()


def test_mots_simples_separes_par_des_espaces():
    assert decomposer_notation("AUT ERS") == ("AUT", "ERS")


def test_qualificatif_entre_parentheses_reste_colle_a_son_mot():
    """`Battery(Power)` n'a pas d'espace interne : un simple split le garde déjà groupé."""
    assert decomposer_notation("Battery(Power)") == ("Battery(Power)",)


def test_gas_fuelled_est_une_seule_notation_malgre_l_espace():
    """Le cas qui justifie `NOTATIONS_MULTI_MOTS` : la seule notation observée qui contient un
    espace au lieu d'une parenthèse collée."""
    assert decomposer_notation("Gas fuelled") == ("Gas fuelled",)


def test_qualificatif_avec_espace_interne_reste_un_seul_flux():
    """Cas réel du catalogue (A+, source DNV) : le qualificatif contient lui-même un espace.
    Une simple découpe sur les espaces couperait `TMON(oil` et `lubricated)` en deux flux."""
    assert decomposer_notation("E0 TMON(oil lubricated)") == (
        "E0",
        "TMON(oil lubricated)",
    )


def test_qualificatif_avec_virgule_et_deux_mots_internes_reste_un_seul_flux():
    """Cas réel (Deep Blue, source DNV) : virgule ET deux mots à l'intérieur des parenthèses."""
    assert decomposer_notation("ER(SCR, TIER III)") == ("ER(SCR, TIER III)",)


def test_decompose_la_chaine_reelle_de_havila_capella():
    """Exemple réel vérifié (voir la consigne) : neuf flux, dont un multi-mots."""
    chaine = "BIS Battery(Power) BWM(T) Clean(Design) COMF(V-2) E0 Gas fuelled NAUT(AW) Recyclable"
    assert decomposer_notation(chaine) == (
        "BIS",
        "Battery(Power)",
        "BWM(T)",
        "Clean(Design)",
        "COMF(V-2)",
        "E0",
        "Gas fuelled",
        "NAUT(AW)",
        "Recyclable",
    )


# --- Parsing DNV -----------------------------------------------------------------------------


def test_dnv_extrait_les_candidats_de_la_recherche():
    charge = {
        "vessels": [
            {
                "name": "AZZAM",
                "id": "G116098",
                "imoNo": "9693367",
                "classRelation": True,
            }
        ],
        "totalCount": 1,
    }
    assert dnv_extraire_candidats(charge) == [
        {"id": "G116098", "nom": "AZZAM", "imo": "9693367"}
    ]


def test_dnv_reponse_sans_navires_donne_une_liste_vide():
    assert dnv_extraire_candidats({"vessels": [], "totalCount": 0}) == []


def test_dnv_refuse_une_forme_inconnue_en_le_disant():
    with pytest.raises(ValueError, match="vessels"):
        dnv_extraire_candidats({"resultats": []})


def test_dnv_extrait_les_details_avec_la_distinction_design_operation():
    """Cas réel AZZAM : notation design non vide, notation en exploitation vide — un signal,
    pas une absence de donnée."""
    charge = {
        "identification": {"imoNumber": "9693367"},
        "classification": {
            "classNotationStringDesign": "AUT ERS",
            "classNotationStringInOperation": "",
        },
        "dimensions": {"lengthOverall": 180.61},
        "yard": {
            "dateOfBuild": "2013-10-22T13:00:00",
            "contractedBuilder": "Fr. Lürssen Werft GmbH & Co. KG",
        },
    }
    details = dnv_extraire_details(charge)
    assert details["imo"] == "9693367"
    assert details["notation_design"] == "AUT ERS"
    assert details["notation_operation"] == ""
    assert details["longueur"] == 180.61
    assert details["annee"] == 2013.0
    assert details["constructeur"] == "Fr. Lürssen Werft GmbH & Co. KG"


def test_dnv_details_sans_notation_en_exploitation_donne_none():
    """Si la clé elle-même est absente (source muette), c'est `None` — pas `""`."""
    charge = {
        "identification": {},
        "classification": {"classNotationStringDesign": "AUT"},
        "dimensions": {},
        "yard": {},
    }
    assert dnv_extraire_details(charge)["notation_operation"] is None


# --- Parsing LR ------------------------------------------------------------------------------


def test_lr_extrait_les_candidats_avec_annee_de_construction():
    charge = {
        "results": [
            {
                "shipName": "ECLIPSE",
                "imoNumber": "9897092",
                "dateOfBuild": "2022-01-07T00:00:00+00:00",
                "shipType": "LPG Tanker",
            }
        ],
        "count": 1,
    }
    assert lr_extraire_candidats(charge) == [
        {"nom": "ECLIPSE", "imo": "9897092", "annee": 2022.0, "type": "LPG Tanker"}
    ]


def test_lr_reponse_sans_resultats_donne_une_liste_vide():
    assert lr_extraire_candidats({"results": [], "count": 0}) == []


def test_lr_refuse_une_forme_inconnue_en_le_disant():
    with pytest.raises(ValueError, match="results"):
        lr_extraire_candidats({"hits": []})


# --- Parsing RINA ----------------------------------------------------------------------------


def test_rina_extrait_les_candidats_reels_ocean_victory():
    charge = {
        "resultType": 1,
        "result": {
            "records": [
                {
                    "nome": "OCEAN VICTORY",
                    "imo": "9868869",
                    "dataCompLavCant": "2021",
                    "lungStazza": "99.69",
                }
            ]
        },
        "customStatus": None,
    }
    assert rina_extraire_candidats(charge) == [
        {"nom": "OCEAN VICTORY", "imo": "9868869", "annee": 2021.0, "longueur": 99.69}
    ]


def test_rina_resulttype_erreur_donne_une_liste_vide_pas_une_exception():
    """Observé en vrai sur `shipDetail` : une exception serveur générique, jamais des
    candidats. On la traite comme une absence de résultat, pas comme une panne à remonter."""
    charge = {
        "resultType": 3,
        "result": {"errorMessage": "EJBTransactionRolledbackException"},
    }
    assert rina_extraire_candidats(charge) == []


def test_rina_refuse_une_forme_totalement_inconnue():
    with pytest.raises(ValueError, match="result"):
        rina_extraire_candidats({"autre_chose": []})


# --- Confirmation par second champ : le cœur de la méthode ---------------------------------


def test_annee_exacte_confirme():
    assert confirmer(2013.0, None, None, annee_source=2013.0) == ("annee",)


def test_annee_a_un_an_pres_confirme():
    assert confirmer(2013.0, None, None, annee_source=2014.0) == ("annee",)


def test_annee_a_deux_ans_ne_confirme_pas():
    assert confirmer(2013.0, None, None, annee_source=2015.0) == ()


def test_longueur_a_un_metre_pres_confirme():
    assert confirmer(None, 180.61, None, longueur_source=181.5) == ("longueur",)


def test_longueur_a_plus_d_un_metre_ne_confirme_pas():
    assert confirmer(None, 180.61, None, longueur_source=185.0) == ()


def test_constructeur_par_mot_significatif_partage_confirme():
    """Le cas réel AZZAM : le catalogue dit « Lürssen Yachts », DNV dit « Fr. Lürssen Werft
    GmbH & Co. KG » — aucune égalité de chaîne, mais un mot significatif partagé."""
    champs = confirmer(
        None,
        None,
        "Lürssen Yachts",
        constructeur_source="Fr. Lürssen Werft GmbH & Co. KG",
    )
    assert champs == ("constructeur",)


def test_constructeurs_sans_mot_significatif_partage_ne_confirme_pas():
    assert confirmer(None, None, "Lürssen Yachts", constructeur_source="Feadship") == ()


def test_suffixes_generiques_seuls_ne_confirment_jamais():
    """« Yachts » et « GmbH » ne discriminent rien : deux constructeurs différents qui les
    partagent tous les deux ne doivent pas être pris pour une concordance."""
    assert (
        confirmer(None, None, "Sunseeker Yachts", constructeur_source="Feadship GmbH")
        == ()
    )


def test_plusieurs_champs_concordants_sont_tous_rapportes():
    champs = confirmer(
        2013.0, 180.61, "Lürssen", annee_source=2013.0, longueur_source=180.0
    )
    assert champs == ("annee", "longueur")


def test_champ_absent_cote_source_n_empeche_pas_les_autres_de_confirmer():
    """LR ne fournit ni longueur ni constructeur : leur absence ne doit ni confirmer ni
    invalider, seulement ne rien ajouter."""
    champs = confirmer(2013.0, 180.61, "Lürssen", annee_source=2013.0)
    assert champs == ("annee",)


def test_aucun_champ_concordant_rejette():
    assert confirmer(2013.0, 180.61, "Lürssen", annee_source=1990.0) == ()


# --- Le flux complet, source par source, avec un client en mémoire -------------------------


class ReponseFactice:
    def __init__(self, charge):
        self._charge = charge

    def json(self):
        return self._charge

    def raise_for_status(self):
        return None


class _ReponseAvecStatut:
    """Une fausse réponse HTTP porteuse d'un vrai `status_code`, pour exercer le repli
    exponentiel et le disjoncteur de `ClientEspace` — `ReponseFactice` n'en a pas besoin."""

    def __init__(self, status_code, charge=None):
        self.status_code = status_code
        self._charge = charge

    def json(self):
        return self._charge

    def raise_for_status(self):
        if self.status_code >= 400:
            requete = httpx.Request("GET", "https://exemple.test")
            reponse = httpx.Response(self.status_code, request=requete)
            raise httpx.HTTPStatusError(
                str(self.status_code), request=requete, response=reponse
            )


class ClientFactice:
    """Sert des réponses préparées, indexées par URL, et retient les appels reçus."""

    def __init__(self, reponses):
        self.reponses = reponses
        self.appels = []

    def get(self, url, params=None, headers=None):
        self.appels.append(("GET", url, params, headers))
        return ReponseFactice(self.reponses[url])

    def post(self, url, json=None):
        self.appels.append(("POST", url, json))
        return ReponseFactice(self.reponses[url])


NAVIRE_AZZAM = {
    "id": "68f69fa0adb3c78f27886520",
    "name": "Azzam",
    "year": 2013.0,
    "overall_length": 180.61,
    "builder": "Lürssen Yachts",
}


def test_apparier_dnv_confirme_et_decompose():
    from labs.registres_classe import DNV_BASE

    client = ClientFactice(
        {
            f"{DNV_BASE}/vessel/get": {
                "vessels": [{"name": "AZZAM", "id": "G116098", "imoNo": "9693367"}]
            },
            f"{DNV_BASE}/vesseldetails": {
                "identification": {"imoNumber": "9693367"},
                "classification": {
                    "classNotationStringDesign": "AUT ERS",
                    "classNotationStringInOperation": "",
                },
                "dimensions": {"lengthOverall": 180.61},
                "yard": {
                    "dateOfBuild": "2013-10-22T13:00:00",
                    "contractedBuilder": "Fr. Lürssen Werft GmbH & Co. KG",
                },
            },
        }
    )

    resultat = apparier_dnv(client, NAVIRE_AZZAM, "2026-08-17")

    assert isinstance(resultat, Correspondance)
    assert resultat.confiance == "confirme"
    assert resultat.imo == "9693367"
    assert resultat.notation_operation_brute == ""  # vide, pas None : un vrai résultat
    assert resultat.flux_design == ("AUT", "ERS")
    assert resultat.flux_operation == ()
    assert set(resultat.champs_confirmes) == {"annee", "longueur", "constructeur"}


def test_apparier_dnv_sans_candidat_renvoie_none():
    from labs.registres_classe import DNV_BASE

    client = ClientFactice({f"{DNV_BASE}/vessel/get": {"vessels": []}})

    assert apparier_dnv(client, NAVIRE_AZZAM, "2026-08-17") is None


def test_apparier_dnv_candidat_non_confirme_est_rejete_pas_exclu():
    """Un candidat trouvé par nom mais dont aucun champ ne concorde doit apparaître avec
    `confiance="rejete"`, jamais être traité comme si de rien n'était trouvé."""
    from labs.registres_classe import DNV_BASE

    autre_navire = {
        **NAVIRE_AZZAM,
        "year": 1990.0,
        "overall_length": 12.0,
        "builder": "Inconnu",
    }
    client = ClientFactice(
        {
            f"{DNV_BASE}/vessel/get": {
                "vessels": [{"name": "AZZAM", "id": "G116098", "imoNo": "9693367"}]
            },
            f"{DNV_BASE}/vesseldetails": {
                "identification": {"imoNumber": "9693367"},
                "classification": {},
                "dimensions": {"lengthOverall": 180.61},
                "yard": {
                    "dateOfBuild": "2013-10-22T13:00:00",
                    "contractedBuilder": "Fr. Lürssen Werft GmbH & Co. KG",
                },
            },
        }
    )

    resultat = apparier_dnv(client, autre_navire, "2026-08-17")

    assert resultat.confiance == "rejete"
    assert resultat.imo is None
    assert resultat.champs_confirmes == ()


def test_apparier_filtre_les_homonymes_partiels_avant_toute_confirmation():
    """« Eclipse » retrouve chez LR un pétrolier GPL ET un paquebot nommés différemment
    (« ECLIPSE » et « CELEBRITY ECLIPSE ») : seul le nom strictement égal doit être considéré
    comme un candidat — le paquebot ne doit jamais entrer en confirmation."""
    from labs.registres_classe import LR_URL

    navire = {
        "id": "x",
        "name": "Eclipse",
        "year": 2022.0,
        "overall_length": None,
        "builder": None,
    }
    client = ClientFactice(
        {
            LR_URL: {
                "results": [
                    {
                        "shipName": "ECLIPSE",
                        "imoNumber": "9897092",
                        "dateOfBuild": "2022-01-07T00:00:00+00:00",
                        "shipType": "LPG Tanker",
                    },
                    {
                        "shipName": "CELEBRITY ECLIPSE",
                        "imoNumber": "9404314",
                        "dateOfBuild": "2010-04-15T00:00:00+00:00",
                        "shipType": "Passenger / Cruise",
                    },
                ]
            }
        }
    )

    resultat = apparier_lr(client, navire, "2026-08-17")

    assert resultat.confiance == "confirme"
    assert resultat.imo == "9897092"  # le candidat au nom exact, jamais le paquebot


def test_apparier_rina_sans_candidat_renvoie_none():
    from labs.registres_classe import RINA_SHIPS_URL

    client = ClientFactice(
        {RINA_SHIPS_URL: {"resultType": 1, "result": {"records": []}}}
    )
    navire = {
        "id": "x",
        "name": "Falkor (Too)",
        "year": 2011.0,
        "overall_length": 110.6,
    }

    assert apparier_rina(client, navire, "2026-08-17") is None


def test_apparier_rina_ne_renvoie_jamais_de_notation():
    """`shipDetail` est inaccessible (voir la docstring du module) : même confirmé, un
    résultat RINA n'a pas de notation — `None`, pas une chaîne vide inventée."""
    from labs.registres_classe import RINA_SHIPS_URL

    navire = {
        "id": "x",
        "name": "Ocean Victory",
        "year": 2021.0,
        "overall_length": 99.69,
    }
    client = ClientFactice(
        {
            RINA_SHIPS_URL: {
                "resultType": 1,
                "result": {
                    "records": [
                        {
                            "nome": "OCEAN VICTORY",
                            "imo": "9868869",
                            "dataCompLavCant": "2021",
                            "lungStazza": "99.69",
                        }
                    ]
                },
            }
        }
    )

    resultat = apparier_rina(client, navire, "2026-08-17")

    assert resultat.confiance == "confirme"
    assert resultat.imo == "9868869"
    assert resultat.notation_design_brute is None
    assert resultat.flux_design == ()


# --- Le contrat de politesse : un client par domaine, espacé de ses propres appels ---------


def test_client_espace_respecte_le_delai_entre_deux_appels():
    horloges = iter(
        [0.0, 0.3, 0.3]
    )  # premier appel, deuxième appel avant délai, après pause
    pauses = []

    class ClientHttpFactice:
        def get(self, url, params=None, headers=None):
            return ReponseFactice({"vessels": []})

    client = ClientEspace(
        ClientHttpFactice(),
        delai=1.0,
        pause=pauses.append,
        horloge=lambda: next(horloges),
    )

    client.get("https://vesselregister.dnv.com/vesselregister/vessel/get")
    client.get("https://vesselregister.dnv.com/vesselregister/vessel/get")

    assert pauses == [0.7]  # 1.0 - (0.3 - 0.0)


def test_client_espace_ne_pause_pas_si_le_delai_est_deja_ecoule():
    horloges = iter(
        [0.0, 5.0, 5.0]
    )  # deux lectures au 2e appel : écoulé, puis nouveau repère
    pauses = []

    class ClientHttpFactice:
        def get(self, url, params=None, headers=None):
            return ReponseFactice({"vessels": []})

    client = ClientEspace(
        ClientHttpFactice(),
        delai=1.0,
        pause=pauses.append,
        horloge=lambda: next(horloges),
    )

    client.get("https://vesselregister.dnv.com/vesselregister/vessel/get")
    client.get("https://vesselregister.dnv.com/vesselregister/vessel/get")

    assert pauses == []


# --- Résilience du transport : repli exponentiel puis disjoncteur --------------------------


def test_repli_exponentiel_reussit_apres_deux_echecs_5xx():
    """Le cas réel : un 500 ponctuel de Lloyd's Register, absorbé par un nouvel essai."""
    reponses = iter(
        [
            _ReponseAvecStatut(500),
            _ReponseAvecStatut(500),
            _ReponseAvecStatut(200, charge={"vessels": []}),
        ]
    )
    pauses = []
    # Toujours largement au-delà de `delai` : isole les pauses du repli de celles, distinctes,
    # de l'espacement entre requêtes (`_attendre`), sans quoi les deux s'entremêleraient.
    horloges = iter(i * 100.0 for i in range(20))

    class ClientHttpFactice:
        def get(self, url, params=None, headers=None):
            return next(reponses)

    client = ClientEspace(
        ClientHttpFactice(),
        delai=1.0,
        pause=pauses.append,
        horloge=lambda: next(horloges),
        tentatives_max=3,
        delai_base_reessai=2.0,
    )

    reponse = client.get("https://vesselregister.dnv.com/vesselregister/vessel/get")

    assert reponse.json() == {"vessels": []}
    assert pauses == [2.0, 4.0]  # repli qui double : 2s puis 4s
    assert client.circuit_ouvert is False  # un succès in fine remet le compteur à zéro


def test_repli_exponentiel_abandonne_apres_tentatives_max():
    reponses = iter([_ReponseAvecStatut(500)] * 3)

    class ClientHttpFactice:
        def get(self, url, params=None, headers=None):
            return next(reponses)

    client = ClientEspace(
        ClientHttpFactice(),
        delai=1.0,
        pause=lambda _: None,
        horloge=lambda: 0.0,
        tentatives_max=3,
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://vesselregister.dnv.com/vesselregister/vessel/get")


def test_le_disjoncteur_s_ouvre_apres_le_seuil_d_echecs_consecutifs():
    """Après `seuil_echecs_consecutifs` appels totalement épuisés, le domaine est mis en
    pause : plus aucune requête réseau, jamais — mieux vaut renoncer que marteler un service
    qui s'effondre."""
    appels = []

    class ClientHttpFactice:
        def get(self, url, params=None, headers=None):
            appels.append(url)
            return _ReponseAvecStatut(500)

    client = ClientEspace(
        ClientHttpFactice(),
        delai=1.0,
        pause=lambda _: None,
        horloge=lambda: 0.0,
        tentatives_max=1,  # une seule tentative par appel, pour isoler le compteur d'échecs
        seuil_echecs_consecutifs=2,
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://exemple.test")
    assert client.circuit_ouvert is False  # un seul échec : pas encore ouvert

    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://exemple.test")
    assert client.circuit_ouvert is True  # deuxième échec consécutif : seuil atteint

    nombre_avant = len(appels)
    with pytest.raises(DomaineIndisponible):
        client.get("https://exemple.test")
    assert (
        len(appels) == nombre_avant
    )  # aucun appel réseau supplémentaire une fois ouvert


def test_un_succes_reinitialise_le_compteur_d_echecs_consecutifs():
    sequence = iter(
        [_ReponseAvecStatut(500), _ReponseAvecStatut(200, charge={"vessels": []})]
    )

    class ClientHttpFactice:
        def get(self, url, params=None, headers=None):
            return next(sequence)

    client = ClientEspace(
        ClientHttpFactice(),
        delai=1.0,
        pause=lambda _: None,
        horloge=lambda: 0.0,
        tentatives_max=1,
        seuil_echecs_consecutifs=2,
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://exemple.test")  # 1er échec
    client.get("https://exemple.test")  # succès : remet le compteur à zéro

    assert client._echecs_consecutifs == 0
    assert client.circuit_ouvert is False


# --- Reprise : ne jamais refaire un couple (navire, source) déjà collecté ------------------


def test_collecter_saute_les_couples_deja_faits():
    import pandas as pd

    from labs.registres_classe import collecter

    navires = pd.DataFrame(
        [
            {
                "id": "y1",
                "name": "Bateau Un",
                "year": 2020.0,
                "overall_length": 40.0,
                "builder": None,
            }
        ]
    )

    class ClientQuiNeDoitJamaisEtreAppele:
        def get(self, *a, **k):
            raise AssertionError(
                "un couple déjà fait ne doit déclencher aucun appel réseau"
            )

        def post(self, *a, **k):
            raise AssertionError(
                "un couple déjà fait ne doit déclencher aucun appel réseau"
            )

    resultats, non_trouves, erreurs = collecter(
        {"dnv": ClientQuiNeDoitJamaisEtreAppele()},
        navires,
        journal=lambda _: None,
        deja_fait={("y1", "dnv")},
    )

    assert resultats == []
    assert non_trouves == {"dnv": 0}
    assert erreurs == {"dnv": 0}


# --- La vue réutilisable : yacht_id -> IMO --------------------------------------------------


def test_imo_confirmes_ne_garde_que_les_confirmes_avec_imo():
    import pandas as pd

    from labs.registres_classe import imo_confirmes

    df = pd.DataFrame(
        [
            {"yacht_id": "y1", "source": "dnv", "confiance": "confirme", "imo": "111"},
            {"yacht_id": "y2", "source": "dnv", "confiance": "rejete", "imo": None},
            {"yacht_id": "y3", "source": "dnv", "confiance": "confirme", "imo": None},
        ]
    )

    resultat = imo_confirmes(df)

    assert dict(resultat) == {"y1": "111"}


def test_imo_confirmes_ne_duplique_pas_un_navire_confirme_par_deux_sources():
    import pandas as pd

    from labs.registres_classe import imo_confirmes

    df = pd.DataFrame(
        [
            {"yacht_id": "y1", "source": "dnv", "confiance": "confirme", "imo": "111"},
            {"yacht_id": "y1", "source": "lr", "confiance": "confirme", "imo": "111"},
        ]
    )

    resultat = imo_confirmes(df)

    assert len(resultat) == 1
    assert resultat["y1"] == "111"


# --- Échantillonnage : au-delà des seuls navires déjà tagués DNV ---------------------------


def test_echantillon_inclut_tous_les_navires_deja_tagues():
    import pandas as pd

    df = pd.DataFrame(
        {
            "id": [f"y{i}" for i in range(10)],
            "name": [f"Bateau {i}" for i in range(10)],
            "vessel_class": ["Det Norske Veritas (DNV)"] * 3 + [None] * 7,
        }
    )

    resultat = echantillon(df, taille=2, graine=1)

    assert (resultat["vessel_class"] == "Det Norske Veritas (DNV)").sum() == 3
    assert len(resultat) == 5  # 3 tagués + 2 tirés au sort


def test_echantillon_est_reproductible_a_graine_fixe():
    import pandas as pd

    df = pd.DataFrame(
        {
            "id": [f"y{i}" for i in range(20)],
            "name": [f"B{i}" for i in range(20)],
            "vessel_class": [None] * 20,
        }
    )

    a = echantillon(df, taille=5, graine=42)
    b = echantillon(df, taille=5, graine=42)

    assert list(a["id"]) == list(b["id"])


# --- Résilience réseau : un 500 ponctuel ne doit pas coûter toute la collecte --------------


class ClientQuiEchoueUneFois:
    """Lève une `httpx.HTTPStatusError` sur son premier appel, répond normalement ensuite.

    Rejoue en mémoire la panne réelle survenue en collecte : un 500 ponctuel de Lloyd's
    Register, qui a fait perdre plusieurs minutes de collecte déjà faite avant la correction.
    """

    def __init__(self, reponse_normale):
        self._reponse_normale = reponse_normale
        self.appels = 0

    def _echouer(self):
        requete = httpx.Request("POST", "https://exemple.test")
        reponse = httpx.Response(500, request=requete)
        raise httpx.HTTPStatusError("500", request=requete, response=reponse)

    def get(self, url, params=None, headers=None):
        self.appels += 1
        if self.appels == 1:
            self._echouer()
        return ReponseFactice(self._reponse_normale)

    def post(self, url, json=None):
        self.appels += 1
        if self.appels == 1:
            self._echouer()
        return ReponseFactice(self._reponse_normale)


def test_collecter_survit_a_une_erreur_reseau_et_traite_le_navire_suivant():
    import pandas as pd

    from labs.registres_classe import collecter

    navires = pd.DataFrame(
        [
            {
                "id": "y1",
                "name": "Bateau Un",
                "year": 2020.0,
                "overall_length": 40.0,
                "builder": None,
            },
            {
                "id": "y2",
                "name": "Bateau Deux",
                "year": 2020.0,
                "overall_length": 40.0,
                "builder": None,
            },
        ]
    )
    clients = {"dnv": ClientQuiEchoueUneFois({"vessels": []})}

    resultats, non_trouves, erreurs = collecter(
        clients, navires, journal=lambda _: None
    )

    assert erreurs == {"dnv": 1}  # le premier appel (Bateau Un) a échoué...
    assert non_trouves == {
        "dnv": 1
    }  # ...mais le second (Bateau Deux) a bien été traité
    assert resultats == []


def test_collecter_distingue_erreurs_non_trouves_et_resultats():
    """Trois compteurs pour trois absences différentes — jamais l'une confondue avec une autre."""
    import pandas as pd

    from labs.registres_classe import DNV_BASE, collecter

    navires = pd.DataFrame(
        [
            {
                "id": "y1",
                "name": "AZZAM",
                "year": 2013.0,
                "overall_length": 180.61,
                "builder": None,
            }
        ]
    )
    client = ClientFactice(
        {
            f"{DNV_BASE}/vessel/get": {
                "vessels": [{"name": "AZZAM", "id": "G1", "imoNo": "9693367"}]
            },
            f"{DNV_BASE}/vesseldetails": {
                "identification": {"imoNumber": "9693367"},
                "classification": {},
                "dimensions": {"lengthOverall": 180.61},
                "yard": {},
            },
        }
    )

    resultats, non_trouves, erreurs = collecter(
        {"dnv": client}, navires, journal=lambda _: None
    )

    assert len(resultats) == 1
    assert resultats[0].confiance == "confirme"
    assert non_trouves == {"dnv": 0}
    assert erreurs == {"dnv": 0}
