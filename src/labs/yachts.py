"""Récupération du jeu de données yachts depuis l'API publique, vers Parquet.

9 407 navires, servis par pages de 100 au maximum — soit 95 requêtes. L'API applique une
limite de 60 requêtes par minute et par IP, et elle héberge aussi le site vitrine : on ne la
sature pas pour gagner trente secondes.

Le fichier Parquet produit est versionné dans ce dépôt. Les analyses des articles partent de
lui, pas du live : elles restent reproductibles à l'identique dans six mois, et le lecteur qui
exécute un notebook ne déclenche pas 95 requêtes chez quelqu'un d'autre.

## Trois pannes réelles, et pourquoi elles ont coûté si cher

Ce module a d'abord été écrit d'un bloc : une fonction, une boucle, un `urlopen`. Il
marchait. Il a quand même coûté une heure, pour trois raisons dont aucune n'était difficile.

1. **403 de Cloudflare** sur l'agent par défaut d'`urllib`. Diagnostic immédiat, correctif
   d'une ligne.
2. **`/yachts` renvoie un objet `{total, page, page_size, items}`, pas un tableau** —
   contrairement à `/yachts/random`. `extend()` sur un dict empile ses *clés* : la boucle
   tournait 2 352 fois au lieu de 95, sans lever la moindre erreur. Seul symptôme : un script
   anormalement lent.
3. **Aucune progression visible**, faute de `flush` : impossible de voir où il en était.

Le troisième défaut est ce qui a rendu le deuxième si coûteux. Sans progression, sans moyen
d'interroger une seule page isolément, j'ai cherché la lenteur du côté du réseau — et j'ai
« corrigé » en remplaçant `urllib` par un client `httpx` réutilisé, en attribuant les 11 s par
page à des poignées de main TLS. **Ce diagnostic était faux** et ce correctif n'a rien changé :
une page répond en 0,06 s, la lenteur venait des 2 352 tours de boucle. La version précédente
de ce fichier affirmait le contraire ; c'est corrigé ici.

La leçon n'est pas « il fallait mieux lire la documentation ». C'est qu'un script sans
coutures ne se laisse pas interroger : on ne pouvait pas demander « que renvoie une page ? »
sans lancer les 95. Le découpage ci-dessous n'est pas cosmétique — il rend chacune de ces trois
pannes vérifiable par un test qui ne touche pas au réseau.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
import pandas as pd

API = "https://api.pythonrocks.academy/yachts"
PAGE_SIZE = 100
DELAI = 1.05  # secondes entre deux requêtes -> ~57/min, sous la limite de 60
AGENT = "pythonrocks-labs/0.1 (+https://github.com/drdjekyl/pythonrocks-labs)"
SORTIE = Path(__file__).resolve().parents[2] / "data" / "yachts.parquet"


class Page(Protocol):
    """Ce qu'on attend d'une réponse HTTP — et rien de plus.

    Déclarer le strict nécessaire plutôt que de dépendre de `httpx.Response` permet aux tests
    de fournir un objet de trois lignes. C'est la couture qui rend le reste vérifiable.
    """

    def json(self) -> Any: ...
    def raise_for_status(self) -> Any: ...


@runtime_checkable
class Client(Protocol):
    def get(self, url: str, params: dict[str, Any]) -> Page: ...


def extraire(charge: Any) -> list[dict]:
    """Renvoie les navires d'une réponse d'API, ou échoue en le disant.

    C'est ici qu'a vécu la panne la plus coûteuse : `/yachts` renvoie un objet, pas un
    tableau, et confondre les deux n'a levé aucune erreur — `extend()` sur un dict empile ses
    clés. On lève désormais explicitement, parce qu'une forme inattendue doit s'arrêter net et
    non dégénérer en boucle lente.
    """
    if isinstance(charge, dict):
        if "items" not in charge:
            raise ValueError(f"réponse sans clé 'items' : {sorted(charge)}")
        return charge["items"]
    if isinstance(charge, list):
        return charge
    raise TypeError(f"réponse inattendue : {type(charge).__name__}")


def recuperer(
    client: Client,
    journal: Callable[[str], None] = print,
    pause: Callable[[float], None] = time.sleep,
    page_max: int = 500,
) -> list[dict]:
    """Parcourt les pages jusqu'au total annoncé par `X-Total-Count`.

    Le client, le journal et la pause sont injectés : un test fournit un client en mémoire, un
    journal qui accumule, une pause qui ne dort pas — et la suite s'exécute en millisecondes
    sans réseau.

    `page_max` est un garde-fou, pas un paramètre de réglage : une API qui annonce un total
    qu'elle n'atteint jamais ferait tourner cette boucle indéfiniment. C'est exactement le mode
    de défaillance qui a coûté le plus cher ici, et il ne doit plus pouvoir se reproduire.
    """
    lignes: list[dict] = []
    total: int | None = None

    for page in range(1, page_max + 1):
        reponse = client.get(API, params={"page": page, "page_size": PAGE_SIZE})
        reponse.raise_for_status()
        donnees = extraire(reponse.json())

        if total is None:
            total = int(getattr(reponse, "headers", {}).get("X-Total-Count", 0))
            journal(f"{total} navires à récupérer, {PAGE_SIZE} par page")

        if not donnees:
            break

        lignes.extend(donnees)
        journal(f"  page {page:>3} — {len(lignes):>5}/{total}")

        if len(lignes) >= total:
            break

        pause(DELAI)
    else:
        raise RuntimeError(
            f"{page_max} pages parcourues sans atteindre le total annoncé ({total}) — "
            "l'API a changé de forme ou de contrat"
        )

    return lignes


def main() -> int:
    debut = time.monotonic()
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=30) as client:
        lignes = recuperer(client, journal=lambda m: print(m, flush=True))

    df = pd.DataFrame(lignes)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SORTIE, index=False)
    print(
        f"{len(df)} lignes, {len(df.columns)} colonnes -> {SORTIE.name} "
        f"({SORTIE.stat().st_size / 1024:.0f} Ko, {time.monotonic() - debut:.0f}s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
