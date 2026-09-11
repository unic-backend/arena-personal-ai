# JOURNAL DES CHANGEMENTS — mémoire de session

*Ce que chaque session a réellement livré, avec sa preuve. Le récit complet vit
dans `docs/REPRISE.md` ; ici, l'essentiel pour reprendre sans tout relire.*

---

## 2026-08-28 — session « réveil, sécurité, chapitres 8 et 9, MoneyPrinterTurbo »

### Livré et fusionné

| PR | Ce qui change | Preuve |
|---|---|---|
| **#15** | la vidéo à l'agent vidéo, les documents au chemin documentaire (`suivi_video`, `travaux`, `indexer`, `inventory`) | 68 → 72 modules atteints |
| **#16** | la mémoire du chat : le sens (`semantique`) et une chose dite une fois (`consolidation`) | 72 → 74 |
| **#17** | le coût d'une réponse (`voies`, `mesures`) et un raisonnement qui calcule vraiment (`reasoning_engine`) ; `GET /api/observability` | 74 → 77, **0 module réel endormi** |
| **#18** | **sécurité** : LibreChat et Open WebUI retirés — 4 des 5 clés fuitées deviennent mortes (DEC-0007) | 2 sabotages |
| **#19** | le dépôt est passé **privé** par le propriétaire ; documents mis à jour | `"private": true` vérifié |
| **#20** | **chapitre 8** : courrier — lire, trier, et n'envoyer qu'avec son accord | 1462 → 1520 tests |

| **#21** | 4 commits : `doctor.py` qui mesure ; **chapitre 9 — agenda** ; `doctor.py` qui lit les noms dans le code ; **MoneyPrinterTurbo** sur l'agent vidéo | fusionnée en `45861a7` |

Mesure finale de la session : `ruff` propre, **1615 passed / 21 deselected**,
110 modules, 82 atteints, aucun module réel endormi.

### Pièges trouvés par les tests, pas par relecture

- « fais-moi une vidéo sur les cloisons BA13 » partait chez l'assistant **devis** (le mot « ba13 » l'emportait) ;
- « suis-je libre **cette semaine** ? » partait chercher l'**actualité** sur le web ;
- « écris un mail au client » devait **rester** au métier, et y est resté (test du propriétaire du 27/08) ;
- « génère » porte un accent **grave** que `[ée]` ne couvrait pas ;
- `doctor.py` réclamait `GMAIL_CLIENT_ID` quand le projet attend `GOOGLE_CLIENT_ID`.

### Sabotages de la session

24 garanties cassées volontairement, 24 fois un test précis est tombé, toutes
restaurées. Les plus parlantes : « l'agent envoie sans confirmation » fait passer
le statut de `NEEDS_CONFIRMATION` à **`SUCCESS`** — le message part vraiment.

### Réseaux sociaux (DEC-0010)

17 compétences de `charlie947/social-media-skills` inspectées, **méthode
extraite, fichiers non copiés**. Six capacités opérationnelles, quatre déclarées
`CONFIGURATION_REQUISE`/`INDISPONIBLE` avec ce qui leur manque. Publier passe par
le connecteur : confirmation **et** coupe-circuit `PUBLISH` (à `false`).

---

## 2026-08-29 — ARENA hybride, réseaux sociaux actifs, coordination, OpenTakeoff

### Livré et fusionné (PR #23 — 6 commits, fusionnée 2 min après ouverture)

| Ce qui change | Preuve |
|---|---|
| **ARENA hybride (DEC-0009)** : confidentialité 4 niveaux, Groq + DeepInfra, aiguilleur `RouteurModeles`, suivi de coût, banc d'essai | +180 tests |
| **Réseaux sociaux actifs (DEC-0010)** : `charlie947/social-media-skills` — méthode extraite (règles → code qui compte, voix → mémoire réelle, idées → combinatoire), rien copié | `PUBLISH: false` tenu |
| **Coordination des tâches (DEC-0011)** : `grok-bot-0.18-reconstructed` **refusé** (code extrait de binaires propriétaires, aucune licence — sa propre `PROVENANCE.md` l'interdit) ; `core/execution/coordination.py` écrit sans emprunt, branché sur le moteur de raisonnement | Docker absent : `calcul SKIPPED`, `aboutie: True` |

Piège trouvé en cours de route : la PR #22 avait été fusionnée 2 minutes après
son ouverture, n'emportant que le commit `PROJECT_MEMORY` — les 6 commits
suivants sont restés hors PR jusqu'à la #23 (rebase propre, aucun conflit).

### En cours — OpenTakeoff, le métré d'un plan PDF (DEC-0012)

`Kentucky-ai/opentakeoff` (Apache-2.0) construit et **fait tourner pour de
vrai** dans cette session (Node installé, `demo/sample-plan.pdf` mesuré : 4
pièces, 1751.92 SF, rapport + PDF marqué réellement écrits sur disque).

Différence structurelle découverte en l'inspectant : son serveur MCP ne parle
QUE stdio (`StdioServerTransport`), jamais HTTP — le transport HTTP écrit pour
WanGP ne pouvait pas s'y brancher. `core/mcp/stdio_transport.py` est un second
transport MCP, qui réutilise le contrat `Reponse` du premier sans le dupliquer.
Piège trouvé par un test, pas par relecture : mélanger `select()` bas niveau et
`readline()` bufferisé faisait attendre le délai complet (60 s) pour une ligne
déjà arrivée — deux lignes écrites par le même appel système atterrissaient
dans le tampon interne de `TextIOWrapper`, invisible au `select()` suivant.
Corrigé en lisant au niveau du descripteur (`os.read`).

Sous-ensemble réel, jamais les quarante outils du serveur : rien qui suppose de
désigner une coordonnée sur l'image du plan (un modèle de texte ne la voit
pas). Limite honnête tenue par un test sabotable : le périmètre d'une pièce
mesurée n'est JAMAIS transformé en surface de cloisons à chiffrer — seul un
faux plafond, sans ambiguïté, peut se chiffrer depuis la surface au sol
mesurée.

Mesure de fin de session : `ruff` propre, **1861 passed / 21 deselected**
(1813 avant → 1861, +48 tests), 4 sabotages sur ce chapitre, tous restaurés.

### Suite du 29/08 — DeepSeek Harness, Gardien, décisions du propriétaire, Hell-Grind

| PR | Ce qui change |
|---|---|
| **#25** | DeepSeek Harness (DEC-0013) : Cordis (bus de plugins) refusé — résout un problème qu'ARENA n'a pas ; `core/execution/hooks.py` + `core/execution/disjoncteur.py` extraits, premier consommateur réel |
| **#27–28** | Live-SWE-agent (DEC-0014) : aucun code d'agent trouvé — `core/guardian/` construit à côté (DÉCOUVRE/RAPPORTE, jamais MODIFIE) ; correctif d'honnêteté sur `doctor.py` |
| **#30** | `apps/pwa/server/` supprimé — décision du propriétaire, donnée depuis son téléphone |
| **#31** | correctif interface : `.writing-text` invisible en mode clair (composeur + édition d'un message) |
| **(suivante)** | Hell-Grind-AIGC-Skill (DEC-0015) : `tools/video/prompt_audit.py` — premier appelant réel de `wan2gp.generer`, bloqué tant qu'un prompt n'est pas structurellement complet |

Mesure de fin de session : `ruff` propre, **1972 passed / 21 deselected**
(1861 → 1972, +111 tests sur cette suite de PR), 130 modules / 103 atteints /
27 orphelins (tous des `__init__.py`).

Correction du propriétaire le lendemain (« la surface d'un cloisons c'est
largeurs et hauteur ») : la première version confondait surface au sol et
surface de mur pour doublage/habillage/coffre. Corrigée en trois issues
(plafond plat / mur avec hauteur / rampant jamais calculable) — **1872
passed** (+11 tests, 2 sabotages de plus).

### DeepSeek Harness — crochets, pas Cordis (DEC-0013)

Audité dans son propre code (`packages/core/tools/src/index.ts`,
`packages/guard/`), pas seulement son README. Cordis (son bus de plugins
entier) refusé : il résout un problème qu'ARENA n'a pas (plusieurs équipes
publiant des plugins), et le reprendre aurait créé un second système
d'orchestration à côté de celui déjà verrouillé.

Ce qui a été extrait, sans une ligne de TypeScript reprise :
`core/execution/hooks.py` (deux points, ajoutés APRÈS les quatre contrôles
verrouillés de `core/connectors/base.py`, jamais à leur place) et son premier
consommateur réel, `core/execution/disjoncteur.py` — un disjoncteur qui coupe
court après des échecs consécutifs REELS, pour ne plus repayer le délai
d'attente complet d'un service tombé à chaque appel. Câblé une fois dans
`runtime.py`, partagé par les huit connecteurs.

Preuve bout en bout (`tests/core/test_crochets_integration.py`) : un vrai
connecteur de test échoue 3 fois pour de vrai (`appels_reels == 3`), le 4e
appel ne retouche plus le service (`appels_reels` reste a 3) — le compte
d'appels réels est la preuve, pas seulement le message rendu.

Mesure : **1899 passed / 21 deselected** (1872 → 1899, +27 tests), 4
sabotages, tous restaurés.

---

## 2026-08-28 (fin) — mise en place de PROJECT_MEMORY

Créé après la fusion de la PR #21 : ce dossier arrive donc dans une pull
request qui lui est propre. Création de `PROJECT_MEMORY/` (8 fichiers) sur
demande du propriétaire :
carte, architecture, systèmes achevés, travail en cours, zones verrouillées,
dépendances, index des décisions, ce journal.

**Aucun code applicatif modifié.** Aucun système marqué `100%` sans preuve : la
distinction « logique vérifiée » / « bout en bout » est posée explicitement dans
`COMPLETED_SYSTEMS.md`, parce que rien de ce qui dépend d'Ollama, de ffmpeg, de
Docker ou de Google n'a jamais tourné sur la machine de l'assistant.

---

## 2026-09-07 — audit OmniVoice : la licence des poids, et un seul routeur de voix

**DEC-0069.** Le moteur par défaut d'ARENA allait devenir OmniVoice — dont les
**poids** sont CC-BY-NC, usage commercial interdit — sur les vidéos d'une
entreprise. Trois faits qui ne se recoupaient qu'ensemble : `omnivoice` est la
première entrée du registre de VoiceStudio, ARENA prenait le premier
disponible, et le dépôt d'OmniVoice ne porte qu'une licence Apache-2.0 pour son
**code**, sans un mot sur ses poids.

| Livré | Preuve |
|---|---|
| `core/audio/routage_tts.py` — **un seul** routeur (parler *et* cloner), qui connaît les licences | 37 tests |
| refus du commercial sur poids non commerciaux, porte `usage="recherche"` ouverte | 7 tests bout en bout au connecteur |
| `effective_device` / `routing_status` lus et rapportés — VoiceStudio les publiait, ARENA les jetait | 4 tests |
| `scripts/verifier_voix.py` — la chaîne réelle sur SA machine, amplitude comprise | 4 tests |
| `scripts/doctor.py` ne dit plus `[OK]` si tous les moteurs sont non commerciaux | 2 tests |

**Sept sabotages joués, six ont cassé un test. Le septième est passé** : le
contrôle de licence de `doctor.py` n'avait aucun test. Il en a deux
maintenant. Quatrième fois en trois jours qu'une garantie de ce dépôt se
révèle non tenue jusqu'à ce qu'on la sabote.

`ruff` propre, **4085 passed / 25 skipped** (etait 4030), 212 modules dont 168 atteints.

> **Dette de mémoire, signalée sans être corrigée** : `PROJECT_MEMORY/DECISIONS.md`
> s'arrête à DEC-0020 et se date du 29/08/2026 — il lui manque 49 décisions.
> `docs/DECISIONS.md` reste l'autorité et est à jour. Rattraper l'index est un
> travail à part, pas un effet de bord de cette mission.

---

## 2026-09-07 (suite) — `architecture_3d` : ARENA sait construire un bâtiment

**DEC-0070.** ARENA savait **lire** un IFC et chiffrer une cloison ; elle ne
savait pas **construire**. Pascal Editor (MIT) comble ce trou — comme
**backend** d'une capacité d'ARENA, jamais comme propriété d'un modèle.

| Livré | Preuve |
|---|---|
| `core/architecture/` — capacité, vocabulaire de 22 opérations, plan déterministe | 44 tests |
| `core/connectors/architecture_3d.py` — permissions, confirmation unique, journal | 3 actions (`read`/`batir`/`demolir`) |
| intention `ARCHITECTURE_3D`, voie instantanée, routage — **aucun agent créé** | la mission l'interdit quand la capacité suffit |
| ligne « Architecture 3D » dans `doctor.py` | 28 → **29 vérifications** |

**Mesuré sur la phrase de la mission** : 11 opérations en 476 ms, **36 murs**
(4 de pourtour : 20, 15, 20, 15 m) et **8 pièces** aux noms demandés. Deux
sessions ouvertes en même temps ne partagent jamais une scène.

**Trois pannes trouvées en exécutant, pas en lisant** : le paquet publié ne
tourne pas sous Node malgré son README (Bun exigé) ; `zod` 4.5.4 cassait
**toutes** les écritures pendant que les lectures restaient parfaites ; et
22 règles de permission nommées par capacité ne matchaient rien — la
politique interroge l'**action**, pas le nom.

Cinq sabotages joués, **cinq ont cassé un test**.

`ruff` propre, **4137 passed / 25 skipped**, 217 modules dont 172 atteints.

---

## 2026-09-07 (suite) — le formulaire venait d'une lecture qui échouait

**DEC-0071.** Sa capture : « Fais-moi une cloison de 5 m sur 2,5 m, avec une
porte de 80 × 210 cm » → trois questions de formulaire. Son mot : *« il se
base toujours sur une conduite de réponse alors qu'il devrait réfléchir »*.

| Défaut | Correctif |
|---|---|
| `metre.py` exigeait un CHIFFRE avant le nom et ignorait « sur » → sa phrase n'était **jamais lue** | compte optionnel et en lettres, « sur » ajouté |
| **Aucune ouverture n'était déduite** nulle part → cloison avec porte chiffrée comme pleine | `lire_ouvertures` : portes, fenêtres, baies, cm→m |
| Les trois questions étaient posées **à l'entrée** | répondre d'abord ; questionner à la fin, et seulement pour un document qui part |

Sa phrase donne maintenant : 12,5 m² − 1,68 m² = **10,82 m² à plaquer**, puis
11 plaques BA13, 13 montants, 3 rails — avec sa grille de prix.

Un test cassé par le correctif vérifiait la chaîne « tu les demandes » : une
**formulation**, pas une garantie. Réécrit pour mesurer le comportement.

Quatre sabotages joués, quatre ont cassé un test. `ruff` propre,
**4156 passed / 25 skipped**.

---

## 2026-09-07 (suite) — Open SWE : rien d'installé, la reprise gagnée

**DEC-0072.** Mission : fusionner les meilleures capacités de
`langchain-ai/open-swe` dans le génie logiciel d'ARENA, sans deuxième agent.

**Refusé, mesuré** : Open SWE exige `Python >= 3.14`, ARENA tourne sur
**3.11.15**. Et ses dépendances apporteraient un second moteur d'orchestration
(LangGraph + deepagents), **quatre sandbox cloud** et des paquets liés à un
fournisseur — exactement les doublons que la mission interdit. Licence MIT :
la copie était permise, elle n'était pas utile.

**Le seul manque réel** : `DioumtoukayAgent` s'arrêtait à 12 actions / 20 min
en rendant « la suite reste à faire », et ne gardait qu'un **résumé en prose**.
`FileDeTravaux` est purement en mémoire. « Reprends ce que tu faisais »
repartait de zéro.

| Livré | Preuve |
|---|---|
| `core/execution/reprise.py` — journal d'étapes durable, écriture atomique après **chaque** action | 16 tests |
| `balayer()` — l'idée de leur `reconcile.py` : une tâche morte cesse de se déclarer vivante | 4 tests |
| Reprise branchée dans l'agent **existant** — aucun agent, aucune file de plus | 11 tests bout en bout |

**Mesuré sur un vrai dépôt buggé** : `pytest` échoue, le fichier est vraiment
modifié, `pytest` passe. Interruption puis reprise : 2 étapes + 1, **même
`task_id`**. Seul le modèle est doublé, et c'est dit.

Cinq sabotages joués, **cinq ont cassé un test**. `ruff` propre,
**4183 passed / 25 skipped**, 218 modules dont 173 atteints.

---

## 2026-09-08 — Open SWE, suite : le connecteur GitHub qui manquait vraiment

**DEC-0073.** Une session parallèle a reçu la même mission (fusionner Open
SWE) au même moment, sans le savoir. Son audit affirmait qu'un connecteur
GitHub existait déjà côté ARENA — mesuré faux : `git grep` sur `origin/master`
ne trouvait rien. Cette session a construit ce qui manquait réellement, sans
défaire DEC-0063 (garde-fous de boucle) ni DEC-0072 (reprise de tâche).

| Livré | Preuve |
|---|---|
| `core/connectors/github.py` — premier connecteur GitHub du dépôt, contrat `Connecteur` existant | 22 tests, sabotage sur la garde de PR (confirmation avant tout réseau, brouillon forcé dans le vrai corps POST, client injecté jamais fermé) |
| `DioumtoukayAgent` : `analyser`/`diagnostiquer` (consultent `RepoEngineerAgent`/`SWEAgent` comme outils, plus des culs-de-sac séparés), `ouvrir_pr`/`etat_ci` | 14 tests |
| `core/production/disponibilite_swe.py` — la capacité `software_engineering`, sondée pour de vrai sur 3 backends | 8 tests |

**Corrigé en route** : `tests/test_connecteurs_dormants.py` (code de l'autre
session) parcourait `tools/vision/faceplugin/.../.venv/` — un SDK tiers
vendored — une fois par connecteur enregistré, `ast.parse` sur `sympy` entier
compris. La suite complète ne terminait jamais sur cette machine. Exclusion
via `scripts/orphelins.py::MOTEURS_EXTERNES`, déjà éprouvée pour le même
défaut ailleurs dans le dépôt.

`ruff` propre, **suite complète : 4219 passed, 31 skipped, 48 deselected,
0 failed** (522.77s, `gitingest`/`txtai`/`ifcopenshell` installés — leur
absence donnait 57 échecs `ModuleNotFoundError`, aucun lié à cette fusion).
220 modules dont 175 atteints.

---

## 2026-09-08 (suite) — File_Converter_Pro : une capacité de conversion, pas une deuxième application

**DEC-0074.** Mission : exploiter les capacités utiles de
`Hyacinthe-primus/File_Converter_Pro` (GPLv3, app de bureau Windows) pour
ARENA — sans deuxième application, deuxième système documentaire, ou
deuxième moteur vidéo/PDF.

**Le manque réel, mesuré avant tout code** : aucune conversion générale
n'existait. `Pillow` n'était même pas une dépendance.

| Livré | Preuve |
|---|---|
| `core/connectors/file_conversion.py` — 6 capacités, contrat `Connecteur` existant | 44 tests, conversions réellement exécutées |
| `core/production/conversion/registre.py` — disponibilité/version/limites de qualité MESURÉES, ce que File_Converter_Pro lui-même ne fait pas | matrice de 156 couples de formats |
| 6 moteurs : LibreOffice, Pillow, CairoSVG, WeasyPrint+Markdown, pypdfium2 (déjà une dépendance), `FFmpegTool` étendu (jamais dupliqué) | chaque famille testée sans mock |
| `ACTION: convertir` dans Dioumtoukay | 5 tests, un end-to-end sans mock (DOCX->PDF réel) |
| Lot via `FileDeTravaux` déjà existante | 2e usage réel après `suivi_video.py` |

**Deux vrais défauts trouvés en construisant** : `soffice --infilter` en
deux arguments séparés (liste `subprocess.run`) est refusé silencieusement
par LibreOffice (code 0, rien écrit) — corrigé en un seul jeton
`--infilter=X`. Un `.docx` corrompu devenait, via LibreOffice, un PDF
« réussi » sans rien prouver sur l'entrée — `format_source_coherent()`
(octets magiques) refuse maintenant ce cas avant tout moteur.

**Non intégré, sciemment** : watch folders/scheduler (aucun n'existe dans
ARENA — en ajouter un serait le deuxième ordonnanceur interdit),
HEIC/AVIF/RAW/PSD/EPUB (dépendances non mesurées ou non demandées),
Windows-only (`docx2pdf`, menu contextuel), interface/gamification.

`ruff` propre. Tests ciblés au vert (53 nouveaux, aucun mock sur les
moteurs réels).

---

## 2026-09-09 — AI File Sorter + audit expérimental complet de l'agentivité

**DEC-0075.** Mission en deux parties : classer des fichiers (`file_
organization`, inspiré de `hyperfield/ai-file-sorter`, AGPLv3, Qt/C++) et
vérifier EXPÉRIMENTALEMENT ce qu'ARENA sait vraiment faire — filesystem,
terminal, code, Git — jamais supposé.

| Vérifié pour de vrai | Preuve |
|---|---|
| Filesystem (Atelier) | lister/lire/écrire/modifier/déplacer, chacun vérifié sur disque indépendamment du rapport de l'agent |
| Terminal | args/stdout/stderr/exit code/timeout (arrêt réel à 2.0s sur une commande de 30s), pas de shell=True |
| Boucle de correction de bug | lire → tests échouent → corrige → tests passent, vérifié par un `pytest` relancé séparément |
| Git | status/diff/branche/commit réels, aucun push |
| Permissions | DENY par défaut, ALLOW, CONFIRMATION — les trois mesurés live |
| Tâches de fond | progression réelle, annulation réelle (pas seulement marquée) |

**Quatre primitives filesystem manquaient** (copier/supprimer/créer
dossier/metadata+hash) — mesuré par `hasattr()` avant d'écrire une ligne,
ajoutées à `Atelier`. **Un vrai manque de sécurité trouvé** : aucun
chemin de lecture de Dioumtoukay n'utilisait `core/security/trust.py`
(déjà existant) — fermé pour la nouvelle capacité.

| Livré | Preuve |
|---|---|
| `core/production/organisation/` — plan à vocabulaire FERMÉ, sécurité confinée au dossier, mémoire réutilisant `MemoirePersonnelle` | 28 tests connecteur |
| `core/connectors/file_organization.py` — inspecter/planifier/appliquer/annuler/etat | suppression : accord SÉPARÉ de la confirmation ordinaire |
| 4 actions Dioumtoukay | 8 tests, un end-to-end réel (inspecter→planifier→appliquer→annuler, vérifié sur disque) |

**Bug trouvé et corrigé** : comptage d'irréversibles cherchait
`"reversible"` sans accent — toujours zéro. Corrigé sur le type
d'opération.

**Non intégré** : watch folders/scheduler (aucun n'existe — deuxième
ordonnanceur interdit), vision réelle sur image (Ollama absent ici —
UNKNOWN, à mesurer sur son PC).

`ruff` propre. Restart testé (import frais du runtime) : filesystem,
shell, git, file_conversion, file_organization, github, permissions —
tous confirmés opérationnels après coup.

---

## 2026-09-09 (suite) — PDFx : pages PDF + format multi-documents

**DEC-0076.** Mission : étudier `AlexandrosGounis/pdfx` (Electron, MIT)
pour ARENA — sans cloner l'app, sans deuxième système PDF.

**Le manque réel** : `pypdf` déjà présent (lecture seule) mais jamais en
écriture — aucune fusion/scission/pages/manifeste.

| Livré | Preuve |
|---|---|
| `core/production/documents_pdf/` — dix opérations via `pypdf` seul | 31 tests, aucun mock |
| Format PDFx adopté (import+export) — manifeste en pièce jointe PDF, `pypdf` seul, zéro dépendance neuve | round-trip complet vérifié : fusion 3 PDF → démontage → documents identiques |
| `core/connectors/pdf.py` — 10 capacités, jamais destructif sur la source | ALLOWED sous WRITE_FILES |
| 4 actions Dioumtoukay | scénario exact de la mission (4 docs, ordre précis) rejoué et vérifié |

**Bug trouvé et corrigé** : comptage de pages hors de la garde
anti-chiffrement — un PDF chiffré levait une exception non gérée au lieu
d'un refus propre.

**Sécurité testée avec de vrais fichiers** : corrompu (échec propre),
chiffré (refusé explicitement), JavaScript embarqué (jamais exécuté —
`pypdf` n'a aucun moteur JS), injection de prompt dans le texte (marquée
donnée via `core/security/trust.py`, motifs relevés).

**Non intégré** : Electron/UI (ARENA reste un backend Python), rédaction
(non demandée), assistant IA propre à PDFx (ARENA route déjà ses modèles).

`ruff` propre. 242 modules, 194 atteints, aucun module réel endormi.
Restart testé.

---

## 2026-09-09 (suite) — Cline : deux gardes anti-blocage pour Dioumtoukay

**DEC-0077.** Mission : étudier `cline/cline` (Apache-2.0, monorepo avec
compte cloud/ordonnanceur/démon/équipe) pour renforcer Dioumtoukay — jamais
un second agent de codage.

**Le manque réel** : les gardes DEC-0063 (plafond de temps, réponses
illisibles) ne détectaient ni une action valide rejouée à l'identique, ni
des échecs d'exécution répétés sur des actions différentes.

| Livré | Preuve |
|---|---|
| `Action.signature()` + `ACTIONS_IDENTIQUES_CONSECUTIVES_MAX = 3` | test dédié + sabotage (condition neutralisée → le test échoue) |
| `ECHECS_CONSECUTIFS_MAX = 3` | test dédié + sabotage (condition neutralisée → le test échoue) |
| Recherche MCP côté ARENA avant conclusion | `core/mcp/transport.py`+`stdio_transport.py` déjà réels, déjà utilisés — rien dupliqué |

**Aucun fichier neuf** : les deux gardes vivent dans
`agents/dioumtoukay/dioumtoukay_agent.py`, au même niveau que DEC-0063.

**Un test existant corrigé** : `test_il_s_arrete` rejouait la même action
pour tester `TOURS_MAX` — la nouvelle garde l'arrêtait avant. Corrigé pour
alterner deux actions.

**Non intégré** : ordonnanceur/démon/comptes d'équipe de Cline (aucun
besoin correspondant), pont d'approbation par fichiers (`core/actions/
attente.py` fait déjà mieux), modules `agents/llms/mcp/cli` de Cline (ARENA
a déjà chacun de leurs équivalents — matrice 20 lignes dans
`docs/audits/cline_audit.md`, 19/20 `KEEP ARENA`).

`ruff` propre sur les fichiers touchés. Suite complète relancée après
modification (voir le rapport final pour le résultat).

---

## 2026-09-09 (suite) — Les trois défauts de DEC-0077, séparément

Un des trois n'en était pas un : `test_meme_format_source_et_cible_est_un_
echec` (file_conversion) accusé à tort — vérifié en isolation, propre,
6,2 s. Le court-circuit « déjà au bon format » existe et fonctionne avant
tout moteur ; l'investigation précédente avait mal isolé le test fautif au
milieu de plusieurs `pytest` bloqués en parallèle.

| Corrigé | Cause réelle | Preuve |
|---|---|---|
| `RepoEngineerAgent` attend jusqu'à 180 s de `gitingest` | délai trop généreux pour un « coup d'œil » — sous contention, très lent | nouveau paramètre `delai` (plafonné), ingestion réelle du dépôt mesurée à 14 s en isolation ; tests + sabotage |
| `test_le_rapport_survit_a_n_importe_quelle_sonde_qui_leve` rejouait ~10× les vraies sondes | Faceplugin (sous-processus, 120 s prévus pour un 1er chargement sans GPU) invoqué pour de vrai à chaque itération | rendu hermétique (témoin par sonde non testée), sabotage vérifié : 0,1 s au lieu de plusieurs minutes |

**Incident en cours de route** : disque de la machine cloud plein (0 octet
disponible) pendant la vérification — fichiers temporaires accumulés dans
`/tmp` (logs `pytest`, copies `.bak` de sabotage) sur plusieurs missions.
Nettoyé (2314 fichiers), 4 Go libérés. Sans rapport avec le code du dépôt.

Suite complète, après nettoyage : **4372 passed, 31 skipped, 48 deselected,
0 failed** (456 s). `ruff check .` propre.

---

## 2026-09-10 — Intelligence financière (DEC-0078), AutoHedge audité

Mission : étudier `The-Swarm-Corporation/AutoHedge` et en tirer une capacité
d'analyse financière pour ARENA — jamais un fonds spéculatif, jamais un
ordre réel. Détail complet : `docs/DECISIONS.md` DEC-0078,
`docs/audits/autohedge_audit.md`.

**L'audit, testé en direct, pas seulement lu** : `AutoHedge.run()` n'appelle
qu'un seul agent (le Director) ; Quant/Risque/Exécution n'ont aucun outil
(`tools=`) attaché — leurs « calculs » sont du texte de LLM, confirmé par
zéro `numpy`/`pandas` en dehors de code mort. Les outils Jupiter (Solana)
sont réels et fonctionnent **en isolation** (prix SOL réel obtenu, cohérent
avec CoinGecko), mais **jamais câblés** au produit
(`tools_registry.get_tools()` n'est importé nulle part). Aucun test dans
tout le dépôt malgré 5 workflows CI. Aucune boucle autonome.

**Construit dans ARENA**, tout nouveau, rien dupliqué :

| Fichier | Rôle |
|---|---|
| `core/connectors/market_data.py` | CoinGecko, lecture seule, sans clé — même cadre `Connecteur` que tout le reste |
| `core/finance/quant.py` | Arithmétique pure (RSI, MACD, Bollinger, drawdown, corrélation...), zéro appel modèle |
| `core/finance/risk.py` | Classification de risque déterministe + scénarios (stop-loss, taille de position) |
| `core/finance/paper_trading.py` | Portefeuille simulé, SQLite, aucun ordre réel — appelé par `FinanceAgent` sur ordre simulé explicite |
| `core/finance/structured_output.py` | Le schéma de sortie fixe |
| `agents/finance/finance_agent.py` | Director ARENA : données réelles -> calcul -> risque -> interprétation, ordre fixé dans le code |
| `agents/orchestrator/orchestrator_agent.py` | Intention `FINANCE`, même correctif de collision date que le courrier (31/08/2026) |

**Rien copié d'AutoHedge** : ni code, ni dépendances (`swarms`, `solders`
absents de `requirements.txt`), seulement le principe de séparation des
rôles, adapté au cadre d'agents existant d'ARENA.

**Délibérément pas fait** : aucune intégration Solana/Jupiter (le risque
réel d'AutoHedge n'est même pas câblé chez eux) ; aucun fournisseur
actions/ETF (pas de clé fournie) ; aucun backtesting.

**Un orphelin réel trouvé et réveillé en cours de route** :
`scripts/orphelins.py` a signalé `core.finance.paper_trading` comme
module réel jamais atteint — exactement ce que `CLAUDE.md` mesure et
interdit de laisser dormir. Corrigé dans la même passe : `FinanceAgent`
reconnaît maintenant un ordre simulé **explicite** (« achète 0,1 bitcoin
simulé »), toujours au prix de marché réel, jamais inventé, et refuse
tout le reste (le mot « simulé » est obligatoire). `250 modules, 200
atteints, aucun module réel endormi` (`CLAUDE.md` mis à jour, était
242/194).

Quatre sabotages, quatre restaurations : le garde-fou anti-fabrication
(retiré → le modèle est consulté sans données réelles, test rouge),
la collision date/finance dans l'orchestrateur (retirée → repart en
FRESH_INFO), la frontière de mot des tickers courts (retirée → « analyse
ce mur isolé » déclenche FINANCE à tort), le mot « simulé » obligatoire
(retiré → « achète 0,5 bitcoin » ordinaire est lu comme un ordre).

`ruff check .` propre. Suite complète relancée après le réveil de
`paper_trading.py` : **4507 passed, 31 skipped, 48 deselected, 0 failed**
(422 s).

---

## 2026-09-10 (suite) — Navigation Web : vérification déterministe (DEC-0079), Fuji-Web audité

Mission : étudier `normal-computing/fuji-web` et renforcer la navigation
Web existante d'ARENA. Détail complet : `docs/DECISIONS.md` DEC-0079,
`docs/audits/fuji_web_audit.md`.

**ARENA avait déjà un navigateur autonome complet** (`browser-use` +
Playwright, DEC-0059) — rien à combler côté moteur. **L'audit, testé
contre la vraie bibliothèque installée** (dans un environnement isolé,
jamais le dépôt) : Fuji-Web est une extension Chrome supervisée par un
humain, pas un service headless — architecture différente, pas un
concurrent direct. Son seul fichier de test n'est jamais exécuté par sa
propre CI (`"test": "exit 0"`). Liste déroulante, multi-onglet, sauvegarde
de workflow : roadmap, confirmés absents du code — `browser_use` les a
déjà tous. Son vrai défaut : aucune vérification déterministe du résultat
d'une action.

**Le moteur Chromium/Playwright réel d'ARENA a été conduit en direct**
(page locale construite pour le test, sans modèle) : navigation, clic sur
le bon élément parmi deux pièges, formulaire, contenu dynamique,
capture d'écran et téléchargement — fichiers physiques vérifiés sur
disque. Un vrai défaut de récupération trouvé en testant les pannes
(re-naviguer sur le même onglet après un échec de navigation) — sans
conséquence pour ARENA, qui ne réutilise jamais une page entre deux
tâches.

**Corrigé** :

| Fichier | Changement |
|---|---|
| `tools/browser/browser_use_tool.py` | Plafond de pas explicite, callback d'étapes → statuts concis, `sensitive_data`/`allowed_domains` (identifiants protégés — refus sans domaines restreints, `browser_use` avertit lui-même du risque de fuite par injection de prompt), signaux déterministes renvoyés |
| `core/connectors/browser.py` | `classer_resultat()` — un succès auto-déclaré contredit par des erreurs devient `PARTIAL`, jamais un succès plein |
| `agents/browser/browser_agent.py` | Résultat d'une page tierce désormais enveloppé (`TrustLevel.EXTERNAL`) — avant cette mission, il arrivait brut dans la réponse |
| `apps/backend/runtime.py` | Le connecteur browser partage enfin `ollama_rapide` au lieu d'en reconstruire un second — l'avertissement que ce fichier porte depuis sa première ligne |

**Délibérément pas fait** : aucun second agent/moteur de navigateur ;
aucun routage dynamique cloud pour la navigation (`RouteurModeles` choisit
par appel, `browser_use.Agent` attend un LLM statique — les deux ne
s'emboîtent pas sans refonte plus profonde, **limitation documentée**,
non masquée) ; aucun coffre-fort d'identifiants inventé (le branchement
`sensitive_data` est prêt, rien ne le remplit aujourd'hui).

Trois sabotages, trois restaurations : la distinction succès/erreurs
contradictoires, le refus d'identifiants sans domaines restreints,
l'enveloppe de confiance (TEST 10, injection de prompt).

`ruff check .` propre. Suite complète (`python -m pytest tests/ -q`) :
4534 passed, 31 skipped, 48 deselected, 0 failed (422.57s / 7m02s, mesuré
le 10/09/2026, confirmé par une seconde mesure indépendante).

---

## 2026-09-10 (suite) — Parole conversationnelle : Sesame CSM audité, jamais par défaut (DEC-0080)

Mission : étudier `SesameAILabs/csm` et intégrer sa vraie force — la
conversation — dans le routeur de voix existant d'ARENA, sans créer de
second système. Détail complet : `docs/DECISIONS.md` DEC-0080,
`docs/audits/sesame_csm_audit.md`.

**ARENA avait déjà un routeur de voix unique** (`core/audio/routage_tts.py`,
DEC-0069), alimenté par VoiceStudio. Rien à dupliquer côté architecture —
CSM entre dans le MÊME `choisir()`, comme un moteur de plus, jamais un
second routeur. Code et poids Apache-2.0 de bout en bout (vérifié
directement, pas supposé du README) : aucune contrainte juridique, à la
différence de VoiceStudio (AGPL) ou KrillinAI (GPL) — la frontière « service
séparé » retenue ici est purement technique (isoler des dépendances
étroitement épinglées : `torch`, `torchtune`, `torchao`, `moshi`).

**Une vraie trouvaille en comparant les deux implémentations** (mission
§8) : l'implémentation Transformers-native de CSM (préférée — maintenue,
dépendances stables) n'applique PAS le filigrane que le runtime original de
Sesame applique systématiquement — vérifié directement dans le code source
de `transformers` (zéro occurrence de « watermark »/« silentcipher »).
`tools/audio/csm_service/watermark.py` le réapplique lui-même, avec la clef
publique que Sesame publie pour ce checkpoint précis — trois refus en
cascade si le filigrane échoue, jamais un fichier sans provenance renvoyé.

**Testé en direct, dans un environnement isolé, contre le vrai service HTTP**
(pas un double) : `/health` ne charge rien avant le premier appel, confirmé
; `/generate` tente un vrai chargement Hugging Face et échoue avec le
message RÉEL d'un accès gated non authentifié (`401 Client Error`, cité tel
quel) — relayé sans déformation jusqu'au connecteur ARENA, vérifié bout en
bout. Aucun GPU ni accès HF gated disponible ici : le chargement réel du
modèle, la VRAM et la durée de génération sur la RTX A2000 cible n'ont pas
pu être mesurés — non affirmés nulle part, **limitation documentée**.

**Corrigé/créé** :

| Fichier | Changement |
|---|---|
| `core/audio/routage_tts.py` | `choisir()` gagne `langue`/`conversationnel` — CSM exclu hors anglais (son propre FAQ), préféré seulement si demandé explicitement |
| `core/audio/verification.py` (nouveau) | Extrait de `audio_voix.py` : `hote_local_ou_refuse`/`sonder_le_fichier`/`ressemble_a_du_wav`, partagés avec `csm.py` — évite la duplication que la mission interdit |
| `core/connectors/csm.py` (nouveau) | Pilote `tools/audio/csm_service/` par HTTP — aucune capacité de clonage, jamais un fichier de référence transmis |
| `agents/audio/audio_agent.py` | `_dialogue` — le SEUL endroit où les moteurs de `audio` et `csm` se rencontrent ; CSM injoignable ou en français fait retomber le choix sur VoiceStudio sans rien casser |
| `agents/video/production_agent.py` | `_appeler_narration` transmet `conversationnel`/`conversation`/`speaker` quand le plan le demande — inchangé sinon |
| `tools/audio/csm_service/` (nouveau) | Service HTTP original d'ARENA, environnement isolé, sa propre suite de tests (hors `pytest tests/` — `torch` n'y est pas installé) |
| `config/permissions_services.yaml`, `scripts/doctor.py`, `apps/backend/runtime.py` | Permissions, diagnostic (`verifier_csm`), enregistrement du connecteur |

**Délibérément pas fait** : aucun chemin de clonage vocal chez CSM (même
règle absolue que KrillinAI pour le même risque) ; aucune langue promise
au-delà de l'anglais sans mesure réelle ; le runtime original de CSM (la
version Transformers-native est préférée, filigrane réappliqué).

Trois sabotages, trois restaurations : la restriction de langue du routeur
(retirée → un test en français choisissait CSM), le refus de filigrane côté
connecteur (retiré → un fichier non filigrané gardé et déclaré succès), le
même refus côté service (retiré → un audio non filigrané partait avec un
code 200).

`ruff check .` propre. Suite complète (`python -m pytest tests/ -q`) :
4582 passed, 31 skipped, 48 deselected, 0 failed (509.25s / 8m29s, mesuré
le 10/09/2026). Suite isolée du service CSM
(`tools/audio/csm_service/test_server.py`, son propre environnement) :
11 passed.

## 2026-09-10 (suite) — Métadonnées de fichiers média (DEC-0081), exif-viewer audité

Mission ARENA × EXIF & MEDIA METADATA. `ternera/exif-viewer` audité (aucune
licence, extension Chrome — rien repris hors le vocabulaire EXIF/TIFF
standard, déjà natif dans Pillow). ARENA n'avait aucune capacité de
métadonnées avant cette session (`sonder_le_media` du montage n'extrait que
durée/dimensions, pour son propre import) : `IMPLEMENT_NEW`.

**Créé** :

| Fichier | Changement |
|---|---|
| `core/connectors/media_metadata.py` (nouveau) | `analyser` : image (Pillow, EXIF + sous-IFD GPS/Exif), vidéo/audio (`FFmpegTool`, `ffprobe`) ; accepte un chemin ou une image en mémoire (base64) |
| `agents/vision/vision_agent.py` | même patron que `_detecter_securite_chantier` : second appel déterministe, section distincte après la description libre, jamais fondu ; repli si Ollama injoignable |
| `agents/orchestrator/orchestrator_agent.py` | tuple `VISION` étendu aux phrases exactes de la mission |
| `apps/backend/runtime.py`, `config/permissions_services.yaml` | connecteur câblé, `media_metadata: read ALLOWED` (refusé par défaut sans cette entrée — trouvé et corrigé avant les tests formels) |

**Délibérément pas fait** : aucun doctor check dédié (Pillow est toujours
présent, faible valeur) ; rien d'`exif-viewer` au-delà du vocabulaire de tags
standard.

GPS jamais envoyé au réseau (vérifié : le module lui-même ne contient ni
`httpx`, ni `requests`, ni `socket`), jamais inventé quand absent — dit
explicitement (« GPS : absent du fichier »).

30 tests dédiés, réels : EXIF+GPS construits et relus par Pillow, sans EXIF,
PNG, WebP, fichier corrompu, extension mensongère détectée, EXIF malformé,
fichier volumineux, vidéo/audio réels via un vrai `ffmpeg`, image en mémoire
sans toucher le disque. Bout en bout (`POST /api/chat`) : le vrai repli sans
Ollama (mesuré, pas simulé — ce bac à sable n'en a pas non plus pour la
vision), combinaison Vision+métadonnées (seule la réponse Qwen3-VL est
simulée, `FakeProvider` — le reste est réel), GPS absent jamais inventé dans
la réponse HTTP réelle. Rapport complet → `docs/audits/exif_viewer_audit.md`.

`ruff check .` propre. Suite complète : voir le commit — chiffres mesurés
après ce changement, collés dans le message qui les rapporte.

## 2026-09-10 (suite) — Instantané de projet pour Dioumtoukay (DEC-0082), OpenContext audité

Mission ARENA × OPENCONTEXT. `0xranx/OpenContext` audité (MIT) : une
bibliothèque personnelle de notes Markdown hors dépôt, avec recherche et
serveur MCP — **aucune invalidation git-consciente, aucun état
STABLE/STALE**, vérifié par recherche exhaustive dans son code (zéro
résultat pour `git diff`/`invalidat`/`fingerprint`). L'audit d'ARENA a
trouvé un écosystème mémoire/contexte déjà mature (OpenViking, Claude
Context, Graphify, GitIngest, `recherche_unifiee.py`, `reprise.py`) et
UN manque réel, mesuré : `agents/dioumtoukay/dioumtoukay_agent.py::
_reperes()`, le seul point de départ d'une tâche de codage, ne lisait
jamais `PROJECT_MEMORY/`.

**Créé** :

| Fichier | Changement |
|---|---|
| `core/context/instantane_projet.py` (nouveau) | Lit `PROJECT_MEMORY/LOCKED_ZONES.md`+`PROJECT_MAP.md`+titres récents de `docs/DECISIONS.md`, budgété à 8000 caractères ; fraîcheur par date déclarée vs commits git réels depuis |
| `agents/dioumtoukay/dioumtoukay_agent.py` | `_reperes()` inclut l'instantané — une fois par tâche, jamais par tour |
| `core/context/recherche_unifiee.py` | 4ᵉ source `project_snapshot`, ses propres mots-clés (`MOTS_PROJET`), synchrone/locale, sans `registre` |

**Délibérément pas fait** : liens stables (UUID, idée d'OpenContext) —
valeur non démontrée pour un seul propriétaire ; fingerprints par
dossier — un mappage deviné serait faux dès qu'une convention change, un
compte de commits global reste grossier mais honnête ; banc de jetons
formel — aucun modèle joignable ici pour le mesurer réellement.

Deux sabotages, deux restaurations : le calcul de fraîcheur (mis à zéro
→ un test le détecte), l'injection dans `_reperes()` (désactivée → un
test le détecte). 30 tests dédiés/étendus, réels (dépôt git construit
pour de vrai dans chaque test de fraîcheur, jamais simulé).

**Régression trouvée et corrigée au passage** : le module `media_metadata`
de la mission précédente (DEC-0081) avait fait passer le compte de
modules d'`orphelins.py` sans que `CLAUDE.md` soit remesuré —
`test_le_compteur_de_modules_de_CLAUDE_md_est_a_jour` l'a attrapé, corrigé
dans ce commit.

`ruff check .` propre. Suite complète : voir le commit — chiffres mesurés
après ce changement. Rapport complet → `docs/audits/opencontext_audit.md`.

## 2026-09-10 (suite) — Compétences techniques dynamiques (DEC-0083), AutoSkills audité

Mission ARENA × AUTOSKILLS. `midudev/autoskills` audité (**CC-BY-NC-4.0**,
vérifié dans le `LICENSE` racine ET `packages/autoskills/package.json`) :
détection déterministe de pile, registre de 218 compétences multi-sources,
revue par modèle (`gpt-5.4`) avant approbation. Principe de détection
repris (réimplémenté en Python) ; revue par modèle rejetée (ARENA préfère
un contrôle déterministe) ; aucune ligne de code copiée (licence
non-commerciale). Aucun détecteur de pile technique n'existait dans ARENA
avant cette mission (mesuré, recherche exhaustive).

**Créé** :

| Fichier | Changement |
|---|---|
| `core/skills/detection.py` (nouveau) | Détection déterministe (paquets npm, fichiers de config, `requirements.txt`) — 11 technologies, `apps/pwa/` atteint |
| `core/skills/registry.py` (nouveau) | Schéma `skill.json`+`SKILL.md`, empreinte SHA-256, licence non-commerciale bloquée |
| `core/skills/selection.py` (nouveau) | Réutilise `core/specialistes/selection.py::_sans_accents`/`_reconnait` ; filtre projet puis tâche, plafond 3 |
| `core/skills/securite.py` (nouveau) | Réutilise `core/security/trust.py::inspect()` + motifs destructeurs propres |
| `core/skills/instantane.py` (nouveau) | Point d'entrée unique : `BLOCKED`/`OUTDATED` exclus, `REVIEW_REQUIRED` annoncé |
| `core/skills/store/` (nouveau, 7 compétences) | python-fastapi, react-typescript, tailwindcss, vite, docker, github-actions, playwright — contenu ORIGINAL |
| `agents/dioumtoukay/dioumtoukay_agent.py` | `_reperes()` prend la demande, inclut les compétences pertinentes |

**Délibérément pas fait** : aucune compétence empruntée à un tiers (218
licences à vérifier une par une, hors périmètre) ; `skills-lock.json` par
projet cible (rien à verrouiller, ARENA ne télécharge rien dans le dépôt
de l'utilisateur) ; workspace multi-niveaux façon pnpm/gradle (deux
niveaux suffisent, seul cas réel : `apps/pwa/`).

**Faux positif réel, mesuré, pas caché** : `docker`/`github-actions`/
`tailwindcss`/`vite` ressortent `REVIEW_REQUIRED` — leur contenu parle
légitimement de secrets/jetons. `REVIEW_REQUIRED` n'empêche pas l'usage,
le motif est annoncé dans le prompt.

Deux sabotages, deux restaurations : le filtre projet (technologie
absente laissée passer → 3 tests le détectent), l'exclusion `BLOCKED`
(compétence malveillante de test laissée passer → détecté). 56 tests
dédiés/étendus.

**Banc de jetons, mesuré** : 7 compétences réunies = 11 734 caractères ;
tâche React = 1 900 (-84 %) ; tâche FastAPI = 2 152 (-82 %) ; tâche
Playwright sur ce dépôt (qui n'a pas Playwright) = 0 (-100 %, exclusion
correcte). Détection+sélection : 18-23 ms.

`ruff check .` propre. Suite complète : **4704 passed, 31 skipped, 48
deselected, 0 failed** (618.05s / 10m18s). Rapport complet →
`docs/audits/autoskills_audit.md`.

## 2026-09-10 (suite) — Personnages ARENA Video (DEC-0084), Agent Heroes audité

Mission ARENA × AGENT HEROES. `agentheroes/agentheroes` audité (commit
`dd6ba3d2c7070a77fc8f1dbb190560e77dfbef5e`, **licence discordante** —
README AGPL-3.0 avec un `LICENSE` qui n'existe pas, les 4 `package.json`
disent ISC — traité comme AGPL par prudence, zéro code copié). Identité de
personnage persistante + pipeline WanGP (prompt composé) → Xaar Kaname
(remplacement de visage réel en post-traitement) : deux moteurs déjà
existants, zéro nouveau moteur de génération. `VideoProductionAgent`
(DEC-0037) déjà mature — huit capacités, `xaar_kaname` déjà câblé ; le
vrai manque était l'identité/persistance, pas la génération.

**Créé** :

| Fichier | Changement |
|---|---|
| `core/characters/registry.py` (nouveau) | Registre de personnages, même architecture que `core/skills/registry.py` ; images jamais copiées, moteur validé contre `MOTEURS_CONNUS` |
| `core/production/personnage_video.py` (nouveau) | `composer_prompt`/`soumettre_generation_image`/`appliquer_identite` — deux phases confirmées séparément |
| `apps/backend/routers/personnages.py` (nouveau) | `/api/personnages` CRUD + `/image` + `/identite` |
| `agents/video/production_agent.py` | `personnage_id` dans le contexte ; deux méthodes publiques hors graphe |
| `apps/backend/routers/video_production.py` | `personnage_id` optionnel sur `/api/video/projet` |

**Délibérément pas fait** : aucun fournisseur cloud (Replicate/RunwayML/
OpenAI/Fal.ai — ARENA reste local-first, DEC-0002) ; aucun entraînement
LoRA (rien n'est câblé nulle part dans ARENA) ; aucune UI Characters
dédiée (mission §36, l'API suffit pour l'instant) ; aucune injection dans
`core/context/instantane_projet.py`/`core/skills/` (mission §23-24, hors
du périmètre Video que la mission restreint explicitement).

**Sabotage réel, trouvé par le test sur la vraie pile (`RegistreConnecteurs`
+ `XaarKanameConnector` réels, jamais un double)** : `appliquer_identite`
ne normalisait pas la clé anglaise `status` de `ResultatAction.to_dict()`
vers `statut` — même piège que `_depuis_resultat_action` dans
`production_agent.py`, retrouvé indépendamment ici. `KeyError` sabotage →
restauré → passe.

135 tests dédiés/étendus : persistance + provenance sur un registre relu
depuis le disque (jamais l'objet en mémoire), image de référence jamais
copiée, échecs propres sans appeler le moteur sur du vide, la vraie pile
ne contourne jamais la confirmation, restart à froid réel (nouveau
processus, nouveau `USMAN_PERSONNAGES_DIR`, vraie requête HTTP).

`python scripts/orphelins.py` : 267 modules, 212 atteints (+4/+3),
`CLAUDE.md` remesuré dans ce commit.

Deuxième trouvaille réelle, par la suite complète cette fois :
`tests/test_surface_api.py` (empreinte figée des routes HTTP) a détecté
les quatre routes `/api/personnages*` absentes de sa liste — corrigé,
pas contourné.

`ruff check .` propre. Suite complète : **4751 passed, 31 skipped, 48
deselected, 0 failed** (482.83s / 8m02s). Rapport complet →
`docs/audits/agentheroes_audit.md`.

## 2026-09-10 (suite) — Génération d'image haute qualité (DEC-0085), HiDream-I1 audité

Mission ARENA × HIDREAM-I1. `HiDream-ai/HiDream-I1` audité (commit
`5f92bab45f1dfb1e794ee357286a5b837eaf4400`, **MIT** code et poids, vérifié
sur le dépôt ET les pages HuggingFace) : 17B paramètres, MoE épars, 4
encodeurs texte dont `meta-llama/Meta-Llama-3.1-8B-Instruct` (licence Llama
3.1, PAS MIT, gated). Aucune capacité image texte→image canonique
n'existait dans ARENA avant cette mission (mesuré) — WanGP ne fait que de
la vidéo (image en sous-produit, texte seul), krillin_cover délègue à un
fournisseur externe non-ARENA.

**Créé** :

| Fichier | Changement |
|---|---|
| `core/production/materiel.py` (nouveau) | VRAM (nvidia-smi) / RAM (psutil, nouvelle dépendance) / disque (stdlib) — mesurés, jamais devinés |
| `core/production/hidream_strategie.py` (nouveau) | Décision déterministe LOCAL_FULL/QUANTIZED/OFFLOAD/REMOTE_REQUIRED/UNSUPPORTED, testable sans GPU |
| `core/connectors/hidream.py` (nouveau) | Service `image_generation` (nouveau dans permissions_services.yaml), refuse avant tout envoi si le matériel ne tient pas, revalide chaque fichier annoncé par le worker |
| `core/production/artefact_image.py` (nouveau) | Validation Pillow réelle + provenance (sidecar JSON) |
| `tools/image/hidream/` (nouveau) | Worker FastAPI isolé (même catégorie que `tools/audio/csm_service/`), intégration diffusers officielle, offload CPU séquentiel par défaut |
| `agents/video/production_agent.py` | `hidream_image` dans le graphe + `generer_image` (point d'entrée direct) |
| `apps/backend/routers/image_generation.py` (nouveau) | `/api/image/generer`, `/api/image/capacites`, `/api/image/{job_id}` |

**Délibérément pas fait** : aucune quantification implémentée (aucune
n'existe en amont pour cette architecture MoE, jamais un trick non
vérifié) ; aucun worker distant déployé (contrat prêt, infrastructure non
configurée) ; aucun couplage direct Agent Heroes-personnages↔HiDream (le
router décide, jamais un point à point).

**Sabotage réel** : le rappel de validation dans
`HiDreamConnector._etat` retiré → 2 tests échouent (un « terminé » du
worker redevenait une preuve sans relecture). Restauré → 22 tests du
connecteur repassent.

257 tests dédiés/étendus sur le périmètre de cette mission, dont 14 pour
le worker qui tournent **sans torch/diffusers installés** (la couche HTTP/
gestion de tâches n'en dépend jamais directement — un choix délibérément
différent de `tools/audio/csm_service/server.py`).

`python scripts/orphelins.py` : 274 modules, 217 atteints (+7/+5),
`CLAUDE.md` remesuré. Le worker HiDream rejoint l'exemption déjà écrite
pour le service CSM.

**Classification matérielle finale (RTX A2000 12 Go, 32 Go RAM) : E —
SERVER_ONLY_RECOMMENDED**, calculée par code, jamais estimée à l'œil —
la RAM système (32 Go) est déjà plus petite que le modèle complet (~63 Go),
même avec offload. Ce n'est pas un échec de mission (§34) : l'architecture
complète refuse proprement une exécution qui échouerait, et se branche sur
un futur serveur GPU par un seul changement de variable d'environnement.

Restart test réel : nouveau processus, vraie requête HTTP,
`NEEDS_CONFIRMATION` puis `NOT_CONFIGURED` honnêtes, jamais une génération
simulée.

Deuxième trouvaille réelle, par la suite complète : `tests/
test_capacites_video_pwa.py` (déjà écrit après un incident du 03/09/2026)
a détecté `hidream_image` manquante côté interface PWA
(`videoProjectStore.ts`/`VideoProjectModal.tsx`, icône `ImagePlus` +
libellés FR/EN ajoutés) — corrigé et revérifié directement (`npx tsc
--noEmit`, `npm test` 29 tests, `npm run build`, tous verts).

`ruff check .` propre. Suite complète : **4821 passed, 31 skipped, 48
deselected, 0 failed** (476.95s / 7m56s). Rapport complet →
`docs/audits/hidream_i1_audit.md`.

## 11/09/2026 — Executive Intelligence : décision d'affaires multi-spécialiste (DEC-0086)

Mission ARENA × OPENEXECUTIVE. `SenteLabsAI/OpenExecutive` audité (commit
`fc72987537069173cb6402a1892bc03fd74f5454`, Apache-2.0) — voir
`docs/audits/openexecutive_audit.md`. Aucune capacité de finance d'affaires
n'existait (`agents/finance/finance_agent.py` est un Director de marché
crypto, pas de comptabilité de projet) ; aucun spécialiste stratégie/
marketing/RH/juridique n'existait.

**Construit** : `core/executive/` — contrat structuré (`AnalyseSpecialiste`/
`DecisionExecutive`), calcul financier déterministe (marge, échéancier,
faisabilité de délai, scénarios), classification de risque d'affaires
(réutilise `NiveauRisque` de `core/finance/risk.py`), couche de contexte
métier (lit `config/metier.yaml`, déjà générique), extraction déterministe
de chiffres, sélection dynamique de rôles (plafond 4, repli finance+risque
pour une évaluation générale), six rôles adaptateurs (finance/operations/
risque/approvisionnement/strategie_marche/ressources_humaines — chacun sur
une capacité réelle, jamais un second agent), détection structurelle du
désaccord (jamais moyenné) + synthèse + vérification déterministe des
chiffres cités. `agents/executive/executive_agent.py` (BaseAgent mince,
aucune méthode d'action). `apps/backend/routers/executive.py`
(`/api/executive/analyser`, `/api/executive/roles`). Intention `EXECUTIVE`
ajoutée à l'aiguilleur et au dispatch, testée avant `exige_verification`
(même raison que FINANCE/EMAIL). `MemoryManager.list_facts` ajouté (une
méthode, pas un second système de mémoire) pour la mémoire de décision.

**Zéro second agent-plateforme, zéro second registre/routeur/RAG/mémoire** —
voir le tableau de comparaison dans `docs/audits/openexecutive_audit.md`.

**Ce qui n'a pas été fait** : intégrations Slack/Discord/Telegram/Google
Chat (connecteurs déjà présents ailleurs) ; Graphify non câblé (aucun besoin
mesuré) ; pas de cycle d'autonomie progressive façon `decision_ledger`
d'OpenExecutive (aucune action `AUTO_EXECUTE` à graduer chez ARENA) ;
génération PDF non câblée (le moteur PDF existant de
`agents/plaquiste/devis_pdf.py` pourra recevoir la sortie structurée dans
une mission future).

**Sabotage réel** : le `wrap()` anti-injection du rôle `approvisionnement`
retiré → le test dédié échoue immédiatement (texte de document envoyé brut
au modèle). Restauré → les 15 tests du module repassent.

**Deux bugs réels trouvés et corrigés** : `extraire_jours_pres_de` rendait
le premier nombre de jours d'une fenêtre fusionnée autour d'un mot-clé
plutôt que le plus proche — « Deadline: 14 days ... possible 5-day delay »
cherché près de « delay » rendait 14 au lieu de 5. Corrigé (distance au
mot-clé, pas ordre d'apparition dans le texte), trouvé par les tests
unitaires. Un second, trouvé seulement par le test de redémarrage réel
(pas par les tests écrits d'avance) : le libellé d'une échéance capturait
les sauts de ligne et fusionnait « completion » avec la phrase suivante.
Corrigé, avec un test de non-régression dédié.

166 tests dédiés à ce périmètre, incluant le scénario synthétique exact de
la mission (chantier à 10 000 000, marge 25 % réellement calculée), les
cinq tâches de sélection de spécialistes (code et vidéo jamais détournés
vers l'Executive Intelligence), un test d'injection de prompt sur un
document contractuel piégé, un test UniC Plaquiste en lecture seule sur le
vrai `config/metier.yaml`, et des tests d'échec (rôle en panne, recherche
web indisponible, modèle indisponible, mémoire absente).

`python scripts/orphelins.py` : 288 modules, 229 atteints (+14/+12),
`CLAUDE.md` remesuré, aucun module réel endormi.

**Régression réelle trouvée par la suite complète** (pas par les tests
ciblés) : une première version enregistrait `"executive"` dans
`core/agent/capacites.py`, le registre qui ne connaît QUE les espaces de la
barre latérale de la PWA — `tests/test_runtime_capacites.py` l'a détecté.
Retiré ; l'agent reste joignable par l'intention `EXECUTIVE` et par
`/api/executive/*`.

`ruff check .` propre. Suite complète, après correction : **4991 passed,
31 skipped, 48 deselected, 0 failed** (477.21s / 7m57s).

## 11/09/2026 (suite) — ComfyUI comme moteur d'exécution alternatif (DEC-0087)

Mission ARENA × COMFYUI. `Comfy-Org/ComfyUI` audité (commit
`6338e4bd428247a4a8843496aa98fb7f2a9d3632`, GPL-3.0, clone réel — pas le
README seul) : `POST /prompt` (workflow JSON « API format »),
`GET /system_stats` (VRAM/RAM réelles par appareil), `GET /history/{id}`,
`POST /free` (décharge les modèles), gestion mémoire automatique (« smart
memory », vérifiée dans `comfy/model_management.py`). `SECURITY.md` amont
confirme noir sur blanc : les extensions tierces (`custom_nodes/`) sont du
code Python arbitraire, **aucune isolation** — zéro nœud tiers installé ici
(mission §10).

Existant réutilisé, rien dupliqué : `core/connectors/hidream.py` (DEC-0085,
seule capacité image-generation, classée `SERVER_ONLY_RECOMMENDED` sur la
RTX A2000 du propriétaire), `core/production/materiel.py`,
`core/production/artefact_image.py`, `core/connectors/registre.py`,
`config/permissions_services.yaml` (service `image_generation` déjà là).

Quatre modules nouveaux : `core/production/comfyui_workflows.py` (registre
CONTRÔLÉ de workflows — un seul `STABLE`, `text_to_image`, gabarit
reconstruit noeud par noeud depuis le JSON officiel audité ; cinq
`CANDIDATE`, schéma écrit, gabarit volontairement absent) ;
`core/production/comfyui_strategie.py` (décision matérielle à six issues,
reconnaissant le déchargement automatique de ComfyUI — contrairement à
HiDream) ; `core/connectors/comfyui.py` (connecteur HTTP direct vers l'API
native de ComfyUI — **aucun worker écrit ici**, contrairement à HiDream :
ComfyUI est déjà un serveur complet) ; `core/production/
image_backend_router.py` (choix DIRECT/COMFYUI, défaut strictement
inchangé — `hidream` en premier, repli mission §39 seulement sur
`NOT_CONFIGURED` et jamais sur demande explicite).

`agents/video/production_agent.py::_soumettre_image` (nouveau) : `generer_image`
(entrée directe) et `_appeler_hidream_image` (étape de graphe) partagent
désormais le MÊME choix de backend au lieu de deux logiques dupliquées.
`apps/backend/routers/image_generation.py` étendu (`backend`/`workflow_id`
optionnels, nouvelle route `GET /api/image/workflows`) ; `config/
permissions_services.yaml` : une action `unload` ajoutée au service
existant.

**Sabotage réel** : la vérification anti-traversée de chemin
(`_chemin_contenu`, mission §31 — un `subfolder`/`filename` annoncé par
ComfyUI ne doit jamais faire lire un fichier hors du dossier de sortie
attendu) retirée → une vraie image placée hors du dossier de base est
confirmée comme un succès légitime. Restaurée → refusée, les 27 tests du
connecteur repassent.

73 tests nouveaux : construction déterministe du JSON officiel, validation
de paramètres (bornes, coercition, champ requis vide traité comme absent),
refus avant tout envoi (workflow inconnu/`CANDIDATE`/checkpoint absent/
matériel insuffisant), relecture réelle avant de confirmer un succès, repli
bidirectionnel mission §39. Régression ciblée (vidéo, HiDream, Wan2GP,
registre d'agents, surface API) : 258 passed, 0 failed.
`python scripts/orphelins.py` : 292 modules, 233 atteints (+4/+4), aucun
module réel endormi.

**Restart test réel** : processus neuf, application importée à froid,
vraies requêtes HTTP — `GET /api/image/workflows` rend le catalogue réel ;
`GET /api/image/capacites?backend=comfyui` rend honnêtement
`NOT_CONFIGURED` (aucun serveur ComfyUI lancé ici) ; `POST /api/image/
generer` avec `backend=comfyui` route bien vers ComfyUI
(`NEEDS_CONFIRMATION`, moteur rapporté `comfyui`) ; le même appel SANS
`backend` route toujours vers `hidream` (comportement DEC-0085 inchangé).

**Régression réelle trouvée par la suite complète** (pas par les tests
ciblés) : `tests/test_connecteurs_dormants.py` (DEC-0068) a détecté
`comfyui` comme connecteur enregistré sans appelant visible en analyse
statique — le nom ne circulait que dans un tuple
(`core/production/image_backend_router.py`), jamais comme argument
littéral ou affectation nommée seule. Réellement joignable (le restart
test ci-dessus le prouve), mais invisible à l'AST : corrigé en nommant la
constante (`BACKEND_COMFYUI = "comfyui"`, motif déjà utilisé ailleurs dans
ce dépôt) plutôt que de l'ajouter à `DORMANTS_CONNUS`, ce qui aurait été
faux.

`ruff check .` propre. Suite complète, après correction : **5065 passed,
31 skipped, 48 deselected, 0 failed** (471.58s / 7m51s).

## 11/09/2026 (suite) — Les cinq workflows ComfyUI restants (DEC-0088)

Suite directe de DEC-0087, même jour. `image_to_image`, `upscale`,
`controlnet_image`, `character_image`, `image_to_video` — les cinq
workflows laissés `CANDIDATE` — construits contre le vrai code source
amont (`nodes.py`, deux modules de `comfy_extras/` — `nodes_upscale_model.py`
et `nodes_video_model.py`, non vendorés —, même commit `6338e4bd` que
DEC-0087, reconfirmé identique). Cinq gabarits promus `STABLE`, même niveau de
preuve que `text_to_image` : construits noeud par noeud contre le vrai
`INPUT_TYPES`/`define_schema`, testés déterministiquement, jamais
confirmés contre un serveur ComfyUI réel (aucun GPU ici, comme pour
`text_to_image` lui-même).

`controlnet_image` utilise `ControlNetApplyAdvanced` — jamais l'ancien
`ControlNetApply`, marqué `DEPRECATED` dans le code source. `image_to_video`
utilise Stable Video Diffusion, la seule famille vidéo native de ComfyUI
(vérifié par recherche exhaustive).

**Une image de référence ne touche jamais le disque d'ARENA** : les
workflows qui en prennent une la déclarent en `image_base64` (mêmes
octets en mémoire que `apps/backend/pieces_jointes.py`, DEC-0019) ;
`core/connectors/comfyui.py::_televerser_images` décode et televerse
(`POST /upload/image`) juste avant l'envoi — jamais un chemin de fichier
local qu'un appelant HTTP pourrait faire pointer vers un secret du
serveur (le défaut qu'`agents/plaquiste/plaquiste_agent.py
::chemin_hors_du_depot` avait dû corriger une fois ici, évité ici dès la
conception, pas filtré après coup).

`EntreeWorkflow.verification_modeles` (nouveau) généralise le contrôle
« le modèle demandé est-il installé » de DEC-0087 au-delà de `ckpt_name` —
`controlnet_image` vérifie deux modèles distincts avant tout envoi.

**Sabotage réel** : `_verifier_modeles` neutralisée → trois tests
échouent (un ControlNet absent serait accepté). Restaurée → les 85 tests
du périmètre ComfyUI repassent. 27 tests nouveaux ; deux tests devenus
obsolètes (plus aucun `CANDIDATE` réel dans le registre) remplacés par un
faux workflow injecté via `monkeypatch`, sans perdre la couverture de la
règle. Régression ciblée : 262 passed, 0 failed.

**Corrigé au passage** : un artefact de manipulation d'outil
(`</new_string>` littéral) s'était glissé à la fin de l'entrée DEC-0087 —
trouvé en relisant le fichier, corrigé.

Restart test réel : `GET /api/image/workflows` rend les SIX workflows en
`STABLE` ; les nouvelles routes passent bien par la confirmation, jamais
contournée.

**Régression réelle trouvée par la suite complète, deux fois de suite**
(pas par les tests ciblés) : `tests/test_documentation.py` vérifie que
tout chemin cité entre apostrophes inverses dans `docs/*.md` existe
réellement dans ce dépôt — `docs/DECISIONS.md` citait deux modules amont
de ComfyUI (jamais vendorés) avec leur chemin `comfy_extras/` complet.
Corrigé une première fois ; le paragraphe décrivant ce correctif a
lui-même recité le motif fautif, faisant échouer le test une seconde
fois — corrigé à son tour. Revérifié : 18 passed.

`ruff check .` propre. Suite complète, après correction : **5094 passed,
31 skipped, 48 deselected, 0 failed** (408.91s / 6m49s).

## 11/09/2026 — Tunnet (orielhaim/tuntun) audité, refusé (DEC-0089)

Demande reçue via un commentaire Reddit décrivant un dépôt permettant de
« se connecter aux agents qui tournent sur son ordinateur principal depuis
son portable ». Dépôt réel cloné et lu (pas le commentaire seul) :
`docs/audits/tunnet_audit.md`. Ce n'est pas le petit outil décrit —
c'est « Tunnet », un produit de mise en réseau maillée complet (19 crates
Rust, dashboard Node, SDK Go, apps mobile/desktop/cloud, opérateur
Kubernetes, moteur de licence commercial), `Status: In development`,
licence éclatée par composant (MPL-2.0 / **AGPL-3.0-only** sur le plan de
contrôle auto-hébergé / Apache-2.0), et le fichier `LICENSING.md` censé
trancher par fichier — cité par le `LICENSE` lui-même — absent du clone.
Aucun code Python, aucune API d'orchestration d'agents.

**Trouvaille qui a tranché** : `scripts/lancer_arena.ps1` fait déjà,
sans dépendance nouvelle, exactement ce que le commentaire décrit — lance
le serveur ARENA, ouvre un Tunnel Cloudflare Quick Tunnel, affiche
l'adresse publique en QR code pour le téléphone. Déjà dans le dépôt, déjà
utilisé. Rien câblé : intégrer Tunnet aurait dupliqué une capacité
opérationnelle avec une dépendance lourde, immature et partiellement
copyleft.
