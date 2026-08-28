# ARENA / Usman — à lire en premier

IA personnelle de **Ousmane Diop (Saer)**, propriétaire d'**UniC Plaquiste**
(cloisons, BA13, plafonds — Dakar). Le modèle tourne **chez lui**, sur sa RTX
A2000. Rien ne part chez un fournisseur d'IA : c'est une décision, pas un
réglage (`docs/DECISIONS.md`, DEC-0002).

---

## ⚠️ Il y a une mission en cours. C'est ta première tâche.

**`docs/CURRENT_TASK.md` — réveiller ce qui dort.** Neuf modules réels étaient
écrits, testés, et **aucune phrase du propriétaire ne les faisait tourner**.
Six sont branchés (la vidéo à l'agent vidéo, les documents au chemin
documentaire, le sens et la consolidation à la mémoire du chat) ; **trois
dorment encore**. La mission est de les brancher, un par
un, chacun sur le bon agent.

N'ouvre pas une nouvelle phase du plan, n'intègre rien de nouveau : il donnera
la suite lui-même quand les neuf seront vivants.

```
python scripts/orphelins.py
```

C'est la mesure qui dit où en est la mission. Elle ne se raconte pas.

---

## Les trois fichiers à lire avant d'écrire une ligne

| Fichier | Ce qu'il te donne |
|---|---|
| `docs/REGLES_DE_TRAVAIL.md` | **Comment travailler avec lui.** Il n'écrit pas de code. Tout découle de ça. |
| `docs/REPRISE.md` | **Où le travail s'est arrêté**, phase par phase, avec ce qui est mesuré et ce qui ne l'est pas. |
| `docs/DECISIONS.md` | Les décisions prises, chacune avec *ce que ça coûte si elle est fausse*. |

Ne demande jamais « où en étions-nous ? ». C'est écrit.

---

## Ce qui ne se négocie pas

**Vérifier, pas supposer.** Une affirmation se paie par une commande lancée
**dans le message qui la rapporte** :

```
python -m ruff check .
python -m pytest tests/ -q
```

Les deux, et la sortie réelle collée. Un résultat d'il y a trois modifications
est une information sur le passé, pas sur l'état actuel.

**Saboter avant de déclarer une garantie tenue.** Casse volontairement ce que
le test protège et prouve qu'il échoue — puis restaure. Un sabotage qui ne fait
rien échouer veut dire que le test manque, ou que le code est mort. C'est arrivé
ici : un test « passait » pour la mauvaise raison, et seul le sabotage l'a
montré.

**Une capacité absente se rapporte, elle ne se simule pas.** `UNKNOWN`,
`NOT_CONFIGURED`, `BLOCKED` sont des réponses valides. Un chiffre plausible à la
place d'une mesure est un mensonge qui devient permanent le jour où un test le
fige. Un `SUCCESS` sans preuve **ne se construit pas** (`core/actions/resultat.py`).

**Un champ absent n'est pas zéro.** Une population inconnue vaut `None`, jamais
`0` — qui se lirait « personne n'y habite ».

**Jamais de secret, jamais de `.env`, jamais de push direct sur `master`.**
Le travail passe par une branche et une **pull request** qu'il fusionne
lui-même : il ne peut pas lancer les tests, la PR est l'endroit où il voit ce
qui entre.

**Implémenter ce qui est demandé, rien de plus.** Une amélioration possible
n'est pas une exigence. Ce qui est utile mais non demandé s'écrit
`SUGGESTION — NON IMPLÉMENTÉE`.

---

## Ce que la machine de l'assistant ne peut pas faire

Quand tu tournes dans le cloud et pas sur son PC : **Ollama n'y est pas** (donc
ni modèle local, ni embeddings `bge-m3`), la recherche web n'y répond pas, et
l'interface ne peut pas être regardée. Toute mesure qui en dépend se rapporte
`UNKNOWN` et attend son PC. Ne la contourne pas, ne l'estime pas.

---

## Deux blocages ouverts, et ils ne sont pas à toi de lever

1. **Six secrets sont encore dans l'historique public du dépôt**, et les clés
   n'ont jamais été changées. La purge est préparée (`documents/RUNBOOK_PURGE_SECRETS.md`),
   **jamais autorisée**. Elle gèle le chapitre 8 (connecteur e-mail). Seul le
   propriétaire décide.
2. **Les mesures de la phase 7.2 attendent son PC** :
   `python scripts/mesurer_performances.py`. Quatre scènes modèle et la
   recherche web sont `UNKNOWN` tant que ce n'est pas lancé.

---

## Où sont les choses

| | |
|---|---|
| `core/` | actions, permissions, connecteurs, mémoire, exécution |
| `agents/` | orchestrateur, plaquiste, analyse de tendances |
| `apps/backend/` | serveur FastAPI, passerelles, `runtime.py` (le câblage) |
| `apps/pwa/` | son interface, servie par ARENA lui-même |
| `tools/` | recherche, documents, vidéo, code |
| `docs/PLAN_ARENA_OS.md` | le plan des 21 phases |

**Ce qui existe mais n'est branché nulle part** : trois modules réels et testés,
listés et ordonnés dans `docs/CURRENT_TASK.md`. Mesuré, pas estimé —
`python scripts/orphelins.py`. C'est la mission en cours.
