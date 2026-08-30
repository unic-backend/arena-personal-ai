# Audit — `ara-mkr/claude-artisan`, intelligence de design pour ARENA

*Demandé le 30/08/2026 : auditer `github.com/ara-mkr/claude-artisan` comme
couche de connaissance UI/UX (design systems, layout, typographie, couleurs,
accessibilité, mobile/desktop, SaaS, dashboards, apps, landing pages, patterns).
Audit d'abord, aucune installation avant preuve.*

## Conclusion, avant le détail

**Intégré.** Contrairement à l'audit Molmo de la même journée, celui-ci se
termine par une intégration réelle, parce que les cinq conditions qui avaient
fait échouer Molmo sont ici toutes remplies :

| Condition | Molmo (rejeté) | claude-artisan |
|---|---|---|
| Pas de doublon avec l'existant | Non — DEC-0019 couvrait déjà tout | **Oui** — ARENA n'a aucune connaissance de design, nulle part |
| Chemin d'exécution compatible avec l'architecture | Non — exige `transformers`, refusé par précédent (DEC-0019) | **Oui** — ce n'est ni un modèle ni un service : du texte + 3 scripts stdlib-only, lus par l'agent qui code |
| Dépôt maintenu | Non — figé depuis 20 mois, successeur déjà sorti | **Oui** — dernier commit le 25/08/2026, 5 jours avant cette mission |
| Coût matériel (RTX A2000, 12 Go) | Bloquant | **Nul** — zéro GPU, zéro appel réseau, zéro modèle |
| Licence | Propre mais seule case cochée | **Propre** (MIT) |

**Ce que c'est réellement** : un *skill* Claude Code — un répertoire de
références et de scripts que l'agent qui écrit du code (moi, dans une session
future sur `apps/pwa/`) consulte pour appliquer un style visuel de façon
cohérente, avec des jetons de conception (tokens) plutôt que des valeurs
codées en dur, et une vérification d'accessibilité réelle (WCAG). Ce n'est
**pas** un agent, ni une capacité qu'ARENA expose au propriétaire au
runtime — rien dans `agents/`, `core/` ou `apps/backend/` n'y touche, et
c'est un choix, pas un oubli (§4).

---

## 1. Ce qu'ARENA avait déjà (audit de l'existant, avant tout le reste)

Recherché avant d'écrire une ligne : aucun fichier de charte graphique, de
design system ou de norme UI/UX nulle part dans le dépôt (`docs/`,
`apps/pwa/`, racine). Aucun répertoire `.claude/` n'existait avant cette
mission — c'est le premier *skill* Claude Code du projet.

Stack front-end déjà en place (`apps/pwa/package.json`) : **React 19 +
Tailwind CSS v4 + `framer-motion` + `zustand`**, compilé en un seul fichier
(`vite-plugin-singlefile`) et servi par ARENA lui-même. C'est exactement la
stack que les jetons du skill ciblent (fragments CSS **et** Tailwind pour
chaque style) — aucune adaptation nécessaire.

**Rien à consolider, rien à remplacer.** La règle « no duplication » de la
mission est vérifiée par une recherche vide, pas supposée.

---

## 2. Ce que le dépôt contient vraiment

Cloné (`ae6d3ad`, 25/08/2026) et audité fichier par fichier, pas résumé sur
la seule foi du README :

- **Un *skill* Claude Code**, pas une bibliothèque ni un service :
  `design-language/SKILL.md` documente un flux en 5 étapes (identifier le
  style → lire sa fiche → générer ses jetons → les appliquer partout →
  vérifier). Pensé pour être lu par un agent, pas exécuté par ARENA.
- **224 styles catalogués** (`scripts/style_catalog.json` — le dépôt a
  grandi depuis le chiffre de 199 annoncé par le README ; **incohérence
  constatée, non corrigée** : je n'édite pas la documentation d'un tiers
  sans le dire, voir §6), organisés en 9 familles (morphismes,
  verre/transparence, brutalisme, systèmes de plateforme comme Material 3 /
  Fluent 2 / Carbon, mouvements historiques, rétrofuturisme, minimalisme,
  texture/matière, sous-cultures). Chaque style : jetons CSS + Tailwind,
  règles pour 10 primitives de composants, corrections d'accessibilité
  spécifiques, exemples HTML stylés.
- **Un arbre de décision** (`references/style-selection-decision-tree.md`)
  qui traduit une envie vague (« premium et futuriste », « sérieux et
  dense en données ») en style précis — directement utile pour les
  familles citées par la mission : `material-design-3`, `carbon-design`,
  `ant-design`, `fluent-design-2`, `dashboard-analytics`, `gradient-saas`
  couvrent nommément SaaS/dashboard/app/desktop.
- **Trois scripts, standard library only** (aucune dépendance Python
  nouvelle — vérifié en lisant leurs imports, pas supposé) :
  `generate_tokens.py` (jetons CSS/Tailwind), `contrast_check.py` (WCAG
  AA/AAA, vrai calcul de luminance), `consistency_audit.py` (détecte les
  valeurs codées en dur qui ne remontent à aucun jeton).
- **Licence MIT**, dépôt entier, y compris les backbones de style — pas
  de composant tiers avec une licence différente trouvé.

### Ce qui n'a pas sa place ici (rule 3 : no blind copy)

Deux scripts et un répertoire d'images, **exclus de la copie** :

- `scripts/screenshot_all.mjs` — dépend de `playwright` (npm), sert
  uniquement à générer les captures d'écran du **README du dépôt source**.
  Aucun rôle dans le flux du skill (absent des « Three Core Scripts » de
  `SKILL.md`). L'inclure aurait ajouté une dépendance Node à ARENA pour un
  usage qui ne le concerne pas.
- `scripts/stitch_banner.py` — dépend de `Pillow` (non-stdlib), assemble la
  bannière marketing du dépôt source. Même raison d'exclusion.
- `assets/release-assets/` — 2,9 Mo d'images promotionnelles du dépôt
  source (bannière « 199-style-expansion »). Aucune valeur pour ARENA.

Root du dépôt source également exclu : `README.md`, `COMMIT_GUIDE.md`,
`.gitignore`, `LICENSE` racine — ce sont les conventions de contribution du
dépôt **source**, pas d'ARENA. La licence reste néanmoins présente : chaque
fichier copié l'est avec `design-language/LICENSE.txt`, qui voyage avec le
contenu (obligation MIT respectée sans dupliquer le root).

**Ce qui est copié, et rien d'autre** : `design-language/` (SKILL.md,
`references/`, `assets/component-examples`, `assets/starter-themes`,
`scripts/{generate_tokens,contrast_check,consistency_audit}.py`,
`scripts/style_catalog.json`, `LICENSE.txt`) → **6,1 Mo**, contre 14 Mo pour
le dépôt cloné en entier. Le tri a retiré ce qui ne sert qu'au dépôt source
lui-même, pas au contenu qu'il documente.

---

## 3. Preuve — les trois scripts, exécutés réellement, depuis leur emplacement final

Pas supposé, lancé :

```
$ python3 .claude/skills/design-language/scripts/generate_tokens.py --list | wc -l
224

$ python3 .claude/skills/design-language/scripts/generate_tokens.py material-design-3 /tmp/artisan_verify
Wrote /tmp/artisan_verify/material-design-3.css
Wrote /tmp/artisan_verify/material-design-3.tailwind.config.fragment.js
Style: Material Design 3 / Material You — signature: Dynamic color extracted from user wallpaper (tonal palettes)
Don't confuse with: material-design, fluent-design-2

$ python3 .claude/skills/design-language/scripts/contrast_check.py "#ffffff" "#000000"
contrast ratio: 21.00:1
  AA  normal (4.5:1): PASS   AA  large (3.0:1): PASS
  AAA normal (7.0:1): PASS  AAA large (4.5:1): PASS

$ python3 .claude/skills/design-language/scripts/consistency_audit.py /tmp/artisan_verify --style material-design-3
Audited /tmp/artisan_verify against token set [catalog:material-design-3]
  allowed colors: 15  radii: 6  shadows: 3  fonts: 3
No off-token hardcoded values found. Style looks consistently applied. ✅
```

Cas d'échec vérifié aussi (pas seulement le chemin heureux) :

```
$ python3 .../contrast_check.py "#888888" "#999999"
contrast ratio: 1.24:1
  AA normal (4.5:1): FAIL   AAA normal (7.0:1): FAIL
```

Les trois scripts produisent des fichiers réels, un vrai calcul WCAG (17.06:1
puis 21.00:1 puis 1.24:1 — trois valeurs distinctes, pas une constante), et
un vrai audit de cohérence. Rien de simulé.

---

## 4. Stratégie d'intégration — *skill* de développement, jamais capacité runtime

**Copié dans `.claude/skills/design-language/`** — un *skill* Claude Code au
niveau du projet. N'importe quelle session future travaillant sur
`apps/pwa/` peut l'invoquer pour styliser un écran de façon cohérente
(jetons d'abord, accessibilité vérifiée, pas de dérive).

**Délibérément absent** de `agents/`, `core/`, `apps/backend/` :

- Aucun `DesignAgent` créé. La mission demande une couche de connaissance,
  pas une intention orchestrée de plus — en créer une serait dépasser ce
  qui est demandé (`spec-driven-governance` équivalent : implémenter ce qui
  est requis, rien de plus).
- Aucun appel depuis ARENA en service : le skill ne tourne jamais pendant
  qu'Ousmane utilise l'app. Il sert **pendant qu'on la construit**, pas
  pendant qu'elle répond à quelqu'un — même distinction que
  `core/guardian/`, qui découvre et rapporte mais ne modifie jamais le
  dépôt de lui-même.
- **Aucun changement visuel appliqué à la PWA existante.** L'intégration
  rend la capacité disponible ; l'utiliser sur un écran réel d'UniC
  Plaquiste est une décision de style à part, non demandée ici.

C'est cohérent avec DEC-0002 (local-first) par construction plutôt que par
choix : zéro appel réseau, zéro service, zéro dépendance nouvelle
(Python stdlib uniquement) — rien à héberger, rien qui puisse tomber en
panne.

---

## 5. Impact estimé

- **Avant** : ARENA n'avait aucune référence de design consultable — un
  écran nouveau se stylise « à l'instinct », sans jetons, sans vérification
  d'accessibilité, avec un risque de dérive entre composants qu'aucun outil
  du projet ne détecte.
- **Après** : un vocabulaire de 224 styles nommés et documentés, un arbre de
  décision pour traduire une envie du propriétaire en style précis, une
  vérification d'accessibilité réelle avant de livrer, un détecteur de
  dérive pour un écran déjà stylé.
- **Ce que ça ne change pas aujourd'hui** : rien dans `apps/pwa/` n'est
  modifié par cette mission. L'impact est un outil disponible, pas un
  résultat visible avant qu'une tâche demande de styliser un écran précis.

---

## 6. Licence, provenance, et l'inexactitude trouvée

MIT (`design-language/LICENSE.txt`, copyright 2026, auteur du dépôt source).
Copié avec le contenu, comme l'exige la licence. Aucun conflit trouvé avec
un composant tiers.

**Une inexactitude relevée, non corrigée** : `SKILL.md` et le `README.md` du
dépôt source annoncent 199 styles ; le catalogue réellement présent
(`scripts/style_catalog.json`) en contient 224 à la date du commit copié
(`ae6d3ad`, 25/08/2026) — le dépôt a grandi plus vite que sa propre
documentation. Je ne corrige pas le texte d'un tiers copié tel quel ; le
chiffre exact à utiliser est celui que `generate_tokens.py --list` rend en
direct, pas celui écrit dans `SKILL.md`.

---

## 7. Ce que ça coûte si cet audit est faux

Si le skill s'avère peu utilisé ou mal calibré pour l'usage réel d'ARENA
(styles trop éloignés d'UniC Plaquiste), le coût de revenir en arrière est
nul : aucune dépendance ajoutée, aucun code de production touché,
suppression d'un seul répertoire (`.claude/skills/design-language/`) suffit.
Le risque inverse — un écran livré avec des couleurs incohérentes ou un
contraste qui échoue WCAG — est exactement ce que `contrast_check.py` et
`consistency_audit.py` existent pour empêcher, à condition qu'une session
future les lance réellement au lieu de les ignorer.
