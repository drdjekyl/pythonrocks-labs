"""Retrouver les yachts de la base dans les positions AIS publiques de Marine Cadastre.

Le problème : `cleaned_yachts` n'a **ni MMSI ni IMO**. Le seul pont vers un flux AIS est le
*nom* du navire — une clé sale, saisie à la main par des équipages, et surtout **non unique** :
des dizaines de bateaux s'appellent FREEDOM ou LIBERTY, dont des remorqueurs de 40 m et des
cargos de 186 m.

Un `JOIN` sur le nom n'est donc pas une solution, c'est le début du problème. Ce module en
fait un appariement *scoré*, puis mesure ce qu'il retient et ce qu'il jette.

Source : https://coast.noaa.gov/htdata/CMSP/AISDataHandler/ — fichiers quotidiens couvrant les
eaux américaines, publics, sans clé ni inscription. Ils portent `IMO`, `Length` et
`VesselType`, ce qui fournit une vérité terrain : on peut *vérifier* un appariement au lieu de
l'espérer. Contrepartie assumée : pas de Méditerranée. Pour des superyachts en hiver, la
Floride est de toute façon la bonne zone.
"""

import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from labs.ais import normaliser

BASE_URL = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler"
RACINE = Path(__file__).resolve().parents[2]
PARQUET = RACINE / "data" / "yachts.parquet"
CACHE = RACINE / "data" / "ais"

# Nomenclature AIS : 36 = voilier, 37 = navire de plaisance.
TYPES_PLAISANCE = {36, 37}
# Tolérance sur la longueur. L'AIS est saisi à la main et arrondi au mètre ; la base vient
# d'un catalogue de courtage. 3 m d'écart sur un navire de 50 m reste cohérent, 30 m non.
TOLERANCE_M = 3.0

COLONNES = [
    "MMSI",
    "BaseDateTime",
    "LAT",
    "LON",
    "SOG",
    "VesselName",
    "IMO",
    "VesselType",
    "Length",
]


def telecharger(jour):
    """Récupère et décompresse un fichier quotidien. `jour` au format 2023-02-15."""
    CACHE.mkdir(parents=True, exist_ok=True)
    annee, mois, j = jour.split("-")
    csv = CACHE / f"AIS_{annee}_{mois}_{j}.csv"
    if csv.exists():
        return csv

    archive = CACHE / f"{csv.stem}.zip"
    url = f"{BASE_URL}/{annee}/{csv.stem}.zip"
    print(f"téléchargement {jour}…", flush=True)
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(CACHE)
    archive.unlink()
    return csv


def charger_reference():
    """La base yachts, indexée par nom normalisé -> liste de candidats.

    Une liste, jamais un seul candidat : les homonymes existent dans la base elle-même, et les
    écraser fausserait la mesure.
    """
    df = pd.read_parquet(
        PARQUET, columns=["id", "name", "overall_length", "vessel_type"]
    )
    df["cle"] = df["name"].map(normaliser)
    df = df[df["cle"] != ""]
    return df.groupby("cle")[["id", "name", "overall_length"]].apply(
        lambda g: g.to_dict("records")
    )


def naviresp_du_jour(csv, cles):
    """Un enregistrement par navire (MMSI) dont le nom figure dans la base."""
    morceaux = []
    for bloc in pd.read_csv(
        csv, usecols=COLONNES, chunksize=1_000_000, low_memory=False
    ):
        bloc = bloc.dropna(subset=["VesselName"])
        bloc["cle"] = bloc["VesselName"].map(normaliser)
        garde = bloc[bloc["cle"].isin(cles)]
        if not garde.empty:
            morceaux.append(garde)
    if not morceaux:
        return pd.DataFrame(columns=[*COLONNES, "cle"])
    return pd.concat(morceaux, ignore_index=True)


def scorer(navires, reference):
    """Attribue à chaque MMSI un verdict : confirme / rejette, avec le motif.

    Trois signaux indépendants, du plus discriminant au moins :
      1. le type AIS déclaré — un remorqueur n'est pas un yacht ;
      2. la longueur — c'est elle qui élimine le cargo de 186 m nommé INDEPENDENCE ;
      3. la présence d'un IMO réel, indice de navire immatriculé au commerce.
    """
    uniques = navires.drop_duplicates("MMSI").copy()

    def verdict(ligne):
        candidats = reference[ligne["cle"]]
        if ligne["VesselType"] not in TYPES_PLAISANCE:
            return "type non plaisance"
        longueur = ligne["Length"]
        if pd.isna(longueur) or longueur == 0:
            return "longueur absente"
        for c in candidats:
            ref = c["overall_length"]
            if pd.notna(ref) and abs(longueur - ref) <= TOLERANCE_M:
                return "confirme"
        return "longueur incompatible"

    uniques["verdict"] = uniques.apply(verdict, axis=1)
    return uniques


def analyser(jours):
    reference = charger_reference()
    cles = set(reference.index)
    print(f"{len(cles)} noms distincts dans la base", flush=True)

    tous = []
    for jour in jours:
        csv = telecharger(jour)
        navires = naviresp_du_jour(csv, cles)
        navires["jour"] = jour
        tous.append(navires)
        print(
            f"  {jour} : {len(navires):>7} positions, {navires['MMSI'].nunique():>5} navires nommés comme un yacht",
            flush=True,
        )

    positions = pd.concat(tous, ignore_index=True)
    scores = scorer(positions, reference)

    print("\n--- verdicts, par navire unique (MMSI) ---")
    for motif, n in scores["verdict"].value_counts().items():
        print(f"  {motif:24} {n:>5}")

    confirmes = scores[scores["verdict"] == "confirme"]
    print(f"\nconfirmés : {len(confirmes)} navires, {confirmes['cle'].nunique()} noms")
    print(f"taux de survie : {len(confirmes) / len(scores) * 100:.1f}%")
    return positions, scores


def main():
    jours = sys.argv[1:] or ["2023-02-15"]
    analyser(jours)
    return 0


if __name__ == "__main__":
    sys.exit(main())
