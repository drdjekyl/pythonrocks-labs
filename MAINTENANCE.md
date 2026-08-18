# Maintenance — pythonrocks-labs

Backlog vivant, todo uniquement : les entrées s'ajoutent au fil de l'eau et sont supprimées dès
qu'elles sont résolues — pas de changelog dans ce fichier, `git log` est l'historique. Ne pas
laisser grossir sans revue.

---

## ☐ Priorité haute

- **Aucune vérification de source n'a été faite sur trois chiffres qui iront dans un article.**
  Tant que ce n'est pas fait, rien de ce qui suit n'est publiable.
  (1) La **table des seuils MARPOL** de `reglementaire.py` a été reprise telle quelle du chapitre 4
  du mémoire de M2 de l'auteur, jamais confrontée au texte des conventions.
  (2) Les **seuils Tier NOx** utilisés par `vecteur_impacts.py` pour son diagnostic viennent de
  DieselNet ; `imo.org` a répondu 500 aux deux tentatives de sourçage. À re-sourcer sur l'OMI ou
  EUR-Lex.
  (3) Les **983 correspondances confirmées portant un IMO** (soit 964 navires distincts, voir
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
- **Le docstring de `registres_classe.py` décrit encore la collecte pilote, pas la collecte
  complète.** Sa section « Ce que la collecte réelle a donné » annonce 997 navires interrogés,
  308 lignes, 142 confirmées, 132 avec IMO, 31 notations de design et 12 en exploitation. Le
  Parquet livré par la collecte complète des 9 407 en porte 2 642, dont 1 007 confirmées, 983 avec
  IMO (964 navires distincts), 74 notations de design et 37 en exploitation — les taux de rejet par
  source du tableau sont périmés de la même façon. Ces chiffres-là sont ceux qui iront dans un
  article : à réaligner sur le Parquet.
- **Trois flux manquent au vecteur d'impacts, et le manque n'est pas neutre.**
  (1) La **charge hôtelière ne couvre que 3 des 11 groupes EEDI** — la climatisation en particulier
  est exclue, faute de la « interior space » qu'exigent les régressions TU Delft. C'est une
  sous-estimation assumée sur le poste qui domine le bilan annuel.
  (2) Le **PM n'est pas calculé** : aucune source primaire trouvée dans le temps imparti.
  (3) L'**antifouling** et l'**ancrage** sont hors v1 : le premier demanderait une surface mouillée
  et un taux de lessivage sourcés, le second est un risque et non un flux continu.
- **L'agrégation du vecteur en un scalaire reste à écrire**, et c'est le geste le plus contestable
  de tout le travail. Exige des facteurs de caractérisation ACV publiés (ReCiPe, EF 3.1), leur
  publication explicite, et une analyse de sensibilité. Ne jamais inventer de pondération : c'est
  précisément ce que ce travail reproche à l'état de l'art.

## ☐ Priorité basse

- **Deux valeurs de `main_eng_count` sont aberrantes** dans le catalogue amont — 545 et 1 100
  moteurs, erreurs de saisie manifestes. `resume_par_cohorte()` utilise des médianes et y résiste,
  mais tout calcul par navire les traînera. Le correctif appartient à `api-lab`, pas ici.
