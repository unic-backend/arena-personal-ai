# MISSION TERMINÉE — réveiller ce qui dort

*Ouverte et close le 28/08/2026. Mesures de ce fichier prises sur la branche de
la dernière phase, avec `python scripts/orphelins.py`.*

> « regarde toutes les fonctionnalités qui sont intégrées dans le projet, si
> elles existent et exécutent et font de réel travail. Tout doit fonctionner,
> pas dormir là-bas. Tu les places sur les modèles adaptés : celles pour la
> vidéo, celles pour le code, celles pour le chat, celles pour les documents
> UniC Plaquiste. »

**Cette mission est terminée — le 28/08/2026.** Les neuf modules réels tournent
tous depuis un chemin de réponse réel. Le compteur d'orphelins ne contient plus
un seul module à réveiller. Rien de nouveau n'a été intégré : la mission n'a
fait que rendre vivant ce qui existait déjà.

**Le propriétaire donne la suite lui-même.** Deux questions ci-dessous attendent
sa réponse, et elles ne se tranchent pas sans lui.

---

## Ce que « réveillé » veut dire ici

Un module n'est pas réveillé parce qu'il importe, ni parce que ses tests
passent. Il l'est quand **une phrase du propriétaire le fait tourner**.

Cinq conditions, toutes obligatoires, pour chaque module :

1. Un chemin de réponse réel l'atteint — depuis `apps/backend/runtime.py`,
   la passerelle PWA, ou l'agent concerné. Pas depuis un script.
2. Il est branché sur **le bon agent** : la vidéo à la vidéo, le code au code,
   les documents au métier. Un module branché au mauvais endroit ne compte pas.
3. Un test tient le branchement, et **un sabotage le prouve** : on casse la
   garantie, on montre qu'un test précis tombe, on restaure.
4. `python -m ruff check .` et `python -m pytest tests/ -q` passent, lancés
   **dans le message qui l'annonce**.
5. `python scripts/orphelins.py` montre le module **disparu de la liste**.
   C'est la seule preuve qui ne se raconte pas.

Une capacité qui ne peut pas tourner sur la machine de l'assistant (Ollama,
WanGP, recherche web) se rapporte `NOT_CONFIGURED` **avec ce qui manque et la
commande qui l'obtient**. Elle ne se simule pas, et elle ne se déclare pas
terminée.

---

## L'état mesuré aujourd'hui

```
python scripts/orphelins.py
→ Modules totaux : 104  |  atteints : 77  |  orphelins : 27
```

**Les 27 restants ne sont pas des chantiers, et il n'y en a plus aucun à
réveiller.** La liste complète, décomposée :

| Ce que c'est | Combien | Pourquoi ça reste |
|---|---|---|
| `__init__.py` vides | 23 | marqueurs de paquet : il n'y a rien dedans à brancher |
| `apps/pwa/server/*` | 4 | un **second serveur FastAPI**, question ouverte au propriétaire |
| **modules réels endormis** | **0** | c'était la mission |

```
python scripts/orphelins.py  →  aucune ligne
```

---

## Ce qui a été fait, dans l'ordre où il a été fait

**Une phase = un module (ou une paire) = une pull request.** L'ordre a suivi ce
que le propriétaire ressent, pas ce qui était facile.

### Le métier — PR #12 et #13

- `calcul_materiaux` : 234 plaques, 288 montants, 54 rails redonnés à
  l'identique du devis `UC-2026-0804-FG2`.
- `devis_pdf` : un vrai PDF de 3720 octets écrit sur le disque, son chemin est
  la preuve.

### La vidéo et les documents — PR #15

- `suivi_video` + `travaux` sur **l'agent vidéo** : « où en est ma vidéo ? »
  ouvre un suivi en fond, le chat ne l'attend pas. L'identifiant vient du
  journal des actions, jamais de la phrase. Sans WanGP : `NOT_CONFIGURED` avec
  la commande de lancement.
- `indexer` + `inventory` sur **le chemin documentaire** : « indexe mes
  documents » indexe, « d'après mes documents… » interroge. L'indexation tourne
  hors de la boucle du serveur et ne reprend pas un fichier inchangé.

### La mémoire du chat — PR #16

- `semantique` : « combien de panneaux » ramène « 234 plaques BA13 », que le
  lexical seul rendait vide. L'index des vecteurs vit dans le câblage et dure.
  Sans Ollama : `MODE_LEXICAL`, dit dans le journal. Le seuil `0.45` n'a pas été
  touché — il a été mesuré avec `bge-m3`.
- `consolidation` : une phrase retenue deux fois prend une ligne, « vu 2 fois ».
  Rien n'est effacé en mémoire, une supposition ne rejoint jamais un fait.

### Le coût d'une réponse, et le raisonnement — PR en cours

- `voies` : l'orchestrateur consulte la voie juste après le classement ; le
  budget mémoire du prompt en découle. Une intention inconnue prend `LEGERE`.
- `mesures` : chaque tour est chronométré face à la cible de sa voie.
  `GET /api/observability` rend le tableau, **avec** les voies que personne n'a
  empruntées, marquées `UNKNOWN`. Un tour interrompu n'entre pas avec la durée
  de son échec.
- `reasoning_engine` : la question de la phase E est tranchée **dans le sens du
  branchement**, pas de la suppression. Ce qu'il fait de mieux que l'existant se
  dit en une phrase : `DEEP_REASONING` recevait une passe du modèle rapide et un
  chiffre sorti de sa tête ; il reçoit maintenant un plan, un calcul
  **réellement exécuté** en bac à sable, et une rédaction faite à partir du
  résultat obtenu. Quand le bac à sable refuse, la réponse le dit au lieu de
  présenter un résultat élégant que rien n'a vérifié. `/health` annonçait
  « ReasoningEngine » parmi les agents actifs : l'annonce est enfin vraie.

**Aucune suppression n'a été décidée.** Elle se demande au propriétaire.

---

## Ce qui n'est PAS dans la mission

- Les 22 `__init__.py` vides. Ce sont des marqueurs de paquet.
- `apps/pwa/server/{main,providers,oauth,attachments}.py` — **un second
  serveur FastAPI**, avec sa propre gestion de `.env` et de fournisseurs,
  visiblement remplacé par `apps/backend/`. Le supprimer effacerait 482 lignes.
  **Question au propriétaire, pas une tâche.**
- Toute nouvelle fonctionnalité. Cette mission ne fait que rendre vivant ce qui
  existe déjà. Une amélioration repérée en chemin s'écrit
  `SUGGESTION — NON IMPLÉMENTÉE` et ne devient jamais une tâche toute seule.

---

## Les questions ouvertes pour le propriétaire

1. ~~**La rotation de clé a-t-elle bien eu lieu ?**~~ **Répondu le 28/08/2026.**
   Il a changé la clé d'ARENA une fois ; les quatre autres n'ont jamais été
   touchées. Elles servaient à LibreChat et Open WebUI, qu'il n'utilise plus :
   les deux clients sont **retirés du dépôt** (DEC-0007), donc ces quatre
   valeurs n'ouvrent plus rien. Reste `USMAN_API_KEY`, la seule vivante — à
   changer s'il n'est pas certain de l'avoir fait
   (`documents/RUNBOOK_PURGE_SECRETS.md`, étape 1).
2. ~~**Le dépôt est public.**~~ **Fait le 28/08/2026 — il l'a passé en privé
   lui-même.** Vérifié par l'API GitHub : `"private": true`, 0 fork.
   L'exposition publique est close. La purge de l'historique reste **jamais
   autorisée** : elle n'est plus urgente, mais c'est sa décision.
   ~~**Rouvre-t-on le chapitre 8 (connecteur e-mail) ?**~~ **Oui, le
   28/08/2026 — et il est terminé le jour même.** 8.1 : lire et chercher son
   courrier. 8.2 : trier, extraire, rédiger, et **envoyer derrière
   confirmation**. Les identifiants Google vivent dans `.env`, jamais dans le
   dépôt.
3. **`apps/pwa/server/` : on le garde ou on le supprime ?**

Aucune ne se tranche sans lui.

---

## Ce qui est déjà fait dans cette mission

| Date | Module réveillé | Preuve |
|---|---|---|
| 28/08/2026 | `agents/plaquiste/calcul_materiaux` | PR #12 — 234 plaques, 288 montants, 54 rails redonnés à l'identique du devis `UC-2026-0804-FG2` |
| 28/08/2026 | `agents/plaquiste/devis_pdf` | PR #13 — un vrai PDF de 3720 octets écrit sur le disque, son chemin est la preuve |
| 28/08/2026 | `core/execution/travaux` + `core/connectors/suivi_video` | « où en est ma vidéo ? » ouvre un suivi en fond sur l'agent vidéo ; le tour de chat se termine avant lui |
| 28/08/2026 | `tools/documents/indexer` + `tools/documents/inventory` | « indexe mes documents » lit, insère, et ne réindexe pas un fichier qui n'a pas bougé |
| 28/08/2026 | `core/memory/semantique` | « combien de panneaux » ramène « 234 plaques BA13 », que la récupération lexicale rendait vide — mesuré dans le même test |
| 28/08/2026 | `core/memory/consolidation` | une phrase retenue deux fois n'occupe plus qu'une ligne du prompt, avec son compte ; les deux souvenirs sont toujours en mémoire |

| 28/08/2026 | `core/execution/voies` | la voie de l'intention voyage avec la réponse, et le budget mémoire du prompt en découle : deux intentions, deux enveloppes |

| 28/08/2026 | `core/execution/mesures` | chaque tour est chronométré face à la cible de sa voie ; `/api/observability` montre aussi ce qui n'a pas été mesuré |

| 28/08/2026 | `core/reasoning/reasoning_engine` | `DEEP_REASONING` planifie, exécute le calcul en bac à sable, puis rédige — et dit quand le calcul n'a pas eu lieu |

Atteints : **64 → 68 → 72 → 73 → 74 → 75 → 76 → 77**. Modules réels endormis :
**9 → 0**. Le compteur est la mesure, pas le récit.

---

## Comment livrer chaque phase

Il ne lance pas les tests : **la pull request est le seul endroit où il voit ce
qui entre.** Une PR par module, et dedans, dans cet ordre :

1. ce qui dormait, et ce que ça lui coûtait concrètement ;
2. ce qui est branché, où, et sur quel agent ;
3. la sortie **réelle** de `ruff` et de `pytest` ;
4. le sabotage : ce qui a été cassé, quel test est tombé, restauré ;
5. `python scripts/orphelins.py` avant / après.

Puis on s'arrête et on attend son « continuer ». Une phase par tour, jamais
deux — `docs/REGLES_DE_TRAVAIL.md`.

**Les 9 modules sont réveillés.** La mission est finie, compteur à l'appui :
`python scripts/orphelins.py` ne nomme plus aucun module. La suite lui
appartient — il a dit qu'il donnerait la tâche suivante lui-même.
