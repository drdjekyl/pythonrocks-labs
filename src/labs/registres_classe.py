"""IMO et notations environnementales de classe : ce que le nom seul ne peut pas donner.

Le catalogue de 9 407 yachts n'a **ni IMO ni MMSI** (voir `ais` et `marine_cadastre`) — un
verrou structurel : sans identifiant stable, toute jointure externe s'appuie sur le nom, une
clé sale. Trois registres de classification publient l'IMO sans clé ni captcha ; l'un d'eux
publie en plus les notations environnementales de classe (« Clean », « BWM(T) »,
« Gas fuelled »…) pour les navires qu'il classe.

Ce module ne recalcule rien : il interroge, confirme, décompose et range.

## Les trois sources, et ce qu'elles donnent vraiment

- **DNV** (`vesselregister.dnv.com`) : recherche par nom (`vessel/get`), puis détails par
  identifiant (`vesseldetails`). Donne l'IMO ET les notations, en deux chaînes distinctes —
  « design » (à la construction, `classNotationStringDesign`) et « en exploitation »
  (`classNotationStringInOperation`, qui peut être vide alors que le navire *a* des notations
  design : c'est un signal réel, pas une absence de donnée, voir plus bas). Deux appels HTTP
  par navire trouvé, un seul si le nom ne remonte aucun candidat.
- **Lloyd's Register** (`www.lr.org`) : un seul appel (`webapi/searchproxy/search/`), donne
  l'IMO et l'année de construction. Jamais les notations (derrière Class Direct, non public).
- **RINA** : documenté comme accessible via `leonardoinfo.com/libroRegistroWeb/rest/`. Sa page
  d'accueil a été mise hors service (redirection générale vers `leoinfoplus.rina.org`), **mais
  l'API REST elle-même répond toujours** — vérifié en direct, `/search/ships` renvoie de vrais
  résultats JSON avec IMO, année et longueur. En revanche `/search/shipDetail` (nécessaire pour
  `listAdditionalNotation`, les notations RINA) échoue systématiquement avec une exception
  serveur (`EJBTransactionRolledbackException`), quel que soit le nom de paramètre essayé
  (`idNave`, `id`, `name`) — probablement un état de session non documenté que cette API
  attend et qu'on ne devine pas. RINA est donc implémenté ici pour l'IMO seul, jamais pour les
  notations : forcer `shipDetail` aurait été deviner un contrat d'API, pas l'interroger.

## L'appariement par nom ne suffit jamais seul

La leçon coûteuse de `marine_cadastre` (85 % de faux positifs sur un simple `JOIN` par nom)
s'applique ici à l'identique — en pire, même : ces registres font eux-mêmes une recherche
floue (« Eclipse » renvoie aussi bien un yacht qu'un pétrolier GPL qu'un paquebot nommé
« Celebrity Eclipse »). Un candidat n'est donc éligible à confirmation que si son nom, une
fois normalisé, est **strictement égal** au nom normalisé du catalogue — pas un sous-ensemble
flou. Il est ensuite confirmé par au moins un second champ concordant : année de construction
(±1 an), longueur hors-tout (±1 m), ou constructeur (mots significatifs partagés, les
suffixes juridiques et génériques comme « Yachts », « GmbH » ou « Werft » étant ignorés parce
qu'ils ne discriminent rien). Un candidat au nom exact mais non confirmé par un second champ
est *rejeté* — présent dans le jeu de données avec `confiance="rejete"`, IMO et notations à
`None`, pour que le rejet reste traçable sans polluer le sous-ensemble de confiance.

## Deux absences qui ne veulent pas dire la même chose

1. **Non trouvé au registre** : aucun candidat au nom exact ne remonte. Aucune ligne n'est
   produite pour ce couple (navire, source) — ce n'est pas une observation, c'est l'absence
   d'observation.
2. **Trouvé, confirmé, notation vide** : DNV renvoie parfois `""` pour
   `classNotationStringInOperation` alors que le navire est bien classé (cas réel d'AZZAM).
   C'est un résultat réel (« aucune notation environnementale en exploitation »), conservé tel
   quel — jamais confondu avec `None`, qui signifie « cette source ne fournit pas ce champ ».

## Décomposition des notations : un lexique explicite, pas une supposition

Une notation DNV est presque toujours un mot, parfois suivi sans espace d'un qualificatif
entre parenthèses (`Battery(Power)`, `BWM(T)`) — une simple découpe sur les espaces les garde
groupés. La seule exception observée est une notation qui *contient* un espace
(`Gas fuelled`). Deviner quels mots adjacents forment une notation composée serait risquer de
recoller deux notations indépendantes ; `NOTATIONS_MULTI_MOTS` énumère donc explicitement les
seules exceptions constatées, plutôt que d'inférer une règle générale.

## Ce que la collecte réelle a donné, et ce que ça implique

Une exécution sur 997 navires (les 97 déjà tagués DNV par le catalogue + 900 tirés au sort,
`echantillon(taille=900)`) a produit `data/registres_classe.parquet` : 308 lignes, dont 142
confirmées et 166 rejetées.

| Source | Confirmées | Rejetées | Taux de rejet |
| --- | --- | --- | --- |
| DNV  | 51 | 49 | 49 % |
| LR   | 84 | 72 | 46 % |
| RINA |  7 | 45 | 87 % |

**Ce taux de rejet élevé est un succès de la méthode, pas un raté.** Près de la moitié des
candidats DNV et la quasi-totalité des candidats RINA trouvés par nom exact ont été écartés
faute de second champ concordant — sans cette exigence, le volume de correspondances aurait
doublé, rempli de faux positifs indiscernables des vrais. Le nombre qui compte n'est donc pas
« combien de candidats trouvés », c'est « combien confirmés » : 142, dont 132 avec un IMO non
nul (voir `imo_confirmes` plus bas — les dix restants sont des candidats confirmés par un
second champ mais dont le registre lui-même ne publie pas d'IMO, un cas réel et rare, pas une
absence de collecte).

**Le rendement en notations environnementales est le résultat, pas une contre-performance.**
Sur les 9 407 navires du catalogue, 31 ont une notation de design confirmée et 12 une
notation en exploitation confirmée (les deux se recoupent largement). Ce n'est pas un
sous-échantillonnage à corriger en élargissant la collecte : c'est la proportion réelle de
yachts privés dont la notation environnementale de classe est publique. **Cette couche ne
peut donc pas devenir une variable appliquée à la flotte entière** — ni par extrapolation, ni
par modèle — elle reste ce pour quoi elle a été construite : un petit ensemble d'études de cas
de haute confiance, à des fins de validation, jamais une colonne à joindre sur les 9 407.

## Politesse

Chaque client HTTP (un par domaine) espace ses propres appels d'au moins `DELAI` secondes,
`User-Agent` explicite et honnête. `robots.txt` de chaque domaine relu avant la première
requête de collecte réelle (voir le digest de collecte, pas ce module — un `robots.txt` peut
changer) : `vesselregister.dnv.com` et `leonardoinfo.com` n'en publient pas (404, donc aucune
restriction déclarée) ; `www.lr.org` en publie un qui n'exclut que `/episerver/` et `/utils/`,
sans toucher à `/webapi/`.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import httpx
import pandas as pd

from labs.ais import normaliser

RACINE = Path(__file__).resolve().parents[2]
CATALOGUE = RACINE / "data" / "yachts.parquet"
SORTIE = RACINE / "data" / "registres_classe.parquet"

AGENT = "pythonrocks-labs/0.1 (+https://github.com/drdjekyl/pythonrocks-labs; recherche non commerciale)"
DELAI = 1.2  # secondes minimum entre deux appels à un même domaine
LOT = 50  # navires entre deux écritures : un plantage ne coûte jamais plus que ce lot

DNV_BASE = "https://vesselregister.dnv.com/vesselregister"
LR_URL = "https://www.lr.org/webapi/searchproxy/search/"
LR_CONTENT_ID = "02557d43-1f3e-4b88-9251-def56a990b0b"
RINA_SHIPS_URL = "https://www.leonardoinfo.com/libroRegistroWeb/rest/search/ships"

DNV_CLASSE_CATALOGUE = (
    "Det Norske Veritas (DNV)"  # valeur de `vessel_class` dans le catalogue
)

TOLERANCE_ANNEE = 1.0
TOLERANCE_LONGUEUR_M = 1.0

# Suffixes juridiques et génériques d'un nom de chantier : ne discriminent jamais un
# constructeur d'un autre, on les retire avant de comparer les mots significatifs.
MOTS_CONSTRUCTEUR_IGNORES = {
    "YACHTS",
    "YACHT",
    "SHIPYARD",
    "SHIPYARDS",
    "WERFT",
    "GMBH",
    "CO",
    "KG",
    "LTD",
    "LIMITED",
    "INC",
    "SA",
    "SRL",
    "SPA",
    "NV",
    "BV",
    "GROUP",
    "MARINE",
    "INDUSTRIES",
    "FR",
    "SNC",
    "SAS",
    "AG",
    "CANTIERE",
    "CANTIERI",
    "SHIPBUILDING",
    "SHIPYARD.",
}

# La seule notation DNV constatée qui contient un espace au lieu d'une parenthèse collée.
# Énuméré, jamais deviné : voir la docstring du module.
NOTATIONS_MULTI_MOTS = {"GAS FUELLED"}


@dataclass(frozen=True, slots=True)
class Correspondance:
    """Une ligne du jeu de données : un navire du catalogue face à une source, avec verdict.

    `confiance` vaut `"confirme"` ou `"rejete"`. Sur un rejet, `imo` et les champs de notation
    sont `None` — un appariement non confirmé n'est jamais inclus comme donnée exploitable,
    seulement rapporté comme rejeté (voir la docstring du module).
    """

    yacht_id: str
    yacht_nom: str
    source: str  # "dnv" | "lr" | "rina"
    imo: str | None
    notation_design_brute: str | None
    notation_operation_brute: str | None
    flux_design: tuple[str, ...]
    flux_operation: tuple[str, ...]
    confiance: str
    champs_confirmes: tuple[str, ...]
    motif: str
    date_collecte: str


# --- Transport : un client par domaine, chacun espacé de ses propres appels ----------------


class Reponse(Protocol):
    def json(self) -> Any: ...
    def raise_for_status(self) -> Any: ...


class Client(Protocol):
    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Reponse: ...
    def post(self, url: str, json: dict[str, Any] | None = None) -> Reponse: ...


class DomaineIndisponible(Exception):
    """Le disjoncteur est ouvert : trop d'échecs consécutifs sur ce domaine, on ne retente
    plus avant la fin de la collecte en cours. Pas d'appel réseau, pas d'attente."""


# Codes retentés avec repli exponentiel : limite de débit et pannes serveur transitoires.
# Les autres (400, 404…) signalent une requête mal formée, pas un incident passager — les
# retenter ne changerait rien, autant échouer tout de suite.
STATUTS_REESSAYABLES = {429, 500, 502, 503, 504}


class ClientEspace:
    """Un client dont chaque appel est espacé d'au moins `delai` secondes du précédent, avec
    repli exponentiel sur 429/5xx et un disjoncteur par domaine.

    Centralise la politesse *et* la résilience à un seul endroit plutôt que de les parsemer
    dans chaque fonction métier — DNV fait jusqu'à deux requêtes par navire trouvé (recherche
    puis détails), LR et RINA une seule : la couture doit être au niveau du transport.

    La première collecte réelle sur les 900 navires visés s'est arrêtée net sur un unique 500
    de Lloyd's Register, remonté tel quel jusqu'à `main` — près de 30 minutes de collecte déjà
    faite perdues pour un incident transitoire qu'un simple nouvel essai aurait absorbé. Un
    échec isolé retente donc `tentatives_max` fois avec un délai qui double à chaque tentative ;
    au-delà de `seuil_echecs_consecutifs` échecs de suite (retries épuisés), le disjoncteur
    s'ouvre : ce domaine ne reçoit plus aucune requête jusqu'à la fin de la collecte — mieux
    vaut renoncer proprement à un registre qui s'effondre que continuer à le marteler.

    `pause` et `horloge` sont injectés pour que les tests s'exécutent en millisecondes sans
    dormir pour de vrai (voir `feedback_sleep_harness` : un `sleep` en dur bloque le harnais).
    """

    def __init__(
        self,
        client: httpx.Client,
        delai: float,
        pause=time.sleep,
        horloge=time.monotonic,
        tentatives_max: int = 3,
        delai_base_reessai: float = 2.0,
        seuil_echecs_consecutifs: int = 5,
    ) -> None:
        self._client = client
        self._delai = delai
        self._pause = pause
        self._horloge = horloge
        self._dernier: float | None = None
        self._tentatives_max = tentatives_max
        self._delai_base_reessai = delai_base_reessai
        self._seuil_echecs_consecutifs = seuil_echecs_consecutifs
        self._echecs_consecutifs = 0
        self.circuit_ouvert = False

    def _attendre(self) -> None:
        if self._dernier is not None:
            ecoule = self._horloge() - self._dernier
            if ecoule < self._delai:
                self._pause(self._delai - ecoule)
        self._dernier = self._horloge()

    def _executer(self, appel) -> Reponse:
        """`appel` déclenche la vraie requête HTTP. Ne renvoie que sur un statut non
        retentable — 2xx bien sûr, mais aussi un 4xx autre que 429, qu'il n'y a aucune raison
        de retenter."""
        if self.circuit_ouvert:
            raise DomaineIndisponible(
                f"domaine mis en pause après {self._seuil_echecs_consecutifs} échecs consécutifs"
            )

        derniere_erreur: Exception | None = None
        for tentative in range(self._tentatives_max):
            if tentative > 0:
                self._pause(self._delai_base_reessai * (2 ** (tentative - 1)))
            self._attendre()
            try:
                reponse = appel()
                if getattr(reponse, "status_code", None) in STATUTS_REESSAYABLES:
                    reponse.raise_for_status()
            except (httpx.HTTPStatusError, httpx.RequestError) as erreur:
                derniere_erreur = erreur
                continue
            self._echecs_consecutifs = 0
            return reponse

        self._echecs_consecutifs += 1
        if self._echecs_consecutifs >= self._seuil_echecs_consecutifs:
            self.circuit_ouvert = True
        assert derniere_erreur is not None
        raise derniere_erreur

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Reponse:
        return self._executer(
            lambda: self._client.get(url, params=params, headers=headers)
        )

    def post(self, url: str, json: dict[str, Any] | None = None) -> Reponse:
        return self._executer(
            lambda: self._client.post(
                url, json=json, headers={"Content-Type": "application/json"}
            )
        )


# --- DNV -------------------------------------------------------------------------------------


def dnv_extraire_candidats(charge: Any) -> list[dict]:
    if not isinstance(charge, dict) or "vessels" not in charge:
        raise ValueError(f"réponse DNV sans clé 'vessels' : {charge!r}")
    return [
        {"id": v["id"], "nom": v["name"], "imo": v.get("imoNo") or None}
        for v in (charge["vessels"] or [])
    ]


def dnv_extraire_details(charge: Any) -> dict:
    ident = charge.get("identification") or {}
    classification = charge.get("classification") or {}
    dimensions = charge.get("dimensions") or {}
    yard = charge.get("yard") or {}

    annee = None
    construction = yard.get("dateOfBuild")
    if construction:
        annee = float(str(construction)[:4])

    return {
        "imo": ident.get("imoNumber") or None,
        "notation_design": classification.get("classNotationStringDesign"),
        "notation_operation": classification.get("classNotationStringInOperation"),
        "longueur": dimensions.get("lengthOverall"),
        "annee": annee,
        "constructeur": yard.get("contractedBuilder") or yard.get("hullYardName"),
    }


def dnv_rechercher(client: Client, nom: str) -> list[dict]:
    reponse = client.get(f"{DNV_BASE}/vessel/get", params={"term": nom})
    reponse.raise_for_status()
    return dnv_extraire_candidats(reponse.json())


def dnv_details(client: Client, vessel_id: str) -> dict:
    reponse = client.get(f"{DNV_BASE}/vesseldetails", params={"vesselId": vessel_id})
    reponse.raise_for_status()
    return dnv_extraire_details(reponse.json())


# --- Lloyd's Register --------------------------------------------------------------------


def lr_extraire_candidats(charge: Any) -> list[dict]:
    if not isinstance(charge, dict) or "results" not in charge:
        raise ValueError(f"réponse LR sans clé 'results' : {charge!r}")
    candidats = []
    for r in charge["results"] or []:
        annee = None
        construction = r.get("dateOfBuild")
        if construction:
            annee = float(str(construction)[:4])
        candidats.append(
            {
                "nom": r.get("shipName"),
                "imo": r.get("imoNumber") or None,
                "annee": annee,
                "type": r.get("shipType"),
            }
        )
    return candidats


def lr_rechercher(client: Client, nom: str) -> list[dict]:
    corps = {
        "query": {"shipName": nom},
        "contentID": LR_CONTENT_ID,
        "page": 1,
        "facets": {},
        "orderby": {},
    }
    reponse = client.post(LR_URL, json=corps)
    reponse.raise_for_status()
    return lr_extraire_candidats(reponse.json())


# --- RINA (IMO seul — voir la docstring du module pour `shipDetail`) ---------------------


def rina_extraire_candidats(charge: Any) -> list[dict]:
    if not isinstance(charge, dict) or "result" not in charge:
        raise ValueError(f"réponse RINA sans clé 'result' : {charge!r}")
    if charge.get("resultType") != 1:
        return []  # resultType 3 observé = erreur serveur ; jamais des candidats valides
    enregistrements = (charge.get("result") or {}).get("records") or []
    candidats = []
    for r in enregistrements:
        annee = None
        construction = r.get("dataCompLavCant")
        if construction:
            try:
                annee = float(str(construction)[:4])
            except ValueError:
                annee = None
        longueur = None
        if r.get("lungStazza") not in (None, ""):
            try:
                longueur = float(r["lungStazza"])
            except ValueError:
                longueur = None
        candidats.append(
            {
                "nom": r.get("nome"),
                "imo": r.get("imo") or None,
                "annee": annee,
                "longueur": longueur,
            }
        )
    return candidats


def rina_rechercher(client: Client, nom: str) -> list[dict]:
    """L'entrée `X-LeoInputData` est un en-tête HTTP, pas un paramètre de requête — c'est ce
    qui distingue cette API des deux autres, et une erreur facile à commettre en la lisant vite.
    """
    corps = {
        "params": [["name", nom]],
        "paramsGET": {
            "filters": [],
            "fields": "",
            "sorting": "",
            "offset": 0,
            "limit": 10,
        },
    }
    reponse = client.get(RINA_SHIPS_URL, headers={"X-LeoInputData": json.dumps(corps)})
    reponse.raise_for_status()
    return rina_extraire_candidats(reponse.json())


# --- Décomposition des notations -----------------------------------------------------------


def decomposer_notation(chaine: str | None) -> tuple[str, ...]:
    """Découpe une chaîne de notations en flux individuels.

    `None` (source muette sur ce champ) et `""` (source explicite : aucune notation) donnent
    tous deux un tuple vide — la distinction entre les deux vit dans le champ brut à côté, pas
    ici.

    Deux mécanismes, un principe et une exception énumérée :

    1. **L'équilibre des parenthèses**, principe général : un qualificatif entre parenthèses
       peut lui-même contenir un espace ou une virgule (`TMON(oil lubricated)`,
       `ER(SCR, TIER III)`, observés en vrai sur le catalogue) — découper au premier espace
       couperait le qualificatif en deux. On regroupe donc les mots tant que les parenthèses
       ne sont pas refermées, plutôt que de deviner où s'arrête un qualificatif.
    2. **`NOTATIONS_MULTI_MOTS`**, l'exception : la seule notation constatée qui contient un
       espace *sans aucune parenthèse* (`Gas fuelled`). N'étant pas détectable par l'équilibre
       des parenthèses, elle est énumérée explicitement plutôt qu'inférée d'une règle
       générale, qui risquerait de recoller deux notations indépendantes.
    """
    if not chaine:
        return ()
    mots = chaine.split()
    flux: list[str] = []
    i = 0
    while i < len(mots):
        if (
            i + 1 < len(mots)
            and f"{mots[i]} {mots[i + 1]}".upper() in NOTATIONS_MULTI_MOTS
        ):
            flux.append(f"{mots[i]} {mots[i + 1]}")
            i += 2
            continue

        tampon = mots[i]
        while tampon.count("(") > tampon.count(")") and i + 1 < len(mots):
            i += 1
            tampon += f" {mots[i]}"
        flux.append(tampon)
        i += 1
    return tuple(flux)


# --- Confirmation par second champ ----------------------------------------------------------


def _proche(a: float | None, b: float | None, tolerance: float) -> bool:
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= tolerance


def _mots_significatifs(nom: str | None) -> set[str]:
    if not nom:
        return set()
    return {
        mot
        for mot in normaliser(nom).split()
        if len(mot) >= 4 and mot not in MOTS_CONSTRUCTEUR_IGNORES
    }


def _constructeurs_concordent(a: str | None, b: str | None) -> bool:
    return bool(_mots_significatifs(a) & _mots_significatifs(b))


def confirmer(
    annee_catalogue: float | None,
    longueur_catalogue: float | None,
    constructeur_catalogue: str | None,
    *,
    annee_source: float | None = None,
    longueur_source: float | None = None,
    constructeur_source: str | None = None,
) -> tuple[str, ...]:
    """Le tuple des champs qui concordent — vide si aucun. Un tuple non vide = confirmé.

    Champs non fournis par une source (LR ne donne ni longueur ni constructeur, RINA ne donne
    pas de constructeur) : simplement absents de la comparaison, jamais traités comme un
    accord ou un désaccord.
    """
    champs = []
    if _proche(annee_catalogue, annee_source, TOLERANCE_ANNEE):
        champs.append("annee")
    if _proche(longueur_catalogue, longueur_source, TOLERANCE_LONGUEUR_M):
        champs.append("longueur")
    if _constructeurs_concordent(constructeur_catalogue, constructeur_source):
        champs.append("constructeur")
    return tuple(champs)


def _candidats_au_nom_exact(candidats: list[dict], nom_catalogue: str) -> list[dict]:
    """Ne garde que les candidats dont le nom normalisé est strictement égal au nôtre.

    Ces registres font eux-mêmes une recherche floue (« Eclipse » renvoie un pétrolier GPL) —
    un sous-ensemble ou une variante n'est pas « le même navire trouvé par nom », c'est un
    navire différent qui partage une sous-chaîne. Filtrer ici, avant toute confirmation par
    second champ, évite de traiter un homonyme partiel comme un candidat légitime.
    """
    cle = normaliser(nom_catalogue)
    return [c for c in candidats if normaliser(c.get("nom") or "") == cle]


# --- Appariement, source par source ---------------------------------------------------------


def _rejet(
    yacht_id: str, yacht_nom: str, source: str, motif: str, date_collecte: str
) -> Correspondance:
    return Correspondance(
        yacht_id=yacht_id,
        yacht_nom=yacht_nom,
        source=source,
        imo=None,
        notation_design_brute=None,
        notation_operation_brute=None,
        flux_design=(),
        flux_operation=(),
        confiance="rejete",
        champs_confirmes=(),
        motif=motif,
        date_collecte=date_collecte,
    )


def apparier_dnv(
    client: Client, navire: dict, date_collecte: str
) -> Correspondance | None:
    """`None` : aucun candidat au nom exact — pas de ligne. Sinon, confirmé ou rejeté."""
    candidats = _candidats_au_nom_exact(
        dnv_rechercher(client, navire["name"]), navire["name"]
    )
    if not candidats:
        return None

    for candidat in candidats:
        details = dnv_details(client, candidat["id"])
        champs = confirmer(
            navire.get("year"),
            navire.get("overall_length"),
            navire.get("builder"),
            annee_source=details["annee"],
            longueur_source=details["longueur"],
            constructeur_source=details["constructeur"],
        )
        if champs:
            return Correspondance(
                yacht_id=navire["id"],
                yacht_nom=navire["name"],
                source="dnv",
                imo=details["imo"] or candidat["imo"],
                notation_design_brute=details["notation_design"],
                notation_operation_brute=details["notation_operation"],
                flux_design=decomposer_notation(details["notation_design"]),
                flux_operation=decomposer_notation(details["notation_operation"]),
                confiance="confirme",
                champs_confirmes=champs,
                motif=f"confirmé par {', '.join(champs)}",
                date_collecte=date_collecte,
            )

    return _rejet(
        navire["id"],
        navire["name"],
        "dnv",
        f"{len(candidats)} candidat(s) au nom exact, aucun champ secondaire concordant",
        date_collecte,
    )


def apparier_lr(
    client: Client, navire: dict, date_collecte: str
) -> Correspondance | None:
    candidats = _candidats_au_nom_exact(
        lr_rechercher(client, navire["name"]), navire["name"]
    )
    if not candidats:
        return None

    for candidat in candidats:
        champs = confirmer(
            navire.get("year"),
            navire.get("overall_length"),
            navire.get("builder"),
            annee_source=candidat["annee"],
        )
        if champs:
            return Correspondance(
                yacht_id=navire["id"],
                yacht_nom=navire["name"],
                source="lr",
                imo=candidat["imo"],
                notation_design_brute=None,
                notation_operation_brute=None,
                flux_design=(),
                flux_operation=(),
                confiance="confirme",
                champs_confirmes=champs,
                motif=f"confirmé par {', '.join(champs)}",
                date_collecte=date_collecte,
            )

    return _rejet(
        navire["id"],
        navire["name"],
        "lr",
        f"{len(candidats)} candidat(s) au nom exact, aucun champ secondaire concordant "
        "(LR ne fournit que l'année comme champ de confirmation)",
        date_collecte,
    )


def apparier_rina(
    client: Client, navire: dict, date_collecte: str
) -> Correspondance | None:
    candidats = _candidats_au_nom_exact(
        rina_rechercher(client, navire["name"]), navire["name"]
    )
    if not candidats:
        return None

    for candidat in candidats:
        champs = confirmer(
            navire.get("year"),
            navire.get("overall_length"),
            navire.get("builder"),
            annee_source=candidat["annee"],
            longueur_source=candidat["longueur"],
        )
        if champs:
            return Correspondance(
                yacht_id=navire["id"],
                yacht_nom=navire["name"],
                source="rina",
                imo=candidat["imo"],
                notation_design_brute=None,  # `shipDetail` inaccessible, voir la docstring
                notation_operation_brute=None,
                flux_design=(),
                flux_operation=(),
                confiance="confirme",
                champs_confirmes=champs,
                motif=f"confirmé par {', '.join(champs)}",
                date_collecte=date_collecte,
            )

    return _rejet(
        navire["id"],
        navire["name"],
        "rina",
        f"{len(candidats)} candidat(s) au nom exact, aucun champ secondaire concordant",
        date_collecte,
    )


APPARIEURS = {"dnv": apparier_dnv, "lr": apparier_lr, "rina": apparier_rina}


# --- Échantillonnage et collecte -----------------------------------------------------------


def echantillon(df: pd.DataFrame, taille: int, graine: int = 20260817) -> pd.DataFrame:
    """Les navires déjà tagués DNV par le catalogue, plus un tirage aléatoire graine fixe
    parmi le reste — pour aller au-delà des 97 connus sans s'y limiter, et reproductible d'une
    exécution à l'autre.
    """
    tagues = df[df["vessel_class"] == DNV_CLASSE_CATALOGUE]
    reste = df[df["vessel_class"] != DNV_CLASSE_CATALOGUE]
    tirage = reste.sample(n=min(taille, len(reste)), random_state=graine)
    return pd.concat([tagues, tirage], ignore_index=True)


def collecter(
    clients: dict[str, Client],
    navires: pd.DataFrame,
    journal=print,
    erreur_reseau: type[Exception] | tuple[type[Exception], ...] = (
        httpx.HTTPError,
        DomaineIndisponible,
    ),
    deja_fait: set[tuple[str, str]] = frozenset(),
) -> tuple[list[Correspondance], dict[str, int], dict[str, int]]:
    """Interroge chaque source pour chaque navire. Renvoie les correspondances (confirmées et
    rejetées, jamais les non-trouvées), un compteur de non-trouvés par source, et un compteur
    d'erreurs réseau par source — trois compteurs, parce que ce sont trois absences
    différentes : "cherché, rien trouvé" n'est pas "cherché, la source a échoué".

    Une erreur réseau sur un navire (un 500 ponctuel du côté du registre, observé en vrai lors
    de la collecte réelle) ne doit interrompre ni ce navire ni les suivants : sur des centaines
    d'appels à un service tiers, un incident ponctuel est la norme, pas l'exception — la
    version qui laissait n'importe quelle `httpx.HTTPError` remonter jusqu'à `main` a perdu
    plusieurs minutes de collecte déjà faite sur un seul 500 de Lloyd's Register. `ClientEspace`
    absorbe déjà les retentables (429/5xx) avec repli exponentiel ; ce qui arrive encore ici a
    soit épuisé ses tentatives, soit le disjoncteur du domaine est ouvert — dans les deux cas,
    on compte et on continue, jamais on n'interrompt la boucle.

    `deja_fait` (couples navire/source déjà présents dans un jeu de données antérieur) permet
    de reprendre une collecte interrompue sans refaire ce qui l'a déjà été.
    """
    resultats: list[Correspondance] = []
    non_trouves = dict.fromkeys(clients, 0)
    erreurs = dict.fromkeys(clients, 0)
    aujourdhui = date.today().isoformat()

    for _, ligne in navires.iterrows():
        navire = ligne.to_dict()
        for source, client in clients.items():
            if (navire["id"], source) in deja_fait:
                continue
            try:
                correspondance = APPARIEURS[source](client, navire, aujourdhui)
            except erreur_reseau as erreur:
                erreurs[source] += 1
                journal(f"{source:4} {navire['name']:30.30} ERREUR    {erreur}")
                continue
            if correspondance is None:
                non_trouves[source] += 1
            else:
                resultats.append(correspondance)
                journal(
                    f"{source:4} {navire['name']:30.30} {correspondance.confiance:8} "
                    f"imo={correspondance.imo}"
                )

    return resultats, non_trouves, erreurs


def imo_confirmes(df: pd.DataFrame | None = None) -> pd.Series:
    """La vue la plus durable de ce module : `yacht_id -> IMO`, un seul par navire.

    Le livrable le plus réutilisable n'est pas le jeu complet (sources, rejets, notations) —
    c'est ce mapping seul, pour quiconque veut juste résoudre un IMO sans comprendre le reste
    du schéma. `df` par défaut relit `SORTIE` ; le passer explicitement évite une lecture
    disque à qui a déjà le jeu de données en mémoire.

    Un navire confirmé par plusieurs sources n'apparaît qu'une fois (`keep="first"`) : en
    pratique les sources ne se contredisent jamais sur l'IMO (vérifié sur la collecte réelle,
    zéro navire avec deux IMO distincts confirmés) — c'est le même numéro OMI officiel, quelle
    que soit la source qui le publie. Les correspondances confirmées sans IMO (le registre ne
    le publie pas pour ce navire, un cas réel et rare) n'apparaissent pas : ce mapping ne sert
    que l'IMO, jamais un `None`.
    """
    if df is None:
        df = pd.read_parquet(SORTIE)
    confirmes = df[(df["confiance"] == "confirme") & df["imo"].notna()]
    return confirmes.drop_duplicates("yacht_id", keep="first").set_index("yacht_id")[
        "imo"
    ]


def _colonnes_correspondance() -> list[str]:
    return [f.name for f in fields(Correspondance)]


def _en_lignes(correspondances: list[Correspondance]) -> list[dict]:
    """`asdict` en listes plutôt qu'en tuples : Parquet ne sait pas sérialiser un tuple."""
    lignes = [asdict(c) for c in correspondances]
    for ligne in lignes:
        ligne["flux_design"] = list(ligne["flux_design"])
        ligne["flux_operation"] = list(ligne["flux_operation"])
        ligne["champs_confirmes"] = list(ligne["champs_confirmes"])
    return lignes


def _charger_existant() -> pd.DataFrame:
    if SORTIE.exists():
        return pd.read_parquet(SORTIE)
    return pd.DataFrame(columns=_colonnes_correspondance())


def _sauvegarder(
    existant: pd.DataFrame, nouveaux: list[Correspondance]
) -> pd.DataFrame:
    if nouveaux:
        existant = pd.concat(
            [existant, pd.DataFrame(_en_lignes(nouveaux))], ignore_index=True
        )
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    existant.to_parquet(SORTIE, index=False)
    return existant


def main() -> int:
    """Collecte par lots de `LOT` navires, avec écriture et reprise à chaque lot.

    Un plantage à 95 % du parcours (le mode de défaillance réel rencontré) ne coûte plus que
    le lot en cours : `_charger_existant` relit ce qui a déjà été écrit, et `collecter` saute
    les couples (navire, source) déjà présents plutôt que de les refaire.
    """
    taille = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    df = pd.read_parquet(CATALOGUE)
    navires = echantillon(df, taille)
    print(
        f"{len(navires)} navires ciblés sur {len(df)} au catalogue "
        f"({len(navires[navires['vessel_class'] == DNV_CLASSE_CATALOGUE])} déjà tagués DNV)",
        flush=True,
    )

    existant = _charger_existant()
    deja_fait = set(zip(existant["yacht_id"], existant["source"], strict=True))
    if deja_fait:
        print(
            f"reprise : {len(deja_fait)} couples (navire, source) déjà collectés, non refaits",
            flush=True,
        )

    non_trouves_total = dict.fromkeys(APPARIEURS, 0)
    erreurs_total = dict.fromkeys(APPARIEURS, 0)

    with httpx.Client(headers={"User-Agent": AGENT}, timeout=30) as brut:
        clients = {source: ClientEspace(brut, DELAI) for source in APPARIEURS}

        for debut in range(0, len(navires), LOT):
            lot = navires.iloc[debut : debut + LOT]
            resultats, non_trouves, erreurs = collecter(
                clients,
                lot,
                journal=lambda m: print(m, flush=True),
                deja_fait=deja_fait,
            )
            for source in APPARIEURS:
                non_trouves_total[source] += non_trouves[source]
                erreurs_total[source] += erreurs[source]

            existant = _sauvegarder(existant, resultats)
            deja_fait |= {(c.yacht_id, c.source) for c in resultats}
            print(
                f"  lot {debut // LOT + 1}/{-(-len(navires) // LOT)} -> "
                f"{len(existant)} lignes cumulées dans {SORTIE.name}",
                flush=True,
            )

            circuits = [s for s, c in clients.items() if c.circuit_ouvert]
            if circuits:
                print(
                    f"  domaines mis en pause (disjoncteur ouvert) : {circuits}",
                    flush=True,
                )

    print(f"\n{len(existant)} lignes -> {SORTIE.name}")
    if not existant.empty:
        print(existant.groupby(["source", "confiance"]).size().to_string())
    print(f"non trouvés au registre (cette exécution) : {non_trouves_total}")
    print(f"erreurs réseau absorbées (cette exécution) : {erreurs_total}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
