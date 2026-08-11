# pythonrocks-labs

Le code exécutable des articles techniques de
[pythonrocks.academy](https://pythonrocks.academy/ressources/). Un dossier par article, chacun
avec son propre README.

Tout part du même jeu de données réel : **9 407 yachts**, servis par
[api.pythonrocks.academy](https://api.pythonrocks.academy/docs). Les articles s'enchaînent sur
cet unique fil rouge plutôt que sur trois démonstrations sans rapport.

## Démarrer

```bash
uv sync
uv run jupyter lab
```

## Les données

`data/yachts.parquet` est un instantané versionné, produit par `src/labs/yachts.py`.

Les analyses partent de ce fichier, pas de l'API en direct. Deux raisons : elles restent
reproductibles à l'identique dans six mois, et exécuter un notebook ne déclenche pas 95 requêtes
chez quelqu'un d'autre — l'API applique une limite de 60 requêtes par minute et héberge aussi le
site vitrine.

Pour le régénérer (≈ 2 minutes, throttlé volontairement) :

```bash
uv run python src/labs/yachts.py
```

## Licence

MIT.
