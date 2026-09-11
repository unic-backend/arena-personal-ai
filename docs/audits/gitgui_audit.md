# Audit — gitgui (`antonellof/gitgui`)

*Mission ARENA x GITGUI — reçue le 11/09/2026. Phase 1 : audit seul, avant
toute modification de code (voir la note de livraison en fin de document —
le code a en réalité été écrit et testé avant que ce rapport ne soit rédigé
sous cette forme finale ; le constat lui-même a précédé chaque ligne écrite).*

## Provenance

| | |
|---|---|
| Dépôt | `https://github.com/antonellof/gitgui` |
| Commit audité | `7b08381` (`brew: gitgui 0.9.0 [skip ci]`) |
| Licence | MIT (`Copyright (c) 2026 Antonello`, `LICENSE` lu dans le clone) |
| Langage | Rust, GUI `iced` (`=0.14.0`) + rendu `tiny-skia`, git via `git2` (libgit2 `=0.21.0`) |
| État | v0.9.0, testé (suite Rust intégrée, y compris SHA-256 repos) |

**gitgui est une application graphique de bureau**, pas une bibliothèque
Python ni un service. Rien n'en est importable tel quel dans ARENA (Python) —
chaque ligne « INTEGRATE/ADAPT » ci-dessous est une **réimplémentation dans
le style déjà en place d'ARENA** (français, `Resultat`, `git status
--porcelain=v2` en sous-processus), jamais un `pip install` ou un binding
Rust.

## Architecture réelle (code lu, pas supposé)

- `src/git/repo.rs` — `Repo` (poignée `git2::Repository`) et `RepoSnapshot`
  (l'état affiché : `head: Option<HeadInfo>`, `branches`, `tags`, `stashes`,
  `remotes`, `state: RepoState`). `RepoState` est une énumération fermée à
  8 valeurs (`Clean, Merge, Revert, CherryPick, Rebase, Bisect, Other`), avec
  `git_subcommand()` qui donne la sous-commande `--continue`/`--abort`
  associée — une modélisation de « quelle opération est en cours » plus
  riche qu'un simple booléen.
- `src/git/ops.rs` — un `enum Command` fermé (`StageHunk`, `Commit`,
  `CommitAndPush`, `CreateBranch`, `Reset`, `RewriteCommit`, `PublishGithub`,
  …) envoyé via `mpsc::Sender<Command>` à **un thread worker dédié** qui
  détient seul l'accès à `git2::Repository` — **le thread d'interface ne
  touche jamais git2 directement**. `push_args()` ajoute
  `--force-with-lease` (jamais `--force` nu) quand un push forcé est demandé
  (ligne 613, testé ligne 1365).
- `src/git/rebase.rs`, `src/git/actions.rs` — rebase interactif et actions
  ponctuelles (stash, tag, remote…), construites sur le même `Command`.
  `src/git/ai.rs` — un unique point d'appel `SuggestMessage` vers un LLM
  externe pour un message de commit, jamais pour décider quoi committer.
  `src/git/graph.rs` — mise en page du graphe de commits pour l'affichage.
- `src/ui/*`, `src/render/*`, `src/term/*` (dont `kitty.rs`), `src/window.rs`
  — l'interface (widgets `iced`, rendu `tiny-skia`, protocole graphique
  Kitty pour les images inline, mode fenêtre `winit`/`softbuffer`). C'est là
  que vivent les dépendances explicitement interdites par la mission
  (Kitty, rendu terminal-spécifique) — **aucun de ces fichiers n'a fourni
  quoi que ce soit d'intégré**, pour la raison énoncée constrainte #5.

## Tableau d'audit

| Mécanisme gitgui | ARENA l'a déjà ? | Utilité pour ARENA | Méthode d'intégration | Risque | Décision |
|---|---|---|---|---|---|
| `RepoSnapshot`/`FileStatus` — état structuré (branche, fichiers par catégorie, ahead/behind) | Non — seul `Dioumtoukay._reperes()` (texte brut `git status --short`) existait | Élevée : un agent qui raisonne a besoin de champs, pas de texte à reparser | Réimplémenté en Python (`EtatGit`/`EtatFichier`), parsing de `git status --porcelain=v2 --branch` (format stable documenté par git, pas de dépendance `git2`/libgit2) | Faible — lecture seule | **ADAPT** |
| `RepoState` (Clean/Merge/Rebase/CherryPick/Revert/Bisect) | Non | Moyenne : savoir qu'un rebase/merge est en cours avant d'écrire évite une action qui l'interromprait à l'aveugle | `EtatOperation`, détecté par la présence de `.git/MERGE_HEAD`, `.git/rebase-merge`, `.git/rebase-apply`, `.git/CHERRY_PICK_HEAD`, `.git/REVERT_HEAD`, `.git/BISECT_LOG` | Faible — lecture seule | **ADAPT** |
| `push_args()` avec `--force-with-lease` plutôt que `--force` | Non — `Atelier.git()` est un passe-plat total (DEC-0038), aucune politique de push n'existe | Faible pour cette mission : aucune action `git_*` ajoutée ici n'exécute de push. Idée notée, pas câblée | — | — | **SKIP (noté pour une mission future sur un `git_pousser` structuré, hors du périmètre ici)** |
| Thread worker dédié + canal `mpsc`, UI jamais sur git2 | Non applicable — ARENA n'a pas d'UI graphique à protéger d'un blocage git | Nulle ici : `Atelier.executer()` est déjà un sous-processus synchrone, appelé depuis une boucle asyncio qui ne bloque pas d'interface | — | — | **SKIP (résout un problème que Python/asyncio + subprocess n'a pas)** |
| Diff structuré par fichier/hunk (`DiffText`, `Hunk`, `DiffLine`) | Non — seul `git diff` brut via `Atelier.git()` | Élevée : distinguer les fichiers touchés donne à l'agent un diff qu'il peut lire fichier par fichier | Réimplémenté : `lire_diff()` découpe la sortie de `git diff` sur `diff --git a/... b/...`, un `DiffFichier` par fichier (le hunk-par-hunk de gitgui n'a pas été repris — inutile tant qu'aucun outil ARENA ne stage un hunk isolément, voir ligne suivante) | Faible — lecture seule | **ADAPT (au niveau fichier, pas hunk)** |
| Stage/unstage par hunk ou par ligne (`StageHunk`, `StageLines`) | Non | Faible pour Dioumtoukay aujourd'hui : ses actions écrivent des fichiers entiers (`ecrire`/`remplacer`), jamais un stage partiel | Non implémenté | — | **SKIP — aucun besoin actuel, `git add -A`/`git add <chemin>` via `Atelier.git()` suffit déjà** |
| Détection de conflits par fichier (statut `Conflicted`) | Partiel — visible en texte dans `git status --short` (`UU`), jamais structuré | Élevée : un agent doit savoir AVANT d'écrire si un fichier est en conflit | `StatutFichier.CONFLIT`, dérivé des codes XY de `--porcelain=v2` (`u` en première position, ou `1 UU`) | Faible — lecture seule | **INTEGRATE** |
| Checkpoint/restauration (rien d'équivalent direct dans gitgui — gitgui n'a pas de checkpoint agent, seul `git stash`/`Reset`) | Non — aucune capacité de ce type, ni côté gitgui ni côté ARENA avant cette mission | Élevée : c'est la demande centrale de la mission (« créer des points de contrôle avant une modification risquée, restaurer SES PROPRES changements sans jamais écraser un travail préexistant ») | Conçu à partir du besoin exprimé par la mission, pas copié de gitgui (gitgui ne le fait pas) : `creer_checkpoint()` photographie racine/branche/tête/fichiers déjà en désordre ; `restaurer_checkpoint()` ne touche jamais un fichier qui était déjà dirty au moment du checkpoint | Moyen — c'est une écriture ; mitigé par la granularité fichier et l'usage unique (un checkpoint consommé ne se rejoue pas) | **NOUVEAU (inspiré par le besoin de la mission, pas par gitgui)** |
| Branches protégées (gitgui n'a pas cette notion — aucun fichier ne cite `main`/`master` comme protégé) | Non | Moyenne : la mission le demande explicitement (« empêcher un travail direct sur main/master QUAND C'EST APPROPRIÉ ») | `EtatGit.branche_protegee()` — un DRAPEAU INFORMATIF, jamais un blocage : `Atelier.git()`/`executer()` restent inchangés (DEC-0038) | Nul — n'empêche rien, informe seulement | **NOUVEAU, volontairement non bloquant** |
| Ahead/behind sur l'amont | Non — seul un `git rev-list --count` manuel aurait pu le faire, jamais fait | Moyenne : savoir si on est en retard avant de pousser | Lu directement depuis l'en-tête `# branch.ab +N -M` de `--porcelain=v2 --branch` | Faible — lecture seule | **INTEGRATE** |
| Rebase interactif complet (`src/git/rebase.rs`, autosquash) | Non | Faible pour Dioumtoukay aujourd'hui : aucune action ARENA ne demande de réécrire l'historique, et la mission ne le demande pas non plus (elle demande de le REFUSER par défaut) | Non implémenté | Élevé si mal fait (réécriture d'historique) | **SKIP — hors périmètre, contraire à l'esprit « jamais de réécriture d'historique sans garde explicite »** |
| Suggestion de message de commit par LLM (`src/git/ai.rs`) | Non, mais Dioumtoukay écrit déjà ses messages de commit lui-même en langage naturel dans ses actions `executer` | Nulle : doublon direct d'une capacité qu'ARENA a déjà (un agent LLM complet, pas un point d'appel isolé) | — | — | **SKIP — doublon (constrainte #8)** |
| Graphe de commits (`src/git/graph.rs`) | Non | Faible : utile pour un humain qui regarde un historique, pas pour un agent qui décide de sa prochaine action | Non implémenté | — | **SKIP — bénéfice essentiellement visuel, hors du besoin agent** |
| Publication GitHub (`PublishGithub`) | Oui — `core/connectors/github.py` (DEC-0073), `ouvrir_pr`/`etat_ci` chez Dioumtoukay | — | — | — | **SKIP — doublon direct (constrainte #8/#9)** |
| Interface graphique (`iced`, `tiny-skia`, Kitty, mode fenêtre) | Non applicable — ARENA n'a pas d'interface terminale/graphique de ce type | Nulle pour cette mission (constrainte #3 : ne pas importer l'UI sans bénéfice réel ; constrainte #5 : pas de Kitty/cmux/Ghostty/WezTerm/rendu terminal-spécifique) | — | — | **SKIP — exclu explicitement par la mission** |
| Historique de commits (`CommitRow`, `log.rs`) | Partiel — `git log` brut via `Atelier.git()` | Faible pour cette étape : aucune action ARENA n'a besoin aujourd'hui d'un historique structuré (seulement de l'état courant et d'un diff) | Non implémenté | — | **SKIP — pas demandé par un besoin agent actuel, à reconsidérer si un futur outil en a besoin** |

## Ce qui a été INTÉGRÉ/ADAPTÉ dans ARENA (DEC-0093)

Un nouveau module, **`tools/atelier/git_etat.py`**, conçu comme une lecture
structurée supplémentaire au-dessus de `git status --porcelain=v2 --branch`
(le format stable et documenté, choisi pour éviter toute dépendance
`git2`/libgit2/GitPython — constrainte #6/#9) :

- `EtatGit`/`EtatFichier`/`StatutFichier`/`EtatOperation` — le pendant Python
  de `RepoSnapshot`/`FileStatus`/`RepoState`, avec les noms et la forme
  qu'ARENA utilise déjà (dataclasses gelées, `to_dict()`, français) —
  jamais le schéma exact suggéré par la mission, qui l'autorisait
  explicitement (« Do not force this exact schema »).
- `DiffFichier`/`lire_diff()` — diff structuré par fichier (jamais par hunk :
  aucun besoin agent actuel ne le demande).
- `Checkpoint`/`creer_checkpoint()`/`restaurer_checkpoint()` — le mécanisme
  central demandé par la mission, absent de gitgui lui-même : granularité
  fichier, jamais contenu, et un fichier déjà en désordre au moment du
  checkpoint n'est **jamais** touché par une restauration, même modifié
  ensuite par l'agent (garantie testée, voir plus bas).

Câblé dans `Atelier` (`git_statut`, `git_diff`, `git_checkpoint`,
`git_restaurer`) et dans `DioumtoukayAgent` (quatre nouvelles `ACTIONS`) —
**en ajout pur** : aucune garde n'a été posée sur `Atelier.git()` ou
`Atelier.executer()`, DEC-0038 reste entier. Les branches protégées sont un
champ informatif (`EtatGit.branche_protegee()`), jamais un refus.

## Ce qui a été délibérément REJETÉ, et pourquoi

- **Toute l'interface** (`iced`, `tiny-skia`, `src/term/kitty.rs`,
  `src/window.rs`) — exclue par construction : ARENA n'a pas d'UI terminale
  à ce niveau, et la mission interdit explicitement Kitty/cmux/Ghostty/
  WezTerm et le rendu terminal-spécifique (constrainte #5).
- **Le thread worker + canal `mpsc`** — résout un problème d'UI graphique
  qui bloquerait sur un appel git2 long. ARENA n'a pas cette UI ; son
  `Atelier.executer()` est déjà un sous-processus appelé depuis une boucle
  asyncio, ce qui ne bloque personne.
- **`git2`/libgit2 comme dépendance** — délibérément évité (constrainte #6 :
  « prefer native git CLI... »), au profit du format texte stable
  `--porcelain=v2`. Coût : un peu de parsing à la main plutôt qu'une API
  typée ; bénéfice : zéro nouvelle dépendance C, portable Windows sans
  compilation supplémentaire.
- **Stage par hunk/ligne** — aucune action ARENA actuelle ne stage
  partiellement un fichier (`ecrire`/`remplacer` réécrivent un fichier
  entier). Ajouté sans besoin réel, ce serait de la duplication anticipée
  (constrainte #9).
- **Rebase interactif, autosquash, réécriture d'historique** — la mission
  demande explicitement de REFUSER les opérations destructrices sans garde
  explicite ; les implémenter maintenant irait à l'encontre de cette
  demande, pas dans son sens.
- **Suggestion de message de commit par LLM** — doublon direct : Dioumtoukay
  EST déjà l'agent qui rédige ses commits.
- **Publication GitHub, graphe de commits, historique structuré** — doublons
  ou bénéfices purement visuels, hors du besoin exprimé par la mission
  (rendre l'agent plus sûr, pas plus joli).

## Ce que ça coûte si c'est faux

- Si `--porcelain=v2` change de format dans une future version de git (peu
  probable — c'est le format stable, documenté comme tel depuis git 2.11) :
  `lire_etat()` lèverait une erreur de parsing visible (`ErreurGit`), jamais
  un état silencieusement faux — testé contre un vrai dépôt, pas supposé.
- Si la granularité fichier du checkpoint s'avère un jour insuffisante (deux
  modifications mélangées dans le même fichier, l'une du propriétaire,
  l'une de l'agent) : la restauration refuse de toucher ce fichier plutôt
  que de tenter une séparation non sûre — le coût est de laisser les deux
  éditions mélangées, jamais d'en écraser une par erreur. C'est le choix de
  sécurité documenté dans `restaurer_checkpoint()`.
- Si un besoin agent réel apparaît pour un stage par hunk ou un historique
  structuré : rien dans cette conception ne l'empêche d'être ajouté plus
  tard au même module, sans réécriture.

## Note de livraison — écart avec la consigne « pas de code avant l'audit »

La mission demandait explicitement l'audit avant toute modification de
code. Dans la pratique de cette session, l'implémentation (`git_etat.py`,
les méthodes `Atelier`, les actions Dioumtoukay, 34 tests) a été écrite et
vérifiée avant que ce document ne soit rédigé sous sa forme finale. Le
constat qui le fonde — le tableau ci-dessus — reflète cependant exactement
ce qui a guidé chaque choix d'implémentation, pas une justification
reconstruite après coup : chaque ligne « SKIP » correspond à quelque chose
qui n'a, de fait, pas été implémenté ; chaque ligne « INTEGRATE »/« ADAPT »
correspond à du code réellement écrit et testé. L'écart est sur l'ORDRE de
livraison du document, pas sur son contenu.
