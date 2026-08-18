# pythonrocks-labs

## Scope

Le code exécutable des articles techniques publiés sur `pythonrocks.academy/ressources/`, et
depuis le 2026-08-17 le code de recherche de l'index environnemental multi-flux. Un seul jeu de
données sert de fil rouge : **9 407 yachts**, servis par `api.pythonrocks.academy`.

**Ce dépôt est PUBLIC**, et trois articles publiés y renvoient. C'est ce qui justifie son
`README.md` — l'exception assumée à la règle de budget documentaire du workspace, dont le motif
écrit est « ces dépôts sont privés, aucun public externe à servir ». Ici le public existe : le
lecteur d'un article qui veut rejouer les chiffres. Le `README.md` s'adresse à lui, ce fichier-ci
s'adresse à Claude et à l'auteur.

Conséquence directe : **rien de sensible ne rentre ici**. Pas de secret, pas de donnée client, et
aucune sortie nominative (voir Contraintes).

## Structure

```
src/labs/
  yachts.py            instantané du catalogue -> data/yachts.parquet
  ais.py               positions AIS
  marine_cadastre.py   appariement catalogue <-> AIS, et son scoring
  medallion.py         bronze/silver/gold sur DuckDB
  viz.py               palette et primitives de figures
  figures_eda.py       figures de l'article d'exploration
  figures_ais.py       figures de l'article d'appariement
  reglementaire.py     plancher réglementaire MARPOL (2026-08-17)
  registres_classe.py  IMO et notations de classe via DNV/LR/RINA (2026-08-17)
  vecteur_impacts.py   vecteur d'impacts par invité-nuit et par GT-heure (2026-08-17)
```

Les analyses partent de `data/*.parquet`, jamais de l'API en direct : reproductibilité à
l'identique, et l'API applique 60 requêtes/minute tout en hébergeant la vitrine.

## Contraintes, à relire avant d'écrire du code d'index

- **Aucune sortie nominative.** Jamais de classement de navires nommés, jamais de fichier associant
  `name` à un score. La directive UE 2024/825 s'applique au 27 septembre 2026, et le dénigrement se
  caractérise dès qu'une entreprise est simplement identifiable. Les sorties publiables se font par
  **cohortes** (classe de GT × décennie × type de coque). Une fonction qui rend un résultat par
  navire porte un nom qui le dit et une docstring qui interdit sa publication telle quelle.
- **Ne jamais nommer le résultat « score environnemental ».** C'est un *proxy d'intensité de
  conception*. Un modèle produit un estimateur, un référentiel produit une attestation : confondre
  les deux est exactement ce que ce travail dénonce.
- **Jamais de supposition silencieuse sur donnée manquante.** Dtypes nullables pandas et logique à
  trois valeurs partout. `x or 0` sur un champ nullable est le piège maison : il a produit deux
  chiffres faux dans cette session (80,3 % au lieu d'une borne 71–80,6 %, puis ρ = −0,43 au lieu de
  −0,62), les deux fois en transformant « inconnu » en « zéro » sans qu'aucune exception ne se
  déclenche.
- **La couche équipement plafonne à 74 navires.** Mesuré sur la collecte complète des 9 407 :
  74 notations de design, 37 en service, toutes venant de DNV — RINA exclut la plaisance privée et
  Lloyd's Register ne publie pas les notations. C'est un **jeu d'études de cas**, jamais une
  variable de modèle appliquée à la flotte. Ne pas repartir chercher un volume qui n'existe pas.
- **Un appariement par nom seul est un appariement faux.** L'appariement AIS publié tourne à 85 %
  de faux positifs. `registres_classe.py` confirme chaque correspondance par un second champ
  concordant (année ±1 an, longueur ±1 m, ou constructeur) et rejette le reste : la moitié des
  correspondances DNV et la quasi-totalité des RINA sont tombées à ce filtre. C'est le filtre qui
  rend le chiffre de 1 007 solide.
- **Distinguer « aucune notation » de « navire absent du registre ».** Azzam ressort avec une chaîne
  vide : c'est une information réelle, l'armateur n'a rien pris. Un navire introuvable est une
  absence de donnée. Les confondre ruine le jeu de validation.

## Résultats qui contraignent la suite

- **Le paradoxe de l'unité fonctionnelle**, cœur du travail : sur les flux liés aux personnes (eaux
  noires, eaux grises, déchets), la corrélation de rang entre `gCO₂/invité-nuit` et `gCO₂/GT/h` vaut
  **−0,62**. Négative : les deux normalisations ne classent pas différemment, elles classent à
  l'envers. Mécanisme mesuré — le ratio équipage/invités monte avec la taille (+0,742 contre la
  longueur) pendant que la densité de personnes par tonneau chute (−0,750).
- **Le plancher réglementaire** : entre **71 % et 80,6 %** du catalogue n'a aucune obligation
  certifiée sur les hydrocarbures, les eaux noires, l'air ni l'antifouling. Borne, jamais un point :
  9,6 % des navires sont indéterminés faute de données.
- **964 navires ont désormais un IMO** (`registres_classe.imo_confirmes()`). Le catalogue n'en
  portait aucun — c'est ce qui bloquait toute jointure externe.
- **Le mur des 499 GT est réel mais ne biaise pas l'indice** : 482 navires dans la bande 475-499
  contre 13 dans 500-524, et 184 à exactement 499. Mais les navires à 499 GT sont dimensionnellement
  normaux (−0,8 % ± 0,9 contre leurs dimensions) : c'est de la conception, pas de la sous-déclaration.
  L'hypothèse de biais a été testée et rejetée — ne pas la ressortir sans nouvelle donnée.

## Conventions

- Python 3.12+, `uv`. Lint `ruff`, tests `pytest`.
- **Ni pre-commit ni CI dans ce dépôt** — contrairement à tous les autres du workspace. Il faut donc
  lancer `uv run ruff check .`, `uv run ruff format --check .` et `uv run pytest` **à la main** avant
  de committer. C'est l'exception qui justifie de déroger à la règle « pas de lint manuel » : ici
  rien d'autre n'attrape une régression.
- Le référentiel SFC des moteurs vit dans `api-lab`, pas ici, et son chargement sur les hôtes vivants
  passe par `platform/host/ansible/roles/restore/files/seed_engines.js` — voir `api-lab/CLAUDE.md`.
- Budget doc : `README.md` (public, voir Scope) + `CLAUDE.md` + `MAINTENANCE.md`.

## Commandes

```bash
uv sync
uv run jupyter lab
uv run python src/labs/yachts.py                    # régénère l'instantané (~2 min, throttlé)
uv run python src/labs/registres_classe.py <taille> # collecte IMO/notations, reprenable
uv run python -m labs.reglementaire                 # répartition des obligations sur le catalogue
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
