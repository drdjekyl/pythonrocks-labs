# Maintenance — pythonrocks-labs

Backlog vivant, todo uniquement : les entrées s'ajoutent au fil de l'eau et sont supprimées dès
qu'elles sont résolues — pas de changelog dans ce fichier, `git log` est l'historique. Ne pas
laisser grossir sans revue.

---

## ☐ Priorité haute

- **Aucune vérification de source n'a été faite sur deux chiffres qui iront dans un article.**
  Tant que ce n'est pas fait, rien de ce qui suit n'est publiable.
  (1) La **table des seuils MARPOL** de `reglementaire.py` a été reprise telle quelle du chapitre 4
  du mémoire de M2 de l'auteur, jamais confrontée au texte des conventions.
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

## ☐ Priorité basse

- **Deux valeurs de `main_eng_count` sont aberrantes** dans le catalogue amont — 545 et 1 100
  moteurs, erreurs de saisie manifestes. `resume_par_cohorte()` utilise des médianes et y résiste,
  mais tout calcul par navire les traînera. Le correctif appartient à `api-lab`, pas ici.
