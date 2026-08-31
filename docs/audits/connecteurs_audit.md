# Audit des connecteurs — 31/08/2026

Demande du propriétaire, dans ses mots : « CONNECTORS & REAL INTEGRATIONS —
MAKE EVERY CONNECTOR ACTUALLY OPERATIONAL ». Signalé concrètement : cliquer
sur Gmail dans l'interface ne terminait jamais la connexion.

Ce document trace ce qui a été trouvé (mesuré, pas deviné), ce qui a été
construit (DEC-0024), et ce qui reste — pour chaque service demandé, la
raison précise pour laquelle il n'est pas construit et ce qu'il faudrait
pour qu'il le soit.

## 1. Ce que l'audit a trouvé

Le chemin tracé du bouton « Connecter » jusqu'à l'API du fournisseur,
composant par composant :

| Composant | Ce qui existait avant ce chantier |
|---|---|
| `apps/pwa/src/components/chat/ConnectorsModal.tsx` | Interface complète — 17 connecteurs affichés, boutons « Connecter » fonctionnels visuellement |
| `apps/pwa/src/lib/store/connectorStore.ts` | `startOAuth()` appelait `${backend}/connectors/{id}/auth?key=...` |
| `apps/backend/main.py` | **Aucun routeur `connectors` monté.** 7 routeurs seulement (`openai_gateway`, `media`, `chat`, `actions`, `gardien`, `pwa_gateway`, `conversations`) |
| `core/connectors/google_oauth.py` | Échange `refresh_token` → `access_token` seulement. Aucun code pour initier le consentement ni recevoir un `code` d'autorisation |
| `core/connectors/gmail.py` | Complet et testé : lister, chercher, lire, envoyer (verrouillé derrière confirmation) — **mais inatteignable sans jeton, et rien n'obtenait de jeton** |

Trois causes cumulées, chacune suffisante seule à tout bloquer :

1. La route `/connectors/*` n'existait nulle part côté serveur — un `fetch()`
   vers elle recevait 404, quand il partait (voir 3).
2. Même avec la route, aucun code ne savait construire l'URL de consentement
   Google ni échanger le `code` de retour contre des jetons.
3. `activeRemoteCfg()` (`backendStore.ts`) est vide par défaut — ARENA
   n'est **pas** son propre « backend distant » tant que le propriétaire n'a
   pas rempli une URL à la main dans un écran de réglages. Sans ça,
   `startOAuth()` retournait `false` immédiatement, sans requête réseau du
   tout et sans le dire.

**Le catalogue affiché ne correspondait pas au backend réel.** 17
connecteurs dans `catalog.ts` (Gmail, Calendar, Drive, Notion, GitHub,
GitLab, Jira, Linear, X, LinkedIn, WhatsApp, HTTP, RSS, Slack, Salesforce,
HubSpot, Postgres) contre 8 dans `core/connectors/` (`wan2gp`, `galsen`,
`opentakeoff`, `gmail`, `google_oauth`, `moneyprinter`, `devis`,
`calendrier`). Un seul nom se recoupait : Gmail. Les 13 autres (Drive
inclus) n'avaient et n'ont toujours **aucun** code backend — aucune API,
aucune capacité déclarée, rien.

**Provenance** : `ConnectorsModal.tsx`, `connectorStore.ts` et `catalog.ts`
sont arrivés en un seul commit (`8ff90c2 feat(pwa): interface React du
proprietaire`) — la structure (« YOUR backend », coffre AES-256 côté
navigateur, 17 connecteurs génériques dont plusieurs sans rapport avec le
métier d'UniC Plaquiste) indique un gabarit importé tel quel, jamais conçu
pour ni câblé à ARENA.

**Désaccord architectural** : le frontend chiffrait les jetons `apikey`
dans le navigateur (AES-256, coffre à mot de passe) et les envoyait à
chaque requête de chat — un modèle « bring-your-own-key côté client ».
ARENA est conçu pour l'inverse : secrets uniquement côté serveur, `.env`,
jamais le navigateur (`core/security/trust.py`, `core/permissions/`, les
zones verrouillées de `PROJECT_MEMORY/LOCKED_ZONES.md`). Décision du
propriétaire : le retirer plutôt que le garder à côté d'un modèle
serveur-only.

## 2. Ce qui est construit — DEC-0024

Gmail, de bout en bout : `CONNECT → OAUTH → CONSENTEMENT → CALLBACK →
JETON STOCKÉ CÔTÉ SERVEUR → API GMAIL`. Détail complet, preuve par
sabotage, et ce qui reste `NON VÉRIFIÉ` (jamais essayé contre un vrai
compte Google) : `docs/DECISIONS.md` DEC-0024.

Le catalogue de la PWA est reconcilié à la réalité : les 13 connecteurs
sans code backend sont retirés, pas laissés en façade. Le coffre navigateur
est supprimé.

## 3. Ce qui reste, service par service

Pour chacun des services cités dans la demande, ce qui bloque concrètement
et ce qu'il faudrait pour lever le blocage. **Aucun ne peut être fabriqué
sans une action du propriétaire** : un `client_id`/`client_secret` OAuth
n'existe qu'une fois l'app enregistrée par lui, avec son identité, sur la
console du fournisseur.

| Service | Backend existant | Ce qui manque avant du code réel | Action du propriétaire |
|---|---|---|---|
| **Google Calendar** | `core/connectors/calendrier.py` — complet, même identifiant OAuth que Gmail | Le flux `/connectors/gcal/auth` n'est pas déclaré dans `FOURNISSEURS_OAUTH` (scope volontairement limité à Gmail cette fois) | Aucune — coût marginal faible, même app Google. À planifier si demandé |
| **Google Drive** | Aucun | Aucune capacité `core/connectors/` n'existe | Créer l'app (même console, portée Drive), demander la construction du connecteur |
| **Instagram** | Aucun | Nécessite l'API Meta Graph (Instagram Business), une app Meta for Developers, une revue d'app Meta pour les portées de publication | Créer l'app sur developers.facebook.com, lier le compte Instagram Business, donner `client_id`/`secret` |
| **LinkedIn** | Aucun | Nécessite une app LinkedIn Developer, un produit « Share on LinkedIn » ou « Marketing API » selon l'usage visé | Créer l'app sur linkedin.com/developers, demander l'accès au produit voulu |
| **Reddit** | Aucun | Nécessite une app enregistrée sur reddit.com/prefs/apps (type « web app ») | Créer l'app, donner `client_id`/`secret` |
| **TikTok** | Aucun | Nécessite une app TikTok for Developers, revue de l'app pour les portées de publication | Créer l'app sur developers.tiktok.com |
| **Site principal / site expert** (unicplaquiste.com, expert.unicplaquiste.com) | Aucun | Dépend de ce que le CMS/hébergeur expose réellement (API de contenu ? Git ? déploiement ?) — **jamais audité**, l'audit ne peut pas deviner une plateforme sans accès | Dire quel CMS/hébergeur sert ces sites, ou donner un accès (API, dépôt Git, panneau d'administration) |
| **app.unicplaquiste.com + /admin** | Aucun | Idem — nature de l'application inconnue (stack, base de données, API interne ?) | Décrire l'architecture de l'application, ou donner un accès API authentifié |
| **Google Business Profile / Maps** | Aucun | L'URL `maps.app.goo.gl/...` identifie le profil mais ne donne aucun accès — il faut l'API Google Business Profile, distincte de Gmail/Calendar, avec sa propre vérification de propriété d'établissement | Créer l'accès sur business.google.com, vérifier la propriété, puis l'app OAuth correspondante |

**Aucune de ces lignes n'est du travail restant côté code seul** : chacune
attend une information ou une création que seul le propriétaire peut
fournir. Une fois l'un de ces accès obtenu, le chantier suit exactement le
même schéma que Gmail (DEC-0024) : `/connectors/{id}/auth` + `/callback`
dans `apps/backend/routers/connectors.py`, une entrée dans
`FOURNISSEURS_OAUTH`, un connecteur `core/connectors/{id}.py` déclaré dans
`apps/backend/runtime.py`, testé et sabote-vérifié comme Gmail.

## 4. Ce qui ne se fera pas par principe

- **Aucune capacité n'est déclarée avant d'être réellement autorisée par
  l'API du fournisseur.** Si Instagram ne permet pas une action par API
  publique (certaines actions restent manuelles côté Meta selon le type de
  compte), ARENA le dira au lieu de la simuler.
- **Aucun secret ne passe par le navigateur.** Le coffre AES-256 retiré
  cette session ne reviendra pas sous une autre forme sans une décision
  explicite qui l'autorise.
- **Aucun connecteur n'est ajouté « pour compléter la vitrine ».** Un
  connecteur sans backend réel derrière est retiré, pas gardé en façade
  (c'est exactement ce que ce chantier a corrigé).
