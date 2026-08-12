"""Chaque test correspond à une panne qui a réellement eu lieu.

Aucun ne touche le réseau : le client est un objet en mémoire de quelques lignes. La suite
s'exécute en quelques millisecondes, ce qui est la condition pour qu'on la lance vraiment.
"""

import pytest

from labs.yachts import PAGE_SIZE, Client, extraire, recuperer


class ReponseFactice:
    def __init__(self, charge, total=0):
        self._charge = charge
        self.headers = {"X-Total-Count": str(total)}

    def json(self):
        return self._charge

    def raise_for_status(self):
        return None


class ClientFactice:
    """Sert des pages préparées et retient les appels reçus."""

    def __init__(self, pages, total=None):
        self.pages = pages
        self.total = len(pages) * PAGE_SIZE if total is None else total
        self.appels = []

    def get(self, url, params):
        self.appels.append((url, params))
        index = params["page"] - 1
        charge = self.pages[index] if index < len(self.pages) else {"items": []}
        return ReponseFactice(charge, self.total)


def navires(n, depart=0):
    return [{"id": f"y{i + depart}", "name": f"Bateau {i + depart}"} for i in range(n)]


# --- Panne n°1 : l'objet confondu avec un tableau -----------------------------------------


def test_extrait_les_items_et_non_les_cles():
    """Le bug qui a coûté le plus cher : `extend()` sur un dict empile ses clés.

    Sans ce test, la régression est indolore — aucune exception, juste un script lent.
    """
    charge = {"total": 9407, "page": 1, "page_size": 100, "items": navires(2)}

    resultat = extraire(charge)

    assert resultat == navires(2)
    assert resultat != sorted(charge)  # ce que renvoyait la version fautive


def test_accepte_aussi_un_tableau_nu():
    """`/yachts/random` renvoie bien une liste : les deux formes coexistent dans cette API."""
    assert extraire(navires(3)) == navires(3)


def test_refuse_une_forme_inconnue_en_le_disant():
    with pytest.raises(ValueError, match="items"):
        extraire({"total": 9407, "resultats": []})

    with pytest.raises(TypeError, match="inattendue"):
        extraire("9407 navires")


# --- Panne n°2 : la boucle qui ne s'arrête jamais -----------------------------------------


def test_s_arrete_au_total_annonce():
    client = ClientFactice([{"items": navires(PAGE_SIZE, i * PAGE_SIZE)} for i in range(3)])

    lignes = recuperer(client, journal=lambda _: None, pause=lambda _: None)

    assert len(lignes) == 3 * PAGE_SIZE
    assert len(client.appels) == 3  # pas une requête de plus


def test_s_arrete_sur_une_page_vide():
    client = ClientFactice([{"items": navires(PAGE_SIZE)}, {"items": []}], total=10_000)

    lignes = recuperer(client, journal=lambda _: None, pause=lambda _: None)

    assert len(lignes) == PAGE_SIZE


def test_echoue_plutot_que_de_boucler_indefiniment():
    """Si l'API annonce un total qu'elle n'atteint jamais, on s'arrête en le disant.

    C'est le mode de défaillance qui a réellement eu lieu : une boucle qui tourne des milliers
    de fois sans erreur, dont le seul symptôme est la lenteur.
    """
    client = ClientFactice([{"items": navires(1)}] * 20, total=1_000_000)

    with pytest.raises(RuntimeError, match="sans atteindre le total"):
        recuperer(client, journal=lambda _: None, pause=lambda _: None, page_max=10)


# --- Panne n°3 : l'absence de progression -------------------------------------------------


def test_signale_sa_progression_a_chaque_page():
    """Sans progression, un script long est indébogable — c'est ce qui a masqué la panne n°1."""
    client = ClientFactice([{"items": navires(PAGE_SIZE, i * PAGE_SIZE)} for i in range(3)])
    lignes_journal = []

    recuperer(client, journal=lignes_journal.append, pause=lambda _: None)

    assert any("navires à récupérer" in m for m in lignes_journal)
    assert sum(m.startswith("  page") for m in lignes_journal) == 3


# --- Le contrat de politesse --------------------------------------------------------------


def test_respecte_le_delai_entre_deux_pages():
    """La limite est de 60 requêtes/minute et l'API héberge aussi le site vitrine."""
    client = ClientFactice([{"items": navires(PAGE_SIZE, i * PAGE_SIZE)} for i in range(3)])
    pauses = []

    recuperer(client, journal=lambda _: None, pause=pauses.append)

    assert len(pauses) == 2  # pas de pause après la dernière page
    assert all(p >= 1.0 for p in pauses)


def test_le_client_reel_declare_un_agent_utilisateur():
    """Cloudflare renvoie 403 sur l'agent par défaut d'urllib — et se déclarer est la
    politesse minimale quand on interroge l'API de quelqu'un d'autre en boucle."""
    from labs.yachts import AGENT

    assert "pythonrocks-labs" in AGENT
    assert "github.com" in AGENT


def test_le_protocole_client_suffit_a_faire_tourner_la_recuperation():
    """La couture tient : un objet de quelques lignes remplace httpx sans rien adapter."""
    assert isinstance(ClientFactice([]), Client)
