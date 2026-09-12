# TRAVAIL EN COURS

*Mise à jour : 2026-09-12, fin de session (DEC-0087 → DEC-0094).*

## En cours

DEC-0094 (gitgui, second passage — opérations git mutantes sûres à
rejouer : idempotence, précondition/postcondition, `tools/atelier/
git_ops.py`) poussée en PR #196. CI a trouvé une vraie régression (42
échecs au lieu des 39 attendus) : `continuer_operation()` sans éditeur
configuré échouait sur le runner GitHub Actions (« Terminal is dumb, but
EDITOR unset ») alors que ça passait en local (`GIT_EDITOR` déjà présent
localement). Corrigé (`-c core.editor=true` sur l'appel `--continue`),
reproduit et vérifié en local sous les mêmes conditions que CI avant de
pousser, CI re-vérifiée après coup : retombée exactement à 39 échecs
pré-existants. Détail complet : `docs/DECISIONS.md`, DEC-0094. PR #192
(DEC-0092) et #193 (DEC-0093) déjà fusionnées le 11/09/2026 — rien en
attente d'action côté assistant sur ces deux chunks. PR #196 en attente de
fusion par le propriétaire.

## Dernier chunk : DEC-0094 — gitgui, second passage : opérations git mutantes sûres à rejouer

Mission reçue : approfondir DEC-0093 avec ce que la lecture seule ne
couvrait pas — les opérations qui MUTENT le dépôt (stage, commit, branche,
réseau, fusion, conflit), sûres à rejouer (idempotence par identifiant,
section 7 du SPEC.md du dépôt amont gitgui et son `src/agent.rs`, jamais son code copié),
protégées contre une mutation sur un dépôt qui a changé sans qu'on le sache
(précondition de HEAD), vérifiant ce qu'elles ont réellement fait
(postcondition). Audit complet : `docs/audits/gitgui_audit.md`, section
« Second passage ».

`tools/atelier/git_ops.py` (nouveau) : `JournalOperationsGit` (idempotence,
plafonné à 256 comme gitgui), `ErreurPreconditionGit` (refuse AVANT de
muter si le HEAD a changé), `TypeErreurGit` (13 catégories classées par
motif), 18 opérations (`stager`/`desindexer`/`commettre`,
branches/checkout, réseau — `pousser` n'expose AUCUN `force` nu, seul
`force_avec_bail` existe —, fusion/rebase/cherry-pick/revert, tag, stash,
`lire_conflit` à trois côtés, continue/abort détectés jamais devinés).
Câblé jusqu'à 18 nouvelles actions Dioumtoukay.

**Vulnérabilité trouvée en écrivant le module, corrigée avant de
continuer** : un nom de branche `"-D"` passé nu à `git branch <nom>
<depuis>` executait RÉELLEMENT `git branch -D <depuis>` — suppression
forcée de la branche que `depuis` désignait, l'inverse de « créer une
branche ». Mesuré dans un dépôt de test (branche protégée réellement
disparue) avant le correctif : refus de toute référence commençant par `-`
avant de construire la commande, sur chaque paramètre atteignant git comme
référence nue.

Rejeté et documenté (`docs/DECISIONS.md`, DEC-0094) : socket Unix (aucune
frontière de process à traverser, Dioumtoukay/`Atelier` dans le même
process Python), `reset --hard`/`clean -fd`/réécriture d'historique
partagé (hors de la liste d'opérations de la mission, DEC-0038 reste la
seule porte via `Atelier.git()`), une confirmation nouvelle sur les
opérations destructrices (contredirait DEC-0038).

**63 tests nouveaux** : `test_git_ops.py` (47, dont un vrai conflit de
fusion résolu de bout en bout, un vrai rejet non-fast-forward, un vrai
`--force-with-lease` qui refuse tant que le bail est périmé, et 5 tests de
régression sur l'injection par option) ; `test_atelier_git_ops.py` (10,
dont l'idempotence partagée sur la durée de vie d'un `Atelier`) ;
`test_dioumtoukay_git_ops.py` (6, dont un identifiant répété sur DEUX
instances d'agent successives).

## Chunk précédent : DEC-0093 — gitgui audité : état git structuré, checkpoint/restauration pour Dioumtoukay

Mission reçue : étudier `antonellof/gitgui` (MIT, commit `7b08381`) et ne
retenir QUE ce qui rend les agents de codage d'ARENA plus sûrs/autonomes/
transparents sur git — jamais son interface (`iced`/`tiny-skia`/Kitty),
jamais `git2`/libgit2 comme dépendance. Audit complet :
`docs/audits/gitgui_audit.md`.

Nouveau module **`tools/atelier/git_etat.py`** — état structuré
(`EtatGit`/`EtatFichier`/`StatutFichier`/`EtatOperation`, parsing de `git
status --porcelain=v2 --branch`, format stable, aucune dépendance ajoutée),
diff structuré par fichier (`lire_diff()`), et le mécanisme central demandé
par la mission — absent de gitgui lui-même — **checkpoint/restauration**
(`creer_checkpoint()`/`restaurer_checkpoint()`) : granularité FICHIER, un
fichier déjà en désordre au moment du checkpoint n'est jamais touché par une
restauration, même modifié ensuite par l'agent. Câblé dans `Atelier`
(`git_statut`, `git_diff`, `git_checkpoint`, `git_restaurer`) et
`DioumtoukayAgent` (quatre nouvelles `ACTIONS`) — en AJOUT PUR, aucune garde
posée sur `Atelier.git()`/`executer()` : DEC-0038 reste entier. Les branches
protégées (`main`/`master`) sont un champ informatif
(`EtatGit.branche_protegee()`), jamais un refus.

Rejeté et documenté (`docs/audits/gitgui_audit.md`) : toute l'interface
graphique, le thread worker + canal `mpsc` (résout un problème d'UI
qu'ARENA n'a pas), `git2`/libgit2 comme dépendance, stage par hunk/ligne
(aucun besoin agent actuel), rebase interactif/autosquash (irait contre la
demande de refuser le destructeur par défaut), suggestion de message de
commit par LLM (doublon — Dioumtoukay écrit déjà ses commits), publication
GitHub et graphe de commits (doublons ou bénéfice purement visuel).

**34 tests nouveaux, sur de vrais dépôts git** (jamais un raccourci qui
contournerait le parsing réel — vrai `git init`, vrai `git merge` en
conflit, vrai `git rebase` interrompu) : `tests/tools/test_git_etat.py`
(22), `tests/tools/test_atelier_git.py` (7, dont le test qui prouve qu'un
fichier déjà dirty au checkpoint n'est jamais touché), `tests/agents/
test_dioumtoukay_git.py` (5, via la boucle complète de l'agent, jamais un
appel direct qui contournerait le parsing des actions). `ruff check` propre
sur les fichiers touchés. Suite complète : **5256 passed, 31 skipped, 48
deselected, 0 failed** (487.70s, mesuré le 11/09/2026) — exactement +34 sur
la mesure DEC-0091 (5222).

Développé sur une branche fraîche (`claude/gitgui-git-state`, issue
d'`origin/master`) plutôt que sur la branche CASE encore ouverte — éviter de
mélanger deux missions indépendantes dans une seule PR.
## Chunk précédent : DEC-0092 — Case audité et connecté : un ordinateur Linux isolé, jamais un second cerveau

`case-computers/case` audité (dual AGPL/MIT par dossier, commit `133082b`)
— rapport complet `docs/audits/case_audit.md`. `core/connectors/
case_computer.py` (nouveau) : client REST vers l'API de `cased`, 11
capacités (lister/creer/etat/dormir/reveiller/executer_commande/
lire_fichier/ecrire_fichier/naviguer/capture_ecran/detruire), aucune ligne
AGPL copiée. Câblé dans `DioumtoukayAgent` (onze actions `ordinateur_*`) et
dans le registre de connecteurs (`apps/backend/runtime.py` — expose
`/connectors/case/...` automatiquement, aucun routeur neuf).

**Déploiement local réellement fait** (pas seulement conçu) : le
control-plane (`cased`) a tourné pour de vrai dans cette session (Docker
réel, ~215 Mo, `/var/run/docker.sock` monté) — auth réelle (401/200), santé
réelle (`docker:true`), création réellement tentée et honnêtement refusée
(`ImageNotFound`, aucune image de bureau construite — contrainte disque
mesurée : 1,1 Go disponibles dans cette session). Le client MCP DÉJÀ présent
d'ARENA (`core/mcp/transport.py`, zéro ligne neuve) a listé les 25 outils
réels du serveur MCP de Case.

Rejeté et documenté (`docs/DECISIONS.md`, DEC-0092) : l'agent Drive de Case
comme cerveau, MCP comme seul chemin (wake/destroy absents de sa surface),
duplication d'Agent-Reach/Fuji/Lightpanda, VPS (préparé, pas tenté).

**38 tests nouveaux** (34 déterministes + 4 `integration`, tous verts) :
`test_connecteur_case_computer.py` (28, dont 3 contre l'instance Case
réelle), `test_dioumtoukay_case.py` (10, dont 1 faisant tourner la boucle
ENTIÈRE de Dioumtoukay contre le vrai `cased` — mission §52).

## Chunk précédent : DEC-0091 — Trans4mers audité : crash recovery et concurrence pour Dioumtoukay, aucun second runtime

`abhayzangir1/trans4mer` audité (MIT, commit `d0940a9`) — rapport complet
`docs/audits/trans4mer_audit.md`. Dioumtoukay/Atelier restent le runtime
canonique (DEC-0038 : aucune confirmation, aucun chemin interdit, non
re-litigé). Trois manques réels comblés :

1. **Amorce/confirmation** (`core/execution/reprise.py` :
   `Etape.confirmee`, `amorcer()`/`confirmer()`) — une action est
   maintenant journalisée AVANT de tourner, pas après ; une étape jamais
   confirmée (crash en plein vol) est rapportée ÉTAT INCONNU à la reprise,
   jamais un succès ni un échec supposé.
2. **Verrou par fichier** (`tools/atelier/verrous.py`, nouveau) — deux
   tâches qui écrivent le même fichier en même temps (le câblage réel :
   un seul `Atelier` partagé, une boucle `async`) sont sérialisées, jamais
   refusées — un mutex, pas une porte d'autorisation.
3. **Worktrees isolés** (`Atelier.isoler()`/`nettoyer_worktree()`) — `git
   worktree add`/`remove` en shell nu, `.gitignore` protégé, jamais de
   suppression forcée d'un travail non commité.

Rejeté et documenté (`docs/DECISIONS.md`, DEC-0091) : porte d'approbation
humaine et bac à sable de chemins (contrediraient DEC-0038), CQRS complet,
PTY, navigateur/mémoire/RAG/MCP (déjà couverts ailleurs, aucun doublon).

**16 tests nouveaux, chacun avec un sabotage réel** : `test_reprise_amorce.py`
(6, dont un test qui fixe le comportement de l'ANCIEN chemin pour prouver le
manque) ; `test_atelier_concurrence.py` (3, deux VRAIS threads synchronisés
par `threading.Barrier`, verrou neutralisé pour prouver qu'il protégeait
vraiment) ; `test_atelier_worktree.py` (7, vrai dépôt git, vrai `git
worktree`, un fichier non commité qui survit à un nettoyage refusé).

## Chunk précédent : DEC-0090 — Mémoire canonique enrichie (AI Memory Vault audité)

`ai-encryption-tool/ai` audité (MIT, commit `5e6d218c`) — rapport complet
`docs/audits/ai_memory_vault_audit.md`. Aucun second système de mémoire :
tout étend `core/memory/personnelle.py` (`MemoirePersonnelle`), déjà actif
et plus riche que leur modèle (provenance `Nature` FAIT/PREFERENCE/
INFERENCE/CONTEXTE_TEMPORAIRE).

Construit : gouvernance (`Etat` ACTIF/REJETE/ARCHIVE, `rejeter`/`archiver`/
`reactiver`/`supprimer`, migration auto d'une base pré-existante) ;
chiffrement au repos (`core/memory/chiffrement.py`, AES-256-GCM +
PBKDF2-HMAC-SHA256 600k itérations, `Coffre`) ; import ChatGPT/Claude/texte
(`core/memory/import_conversations.py`, toujours `Nature.INFERENCE`,
injection de prompt vérifiée inerte) ; premier serveur MCP d'ARENA
(`core/mcp/memory_server.py`, 6 outils, testé via un vrai sous-processus
stdio) ; API HTTP (`apps/backend/routers/memory.py`).

**Régression trouvée par la suite complète** : `core.mcp.memory_server`
remontait comme orphelin (un serveur MCP est lancé par son client, jamais
importé par ARENA) — ajouté à `SERVICE_LANCE_PAR_LE_PROPRIETAIRE` dans
`scripts/orphelins.py`, compteur de `CLAUDE.md` mis à jour (296/236).

Isolation de projet et efficacité en tokens mesurées (pas supposées) :
réduction **> 90 %** des caractères envoyés sur un cas réel.

## Chunk précédent : DEC-0089 — Tunnet audité, refusé (rien à câbler)

Demandé via un commentaire Reddit. Dépôt réel cloné et lu : ce n'est pas
le petit outil de connexion décrit, mais un produit complet de mise en
réseau maillée (19 crates Rust, licence éclatée AGPL/MPL/Apache,
`Status: In development`). `scripts/lancer_arena.ps1` fait déjà ce que le
besoin décrit (serveur + Tunnel Cloudflare + QR code) — rien câblé, pour
ne pas dupliquer une capacité qui existe et fonctionne.

## Chunk précédent : DEC-0088 — les cinq workflows ComfyUI restants

`image_to_image`, `upscale`, `controlnet_image`, `character_image`,
`image_to_video` — implémentés contre le vrai code source ComfyUI
(`nodes.py`, `comfy_extras/`), promus `STABLE` au même niveau de preuve
que `text_to_image`. Image de référence jamais sur le disque d'ARENA
(`image_base64`, mêmes octets en mémoire que les pièces jointes du chat,
DEC-0019) — `_televerser_images` decode+televerse a ComfyUI juste avant
l'envoi. `verification_modeles` (nouveau) généralise le controle
« modele installe ? » au-dela de `ckpt_name`.

**Sabotage réel** : `_verifier_modeles` neutralisée → 3 tests échouent
(ControlNet absent accepté). Restaurée → 85 tests repassent. 27 tests
nouveaux, régression ciblée 262 passed. Un artefact de manipulation
d'outil (`</new_string>` littéral) trouvé et corrigé à la fin de l'entrée
DEC-0087 dans `docs/DECISIONS.md`. Restart test réel : les six workflows
rendus `STABLE` par `/api/image/workflows`.

**Deux régressions réelles trouvées par la suite complète, pas par les
tests ciblés** : `tests/test_documentation.py` a détecté que l'entrée
DEC-0088 citait deux chemins amont ComfyUI non vendorés avec leur chemin
complet — corrigé une première fois, puis le paragraphe DÉCRIVANT ce
correctif a lui-même recité le motif fautif, cassant le test une seconde
fois. Corrigé à son tour, revérifié (18 passed). Suite complète finale :
**5094 passed, 31 skipped, 48 deselected, 0 failed** (408.91s).

## Chunk précédent : DEC-0087 — ComfyUI comme moteur d'exécution alternatif

`core/production/comfyui_workflows.py` (registre CONTRÔLÉ de workflows —
un seul `STABLE`, `text_to_image`), `core/production/comfyui_strategie.py`
(décision matérielle à six issues, reconnaît le déchargement automatique
de ComfyUI), `core/connectors/comfyui.py` (connecteur HTTP direct — aucun
worker écrit, contrairement à HiDream : ComfyUI est déjà un serveur
complet), `core/production/image_backend_router.py` (choix DIRECT/COMFYUI,
défaut inchangé : `hidream` en premier, repli seulement sur
`NOT_CONFIGURED`). `agents/video/production_agent.py::_soumettre_image`
unifie `generer_image` et l'étape de graphe `hidream_image` sur le même
choix de backend.

**Sabotage réel** : la défense anti-traversée de chemin (`_chemin_contenu`)
retirée → un fichier hors du dossier de sortie attendu est confirmé comme
un succès. Restaurée → refusé, 27 tests repassent. 73 tests nouveaux,
régression ciblée 258 passed. `scripts/orphelins.py` : 292 modules, 233
atteints (+4/+4). Restart test réel : `backend=comfyui` route bien vers
ComfyUI, l'appel par défaut route toujours vers `hidream` (DEC-0085
inchangé) — aucun serveur ComfyUI n'a tourné ici (pas de GPU dans cet
environnement de développement), `NOT_CONFIGURED` honnête à chaque appel.

**Régression réelle trouvée par la suite complète** (pas par les tests
ciblés) : `tests/test_connecteurs_dormants.py` a détecté `comfyui` comme
connecteur sans appelant visible en analyse statique (le nom ne circulait
que dans un tuple). Corrigé en nommant la constante
(`BACKEND_COMFYUI = "comfyui"`), jamais ajouté à `DORMANTS_CONNUS` — le
connecteur EST joignable. Revérifié : 8 passed.

## Dernier chunk documenté avant celui-ci : DEC-0086 — Executive Intelligence

`core/executive/` (dix modules) : décision d'affaires multi-spécialiste,
`OpenExecutive` audité (SenteLabsAI, Apache-2.0), désaccord préservé entre
rôles, calcul déterministe (marge/échéancier/faisabilité). 166 tests, suite
complète mesurée alors : 4991 passed, 0 failed. Détail complet :
`docs/DECISIONS.md`, DEC-0086 ; PR ouverte séparément pour la mise à jour
de ce fichier de mémoire lui-même (`claude/active-work-post-dec-0086`) —
vérifier si elle a fusionné ; si non, son contenu est repris ci-dessus.

## ⚠️ L'historique détaillé entre DEC-0024 et DEC-0085 n'a pas été relu ici

Plus de 150 PR sont passées entre ce chunk et le précédent point vraiment
à jour de ce fichier (DEC-0024, connecteurs Gmail réels — voir
`docs/audits/connecteurs_audit.md`). Le relire correctement exige de
reparcourir chaque PR fusionnée depuis, hors périmètre d'une seule
session. Pour tout le
reste, `docs/DECISIONS.md` (toutes les entrées) reste la source exacte ; ce
fichier est un index, pas l'autorité.

## État à l'instant (2026-08-29 — voir l'avertissement ci-dessus)

| | |
|---|---|
| Branche | `claude/arena-personal-ai-integration-grp0ey` (repartie de `master` à chaque PR fusionnée en cours de session — voir CHANGELOG.md) |
| `master` | PR #26 à #34 fusionnées (DEC-0019, Qwen3-VL) ; DEC-0020 (diagnostic/réparation) prête à pousser |
| Tests | **2011** hors ligne au vert, 21 `integration` désélectionnés (+5 depuis DEC-0020) |
| Lint | `ruff` propre |
| Orphelins | 132 modules, 104 atteints, 28 orphelins — **tous** `__init__.py` vides. Aucun module réel endormi (`apps/pwa/server/` supprimé le 29/08/2026) |

## Dernier chunk : DEC-0020 — diagnostic et réparation, pas de nouvelle capacité

Mission demandée le 29/08/2026 : auditer la dette technique laissée par les
missions précédentes (silences avalés, fuites de ressources, frontières
entre composants, sécurité) et **réparer**, pas ajouter. Détail complet :
`docs/DECISIONS.md` DEC-0020.

Trois défauts confirmés et corrigés, chacun sabote-puis-restauré :
1. `agents/plaquiste/plaquiste_agent.py` — un chemin de plan pouvait
   désigner un fichier du dépôt d'ARENA lui-même (`.env`,
   `config/metier.yaml`) avant d'atteindre OpenTakeoff. Corrigé par
   `chemin_hors_du_depot()`, un contrôle de contention.
2. `core/execution/travaux.py` — l'historique des travaux **finis**
   grossissait sans fin (seul le parallélisme était borné). Corrigé par
   `TRAVAUX_TERMINES_GARDES = 200` + `_purger_les_anciens()`.
3. `core/models/ollama_provider.py` — une ligne de flux Ollama illisible
   disparaissait sans aucune trace (`except Exception: pass`). Corrigé par
   un `logger.debug()`.

Le reste de l'audit (≈50 `except Exception` du dépôt relus un par un,
cycle de vie httpx/MCP, TODO/FIXME/XXX, `shell=True`/`eval`/`exec`/
`pickle`, l'intégration Qwen3-VL relue au niveau du code) n'a rien trouvé
de plus — déjà correct. **Ne pas rouvrir ces composants "pour être sûr"** :
c'est exactement ce que la règle du projet interdit.

## Ce qui s'est fermé avant (PR #26 → #33)

| PR | Ce qui change | Statut |
|---|---|---|
| **#27** | `core/guardian/` — DÉCOUVRE et RAPPORTE (jamais MODIFIE), DEC-0014 | **FERMÉ** — 25 tests unitaires + 6 API, scénario §27 bout en bout |
| **#28** | correctif : `verifier_gardien()` distinguait mal « jamais lancé » de « lancé, rien trouvé » | **FERMÉ** — sabotage/restauration prouvés, +5 tests |
| **#29** | doc seule : la recherche web reste `UNKNOWN` en cloud à cause d'un 403 du bac à sable, pas seulement d'Ollama absent | **FERMÉ** — aucun code touché |
| **#30** | `apps/pwa/server/` supprimé (4 fichiers, 482 lignes) — décidé par le propriétaire depuis son téléphone | **FERMÉ** — 27 orphelins restants, tous `__init__.py` vides |
| **#31** | correctif interface `.writing-text` (mode clair) + DEC-0015 (audit de prompt WanGP) + DEC-0016 (Spec Kit refusé) — bundlées, PR fusionnée avant que chaque commit ait sa propre PR | **FERMÉ** — 35 tests, sabotage prouvé |
| **#32** | DEC-0017 — Agent-Reach refusé (sonde/installateur, rien à intégrer) ; `DeepResearcherAgent` corrigé : 3 recherches en séquence → en parallèle | **FERMÉ** — +1 test, sabotage (0,90 s séquentiel → 0,35 s parallèle) |
| **#33** | DEC-0018 — consolidation des modèles auditée, rien à fusionner (doc seule) | **FERMÉ** — aucun code touché |
| *(suivante)* | DEC-0019 — Qwen3-VL : `agents/vision/vision_agent.py`, intention `VISION`, `OllamaProvider.generate(images=...)`, pièces jointes image (jpg/png/webp/gif) | **FERMÉ** — 33 tests, 2 sabotages |

Mesures 7.2 (phase entière) : **toujours `UNKNOWN`**, structurellement — ne pas
retenter depuis le cloud (Ollama absent, recherche web bloquée par la
politique réseau du bac à sable). Attend son PC, raison déjà écrite dans
`docs/REPRISE.md`. La vision (DEC-0019) attend la même chose : `qwen3-vl:4b`
n'a jamais tourné, aucune image réelle n'a été analysée.

## Diagnostic machine (`doctor.py`), mesuré le 29/08/2026

Sur la machine de l'assistant (cloud, sans Ollama/Docker/ffmpeg/GPU — jamais
présents ici) :

```
[OK]   Python                   version 3.11.15
[ABS]  Environnement virtuel    aucun venv actif
[ABS]  Dependances              1 paquet manquant : uvicorn
[CONF] Cle API                  USMAN_API_KEY absente
[OK]   Inference (hybride)      mode HYBRIDE, tout passe par Ollama
[PANNE] Ollama / Modele rapide / Modele profond / Modele d'embeddings
[ABS]  Carte graphique / ffmpeg (video) / Docker (bac a sable)
[CONF] WanGP (generation video) / Video courte (MPT)
[CONF] Metre de plan (OpenTakeoff)  OPENTAKEOFF_MCP_DIR absent ou dist/server.js introuvable
[CONF] Courrier (Gmail) / Agenda (Calendar)  identifiants Google absents
[OK]   Connaissances metier     31 article(s) tarifes
[ABS]  Documents                dossier vide
```

**La ligne `Metre de plan (OpenTakeoff)` a été vérifiée BOUT EN BOUT** :
OpenTakeoff construit une fois dans cette session (`node`, `npm install`,
`npm run build`, hors dépôt), `OPENTAKEOFF_MCP_DIR` pointé dessus →

```
[OK]   Metre de plan (OpenTakeoff) OpenTakeoff repond : 42 outil(s) annonce(s).
```

`11 capacité(s) indisponible(s)` au lieu de 12. C'est exactement ce que
`scripts/installer_opentakeoff.ps1` produit chez le propriétaire (Windows) —
mesuré ici, jamais supposé. Le reste (Ollama, Docker, WanGP, MoneyPrinterTurbo,
Gmail/Agenda) reste `[ABS]`/`[CONF]`/`[PANNE]` sur cette machine, comme
attendu : rien de tout ça n'y a jamais été installé.

## Ce qui est fusionné dans `master` depuis le 28/08/2026 (PR #21 → #33)

1. `doctor.py` réécrit, puis relié à `sonder()` de chaque connecteur (jamais une seconde logique de santé) ;
2. **chapitre 9 — l'agenda**, **MoneyPrinterTurbo** branché sur l'agent vidéo ;
3. **ARENA hybride (DEC-0009)** : confidentialité 4 niveaux, Groq + DeepInfra, aiguilleur, banc d'essai ;
4. **Réseaux sociaux actifs (DEC-0010)** : méthode extraite de `charlie947/social-media-skills`, rien copié ;
5. **Coordination des tâches (DEC-0011)** : `grok-bot-0.18-reconstructed` refusé (aucune licence) ; `core/execution/coordination.py` écrit sans emprunt ;
6. **OpenTakeoff — métré de plan PDF (DEC-0012)** : transport MCP stdio, sous-ensemble réel, la limite plafond/mur/rampant corrigée sur indication du propriétaire ;
7. **Crochets d'exécution + disjoncteur (DEC-0013)** : idée extraite de DeepSeek Harness (Cordis refusé), premier consommateur réel — coupe court après des échecs consécutifs réels sur un service tombé ;
8. **Gardien de maintenance (DEC-0014)** : idée extraite de live-swe-agent (aucun code d'agent trouvé, refusé) — DÉCOUVRE et RAPPORTE seulement, jamais MODIFIE (commit/PR autonome explicitement hors périmètre, contraire à la règle non négociable du projet) ; correctif ultérieur pour que `doctor.py` distingue « jamais lancé » de « lancé, rien trouvé » ;
9. `apps/pwa/server/` supprimé (décision du propriétaire) ; correctif `.writing-text` invisible en mode clair sur l'interface ;
10. **Hell-Grind-AIGC-Skill (DEC-0015)** : `tools/video/prompt_audit.py` (audit déterministe de prompt, méthode extraite) + `VideoAnalyzerAgent.planifier_scene()` — premier appelant réel de `wan2gp.generer`, jamais invoqué si l'audit trouve une erreur bloquante ;
11. **GitHub Spec Kit (DEC-0016)** refusé — scaffolding de prompts pour agent de codage humain-supervisé, aucun moteur autonome ; câbler « implement » romprait la garantie PR de CLAUDE.md ;
12. **Agent-Reach (DEC-0017)** refusé — sonde/installateur pour agent de codage (yt-dlp, feedparser, Jina Reader, Exa), rien d'unique ; `DeepResearcherAgent` corrigé à la place : 3 recherches séquentielles → parallèles ;
13. **Consolidation des modèles (DEC-0018)** : inventaire audité, rien à fusionner — léger/profond sont des paliers de coût, pas des doublons ;
14. **Qwen3-VL — vision (DEC-0019)** : `agents/vision/vision_agent.py`, intention `VISION`, `qwen3-vl:4b` servi par Ollama (pas `transformers`), pièces jointes image encodées en mémoire jamais sur disque ; correctif au passage : `pwa_gateway.py` ne transmettait aucune pièce jointe à un agent spécialisé.

## Ce qui attend une action du PROPRIÉTAIRE

| Sujet | Ce qu'il faut de lui |
|---|---|
| **`USMAN_API_KEY`** | la changer s'il n'est pas certain de l'avoir fait (runbook, étape 1) |
| **Purge de l'historique** | jamais autorisée. Le dépôt est privé — sa décision |
| **Identifiants Google** | 3 valeurs dans `.env` pour réveiller courrier + agenda |
| **MoneyPrinterTurbo** | `scripts/installer_moneyprinter.ps1`, puis `llm_provider = "ollama"` et une clé Pexels dans **leur** `config.toml` |
| **OpenTakeoff** | `scripts/installer_opentakeoff.ps1`, puis `OPENTAKEOFF_MCP_DIR` dans `.env` — vérifié bout en bout dans cette session (ci-dessus), il ne reste que le geste chez lui |
| **Interface (PWA)** | `npm run build` dans `apps/pwa/` pour que le correctif du mode clair (PR #31) serve réellement |
| **WanGP** | lancer `python wgp.py --mcp --mcp-transport streamable-http ...` pour que `planifier_scene` (DEC-0015) génère vraiment une scène |
| **Vision (Qwen3-VL)** | `ollama pull qwen3-vl:4b` pour que `VisionAgent` (DEC-0019) analyse vraiment une image — jamais chargé ni mesuré dans cette session (pas de GPU ici) |
| **Mesures 7.2** | `python -m pytest -m integration` et `python scripts/mesurer_performances.py` sur son PC |

## Prochaine action recommandée

**Ne pas ouvrir une nouvelle phase du plan de soi-même.** Le propriétaire donne
la suite. Si elle vient : le plan pointe sur **11.1 — appels d'offres
sénégalais** (`docs/PLAN_ARENA_OS.md`), les chapitres 8, 9 et 10 étant terminés.

## Ce qui n'est PAS à faire

- relire le dépôt entier au début d'une session — cette mémoire existe pour ça ;
- refaire vérifier un système verrouillé « pour être sûr » ;
- marquer quoi que ce soit `100%` sans preuve, ni afficher un chiffre non mesuré ;
- toucher à `apps/pwa/` : l'interface n'a **jamais** été regardée.
