# Maintenance — pythonrocks-labs

Backlog vivant, todo uniquement : les entrées s'ajoutent au fil de l'eau et sont supprimées dès
qu'elles sont résolues — pas de changelog dans ce fichier, `git log` est l'historique. Ne pas
laisser grossir sans revue.

---

## ☐ Priorité haute

- **Aucune vérification de source n'a été faite sur deux chiffres qui iront dans un article.**
  Tant que ce n'est pas fait, rien de ce qui suit n'est publiable.
  (1) La **table des seuils MARPOL** de `reglementaire.py` a été reprise telle quelle du chapitre 4
  du mémoire de M2 de l'auteur. **Première confrontation faite le 2026-08-20, contre les pages de
  l'OMI — elle ne confirme pas la table, elle trouve deux écarts sur l'Annexe V.**
  *Confirmé* : l'ISPP de l'Annexe IV s'applique à 400 GT et plus **ou** aux navires certifiés pour
  « **more than** 15 persons ». Le seuil et sa stricte inégalité (`invites > 15`) sont exacts.
  *Écart 1 — le comptage de personnes de l'Annexe V.* L'OMI écrit « 15 persons **or more** » pour le
  plan de gestion des ordures comme pour le registre, là où l'Annexe IV écrit « more than ». Le
  module n'a qu'une constante, `SEUIL_INVITES`, appliquée en `>` aux trois obligations : un navire
  certifié pour **exactement 15 personnes** se voit donc exempté des deux obligations Annexe V
  alors que le texte l'y soumet.
  *Écart 2 — le tonnage du registre des ordures.* `GARBAGE_RECORD_BOOK` est branché sur
  `gt_certificats` (400 GT) ; l'OMI donne **100 GT** pour le registre comme pour le plan. Si l'écart
  se confirme, la bonne branche est `gt_garbage_plan`, déjà définie.
  **Ce qui reste à faire, et pourquoi ce n'est pas clos** : imo.org est une restitution secondaire,
  pas le texte de la convention. C'est une source bien meilleure qu'un mémoire non vérifié — et
  c'est celle qu'on a déjà acceptée pour les seuils Tier NOx — mais deux écarts sur une table
  justifient d'aller à la règle 10 de l'Annexe V elle-même avant de toucher au code. **Ne pas
  corriger les seuils sur la foi de cette note** : ils changent les résultats de recherche.
  *Non vérifié du tout* : `SEUIL_GT_ISM = 500`. Le Code ISM couvre les navires de charge à partir de
  500 GT, mais aussi les navires à passagers **quel que soit leur tonnage** — branche absente du
  module, qui peut compter pour un yacht transportant plus de 12 passagers. La page ISM de l'OMI ne
  donne aucun seuil, il faut le chapitre IX de SOLAS.
  (2) Les **983 correspondances confirmées portant un IMO** (soit 964 navires distincts, voir
  `imo_confirmes()`) et les **74 notations de design** de `data/registres_classe.parquet` n'ont pas
  été revérifiées à la main contre les registres : seule la logique d'appariement est testée, sur
  des réponses simulées. Un échantillon suffirait.

## ☐ Priorité moyenne

- **Refaire l'appariement AIS avec les IMO désormais disponibles.** L'article publié
  « Joindre deux jeux de données sans clé commune » tourne à 85 % de faux positifs faute de clé
  commune. `registres_classe.imo_confirmes()` en fournit maintenant 964. Le gisement reste partiel
  — 10 % du catalogue — mais c'est un sous-ensemble où l'appariement devient exact, donc une
  mesure du taux d'erreur réel de la méthode par nom. Ça vaut soit une correction de l'article
  publié, soit une suite.
