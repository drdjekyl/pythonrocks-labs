"""Collecteur AIS : écoute le trafic maritime et retient ce qui ressemble à nos yachts.

Le problème central, et le sujet de l'article : `cleaned_yachts` ne contient **ni MMSI ni
IMO**. Le seul pont entre la base et un flux AIS est le *nom* du navire — une clé sale,
saisie à la main par des équipages, en majuscules, parfois tronquée, parfois préfixée `M/Y`.
C'est un problème de résolution d'identité, pas un simple `JOIN`.

Stratégie de volume : la Méditerranée et les Caraïbes voient passer bien trop de trafic pour
qu'on stocke tout pendant 72 h. On filtre donc à l'écriture sur le nom normalisé. Les navires
non appariés ne sont pas jetés pour autant : on garde leur nom et un compteur, ce qui permet
ensuite de mesurer ce qu'on a raté plutôt que de l'ignorer.

La clé API se lit dans l'environnement, jamais en dur ni en argument de ligne de commande
(elle apparaîtrait dans l'historique du shell et dans `ps`).
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import websockets

URL = "wss://stream.aisstream.io/v0/stream"

# [[lat_sud, lon_ouest], [lat_nord, lon_est]] — les deux bassins où croisent ces navires.
ZONES = [
    [[30.0, -6.5], [46.5, 36.5]],  # Méditerranée
    [[9.0, -87.0], [27.5, -59.0]],  # Caraïbes
]

RACINE = Path(__file__).resolve().parents[2]
PARQUET = RACINE / "data" / "yachts.parquet"
BASE = RACINE / "data" / "ais" / "collecte.sqlite"

# Préfixes de complaisance que les équipages ajoutent au nom : « M/Y BOAT », « S/Y BOAT ».
PREFIXES = re.compile(r"^(M/?Y|S/?Y|MY|SY|MV|SV)[\s.]+", re.IGNORECASE)


def normaliser(nom):
    """Ramène un nom de navire à une forme comparable.

    Majuscules, sans accents, sans ponctuation, espaces réduits, préfixe de type retiré.
    Volontairement simple : chaque règle supplémentaire augmente le rappel mais aussi le
    risque de faux positifs, et l'article mesure ce compromis plutôt que de le postuler.
    """
    if not nom:
        return ""
    nom = unicodedata.normalize("NFKD", str(nom))
    nom = "".join(c for c in nom if not unicodedata.combining(c))
    nom = PREFIXES.sub("", nom.strip())
    nom = re.sub(r"[^A-Za-z0-9 ]", " ", nom)
    return re.sub(r"\s+", " ", nom).strip().upper()


def charger_noms():
    """Index {nom normalisé -> liste d'identifiants}, depuis l'instantané Parquet.

    Une liste et non un identifiant unique : plusieurs yachts portent le même nom, et écraser
    silencieusement les homonymes fausserait la mesure de précision.
    """
    df = pd.read_parquet(PARQUET, columns=["id", "name"])
    index = {}
    for identifiant, nom in zip(df["id"], df["name"], strict=True):
        cle = normaliser(nom)
        if cle:
            index.setdefault(cle, []).append(identifiant)
    return index


def ouvrir_base():
    BASE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(BASE)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS positions (
            mmsi INTEGER, nom TEXT, nom_normalise TEXT, yacht_ids TEXT,
            latitude REAL, longitude REAL, sog REAL, cog REAL, horodatage TEXT
        );
        CREATE TABLE IF NOT EXISTS statiques (
            mmsi INTEGER, nom TEXT, nom_normalise TEXT, imo INTEGER,
            call_sign TEXT, type_navire INTEGER, destination TEXT, horodatage TEXT
        );
        -- Les navires vus mais non appariés : c'est cette table qui permettra de dire ce
        -- qu'on a raté, au lieu de ne mesurer que ce qu'on a trouvé.
        CREATE TABLE IF NOT EXISTS vus (
            nom_normalise TEXT PRIMARY KEY, nom TEXT, mmsi INTEGER, occurrences INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi);
    """)
    return conn


async def collecter(duree_secondes):
    cle = os.environ.get("AISSTREAM_API_KEY")
    if not cle:
        return "AISSTREAM_API_KEY absent de l'environnement"

    index = charger_noms()
    conn = ouvrir_base()
    print(f"{len(index)} noms de yachts indexés", flush=True)

    debut = datetime.now(UTC)
    apparies = total = 0

    while (datetime.now(UTC) - debut).total_seconds() < duree_secondes:
        try:
            async with websockets.connect(URL, ping_interval=20) as ws:
                # L'abonnement doit partir dans les 3 secondes suivant l'ouverture.
                await ws.send(
                    json.dumps(
                        {
                            "APIKey": cle,
                            "BoundingBoxes": ZONES,
                            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                        }
                    )
                )
                print("connecté, abonnement envoyé", flush=True)

                # `async for ... in ws` bloquerait indéfiniment sur un flux silencieux : la
                # condition de durée n'est réévaluée qu'à la réception d'un message. Or un
                # flux muet est un cas réel, pas théorique (aisstream accepte l'abonnement et
                # ne livre parfois rien). Le timeout rend la boucle sortable dans tous les cas.
                while True:
                    if (datetime.now(UTC) - debut).total_seconds() >= duree_secondes:
                        break
                    try:
                        brut = await asyncio.wait_for(ws.recv(), timeout=30)
                    except TimeoutError:
                        print("aucun message depuis 30s", flush=True)
                        continue

                    message = json.loads(brut)
                    meta = message.get("MetaData", {})
                    nom = (meta.get("ShipName") or "").strip()
                    cle_nom = normaliser(nom)
                    mmsi = meta.get("MMSI")
                    total += 1

                    ids = index.get(cle_nom)
                    if ids:
                        apparies += 1
                        enregistrer(conn, message, nom, cle_nom, ids, mmsi)
                    else:
                        conn.execute(
                            "INSERT INTO vus(nom_normalise, nom, mmsi, occurrences) "
                            "VALUES(?,?,?,1) ON CONFLICT(nom_normalise) DO UPDATE SET "
                            "occurrences = occurrences + 1",
                            (cle_nom, nom, mmsi),
                        )

                    if total % 500 == 0:
                        conn.commit()
                        ecoule = (datetime.now(UTC) - debut).total_seconds()
                        print(
                            f"{ecoule / 3600:5.2f}h — {total:>7} messages, "
                            f"{apparies:>5} appariés",
                            flush=True,
                        )
                    if (datetime.now(UTC) - debut).total_seconds() >= duree_secondes:
                        break

        # Volontairement large : une collecte de 72h doit survivre à tout — coupure réseau,
        # JSON malformé, fermeture serveur. Une exception non rattrapée perdrait la collecte.
        except Exception as erreur:
            conn.commit()
            print(
                f"déconnexion ({type(erreur).__name__}), reprise dans 10s", flush=True
            )
            await asyncio.sleep(10)

    conn.commit()
    conn.close()
    print(f"terminé : {total} messages, {apparies} appariés", flush=True)
    return 0


def enregistrer(conn, message, nom, cle_nom, ids, mmsi):
    horodatage = datetime.now(UTC).isoformat()
    corps = message.get("Message", {})
    joints = ",".join(ids)

    if "PositionReport" in corps:
        p = corps["PositionReport"]
        conn.execute(
            "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?)",
            (
                mmsi,
                nom,
                cle_nom,
                joints,
                p.get("Latitude"),
                p.get("Longitude"),
                p.get("Sog"),
                p.get("Cog"),
                horodatage,
            ),
        )
    elif "ShipStaticData" in corps:
        s = corps["ShipStaticData"]
        conn.execute(
            "INSERT INTO statiques VALUES (?,?,?,?,?,?,?,?)",
            (
                mmsi,
                nom,
                cle_nom,
                s.get("ImoNumber"),
                s.get("CallSign"),
                s.get("Type"),
                (s.get("Destination") or "").strip(),
                horodatage,
            ),
        )


def main():
    heures = float(sys.argv[1]) if len(sys.argv) > 1 else 72.0
    print(f"collecte prévue : {heures}h", flush=True)
    return asyncio.run(collecter(heures * 3600))


if __name__ == "__main__":
    sys.exit(main())
