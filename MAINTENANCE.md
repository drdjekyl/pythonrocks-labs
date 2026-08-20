# Maintenance — pythonrocks-labs

Backlog vivant, todo uniquement : les entrées s'ajoutent au fil de l'eau et sont supprimées dès
qu'elles sont résolues — pas de changelog dans ce fichier, `git log` est l'historique. Ne pas
laisser grossir sans revue.

---

## ☐ Priorité haute

- **Les 983 correspondances confirmées portant un IMO** (soit 964 navires distincts, voir
  `imo_confirmes()`) et les **74 notations de design** de `data/registres_classe.parquet` n'ont pas
  été revérifiées à la main contre les registres : seule la logique d'appariement est testée, sur
  des réponses simulées. Un échantillon suffirait. **Tant que ce n'est pas fait, rien de ce qui
  s'appuie sur ces correspondances n'est publiable** — même règle que la table des seuils MARPOL
  ci-dessous, déjà traitée.

  *Table des seuils MARPOL/SOLAS, résolu le 2026-08-21* : confrontée au texte primaire OMI (pas
  une restitution secondaire — résolutions MEPC.201(62)/MEPC.360(79) lues en PDF, texte consolidé
  SOLAS d'une autorité maritime nationale), trois écarts confirmés et corrigés dans
  `reglementaire.py`/`tests/test_reglementaire.py` : (1) le seuil de personnes de l'Annexe V
  (plan de gestion + registre des ordures) est « 15 or more » — inclusif — et non « more than 15 »
  comme l'ISPP de l'Annexe IV, qui lui reste correctement strict ; (2) le registre des ordures est
  passé à 100 GT (au lieu de 400) par l'amendement MEPC.360(79), en vigueur depuis le 2024-05-01 —
  le mémoire de 2023 portait l'ancien seuil ; (3) le Code ISM (SOLAS IX/2) s'applique aussi aux
  navires à passagers (SOLAS I/2(f), plus de 12 personnes) **sans aucun seuil de tonnage**, branche
  absente de la table d'origine. Effet mesuré sur les 9 407 navires : `GARBAGE_RECORD_BOOK` passe
  de 1 820 à 8 174 confirmés (converge avec `GARBAGE_MGMT_PLAN`, même seuil désormais), `ISM` de
  926 à 1 178. Suite logique et distincte : republier/corriger tout contenu déjà sorti de ce
  module sur l'ancienne table, si un tel contenu existe.

## ☐ Priorité moyenne

- **Refaire l'appariement AIS avec les IMO désormais disponibles.** L'article publié
  « Joindre deux jeux de données sans clé commune » tourne à 85 % de faux positifs faute de clé
  commune. `registres_classe.imo_confirmes()` en fournit maintenant 964. Le gisement reste partiel
  — 10 % du catalogue — mais c'est un sous-ensemble où l'appariement devient exact, donc une
  mesure du taux d'erreur réel de la méthode par nom. Ça vaut soit une correction de l'article
  publié, soit une suite.
