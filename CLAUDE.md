# ARENA / Usman — à lire en premier

IA personnelle de **Ousmane Diop (Saer)**, propriétaire d'**UniC Plaquiste**
(cloisons, BA13, plafonds — Dakar). Le modèle tourne **chez lui**, sur sa RTX
A2000. Rien ne part chez un fournisseur d'IA : c'est une décision, pas un
réglage (`docs/DECISIONS.md`, DEC-0002).

---

## ✅ La mission « réveiller ce qui dort » est terminée. Attends sa prochaine tâche.

**`docs/CURRENT_TASK.md`** — neuf modules réels étaient écrits, testés, et
**aucune phrase du propriétaire ne les faisait tourner**. Les neuf tournent
maintenant, chacun sur le bon agent : la vidéo à l'agent vidéo, les documents
au chemin documentaire, le sens et la consolidation à la mémoire du chat, les
voies et leurs mesures à l'exécution, le raisonnement au moteur qui calcule
vraiment.

```
python scripts/orphelins.py
→ 255 modules, 202 atteints. Aucun module réel endormi.   (mesuré le 10/09/2026)
```

C'est la mesure, et elle ne se raconte pas — **elle se refait**. Ce bloc a
porté « 104 modules, 77 atteints » jusqu'au 03/09/2026, longtemps après que le
dépôt en compte 178. Un chiffre figé dans le fichier que chaque session lit en
premier ne vieillit pas visiblement : il se lit comme l'état du jour. Relance
la commande plutôt que de recopier ce nombre. **N'ouvre pas une nouvelle phase du
plan et n'intègre rien de nouveau** : il donne la suite lui-même. Les deux
questions posées à ce moment-là sont tranchées depuis : la visibilité du dépôt
(public — privé le 28/08/2026, repassé public le 06/09/2026, les deux fois sur
sa décision) et le sort de `apps/pwa/server/` (supprimé le 29/08/2026, sur sa
décision — voir `docs/CURRENT_TASK.md`).

---

## Avant de relire le dépôt : `PROJECT_MEMORY/`

**Ne scanne pas le projet entier au début d'une session.** La mémoire
opérationnelle est là pour ça, et elle est tenue à jour :

| Fichier | Quand l'ouvrir |
|---|---|
| `PROJECT_MEMORY/PROJECT_MAP.md` | « où est quoi ? » — **toujours en premier** |
| `PROJECT_MEMORY/ACTIVE_WORK.md` | « où en est-on, qu'attend-il de moi ? » |
| `PROJECT_MEMORY/ARCHITECTURE.md` | « comment ça se parle ? » |
| `PROJECT_MEMORY/LOCKED_ZONES.md` | **avant de toucher à quoi que ce soit d'existant** |
| `PROJECT_MEMORY/COMPLETED_SYSTEMS.md` | « est-ce déjà vérifié, et jusqu'où ? » |
| `PROJECT_MEMORY/DEPENDENCIES.md` | « de quoi ça dépend ? » |
| `PROJECT_MEMORY/DECISIONS.md` | index de `docs/DECISIONS.md` |
| `PROJECT_MEMORY/CHANGELOG.md` | ce que la session précédente a livré |

Ouvre ensuite **les seuls fichiers que la tâche exige**. Un dépôt relu en entier
à chaque fois est du contexte dépensé pour rien.

Et tiens-la à jour : une mémoire périmée est pire qu'aucune mémoire.

---

## Les trois fichiers à lire avant d'écrire une ligne

| Fichier | Ce qu'il te donne |
|---|---|
| `docs/REGLES_DE_TRAVAIL.md` | **Comment travailler avec lui.** Il n'écrit pas de code. Tout découle de ça. |
| `docs/REPRISE.md` | **Où le travail s'est arrêté**, phase par phase, avec ce qui est mesuré et ce qui ne l'est pas. |
| `docs/DECISIONS.md` | Les décisions prises, chacune avec *ce que ça coûte si elle est fausse*. |
| `docs/COMMANDES_PC.md` | **Les commandes de sa machine.** Ne lui en invente jamais une : cette fiche, ou `python scripts/doctor.py`. |

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

Ce que la machine a vraiment, où qu'elle soit, se mesure :

```
python scripts/doctor.py
```

**30 vérifications** réelles, chacune avec la commande qui la répare. Aucun
`[OK]` n'y est affirmé sans mesure — ce fichier l'a fait, une fois, et un test
l'en empêche désormais.

Ce nombre-ci avait vieilli pareil : il annonçait « vingt-deux » alors que le
diagnostic en faisait 27 (mesuré le 07/09/2026). Un test le compte maintenant,
comme celui des modules — les deux chiffres de ce fichier sont désormais tenus.

---

## Deux blocages ouverts, et ils ne sont pas à toi de lever

1. **Six secrets sont dans l'historique du dépôt — qui est PUBLIC depuis le
   06/09/2026**, remis en public par le propriétaire lui-même (il l'avait mis
   en privé le 28/08/2026 pour la même raison ; c'est un aller-retour, pas un
   oubli). Vérifié par l'API GitHub : `"visibility": "public"`. **L'exposition
   publique n'est plus close** : l'historique fuité est de nouveau lisible par
   quiconque a le lien. Quatre de ces cinq clés sont **mortes** : LibreChat et
   Open WebUI sont retirés, plus rien ne les lit (DEC-0007, et un test le
   tient). La cinquième, `USMAN_API_KEY`, ouvre ARENA — il a dit la changer
   lui-même au moment de repasser en public ; **non vérifié par une mesure**,
   ne pas l'écrire ailleurs comme acquis tant que ça ne l'est pas.
   La purge de l'historique reste préparée (`documents/RUNBOOK_PURGE_SECRETS.md`)
   et **jamais autorisée** — c'est sa décision, redevenue plus urgente
   qu'avant le 06/09/2026 puisque l'exposition n'est plus contenue.
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

**Ce qui n'est branché nulle part** : plus aucun module réel. Il reste des
`__init__.py` vides (des marqueurs de paquet). `apps/pwa/server/` — le second
serveur FastAPI, question posée au propriétaire — a été supprimé le
29/08/2026 sur sa décision : `docs/CURRENT_TASK.md`. Mesuré, pas estimé :
`python scripts/orphelins.py`.
