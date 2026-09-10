# Audit — midudev/autoskills

**Dépôt étudié** : https://github.com/midudev/autoskills
**Commit audité** : `0ec725320d2137253ab2e68e7ba8a072148e741a` (17/07/2026,
tête du dépôt au 10/09/2026).
**Licence** : **CC-BY-NC-4.0** — vérifiée à DEUX endroits, pas un seul :
le `LICENSE` racine du site vitrine (`autoskills.sh`, Astro) **et**
`packages/autoskills/package.json` (`"license": "CC-BY-NC-4.0"`), le paquet
npm réellement publié (`autoskills`, `bin: autoskills`). **Non-commerciale**
— ARENA sert UniC Plaquiste, une activité commerciale réelle (DEC-0002 et
suivants) : **aucune ligne de code n'a été copiée**, et le paragraphe
« Licensing » ci-dessous explique pourquoi la question ne s'est même pas
posée pour le contenu produit ici.
**Méthode** : clone réel, lecture directe de `lib.ts` (704 lignes),
`installer.ts` (786 lignes), `main.ts`, `skills-registry/index.json`
(218 entrées). Rien pris sur la seule foi du README.

---

## Ce que le dépôt est réellement

Un CLI Node.js (`autoskills`, alias `oc`... non, alias direct `autoskills`)
qui : détecte les technologies d'un projet par preuve déterministe
(`detectTechnologies`, `lib.ts:560`), sélectionne les compétences
pertinentes dans un registre de **218 entrées** agrégées depuis de
nombreuses sources amont (`vercel-labs/agent-skills`,
`vercel-labs/next-skills`, et bien d'autres — `source` par entrée, jamais
un seul auteur), les télécharge dans un cache local content-addressé
(clé = `bundleHash`), vérifie leur intégrité par SHA-256 avant application,
et enregistre ce qui est installé dans `skills-lock.json` (à la racine du
PROJET, pas du registre).

## Matrice de validation

| Capacité annoncée | Vérifié comment | État |
|---|---|---|
| Détection déterministe (pas de modèle) | `lib.ts:493-545` : `packages`/`packagePatterns`/`configFiles`/`fileExtensions`/`gems`/`configFileContent`, tout par preuve de fichier | **IMPLEMENTED** |
| Support monorepo/workspace | `resolveWorkspaces` (pnpm-workspace.yaml, gradle, .NET) | **IMPLEMENTED**, plus large que le besoin réel d'ARENA |
| Compétences combinées (« react + threejs ») | `detectCombos`, `COMBO_SKILLS_MAP` | **IMPLEMENTED** |
| Intégrité par empreinte | `installer.ts` : SHA-256 par fichier + `bundleHash` global, comparés avant toute écriture | **IMPLEMENTED** |
| Fichier de verrouillage projet | `skills-lock.json`, écrit par `installer.ts:446-466` | **IMPLEMENTED** |
| Revue de sécurité par compétence | `review.model: "gpt-5.4"`, `status: "approved"`, `flags: []` dans `index.json` — **un modèle juge**, pas un contrôle déterministe | **IMPLEMENTED, mécanisme rejeté ici** (voir Décision) |
| Provenance multi-source | `source`/`skillPath`/`commitSha` par entrée — 218 compétences, PAS toutes de midudev | **IMPLEMENTED** — et donc 218 licences potentiellement distinctes, jamais vérifiées une par une ici |

## Ce qui est réellement réutilisable (idées, jamais code)

1. **Détection déterministe multi-preuve** (paquet déclaré, fichier de
   config présent, sous-chaîne dans un fichier de config connu) — idée
   reprise, réimplémentée en Python propre à ARENA
   (`core/skills/detection.py`), sur un catalogue volontairement restreint
   (11 technologies réellement pertinentes ici, pas 218 dont la plupart —
   Terraform, Rails, Swift — n'ont aucun chemin d'exécution dans ce dépôt,
   même règle que `core/specialistes/catalogue.py` règle 1).
2. **Compétences combinées** — repris (`core/skills/detection.py::COMBOS`),
   un seul exemple réel pour l'instant (`react-vite-typescript`, la pile
   d'`apps/pwa/`).
3. **Empreinte + verrou** — le PRINCIPE (calculer une empreinte, la
   comparer, détecter l'altération) est repris ; le SCHÉMA JSON est propre
   à ARENA (`skill.json` par compétence, `sha256_skill_md`), jamais copié
   de `skills-registry/index.json`.
4. **Revue avant confiance** — le principe (rien n'est `TRUSTED` sans
   contrôle) est repris ; **le mécanisme est rejeté** — voir Décision.

## Ce qui n'a délibérément pas été repris

- **Le code TypeScript lui-même** — licence non-commerciale, voir plus
  haut. Aucune ligne.
- **Le registre de 218 compétences** — mission §13 : « ARENA must NOT
  blindly discover random GitHub repositories and install their
  instructions ». Chaque entrée a sa PROPRE licence amont (`source` varie
  : `vercel-labs/*`, etc.) que ni le registre CC-BY-NC ni cet audit ne
  vérifient une par une — 218 vérifications de licence indépendantes
  dépassent le périmètre de cette mission. **`IMPLEMENT_NEW`** : sept
  compétences ORIGINALES, écrites pour ARENA, dont la licence ne se
  discute pas (voir Licensing).
- **La revue par modèle** (`gpt-5.4`) — ARENA préfère partout un contrôle
  déterministe quand il peut remplacer un jugement de modèle
  (`tools/video/prompt_audit.py`, `core/security/trust.py` lui-même) : un
  modèle qui juge un texte conçu pour tromper un modèle est le cas
  précisément le plus faible pour cette préférence.
- **`skills-lock.json` comme fichier séparé dans le dépôt cible** —
  inutile ici : ARENA ne « télécharge » ni n'« installe » de compétence
  dans le dépôt de l'utilisateur, il les lit depuis son propre registre à
  chaque tâche. Rien à verrouiller côté projet cible.
- **L'app Desktop/l'interface CLI interactive** — hors périmètre (mission
  « ARENA doit savoir quelle compétence charger », jamais « ARENA doit
  avoir un CLI d'installation »).

## Décision : le registre est neuf, la sélection s'appuie sur l'existant

Avant d'écrire une ligne, l'audit d'ARENA (`core/specialistes/`,
`.claude/skills/design-language/`, `core/context/instantane_projet.py`,
`agents/dioumtoukay/dioumtoukay_agent.py`, `agents/repo_engineer/
repo_engineer_agent.py`) a confirmé qu'aucun système existant ne couvre la
détection de pile technique ni une connaissance par TECHNOLOGIE :

| Capacité (mission §18) | ARENA existant | Décision |
|---|---|---|
| Méthode par métier (sécurité, tests, architecture…) | `core/specialistes/` — 14 domaines, mots-clés, max 2 | **KEEP_ARENA**, jamais touché — granularité différente (métier, pas technologie) |
| Compétence de développement pour CET assistant | `.claude/skills/design-language/` | **KEEP_ARENA**, jamais touché — consommé par Claude Code, pas par le runtime ARENA |
| Instantané de projet (PROJECT_MEMORY) | `core/context/instantane_projet.py` (DEC-0082) | **KEEP_ARENA**, réutilisé comme précédent d'intégration dans `_reperes()` |
| Détection de pile technique | **ABSENT — mesuré** (aucun `package.json`/`pyproject.toml` sondé nulle part dans `core/`/`agents/`/`tools/`) | **IMPLEMENT_NEW** (`core/skills/detection.py`) |
| Sélection projet+tâche, mots pondérés | `core/specialistes/selection.py::_sans_accents`/`_reconnait` | **RÉUTILISÉ DIRECTEMENT** (import, pas de copie) dans `core/skills/selection.py` |
| Frontière donnée/consigne pour un texte externe | `core/security/trust.py::inspect()` | **RÉUTILISÉ DIRECTEMENT** dans `core/skills/securite.py` |
| Registre de compétences technologiques, avec intégrité/licence | **ABSENT** | **IMPLEMENT_NEW** (`core/skills/registry.py`) — schéma propre, contenu original |

**Un seul registre canonique** (`core/skills/`), branché à Dioumtoukay au
même point que l'instantané de projet (`_reperes()`) — jamais un second
système d'orchestration, jamais un second agent par compétence (mission
« DO NOT create another agent »).

## Sécurité — le cas réel mesuré, pas hypothétique

Le scanner déterministe (`core/skills/securite.py`, motifs propres +
`core/security/trust.py::inspect()`) a produit un vrai faux positif dès le
premier passage sur les sept compétences écrites pour cette mission :
`docker`, `github-actions`, `tailwindcss` et `vite` ressortent
`REVIEW_REQUIRED` — leur contenu PARLE légitimement de secrets/jetons
(« Secrets come from the environment, never hardcoded »). Vérifié :
`python-fastapi`, `react-typescript`, `playwright` ressortent `TRUSTED`.
**Aucune n'est `BLOCKED`** : le contenu ne contient aucun motif destructeur
(`rm -rf`, script distant exécuté en pipe, exfiltration). `REVIEW_REQUIRED`
n'empêche pas l'usage — le motif est annoncé dans le prompt, jamais caché
(voir `core/skills/instantane.py`). Une compétence de test contenant une
vraie injection + `rm -rf /` (utilisée dans `tests/core/
test_skills_securite.py` et `test_skills_registry.py`) ressort bien
`BLOCKED` et n'atteint jamais `competences_utilisables()`.

## Licensing — vérifié au moment de l'implémentation, comme demandé

Les sept compétences de `core/skills/store/` sont un texte ORIGINAL écrit
pour cette mission (aucune phrase copiée d'AutoSkills, dont le contenu
technique lui-même n'a jamais été lu au-delà de la structure `lib.ts`/
`installer.ts`/`index.json`). `licence: "ARENA (original)"`,
`source: "ARENA"` dans chaque `skill.json`. Le champ `licence` du schéma
est néanmoins appliqué : `EtatCompetence.etat` (`core/skills/registry.py`)
bloque toute compétence future dont la licence commence par `CC-BY-NC`,
`PROPRIETARY` ou `UNLICENSED`, **avant même** le contrôle de sécurité —
testé (`tests/core/test_skills_registry.py::TestLicence`).

## Ce qui reste `SUGGESTION — NON IMPLÉMENTÉE`

- **Un registre de compétences empruntées à des tiers**, façon AutoSkills.
  Chaque entrée demanderait sa propre vérification de licence
  indépendante (mission §12, dernier paragraphe) — hors périmètre de
  cette mission, dont l'objectif était l'INFRASTRUCTURE, pas le contenu.
- **`skills-lock.json` par projet cible** — voir plus haut, aucun besoin
  réel identifié.
- **Workspace multi-niveaux façon pnpm/gradle/.NET** — `core/skills/
  detection.py` sonde deux niveaux (suffisant pour `apps/pwa/`, le seul
  cas réel de ce dépôt) ; une récursion générale n'a aucun cas d'usage
  mesuré ici.
- **Mise à jour incrémentale d'une compétence existante** (mission §14,
  « NEW VERSION → inspect diff → … → promote ») : `version` existe dans
  le schéma, mais aucun mécanisme de diff/promotion n'a été construit —
  sept compétences à un seul auteur (ARENA lui-même) n'ont pas encore
  produit de cas réel de mise à jour à arbitrer.
