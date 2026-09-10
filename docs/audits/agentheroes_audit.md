# Audit — agentheroes/agentheroes

**Dépôt étudié** : https://github.com/agentheroes/agentheroes
**Commit audité** : `dd6ba3d2c7070a77fc8f1dbb190560e77dfbef5e` (tête du dépôt
mesurée le 10/09/2026).
**Licence** : **discordance non résolue, documentée plutôt que tranchée
arbitrairement.** `README.md` affiche « AGPL-3.0 » et pointe vers un fichier
`LICENSE` — qui **n'existe nulle part dans le dépôt** (`find . -iname
"LICENSE*"` : vide, `ls -la` racine confirmé). Les QUATRE `package.json`
réels (racine, `apps/frontend`, `apps/backend`, `apps/workers`) déclarent
tous `"license": "ISC"`. Aucun des deux n'est pris pour argent comptant :
**zéro code copié**, traitement identique à un dépôt AGPL confirmé (même
prudence que `docs/DECISIONS.md` DEC-0083 sur AutoSkills, CC-BY-NC-4.0).
**Méthode** : clone réel, lecture directe de `generation.base.interface.ts`
(52 lignes), `schema.prisma` (modèles complets), les quatre providers de
génération, la structure `apps/`/`packages/` à profondeur 3. Rien pris sur
la seule foi du README.

---

## Ce que le dépôt est réellement

Un monorepo Turborepo/pnpm : `apps/frontend` (Next.js), `apps/backend`
(API + services), `apps/workers` (traitement de fond). Persistance Postgres/
Prisma (`packages/backend/database/prisma/schema.prisma`) : `User`,
`Organization`, `UserOrganization`, `Models` (LoRA/checkpoints entraînés),
`Characters`, `Media`, `Channels`, `Posts`, `SocialAuth`, `Agent`,
`AgentStep`. File de fond BullMQ/Redis (`packages/backend/redis`,
`packages/backend/bull-mq-transport-new`). Génération via **quatre
fournisseurs CLOUD, et aucun local** : `replicate`, `runwayml`, `openai`,
`fal` (`packages/backend/generations/providers/*.provider.ts`), tous
implémentant le même contrat (`generation.base.interface.ts`) :
`generateImage`, `generateVideo`, `testConnection`,
`generateLookALikeImages` (conditionnement par référence, sans
entraînement), `trainImages` + `generateInferenceImage` (LoRA complet),
`generateText`, un catalogue `models: ModelEntry[]` par fournisseur.

## Matrice de validation

| Capacité annoncée | Vérifié comment | État |
|---|---|---|
| Personnages persistants et réutilisables | Modèle Prisma `Characters` (lié à `Media`) | **IMPLEMENTED** |
| Cohérence par référence sans entraînement | `generateLookALikeImages` dans les 4 providers | **IMPLEMENTED**, cloud uniquement |
| Entraînement LoRA | `trainImages` + `generateInferenceImage`, résultat stocké dans `Models` | **IMPLEMENTED**, cloud uniquement — aucun chemin local/auto-hébergé |
| Génération image/vidéo | `generateImage`/`generateVideo` par provider | **IMPLEMENTED**, cloud uniquement |
| Planification/file de fond | BullMQ + Redis (`packages/backend/scheduler/providers`) | **IMPLEMENTED** |
| Édition post-génération | Absente de ce périmètre (pas de moteur de montage propre trouvé dans `apps/backend`) | **NOT_PRESENT** |
| Post-traitement de visage type face-swap | Absent — la « cohérence » vient du PROMPT/référence envoyé au fournisseur cloud, jamais d'un remplacement de visage local | **NOT_PRESENT** |
| Option locale/auto-hébergée | Aucune — les quatre providers sont des API payantes | **NOT_PRESENT** |

## Ce qui est réellement réutilisable (idées, jamais code)

1. **La distinction `generateLookALikeImages` (référence, pas d'entraînement)
   vs `trainImages`+`generateInferenceImage` (LoRA complet)** — idée reprise
   pour cadrer ce qu'ARENA peut honnêtement offrir aujourd'hui : ARENA n'a NI
   l'un NI l'autre nativement (WanGP ne prend qu'un texte), donc le choix
   fait ici n'est ni l'un ni l'autre au sens Agent Heroes — voir Décision.
2. **Un enregistrement de personnage séparé des médias qu'il produit**
   (`Characters` référence `Media`, jamais l'inverse) — repris dans
   `core/characters/registry.py` (`historique` d'un personnage référence
   des fichiers, jamais la relation inverse).
3. **Un contrat de provider uniforme** (`generation.base.interface.ts`) —
   **PAS repris** : ARENA a déjà `core/connectors/base.py::Connecteur`, une
   abstraction équivalente et plus stricte (permission → confirmation →
   santé → quota → hooks), déclarée AVANT cette mission. Un second contrat
   de provider aurait été exactement la duplication que la mission interdit
   (§4).

## Ce qui n'a PAS été repris, et pourquoi

- **Les quatre providers cloud eux-mêmes** : ARENA reste local-first
  (DEC-0002 et suivants). Aucune clé API, aucun compte Fal.ai/Replicate/
  RunwayML/OpenAI n'existe dans cet environnement — en ajouter un aurait
  créé une dépendance non fonctionnelle plutôt qu'une capacité.
- **L'entraînement LoRA (`trainImages`)** : aucun chemin d'entraînement
  n'existe nulle part dans ARENA aujourd'hui, local ou distant. Mission §7 :
  étudié, non reproduit — reproduire une implémentation cloud-spécifique
  aurait rendu ARENA dépendante d'un fournisseur pour une capacité que rien
  ici ne peut honnêtement offrir.
- **BullMQ/Redis** : ARENA a déjà une file de travaux de fond
  (`core/execution/travaux.py`, utilisée par `suivre_generation`/
  `suivre_la_generation` depuis la mission WanGP). L'ajouter aurait été un
  second système de file pour un besoin déjà couvert — mission §19-20.
- **Le schéma Prisma `Characters`** : ARENA n'a pas de base Postgres/ORM
  central pour ce genre d'entité ; `core/skills/registry.py` (mission
  AutoSkills, DEC-0083) est le précédent le plus proche déjà dans ce dépôt
  pour une entrée structurée + provenance + fichier, et c'est lui qui est
  repris (voir `docs/DECISIONS.md` DEC-0084) — pas le schéma Prisma.

## Ce que la mission demande d'exposer honnêtement (§6)

Agent Heroes obtient sa cohérence de personnage **via le fournisseur cloud
lui-même** (conditionnement par référence ou LoRA, côté serveur du
fournisseur). ARENA n'a accès à AUCUN des deux mécanismes : WanGP
(`core/connectors/wan2gp.py`) n'accepte qu'un `source` texte, sans image ni
seed ni embedding. La réponse retenue ici (DEC-0084) n'imite donc PAS Agent
Heroes : elle compose un prompt riche (texte) pour la génération, puis
applique un remplacement de visage RÉEL et mesurable (Xaar Kaname/Deep-Live-
Cam) en post-traitement — une garantie plus faible qu'un vrai conditionnement
amont, dite comme telle plutôt que présentée comme équivalente.

## Ce que ça coûte si c'est faux

Le pipeline personnage d'ARENA dépend de deux moteurs externes non installés
sur cette machine (WanGP, Deep-Live-Cam) : chaque test réel de ce périmètre
rapporte honnêtement `NEEDS_CONFIRMATION`/`NOT_CONFIGURED` plutôt qu'un
artefact produit — voir `docs/DECISIONS.md` DEC-0084, section Vérification.
Si un jour WanGP expose un vrai paramètre de conditionnement par image, la
composition de prompt de `core/production/personnage_video.py` restera
correcte mais incomplète : elle n'utilisera pas ce nouveau paramètre tant
que ce module n'est pas explicitement mis à jour pour le lire.
