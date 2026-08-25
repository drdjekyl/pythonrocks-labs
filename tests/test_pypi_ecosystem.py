"""Aucun test ne touche le réseau : les réponses sont rejouées comme des objets en mémoire,
exactement le format réel observé (voir la docstring du module pour la provenance).
"""

from datetime import date

import pytest

from labs.pypi_ecosystem import (
    BASELINE,
    CATEGORIES,
    PACKAGES,
    ClientPoli,
    extraire_releases,
    extraire_sans_mirroir,
    telecharger_historique,
)


class ReponseFactice:
    def __init__(self, charge, status_code=200):
        self._charge = charge
        self.status_code = status_code

    def json(self):
        return self._charge

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"statut {self.status_code}")


class ClientFactice:
    """Sert des réponses préparées, une par appel, et retient les URL demandées."""

    def __init__(self, reponses):
        self._reponses = list(reponses)
        self.appels: list[str] = []

    def get(self, url, headers=None):
        self.appels.append(url)
        return self._reponses.pop(0)


# --- Le catalogue des 51 paquets ----------------------------------------------------------


def test_51_paquets_repartis_sur_trois_groupes_disjoints():
    assert len(PACKAGES) == 51
    groupes = list(CATEGORIES.values())
    for i, a in enumerate(groupes):
        for b in groupes[i + 1 :]:
            assert not set(a) & set(b), (
                "un paquet appartient à deux catégories à la fois"
            )


def test_baseline_fait_partie_des_paquets_collectes():
    assert BASELINE in PACKAGES
    assert BASELINE in CATEGORIES["etabli"]


# --- pypistats.org : extraction sans_mirroir ------------------------------------------------


def test_extraire_sans_mirroir_ne_garde_que_without_mirrors():
    charge = {
        "data": [
            {"category": "with_mirrors", "date": "2026-01-01", "downloads": 100},
            {"category": "without_mirrors", "date": "2026-01-01", "downloads": 80},
        ]
    }
    lignes = extraire_sans_mirroir(charge)
    assert lignes == [
        {"category": "without_mirrors", "date": "2026-01-01", "downloads": 80}
    ]


def test_extraire_sans_mirroir_leve_sans_cle_data():
    with pytest.raises(ValueError, match="data"):
        extraire_sans_mirroir({"package": "x"})


def test_extraire_sans_mirroir_leve_si_aucune_ligne_without_mirrors():
    with pytest.raises(ValueError, match="without_mirrors"):
        extraire_sans_mirroir(
            {"data": [{"category": "with_mirrors", "date": "x", "downloads": 1}]}
        )


def test_telecharger_historique_normalise_en_minuscules_et_trie_les_colonnes():
    charge = {
        "data": [
            {"category": "without_mirrors", "date": "2026-01-02", "downloads": 200},
            {"category": "without_mirrors", "date": "2026-01-01", "downloads": 100},
            {"category": "with_mirrors", "date": "2026-01-01", "downloads": 999},
        ]
    }
    client = ClientFactice([ReponseFactice(charge)])
    df = telecharger_historique(client, "Requests")
    assert list(df.columns) == ["package", "date", "downloads"]
    assert (df["package"] == "requests").all()
    assert len(df) == 2


# --- pypi.org/pypi/<paquet>/json : métadonnées de release ------------------------------------


def test_extraire_releases_prend_min_max_sur_les_fichiers_avec_horodatage():
    charge = {
        "releases": {
            "1.0.1": [],  # version sans fichier : ne doit compter ni comme release ni comme date
            "1.0.2": [{"upload_time_iso_8601": "2020-01-01T00:00:00.000000Z"}],
            "1.1.0": [
                {"upload_time_iso_8601": "2020-06-01T00:00:00.000000Z"},
                {"upload_time_iso_8601": "2020-06-01T01:00:00.000000Z"},
            ],
        }
    }
    resultat = extraire_releases(charge, "paquet", date(2026, 1, 1))
    assert resultat["n_releases"] == 2  # 1.0.1 ne compte pas, elle n'a aucun fichier
    assert resultat["first_release"] == date(2020, 1, 1)
    assert resultat["last_release"] == date(2020, 6, 1)
    assert resultat["reference_date"] == date(2026, 1, 1)


def test_extraire_releases_indetermine_si_aucun_fichier_nulle_part():
    resultat = extraire_releases({"releases": {"0.1": []}}, "paquet", date(2026, 1, 1))
    assert resultat["n_releases"] == 0
    assert resultat["first_release"] is None
    assert resultat["last_release"] is None


# --- ClientPoli : espacement, repli exponentiel, statuts non retentables -------------------


def test_client_poli_espace_les_appels_d_au_moins_delai():
    horloge = {"t": 0.0}
    pauses = []

    def pause(secondes):
        pauses.append(secondes)
        horloge["t"] += secondes

    class ClientBrutFactice:
        def get(self, url, headers=None):
            return ReponseFactice({"ok": True})

    client = ClientPoli(
        ClientBrutFactice(),
        delai=2.0,
        statuts_reessayables=frozenset({429}),
        pause=pause,
        horloge=lambda: horloge["t"],
    )
    client.get("https://x/1")
    horloge["t"] += 0.5  # à peine 0,5 s écoulée avant le second appel
    client.get("https://x/2")
    assert pauses == [1.5]  # complète jusqu'au délai de 2 s, jamais moins


def test_client_poli_retente_sur_statut_reessayable_puis_reussit():
    class ClientBrutFactice:
        def __init__(self):
            self.appels = 0

        def get(self, url, headers=None):
            self.appels += 1
            if self.appels < 3:
                return ReponseFactice({}, status_code=429)
            return ReponseFactice({"ok": True}, status_code=200)

    brut = ClientBrutFactice()
    client = ClientPoli(
        brut,
        delai=0.0,
        statuts_reessayables=frozenset({429}),
        pause=lambda s: None,
        horloge=lambda: 0.0,
    )
    reponse = client.get("https://x")
    assert reponse.status_code == 200
    assert brut.appels == 3


def test_client_poli_leve_apres_tentatives_epuisees():
    class ClientBrutFactice:
        def get(self, url, headers=None):
            return ReponseFactice({}, status_code=429)

    client = ClientPoli(
        ClientBrutFactice(),
        delai=0.0,
        statuts_reessayables=frozenset({429}),
        pause=lambda s: None,
        horloge=lambda: 0.0,
        tentatives_max=2,
    )
    with pytest.raises(RuntimeError, match="tentatives épuisées"):
        client.get("https://x")


def test_client_poli_ne_retente_pas_un_statut_hors_liste():
    """Un 404 sur un des 51 paquets choisis à la main est une vraie anomalie : elle doit
    remonter immédiatement, pas se perdre dans des tentatives inutiles."""

    class ClientBrutFactice:
        def __init__(self):
            self.appels = 0

        def get(self, url, headers=None):
            self.appels += 1
            return ReponseFactice({}, status_code=404)

    brut = ClientBrutFactice()
    client = ClientPoli(
        brut,
        delai=0.0,
        statuts_reessayables=frozenset({429}),
        pause=lambda s: None,
        horloge=lambda: 0.0,
    )
    reponse = client.get("https://x")
    assert reponse.status_code == 404
    assert brut.appels == 1
