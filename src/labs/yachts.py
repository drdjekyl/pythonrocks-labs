"""Récupération du jeu de données yachts depuis l'API publique, vers Parquet.

9 407 navires, servis par pages de 100 au maximum — soit 95 requêtes. L'API applique une
limite de 60 requêtes par minute et par IP, et elle héberge aussi le site vitrine : on ne la
sature pas pour gagner trente secondes.

Le fichier Parquet produit est versionné dans ce dépôt. Les analyses des articles partent de
lui, pas du live : elles restent reproductibles à l'identique dans six mois, et le lecteur qui
exécute un notebook ne déclenche pas 95 requêtes chez quelqu'un d'autre.

Deux détails coûteux appris en le écrivant, tous deux invisibles sur une seule requête :

- **Réutiliser la connexion.** Avec `urllib.request.urlopen`, chaque page rouvre une connexion
  TLS. Mesuré sur cette API : ~0,1 s par requête isolée, mais ~11 s par page en boucle, soit
  17 minutes au total au lieu de 2. Un `httpx.Client` réutilisé règle le problème.
- **Se déclarer.** Cloudflare protège la zone et renvoie 403 sur l'agent par défaut d'urllib.
  C'est de toute façon la politesse minimale quand on interroge l'API de quelqu'un d'autre en
  boucle : l'administrateur qui lit ses journaux doit pouvoir identifier le trafic.
"""

import sys
import time
from pathlib import Path

import httpx
import pandas as pd

API = "https://api.pythonrocks.academy/yachts"
PAGE_SIZE = 100
DELAI = 1.05  # secondes entre deux requêtes -> ~57/min, sous la limite de 60
AGENT = "pythonrocks-labs/0.1 (+https://github.com/drdjekyl/pythonrocks-labs)"
SORTIE = Path(__file__).resolve().parents[2] / "data" / "yachts.parquet"


def recuperer_tout(client):
    """Parcourt les pages jusqu'à avoir le nombre annoncé par `X-Total-Count`."""
    lignes = []
    total = None
    page = 1

    while True:
        reponse = client.get(API, params={"page": page, "page_size": PAGE_SIZE})
        reponse.raise_for_status()
        # `/yachts` renvoie un OBJET {total, page, page_size, items}, pas un tableau —
        # contrairement à `/yachts/random`, qui lui renvoie bien une liste. Confondre les deux
        # ne lève aucune erreur : `extend()` sur un dict empile ses CLÉS, soit 4 chaînes par
        # page. La boucle tourne alors 2 352 fois pour « atteindre » 9 407, et le seul symptôme
        # est un script anormalement lent.
        donnees = reponse.json()["items"]

        if total is None:
            total = int(reponse.headers.get("X-Total-Count", 0))
            print(f"{total} navires à récupérer, {PAGE_SIZE} par page")

        if not donnees:
            break

        lignes.extend(donnees)
        # `flush` explicite : sans lui, la progression n'apparaît qu'à la fin dès que la
        # sortie n'est pas un terminal, ce qui rend un script long impossible à surveiller.
        print(f"  page {page:>3} — {len(lignes):>5}/{total}", flush=True)

        if len(lignes) >= total:
            break

        page += 1
        time.sleep(DELAI)

    return lignes


def main():
    debut = time.monotonic()
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=30) as client:
        lignes = recuperer_tout(client)

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
