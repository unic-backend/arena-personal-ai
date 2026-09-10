# Audit — normal-computing/fuji-web

**Dépôt étudié** : https://github.com/normal-computing/fuji-web
**Commit audité** : `66f9e6a04e85194604aa4a1b36ab1a854fdfed65` (2026-01-05)
**Licence** : Apache-2.0 (vérifiée directement dans `LICENSE`) — cohérente
avec la déclaration du README.
**Méthode** : lecture ligne à ligne de `src/state/currentTask.ts` (la
boucle), `src/helpers/dom-agent/` et `src/helpers/vision-agent/` (les deux
modes de repérage), `src/helpers/buildAnnotatedScreenshots.ts` +
`src/pages/content/drawLabels.ts` (l'annotation visuelle), `package.json`
et `jest.config.js` (dépendances, tests). Rien pris sur la seule foi du
README.

---

## Ce que le dépôt est réellement

Une **extension de navigateur Chrome** avec panneau latéral (`sidepanel`) :
elle s'installe manuellement dans le navigateur DE L'UTILISATEUR, pilote
l'onglet ACTIF qu'il a ouvert, et lui demande de coller lui-même sa propre
clé API OpenAI/Anthropic/Gemini dans le stockage du navigateur. Ce n'est
pas un service autonome headless — c'est un copilote supervisé, humain
présent devant l'écran. Architecturalement, ce n'est pas ce qu'ARENA a ni
ce dont ARENA a besoin (ARENA lance son propre Chromium headless via
`browser-use`+Playwright, sans humain présent, sans extension).

## Matrice de validation des affirmations

| Capacité | Affirmation README | Code existe | Testée (ce dépôt) | État réel |
|---|---|---|---|---|
| Navigation, extraction de page, clic, saisie | Cœur du produit | Oui, deux modes (`dom-agent`, `vision-agent`) | Lu | **IMPLEMENTED** |
| Boucle observe→plan→agit | Implicite | Oui (`src/state/currentTask.ts`) | Lu | **IMPLEMENTED**, mais bornée par un seul compteur brut (`history.length >= 50`) codé en dur dans l'UI — pas de plafond configurable, pas de détection de boucle dédiée |
| Vérification du résultat d'une action | Non affirmé, mais implicite | **Absente** — aucune étape distincte de « observer à nouveau » ; le modèle doit lui-même remarquer, au tour suivant, qu'un clic n'a rien changé | Lu | **PARTIAL** — repose entièrement sur le bon jugement du prochain appel LLM, jamais un contrôle déterministe |
| Sélection dans une liste déroulante | Non listé | **Absente** du vocabulaire d'actions (`src/helpers/vision-agent/tools.ts` : click, setValue, setValueAndEnter, navigate, scroll, wait, finish, fail) | Lu | **ROADMAP_ONLY** (« Add support for more browsing behaviors (select from dropdown...) ») |
| Extraction du contenu de toute la page | Non listé | Absente (repose sur DOM simplifié tronqué, jamais un mode « page entière ») | Lu | **ROADMAP_ONLY** |
| Workflows multi-onglets | Non listé | Absent (`currentTask.ts` ne suit qu'un seul `tabId`) | Lu | **ROADMAP_ONLY** (« Add support for more complex & cross-tab workflows ») |
| Sauvegarde/partage de workflows | Non listé | Absent | Lu | **ROADMAP_ONLY** (« Add support for saving workflows... sharing workflows ») |
| API pour Puppeteer/Playwright/Selenium | Non listé | Absent — le produit EST l'extension, rien d'exposé pour un appelant programmatique externe | Lu | **ROADMAP_ONLY** (premier point du roadmap) |
| Tests | `package.json`, `jest.config.js`, workflow CI `test.yml` | **Un seul fichier de test dans tout le dépôt** (`templatize.test.ts`, teste la simplification du DOM, pas la boucle ni le repérage) ; `"test": "exit 0"` — **la CI ne lance jamais réellement Jest** | `find . -iname "*.test.ts"` : 1 résultat ; `cat package.json` : script `test` confirmé | **BROKEN** — vert de façade |
| Repérage visuel (Set-of-Mark) | « inspired by UFO paper » | Oui, réel : capture propre → étiquettes numérotées dessinées sur la page → capture annotée → fusion des deux images → le modèle répond par un numéro (`uid`), jamais des coordonnées devinées | Lu | **IMPLEMENTED**, et c'est la meilleure idée du dépôt |
| Statuts d'exécution observables | Non affirmé | Oui, un `actionStatus` fermé (`attaching-debugger`, `pulling-dom`, `annotating-page`, `fetching-knoweldge`, `generating-action`, `performing-action`, `waiting`) | Lu | **IMPLEMENTED**, bonne convention à reprendre (adaptée, jamais copiée) |

## Ce qui est réellement réutilisable

1. **Le repérage par étiquettes numérotées (« Set-of-Mark »)** : demander au
   modèle un numéro plutôt que des coordonnées ou un sélecteur CSS devinés.
   `browser_use` (déjà dans ARENA) fait la même chose par son propre
   mécanisme d'indexation DOM — **rien à porter**, confirmé en inspectant
   `browser_use.tools.service.Tools()` : son vocabulaire d'actions réel
   (`click`, `input`, `select_dropdown`, `upload_file`, `switch`, `scroll`,
   `find_text`, `screenshot`, `save_as_pdf`, `evaluate`, `done`...) couvre
   déjà TOUT ce que Fuji-Web fait, plus le multi-onglet, le
   sélecteur-liste et l'envoi de fichier que Fuji-Web n'a que sur sa feuille
   de route.
2. **La convention d'états d'exécution concis** (`actionStatus`) : adaptée
   en `STATUTS_PAR_ACTION` (`tools/browser/browser_use_tool.py`) — jamais
   copiée, un mappage propre au vocabulaire réel de `browser_use`.
3. **Rien d'autre n'a été repris** : ni code, ni dépendances
   (`@anthropic-ai/sdk`, `openai`, `zustand`... — TypeScript, sans rapport
   avec la pile Python d'ARENA), ni l'architecture d'extension.

## Ce qui a motivé les correctifs côté ARENA

L'absence de vérification déterministe du résultat d'une action
(le défaut central de Fuji-Web) est directement ce que
`core/connectors/browser.py::classer_resultat` corrige : un succès
auto-déclaré par `browser_use` (l'agent a appelé son action `done` avec
`success=True`) n'est plus automatiquement traduit en `SUCCESS` côté
ARENA — les erreurs réellement rencontrées en route sont croisées avec
cette déclaration, et une contradiction devient un `PARTIAL`, jamais un
succès plein.

## Solana / API externe : sans objet

Contrairement à AutoHedge, Fuji-Web n'a aucune capacité d'exécution
financière ou de portefeuille — rien à classifier ici sur ce point.

## Ce qui n'a délibérément pas été repris

- **L'extension de navigateur elle-même** : ARENA n'a besoin d'aucune
  interface installée dans le navigateur du propriétaire — son moteur est
  déjà headless et autonome.
- **Le stockage d'une clé API dans le navigateur** : ARENA n'a pas de
  navigateur "à l'utilisateur" dans ce sens ; ses clés vivent dans `.env`,
  jamais dans un `chrome.storage`.
- **Le vocabulaire d'actions fermé de Fuji-Web** : `browser_use` en offre
  déjà un plus riche, installé et testé dans ARENA depuis le 04/09/2026.
