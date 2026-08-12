"""Bronze / silver / gold sur 2,2 Go d'AIS, avec DuckDB.

L'architecture en couches traîne une réputation de sur-ingénierie réservée aux entrepôts à
plusieurs téraoctets. Ce module la met en place sur trois fichiers CSV et une machine
portable, parce que le bénéfice réel n'est pas la volumétrie — c'est la **rejouabilité**.

Les trois couches, et ce que chacune garantit :

- **bronze** : la donnée brute telle que reçue, jamais modifiée. Sa seule fonction est de
  permettre de tout recalculer si une règle métier change ou se révèle fausse.
- **silver** : typée, filtrée, partitionnée. Une ligne = un fait propre. Aucune décision
  d'analyse à ce stade, seulement des décisions de qualité, énoncées.
- **gold** : les agrégats qu'on sert. Reconstructibles à tout moment depuis silver, donc
  jetables sans regret.

Le vrai déclencheur de ce découpage, ici, est une mésaventure : une restauration de
sauvegarde a effacé deux fois des corrections de données appliquées à la main en production.
Une correction qui ne vit que dans un `UPDATE` tapé un soir n'est pas une correction, c'est un
souvenir. Dans une architecture en couches, elle est du code, versionné, et se rejoue.
"""

import sys
import time
from pathlib import Path

import duckdb

RACINE = Path(__file__).resolve().parents[2]
BRONZE = RACINE / "data" / "ais"  # CSV bruts, tels que publiés par la NOAA
SILVER = RACINE / "data" / "lac" / "silver"
GOLD = RACINE / "data" / "lac" / "gold"
CATALOGUE = RACINE / "data" / "yachts.parquet"


def chrono(libelle, fonction):
    debut = time.monotonic()
    resultat = fonction()
    print(f"  {libelle:44} {time.monotonic() - debut:6.1f} s", flush=True)
    return resultat


def poids(chemin):
    chemin = Path(chemin)
    if chemin.is_dir():
        return sum(f.stat().st_size for f in chemin.rglob("*")) / 1024**2
    return chemin.stat().st_size / 1024**2


def construire_silver(con):
    """CSV bruts -> Parquet typé et partitionné par jour.

    Trois décisions de qualité, énoncées ici et nulle part ailleurs :
      - les positions sans nom de navire sont inutilisables pour la suite ;
      - une latitude hors [-90, 90] est une erreur de transmission, pas une donnée ;
      - le nom est normalisé une seule fois, ici, plutôt que dans chaque analyse.
    """
    SILVER.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT
                MMSI                                   AS mmsi,
                CAST(BaseDateTime AS TIMESTAMP)        AS horodatage,
                CAST(BaseDateTime AS DATE)             AS jour,
                LAT                                    AS latitude,
                LON                                    AS longitude,
                SOG                                    AS vitesse,
                trim(VesselName)                       AS nom,
                upper(regexp_replace(trim(VesselName), '[^A-Za-z0-9 ]', ' ', 'g')) AS nom_normalise,
                IMO                                    AS imo,
                VesselType                             AS type_navire,
                Length                                 AS longueur
            FROM read_csv_auto('{BRONZE}/AIS_*.csv', header = true)
            WHERE VesselName IS NOT NULL
              AND trim(VesselName) <> ''
              AND LAT BETWEEN -90 AND 90
              AND LON BETWEEN -180 AND 180
        )
        TO '{SILVER}' (FORMAT PARQUET, PARTITION_BY (jour), OVERWRITE_OR_IGNORE 1)
    """)


def construire_gold(con):
    """Les agrégats servis. Reconstructibles, donc jamais sauvegardés."""
    GOLD.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        CREATE OR REPLACE VIEW silver AS
            SELECT * FROM read_parquet('{SILVER}/**/*.parquet', hive_partitioning = true)
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW catalogue AS
            SELECT id, name,
                   upper(regexp_replace(trim(name), '[^A-Za-z0-9 ]', ' ', 'g')) AS nom_normalise,
                   overall_length
            FROM read_parquet('{CATALOGUE}')
            WHERE name IS NOT NULL
    """)
    # Un navire par ligne, avec ce qu'on sait de lui et son appariement au catalogue.
    con.execute(f"""
        COPY (
            SELECT s.mmsi,
                   any_value(s.nom)                       AS nom,
                   count(*)                               AS positions,
                   count(DISTINCT s.jour)                 AS jours_vus,
                   max(s.longueur)                        AS longueur_ais,
                   max(s.type_navire)                     AS type_navire,
                   min(c.overall_length)                  AS longueur_catalogue,
                   max(c.id) IS NOT NULL                  AS dans_catalogue
            FROM silver s
            LEFT JOIN catalogue c ON c.nom_normalise = s.nom_normalise
            GROUP BY s.mmsi
        ) TO '{GOLD}/navires.parquet' (FORMAT PARQUET)
    """)


def mesurer(con, repetitions=3):
    """Les chiffres que l'article cite. Mesurés sur une vraie requête, jamais estimés.

    Un `count(*)` ne mesurerait rien : les trois formats répondent instantanément. On pose
    donc une question analytique — regrouper, moyenner, trier — et on prend la médiane de
    plusieurs passages. Le cache disque est chaud, et c'est dit : c'est la condition réelle
    d'un travail d'analyse sur un poste, pas un benchmark de laboratoire.
    """
    import statistics

    def mediane(sql):
        temps = []
        for _ in range(repetitions):
            debut = time.monotonic()
            con.execute(sql).fetchall()
            temps.append(time.monotonic() - debut)
        return statistics.median(temps)

    requetes = {
        "bronze (CSV brut)": f"""
            SELECT CAST(BaseDateTime AS DATE) j, VesselName, count(*) n, avg(SOG) v
            FROM read_csv_auto('{BRONZE}/AIS_*.csv', header = true)
            WHERE VesselName IS NOT NULL AND SOG > 0
            GROUP BY 1, 2 ORDER BY n DESC LIMIT 10""",
        "silver (Parquet partitionné)": f"""
            SELECT jour j, nom, count(*) n, avg(vitesse) v
            FROM read_parquet('{SILVER}/**/*.parquet', hive_partitioning = true)
            WHERE vitesse > 0
            GROUP BY 1, 2 ORDER BY n DESC LIMIT 10""",
        "gold (agrégat pré-calculé)": f"""
            SELECT * FROM read_parquet('{GOLD}/navires.parquet')
            ORDER BY positions DESC LIMIT 10""",
    }

    print("\n--- même question analytique, posée aux trois couches (cache chaud) ---")
    for libelle, sql in requetes.items():
        print(f"  {libelle:32} {mediane(sql):7.3f} s", flush=True)


def main():
    con = duckdb.connect()
    print(f"bronze : {poids(BRONZE):.0f} Mo de CSV bruts")
    chrono("construction silver", lambda: construire_silver(con))
    print(f"silver : {poids(SILVER):.0f} Mo de Parquet partitionné")
    chrono("construction gold", lambda: construire_gold(con))
    print(f"gold   : {poids(GOLD):.1f} Mo")
    mesurer(con)
    return 0


if __name__ == "__main__":
    sys.exit(main())
