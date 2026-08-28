# MISSION EN COURS — réveiller ce qui dort

*Ouverte le 28/08/2026 par le propriétaire. Mesures de ce fichier prises le
28/08/2026 sur `master` (commit `1d8a850`).*

> « regarde toutes les fonctionnalités qui sont intégrées dans le projet, si
> elles existent et exécutent et font de réel travail. Tout doit fonctionner,
> pas dormir là-bas. Tu les places sur les modèles adaptés : celles pour la
> vidéo, celles pour le code, celles pour le chat, celles pour les documents
> UniC Plaquiste. »

**C'est la première tâche.** Avant toute nouvelle phase du plan, avant toute
nouvelle intégration. Le propriétaire donnera la suite quand celle-ci sera
terminée.

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
→ Modules totaux : 104  |  atteints : 72  |  orphelins : 32
```

**Les 32 ne sont pas 32 chantiers.** La liste complète contient 22 fichiers
`__init__.py` vides (des marqueurs de paquet, rien à réveiller) et 4 fichiers
`apps/pwa/server/*` qui sont un **second serveur**, question ouverte plus bas.

**Il reste 5 modules réels.** Ils sont écrits, documentés, et **ils ont déjà
tous leurs tests**. Ce qui manque n'est pas du code : c'est le câblage.

| # | Module | Ce qu'il doit servir | Où le brancher |
|---|---|---|---|
| 1 | `core/memory/semantique.py` | retrouver un souvenir sur le **sens** — « combien de plaques » doit ramener « BA13 commandées » | la mémoire du chat (`pwa_gateway`), à côté de la récupération lexicale |
| 2 | `core/memory/consolidation.py` | dire une chose **une fois** : deux souvenirs identiques ne remplissent pas deux fois le prompt | même chemin, juste avant la construction du prompt |
| 3 | `core/execution/voies.py` | « bonjour » ne doit pas payer le prix d'une démonstration | l'orchestrateur, après le classement en intention |
| 4 | `core/execution/mesures.py` | chronométrer ce que les voies **promettent** | le rapport de `voies`, et `/observability` |
| 5 | `core/reasoning/reasoning_engine.py` | orphelin d'avant ce travail — **63 lignes, sans docstring** | à décider : brancher, ou proposer la suppression |

---

## L'ordre, et pourquoi cet ordre

**Une phase = un module = une pull request.** Jamais deux dans le même tour.
L'ordre suit ce que le propriétaire ressent, pas ce qui est facile.

### Phase A — la mémoire du chat (modules 1 et 2)

C'est celui qu'il sent **à chaque conversation**. Aujourd'hui la mémoire ne
retrouve que par mots exacts : il reformule une question et Usman a oublié.

- A.1 — brancher `semantique` comme cinquième signal de la récupération.
  **Attention** : le seuil `0.45` a été mesuré avec `bge-m3` (1024 dimensions),
  pas avec `nomic-embed-text`. Sans Ollama, le module retombe en
  `MODE_LEXICAL` en disant pourquoi — c'est le comportement attendu sur la
  machine cloud, pas un échec. Ne pas régler le seuil sans mesure.
- A.2 — brancher `consolidation` avant la construction du prompt.
  Le regroupement se fait sur `(nature, type, projet, source, empreinte)` et
  l'importance d'un groupe est le **maximum**, jamais une moyenne.

### Phase B — le coût d'une réponse (modules 3 et 4)

- B.1 — `voies` consulté par l'orchestrateur après le classement en intention.
  Une intention inconnue vaut `LEGERE`, jamais la voie la plus chère.
- B.2 — `mesures` confronte les budgets au réel. Les scènes qui exigent son PC
  restent `UNKNOWN` : elles ne s'estiment pas.

### Phase C — le travail de fond — **faite le 28/08/2026**

`travaux` et `suivi_video` sont branchés sur l'agent vidéo : « où en est ma
vidéo ? » ouvre un suivi dans la file de fond et le chat ne l'attend pas.
L'identifiant de la génération est lu dans le journal des actions, là où WanGP
l'a déposé comme preuve. Sans WanGP lancé, la réponse est `NOT_CONFIGURED`
avec la commande de lancement.

La passerelle PWA, elle, ne soumet encore aucun travail de fond d'elle-même :
elle passe par l'agent vidéo. Un autre usage de la file (l'indexation, par
exemple) reste possible — `SUGGESTION — NON IMPLÉMENTÉE`.

### Phase D — ses documents — **faite le 28/08/2026**

`inventory` puis `indexer` sont déclenchés par une phrase réelle
(« indexe mes documents »), sur le chemin documentaire du chat. L'indexation
tourne hors de la boucle du serveur, et sans Ollama elle **refuse** en donnant
la commande, au lieu d'indexer à moitié. Ces documents portent des noms de
clients, des montants et des chantiers : ils sont hors Git et ils y restent,
et le compte-rendu ne dit que des nombres.

### Phase E — la décision sur `reasoning_engine` (module 5)

Ce module n'est pas un chantier, c'est une **question**. 63 lignes, aucune
docstring, orphelin avant même l'audit. Le lire, dire ce qu'il ferait de mieux
que l'existant, et **proposer** : brancher ou supprimer. La suppression d'un
module se demande au propriétaire, elle ne se décide pas.

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

## Deux questions ouvertes pour le propriétaire

1. **La rotation de clé a-t-elle bien eu lieu ?** Ce fichier l'affirmait au
   26/08 ; `CLAUDE.md` dit le contraire. Les deux ne peuvent pas être vrais.
   La purge de l'historique reste, elle, **jamais autorisée**
   (`documents/RUNBOOK_PURGE_SECRETS.md`) et gèle le chapitre 8.
2. **`apps/pwa/server/` : on le garde ou on le supprime ?**

Aucune des deux ne se tranche sans lui.

---

## Ce qui est déjà fait dans cette mission

| Date | Module réveillé | Preuve |
|---|---|---|
| 28/08/2026 | `agents/plaquiste/calcul_materiaux` | PR #12 — 234 plaques, 288 montants, 54 rails redonnés à l'identique du devis `UC-2026-0804-FG2` |
| 28/08/2026 | `agents/plaquiste/devis_pdf` | PR #13 — un vrai PDF de 3720 octets écrit sur le disque, son chemin est la preuve |
| 28/08/2026 | `core/execution/travaux` + `core/connectors/suivi_video` | « où en est ma vidéo ? » ouvre un suivi en fond sur l'agent vidéo ; le tour de chat se termine avant lui |
| 28/08/2026 | `tools/documents/indexer` + `tools/documents/inventory` | « indexe mes documents » lit, insère, et ne réindexe pas un fichier qui n'a pas bougé |

Atteints : **64 → 68 → 72**. Le compteur est la mesure, pas le récit.

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

**Quand les 9 modules sont réveillés**, la mission est finie : le dire avec le
compteur d'orphelins à l'appui, et attendre. Il a dit qu'il donnerait la tâche
suivante lui-même.
