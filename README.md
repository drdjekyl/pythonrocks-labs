# pythonrocks-labs

Le code exécutable des articles techniques de
[pythonrocks.academy](https://pythonrocks.academy/ressources/), et le code de recherche de
l'index environnemental multi-flux qui les prolonge.

Tout part du même jeu de données réel : **9 407 yachts**, servis par
[api.pythonrocks.academy](https://api.pythonrocks.academy/docs). Les articles s'enchaînent sur
cet unique fil rouge plutôt que sur trois démonstrations sans rapport.

## Démarrer

```bash
uv sync
uv run pytest
```

Il n'y a **pas de notebook versionné ici** : chaque analyse est un module de `src/labs/`,
qu'on exécute ou qu'on importe. C'est ce qui la rend testable et diffable.

```bash
uv run python -m labs.reglementaire   # répartition des obligations sur le catalogue
```

Si [`just`](https://github.com/casey/just) est installé (`uv tool install rust-just`),
`just` liste les recettes, `just check` lance le lint et les tests.

## Ce que contient le dépôt

`src/labs/`, à plat, un module par sujet :

| Module | Rôle |
| --- | --- |
| `yachts.py` | instantané du catalogue depuis l'API → `data/yachts.parquet` |
| `ais.py` | collecte de positions AIS |
| `marine_cadastre.py` | appariement catalogue ↔ AIS par le nom, et son scoring |
| `medallion.py` | couches bronze / silver / gold sur DuckDB |
| `viz.py` | palette et primitives de figures |
| `figures_eda.py` | les figures de l'article d'exploration du catalogue |
| `figures_ais.py` | les figures de l'article d'appariement AIS |
| `reglementaire.py` | plancher réglementaire MARPOL par navire |
| `registres_classe.py` | IMO et notations de classe via DNV / Lloyd's Register / RINA |
| `vecteur_impacts.py` | impacts flux par flux, par invité-nuit et par GT-heure |

`tests/` couvre les modules d'analyse (`pytest`). `figures/` et les couches silver/gold ne sont
pas versionnées : elles se régénèrent en une commande.

## Les données

Deux instantanés Parquet sont versionnés :

- **`data/yachts.parquet`** — le catalogue, 9 407 navires, produit par `src/labs/yachts.py`.
- **`data/registres_classe.parquet`** — les correspondances trouvées dans les registres de
  classification, produites par `src/labs/registres_classe.py` : 2 642 candidats, dont 1 007
  confirmés par un second champ concordant, ce qui donne un IMO à 964 navires du catalogue.
  Le catalogue amont n'en portait aucun.

Les analyses partent de ces fichiers, pas de l'API en direct. Deux raisons : elles restent
reproductibles à l'identique dans six mois, et les rejouer ne déclenche pas 95 requêtes chez
quelqu'un d'autre — l'API applique une limite de 60 requêtes par minute et héberge aussi le
site vitrine.

Pour régénérer le catalogue (≈ 2 minutes, throttlé volontairement) :

```bash
uv run python src/labs/yachts.py
```

## Licence

MIT.
