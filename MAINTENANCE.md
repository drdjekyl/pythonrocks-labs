# Maintenance — pythonrocks-labs

Backlog vivant, todo uniquement : les entrées s'ajoutent au fil de l'eau et sont supprimées dès
qu'elles sont résolues — pas de changelog dans ce fichier, `git log` est l'historique. Ne pas
laisser grossir sans revue.

---

## ☐ Priorité haute

- **Les 74 notations de design** (DNV) de `data/registres_classe.parquet` n'ont pas été
  revérifiées à la main contre le registre : seule la logique d'appariement est testée, sur des
  réponses simulées. **Tant que ce n'est pas fait, rien qui s'appuie sur ces notations n'est
  publiable** — même règle que pour l'IMO ci-dessous, dont le volet plage plausible est désormais
  vérifié.

  *IMO (983 correspondances confirmées / 964 navires distincts), plage basse identifiée le
  2026-08-21, plage plausible échantillonnée le même jour* : la moitié de ces correspondances
  (556/983, 57 %, dont 547 Lloyd's Register) portent un `imo` <4 000 000 — une plage que l'OMI n'a
  ouverte qu'en mars 2023, incompatible avec leur année de construction médiane (2007) ;
  vraisemblablement l'identifiant interne du registre pour un yacht sans IMO statutaire, pas un
  numéro OMI (détail dans `registres_classe.py` et `CLAUDE.md`). Les 427 restantes (≥4 000 000)
  sont la plage plausible.

  Échantillon vérifié sur la plage plausible : 18 correspondances (13 LR / 3 DNV / 2 RINA,
  proportionnel à la population 306/84/37 sur 427, tirage stratifié graine `20260817` — même
  graine que `echantillon()`). Rejeu des appels réels (`dnv_rechercher`/`dnv_details`,
  `lr_rechercher`, `rina_rechercher`) avec les vrais champs catalogue et la logique de
  `confirmer()` : **18/18 (100 %) retombent sur l'IMO déjà présent dans le parquet** — la collecte
  du 2026-08-17 n'a pas de défaut de saisie, elle restitue fidèlement ce que les registres
  renvoient encore aujourd'hui. Mais rejouer l'appariement expose aussi les champs que
  `confirmer()` n'a pas vérifiés (le `type` LR, la longueur/le constructeur DNV/RINA quand ce
  n'est pas le champ qui a confirmé) ; croisés avec une recherche web indépendante sur 13 des
  navires les plus notables :

  - **Confirmé, 13/18** (nom, IMO et chantier/année concordent avec une source publique
    indépendante — VesselFinder, SuperYachtTimes, BoatInternational, MarineTraffic — ou, faute de
    recherche web, avec un `type` LR explicitement "Yacht"/"Yacht (Sailing)" et/ou plusieurs
    champs concordants) : Paolita, Volpini 2, Forever You, Jude, Piacere, Dubawi, ACE, Hodor,
    Kismet, Adela, Dubai Shadow (type LR "Supply Tender" mais confirmé : c'est le navire d'escorte
    du yacht Dubai, pas une fausse piste), Saffuriya (DNV, confirmé par année + longueur +
    constructeur), Harmony G.
  - **Infirmé, 4/18** — l'IMO confirmé appartient en réalité à un navire commercial homonyme sans
    rapport, la seule concordance étant l'année de construction (±1 an), exactement ce qu'autorise
    `confirmer()` avec un seul champ :
    - **Vanquish** (LR, imo 9430911) : type LR "Chemical Tanker, Inland Waterways" ; le web
      confirme un chimiquier fluvial néerlandais construit en 2010, sans rapport avec le yacht
      26,5 m de Warren Yachts (2009) du catalogue.
    - **Dream** (LR, imo 9303728) : type LR "Products Tanker" ; aucun yacht "Dream" avec cet IMO
      trouvé en ligne (deux autres "Dream" yacht existent bien, IMO 9027336 et 1007017 — ce
      dernier explicitement typé "Yacht" par LR mais écarté par l'appariement faute de
      concordance d'année).
    - **Ocean Pearl** (DNV, imo 9401829) : longueur DNV 188,5 m / constructeur "Oshima
      Shipbuilding" contre 41 m / "Rodriquez Yachts" au catalogue ; le web confirme un vraquier
      (renommé depuis Ocean Friend).
    - **Sea Eagle** (DNV, imo 9849045) : longueur DNV 182,9 m / constructeur "STX Offshore &
      Shipbuilding" contre 81 m / "Royal Huisman" au catalogue ; le web confirme un tanker
      chimiquier/produits. LR donne pour ce même `yacht_id` un troisième IMO différent (9830135,
      un vraquier) — les deux sources se trompent chacune sur un navire différent.
  - **Non tranché, 1/18** : **Anne** (RINA, imo 9433365) — longueur RINA 109,8 m contre 52,5 m au
    catalogue (Vitters) ; le web montre cet IMO attribué à la fois à un cargo général portugais et
    au voilier Vitters "Anne" (ex-Erica XII) sans qu'aucune source publique ne tranche laquelle des
    deux le détient réellement. À vérifier via une source primaire (registre d'immatriculation,
    Lloyd's Register Fairplay) avant toute publication qui nommerait cette correspondance.

  **Résidu, remplace l'ancien libellé** : 72 % de confirmation propre n'est pas assez élevé pour
  clore l'item — 22 % de faux positifs confirmés par recherche externe est un ordre de grandeur
  réel, dû à la même cause que documentée dans `registres_classe.py` (« L'appariement par nom ne
  suffit jamais seul ») : un nom générique et une seule concordance de champ (souvent l'année,
  ±1 an) suffisent à `confirmer()`, y compris quand la longueur ou le constructeur disponibles
  auraient immédiatement révélé un navire différent — et ce indépendamment du préfixe IMO, la
  plage plausible n'en est pas protégée. Les correspondances confirmées en plage plausible ne sont
  donc publiables nommément qu'après vérification individuelle comme ci-dessus, pas comme lot.
  Piste non implémentée ici (documentation avant tout, voir `registres_classe.py`) : exiger deux
  champs concordants plutôt qu'un seul pour un nom de navire générique lors d'une future collecte.

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
