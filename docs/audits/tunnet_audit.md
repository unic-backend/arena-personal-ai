# Audit — orielhaim/tunnet (« Tunnet »)

**Dépôt étudié** : https://github.com/orielhaim/tuntun
**Commit audité** : `05ce72f181455a4e8be76ba960df5fd090441cfb` (11/09/2026, tête du
dépôt au 11/09/2026).
**Méthode** : clone réel (`git clone --depth 1`), lecture directe de `README.md`,
`LICENSE`, l'arborescence complète (`crates/`, `apps/`, `packages/`, `go/`,
`charts/`, `helm/`) et des README par composant. Rien pris sur la seule foi du
commentaire Reddit qui a motivé cette demande.

## Ce que le commentaire Reddit laissait entendre, et ce que le dépôt est réellement

Le commentaire (r/opensourcealternat…) décrit l'usage comme : « me permet de
me connecter facilement aux agents qui tournent sur mon ordinateur principal
depuis mon ordinateur portable quand je sors » — ce qui évoque un petit outil
de connexion à distance.

Le dépôt réel, sous le nom **« Tunnet »** (le nom `tuntun` de l'URL est un
alias historique — `README.md` et tous les README internes se nomment
eux-mêmes « Tunnet »), est un **produit de mise en réseau maillée complet** :
19 crates Rust (`tunnet-agent`, `tunnet-control`, `tunnet-relay`,
`tunnet-cli`, `tunnet-mobile`, `tunnet-operator`, `tunnet-policy-engine`,
`tunnet-license`…), une app Node/Bun (dashboard), un SDK Go, des apps
Android/desktop/cloud séparées, des charts Helm et un opérateur Kubernetes —
58 Mo de code source, badge `Status: In development`. C'est un concurrent de
Tailscale/ngrok/Cloudflare Access, pas un connecteur d'agents.

## Ce qui compte pour une décision d'intégration

| Domaine | Constat |
|---|---|
| Portée | Mesh VPN + tunnels publics + SSH + posture d'appareil + opérateur Kubernetes + moteur de licence commerciale (`tunnet-license`, `packages/license` — keyring, jetons, révocation). Un produit commercial avec palier payant, pas un outil communautaire ponctuel |
| Licence | **Éclatée par composant**, jamais une seule licence pour tout le dépôt : MPL-2.0 (agent, SDKs, runtime client), **AGPL-3.0-only** (plan de contrôle, tableau de bord, relais géré, audit, persistance, API interne — tout ce qu'un auto-hébergement ferait tourner), Apache-2.0 (protocole, clients, contrats). Le fichier promis pour trancher au cas par cas, `LICENSING.md`, **cité par `LICENSE` et par plusieurs README de crates, n'existe pas dans ce clone** — impossible de vérifier la licence exacte d'un fichier donné sans lui |
| Langage | 100 % Rust/TypeScript/Go — **aucun code Python**. Rien à importer dans un dépôt Python sans réécrire |
| Surface utile à ARENA | Aucune API pensée pour l'orchestration d'agents (contrairement à ComfyUI, DEC-0087, qui expose une vraie API HTTP de soumission de tâches). Tunnet opère à la couche réseau : une fois un appareil sur le maillage, les outils ordinaires (`curl`, navigateur) l'atteignent — il n'y a rien à « appeler » depuis du code Python |
| Maturité | `Status: In development` — aucune version stable annoncée |

## Ce qui existe déjà dans ARENA pour ce besoin précis — et fonctionne

`scripts/lancer_arena.ps1` (déjà dans le dépôt, déjà utilisé) fait
**exactement** ce que le commentaire Reddit décrit, sans dépendance nouvelle :

1. lance le serveur ARENA (`uvicorn apps.backend.main:app --port 8000`) ;
2. lance un **tunnel Cloudflare Quick Tunnel** (`cloudflared tunnel --url
   http://localhost:8000`) — gratuit, sans compte, sans serveur à
   auto-héberger ;
3. lit l'adresse publique (`*.trycloudflare.com`) dans le journal du tunnel
   et l'affiche en QR code pour le téléphone.

Limite connue et déjà documentée dans le script lui-même : l'adresse d'un
Quick Tunnel **change à chaque démarrage** — c'est le seul vrai manque face à
un maillage nommé de façon stable. Un Tunnel Cloudflare **nommé** (toujours
`cloudflared`, aucune dépendance nouvelle, licence Apache-2.0 côté client)
résout ce point précis sans rien du reste de Tunnet.

## Décision

**Rien n'est intégré.** Trois raisons, chacune suffisante seule :

1. Le besoin réel (joindre le serveur ARENA depuis un téléphone hors du
   réseau local) est déjà couvert, mesuré, et utilisé — l'ajouter en double
   contredirait la règle du projet contre la duplication d'architecture.
2. Le dépôt réel n'est pas l'outil léger décrit dans le commentaire Reddit
   qui a motivé la demande, mais un produit commercial de mise en réseau
   maillée, en développement, dans une pile de langages (Rust/TS/Go) sans
   rapport avec le reste du dépôt Python d'ARENA.
3. La partie du dépôt qu'auto-héberger activerait (plan de contrôle,
   tableau de bord, relais) est **AGPL-3.0-only**, sans le fichier de
   correspondance de licence promis pour distinguer précisément quel
   fichier tombe sous quelle licence.

## Ce que ça coûte si c'est faux

Le coût d'un refus à tort serait de ne pas gagner de maillage privé
multi-appareils (SSH, sous-réseaux, passerelles) — capacité qu'aucune mission
métier n'a demandée à ce jour. Le coût d'une intégration à tort serait
d'ajouter 58 Mo de code dans trois langages étrangers au dépôt, un
auto-hébergement sous AGPL-3.0-only sans savoir précisément quel fichier
cette licence couvre, pour dupliquer une capacité qui existe déjà et
fonctionne. Le second coût est sans commune mesure avec le premier.
