"""Collecte pypistats.org + pypi.org : la matière première du volet « écosystème PyPI ».

Nouvelle investigation, indépendante du fil rouge yachts — pas une extension de `registres_classe`
ou `vecteur_impacts`, un sujet entièrement différent. L'angle éditorial : un cours Python qui
retourne son propre outillage en objet d'étude ML, via les statistiques de téléchargement PyPI de
51 paquets choisis à la main (voir `CATEGORIES` plus bas).

## Deux API, deux comportements différents

- **pypistats.org** (`/api/packages/<paquet>/overall`) : historique quotidien de téléchargements,
  catégorie `with_mirrors` / `without_mirrors` (on garde toujours `without_mirrors`, qui exclut le
  trafic de miroirs/CDN et reflète mieux l'usage réel). Sensible à la casse au sens strict de son
  URL mais tolère tiret/underscore indifféremment — ce module force le nom en minuscules avant
  tout appel, par précaution. **Historique mesuré : exactement 181 jours glissants**
  (2026-02-25 → 2026-08-24 au moment de la collecte réelle de cette investigation, jamais le jour
  courant) — ce n'est pas une limite de ce module, c'est ce que l'API rend. Pas d'authentification.
  Débit non documenté en chiffres mais mesuré empiriquement sur ~95 appels réels : ~1,5 s
  d'espacement séquentiel = 0 échec ; en rafale, 429 sporadique (environ 1 appel sur 8 à 10).
  **Le corps d'une erreur n'est PAS JSON** — HTML pour 429, texte brut `"404"` pour 404 — d'où la
  règle dure de ce module : ne jamais appeler `.json()` avant d'avoir vérifié le statut. Pas de
  `Retry-After` : le repli est un délai fixe empirique qui double à chaque tentative, pas un délai
  lu dans la réponse.
- **pypi.org/pypi/<paquet>/json** : métadonnées de release, insensible à la casse, 404 propre en
  JSON, aucune limite de débit observée. `requires_dist`/`maintainer`/`author` sont peu fiables sur
  les vieux paquets (absents historiquement) — ce module ne les lit pas, seulement
  `releases`, dont chaque version associe une liste de fichiers portant `upload_time_iso_8601`.

## Cadence de release : ce qui compte comme une release

`releases` contient parfois des versions **sans aucun fichier** (retirées du dépôt, ou jamais
publiées avec un artefact téléchargeable — observé en vrai sur `django` : 7 versions sur 441 sans
fichier). Une version sans fichier n'a pas de date d'upload et n'a donc jamais été téléchargeable :
la compter comme une release réelle inventerait une date. `n_releases` ne compte que les versions
qui portent au moins un fichier, et l'âge/la cadence se calculent sur les horodatages de fichiers
réels, jamais sur les seules clés du dictionnaire `releases`.

## Reprenable, comme le reste du dépôt

51 paquets, un appel par API et par paquet (pas de pagination côté pypistats.org : une réponse
donne tout l'historique disponible d'un coup) — un ordre de grandeur sous la collecte yacht. Même
principe que `registres_classe.collecter` : chaque paquet réussi est écrit sur disque avant de
passer au suivant, donc un plantage à mi-parcours (repli épuisé, coupure réseau) ne coûte que le
paquet en cours — relancer `main()` saute tout paquet déjà présent dans les deux Parquet de
sortie.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
TELECHARGEMENTS = RACINE / "data" / "pypi_downloads.parquet"
RELEASES = RACINE / "data" / "pypi_releases.parquet"

AGENT = "pythonrocks-labs/0.1 (+https://github.com/drdjekyl/pythonrocks-labs)"

# --- Les 51 paquets, groupés selon l'hypothèse éditoriale de départ ---------------------------
#
# Ces trois groupes sont la vérité terrain de l'article (posée à la main par lecture directe des
# chiffres pypistats.org, pas par un modèle) : ils servent de LABEL pour évaluer la classification
# (`pypi_classification.py`) et de comparaison a posteriori pour le clustering
# (`pypi_clustering.py`) — jamais d'entrée du clustering lui-même, dont tout l'intérêt éditorial
# est de voir si ces trois groupes ressortent sans qu'on les lui donne.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "etabli": (
        "certifi",
        "requests",
        "urllib3",
        "numpy",
        "pandas",
        "python-dateutil",
        "pip",
        "six",
        "idna",
        "packaging",
        "pyyaml",
        "attrs",
        "jinja2",
        "click",
        "cryptography",
        "scikit-learn",
        "scipy",
        "django",
        "sqlalchemy",
        "matplotlib",
    ),
    "montant": (
        "anthropic",
        "huggingface-hub",
        "tiktoken",
        "openai",
        "duckdb",
        "starlette",
        "boto3",
        "anyio",
        "httpx",
        "uvicorn",
        "ruff",
        "python-dotenv",
        "fastapi",
        "hatchling",
        "pytest",
        "mypy",
        "polars",
        "pydantic",
    ),
    "declinant": (
        "tensorflow",
        "flask",
        "nose",
        "mock",
        "ipaddress",
        "pathlib2",
        "simplejson",
        "enum34",
        "setuptools",
        "flake8",
        "tox",
        "keras",
        "pytz",
    ),
}

PACKAGES: tuple[str, ...] = tuple(
    sorted({paquet for groupe in CATEGORIES.values() for paquet in groupe})
)

# Paquet de référence pour la normalisation (voir `pypi_features.py`) : quasi-dépendance
# universelle, sa hausse de trafic sur la période sert de proxy au trafic PyPI global.
BASELINE = "certifi"

assert len(PACKAGES) == 51, f"51 paquets attendus, {len(PACKAGES)} après dédoublonnage"

# --- Client poli : espacement + repli exponentiel sur les statuts retentables -----------------

DELAI_PYPISTATS = 1.5  # mesuré : 0 échec sur ~95 appels réels à ce rythme
DELAI_PYPI = 0.3  # aucune limite observée, on reste poli quand même
STATUTS_REESSAYABLES_PYPISTATS = frozenset({429})
STATUTS_REESSAYABLES_PYPI = frozenset({429, 500, 502, 503, 504})


class ClientPoli:
    """Un client dont chaque appel est espacé d'au moins `delai` secondes du précédent, avec un
    repli fixe qui double à chaque tentative sur les statuts de `statuts_reessayables`.

    Pas de `Retry-After` chez pypistats.org (voir la docstring du module) : `delai_base_reessai`
    est un délai empirique, pas une valeur lue dans la réponse. `pause` et `horloge` sont
    injectés pour que les tests s'exécutent sans dormir pour de vrai (`feedback_sleep_harness`).
    """

    def __init__(
        self,
        client: httpx.Client,
        delai: float,
        statuts_reessayables: frozenset[int],
        pause=time.sleep,
        horloge=time.monotonic,
        tentatives_max: int = 4,
        delai_base_reessai: float = 4.0,
    ) -> None:
        self._client = client
        self._delai = delai
        self._statuts_reessayables = statuts_reessayables
        self._pause = pause
        self._horloge = horloge
        self._tentatives_max = tentatives_max
        self._delai_base_reessai = delai_base_reessai
        self._dernier: float | None = None

    def _attendre(self) -> None:
        if self._dernier is not None:
            ecoule = self._horloge() - self._dernier
            if ecoule < self._delai:
                self._pause(self._delai - ecoule)
        self._dernier = self._horloge()

    def get(self, url: str) -> httpx.Response:
        """Ne renvoie que sur un statut hors de `statuts_reessayables` — 2xx bien sûr, mais
        aussi un 4xx qu'il n'y a aucune raison de retenter (404 sur un des 51 paquets choisis à
        la main est une vraie anomalie à faire remonter, pas une absence à masquer)."""
        reponse: httpx.Response | None = None
        for tentative in range(self._tentatives_max):
            if tentative > 0:
                self._pause(self._delai_base_reessai * (2 ** (tentative - 1)))
            self._attendre()
            reponse = self._client.get(url, headers={"User-Agent": AGENT})
            if reponse.status_code not in self._statuts_reessayables:
                return reponse

        assert reponse is not None
        raise RuntimeError(
            f"{url} : {self._tentatives_max} tentatives épuisées, "
            f"dernier statut {reponse.status_code}"
        )


# --- pypistats.org -----------------------------------------------------------------------------


def extraire_sans_mirroir(charge: Any) -> list[dict]:
    """Le sous-ensemble `without_mirrors` d'une réponse `/overall`, ou échoue en le disant.

    `without_mirrors` exclut le trafic de miroirs/CDN — c'est la mesure d'usage réel, la même
    que retient la recherche préalable de cette investigation. Une réponse sans la clé `data`
    a changé de contrat : on l'échoue net plutôt que de continuer sur une liste vide qui
    produirait silencieusement un paquet à zéro jour de données.
    """
    if not isinstance(charge, dict) or "data" not in charge:
        cles = sorted(charge) if isinstance(charge, dict) else type(charge).__name__
        raise ValueError(f"réponse sans clé 'data' : {cles}")
    lignes = [
        ligne for ligne in charge["data"] if ligne["category"] == "without_mirrors"
    ]
    if not lignes:
        raise ValueError("aucune ligne 'without_mirrors' dans la réponse")
    return lignes


def telecharger_historique(client: ClientPoli, paquet: str) -> pd.DataFrame:
    """L'historique quotidien `without_mirrors` d'un paquet, en trois colonnes.

    Un seul appel : pypistats.org ne pagine pas `/overall`, il rend tout l'historique
    disponible (181 jours au moment de cette collecte) en une réponse.
    """
    paquet = paquet.lower()
    reponse = client.get(f"https://pypistats.org/api/packages/{paquet}/overall")
    reponse.raise_for_status()  # jamais .json() avant d'avoir vérifié le statut
    lignes = extraire_sans_mirroir(reponse.json())

    df = pd.DataFrame(lignes)[["date", "downloads"]]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["downloads"] = df["downloads"].astype("Int64")
    df.insert(0, "package", paquet)
    return df[["package", "date", "downloads"]]


# --- pypi.org/pypi/<paquet>/json ----------------------------------------------------------------


def extraire_releases(charge: Any, paquet: str, reference: date) -> dict:
    """Première release, dernière release et nombre de releases, à partir des SEULES versions
    portant un fichier réel (voir la docstring du module — les autres n'ont pas de date fiable).

    `reference` est fixé par l'appelant (la date de la collecte), jamais recalculé plus tard :
    l'âge et la récence dérivés de ce résultat restent reproductibles à l'identique, comme le
    reste du dépôt.
    """
    releases = charge.get("releases", {})
    horodatages = [
        fichier["upload_time_iso_8601"]
        for fichiers in releases.values()
        for fichier in fichiers
    ]
    n_releases = sum(1 for fichiers in releases.values() if fichiers)

    if not horodatages:
        # Jamais observé sur les 51 paquets de cette investigation, mais un paquet réel sans
        # aucun fichier publié est possible en théorie : indéterminé, pas zéro ni une supposition.
        return {
            "package": paquet,
            "first_release": None,
            "last_release": None,
            "n_releases": 0,
            "reference_date": reference,
        }

    horodatages_dt = sorted(
        datetime.fromisoformat(h.replace("Z", "+00:00")) for h in horodatages
    )
    return {
        "package": paquet,
        "first_release": horodatages_dt[0].date(),
        "last_release": horodatages_dt[-1].date(),
        "n_releases": n_releases,
        "reference_date": reference,
    }


def recuperer_releases(client: ClientPoli, paquet: str, reference: date) -> dict:
    paquet = paquet.lower()
    reponse = client.get(f"https://pypi.org/pypi/{paquet}/json")
    reponse.raise_for_status()
    return extraire_releases(reponse.json(), paquet, reference)


# --- Persistance reprenable ----------------------------------------------------------------


def _charger(chemin: Path) -> pd.DataFrame | None:
    return pd.read_parquet(chemin) if chemin.exists() else None


def _sauvegarder(morceaux: list[pd.DataFrame], chemin: Path) -> pd.DataFrame:
    df = pd.concat(morceaux, ignore_index=True)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(chemin, index=False)
    return df


def main() -> int:
    debut = time.monotonic()
    aujourdhui = datetime.now(UTC).date()

    telechargements = _charger(TELECHARGEMENTS)
    deja_telecharge = (
        set(telechargements["package"].unique())
        if telechargements is not None
        else set()
    )
    morceaux_telechargements = [telechargements] if telechargements is not None else []

    releases = _charger(RELEASES)
    deja_releases = set(releases["package"].unique()) if releases is not None else set()
    morceaux_releases = [releases] if releases is not None else []

    if deja_telecharge or deja_releases:
        print(
            f"reprise : {len(deja_telecharge)} historiques et {len(deja_releases)} fiches "
            "release déjà collectés, non refaits",
            flush=True,
        )

    with httpx.Client(timeout=30) as brut:
        client_pypistats = ClientPoli(
            brut, DELAI_PYPISTATS, STATUTS_REESSAYABLES_PYPISTATS
        )
        client_pypi = ClientPoli(brut, DELAI_PYPI, STATUTS_REESSAYABLES_PYPI)

        for i, paquet in enumerate(PACKAGES, start=1):
            if paquet not in deja_telecharge:
                historique = telecharger_historique(client_pypistats, paquet)
                morceaux_telechargements.append(historique)
                _sauvegarder(morceaux_telechargements, TELECHARGEMENTS)
                print(
                    f"  [{i:>2}/{len(PACKAGES)}] téléchargements {paquet:20} "
                    f"{len(historique)} jours",
                    flush=True,
                )

            if paquet not in deja_releases:
                meta = recuperer_releases(client_pypi, paquet, aujourdhui)
                morceaux_releases.append(pd.DataFrame([meta]))
                _sauvegarder(morceaux_releases, RELEASES)
                print(
                    f"  [{i:>2}/{len(PACKAGES)}] releases        {paquet:20} "
                    f"{meta['n_releases']} releases, "
                    f"première {meta['first_release']}, dernière {meta['last_release']}",
                    flush=True,
                )

    print(
        f"\n{len(PACKAGES)} paquets -> {TELECHARGEMENTS.name} + {RELEASES.name} "
        f"({time.monotonic() - debut:.0f}s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
