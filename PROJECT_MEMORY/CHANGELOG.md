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
