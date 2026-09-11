# Audit — Case (`case-computers/case`)

*Mission ARENA x CASE — reçue le 11/09/2026. Audit du code cloné, et d'une
instance **réellement déployée** dans cette session (pas seulement lue).*

## Provenance

| | |
|---|---|
| Dépôt | `https://github.com/case-computers/case` |
| Commit audité | `133082b` (« Merge pull request #10 from case-computers/feat/drive-reliability ») |
| Licence | **Dual, par dossier**, `LICENSE.md` lu dans le clone (voir matrice ci-dessous) |
| Architecture | Python (control-plane + MCP), React (`web/`), image Docker `debian:bookworm-slim` (bureau) |

## Matrice de licence (vérifiée, pas supposée)

| Chemin | SPDX | Ce que ça permet ici |
|---|---|---|
| `control-plane/`, `image/`, `Dockerfile.cased`, `compose.yaml`, `requirements*.txt` | `AGPL-3.0-only` | **Aucune ligne copiée dans ARENA.** Déployé séparément, jamais importé. |
| `mcp/`, `bin/case`, `web/`, `tests/`, `Dockerfile.ui`, `case-mcp.json` | `MIT` | Les surfaces client — ARENA n'en a de toute façon copié aucune ligne non plus : le connecteur écrit ici est un CLIENT REST, pas un fork de `mcp/`. |

`LICENSE.md` le dit lui-même, cité tel quel : *« Writing an agent that drives
Case over MCP or REST. Not a derivative work. »* — exactement l'architecture
retenue (§29-30 de la mission) : `core/connectors/case_computer.py` est un
client HTTP, au même titre que `core/connectors/github.py` vers l'API GitHub.
Zéro fichier AGPL n'a été lu à des fins de copie — seulement pour comprendre
le contrat REST qu'il expose (`control-plane/cased.py`, la table de routes).

## Sécurité — `SECURITY.md` lu en entier avant d'écrire une ligne

Points vérifiés dans le code, pas seulement affirmés par la doc :

- **Le mot de passe est tapé dans la page, jamais donné à l'agent** —
  injection CDP `Input.insertText`, jamais une commande shell. `deskd` rend
  **423** sur `/exec`, `/action`, `/file`, `/eval` pendant l'injection —
  vérifié dans `image/deskd.py`, réutilisé tel quel dans le connecteur
  (`_faire_executer_commande` nomme explicitement ce 423, jamais un échec
  générique).
- **MCP n'a aucun outil d'écriture d'identifiant** — vérifié en listant les
  25 outils réels du serveur (`docker run` réel, ci-dessous) : aucun
  `credential_*` n'y figure. La gestion des identifiants reste entièrement
  côté Case (Drive UI, `/fill`, `bin/case cred add`) — ce connecteur **ne
  déclare aucune capacité `credential`/`login`**, vérifié par
  `tests/core/test_connecteur_case_computer.py::TestConfidentialite`.
- **cased mappe `/var/run/docker.sock`** (`compose.yaml`) — nécessaire pour
  que le control-plane crée/détruise des conteneurs de bureau. C'est le
  risque nommé par `SECURITY.md` lui-même (« a desktop can still reach cased
  ») : un ordinateur compromis peut composer cased sur son réseau partagé.
  Aucune mitigation supplémentaire ajoutée ici — Case documente déjà
  `CASE_TOKEN` et `DESK_TOKEN` comme les frontières réelles, et ce connecteur
  ne mount aucun socket lui-même : il parle REST, rien de plus.
- **Ni confirmation obligatoire côté ARENA sur les opérations en LECTURE**
  (lister/état/capture d'écran), **ni sur le cycle de vie ou l'action à
  l'intérieur d'un ordinateur ISOLÉ** (créer/dormir/réveiller/exécuter/
  écrire un fichier/naviguer) — `config/permissions_services.yaml`, `case:
  write: ALLOWED, risque MEDIUM`. **`destroy` seul exige confirmation** :
  irréversible, données persistantes perdues.

## Déploiement local — réellement fait, pas seulement lu

**Contrainte mesurée avant tout : 1.1 Go disponibles sur cette session**
(`df -h /` — un quota de session, pas le disque physique). L'image de bureau
(`image/Dockerfile` : `debian:bookworm-slim` + Chromium + xfwm4 + xfce4-panel
+ thunar + polices) pèse, mesuré sur des bases comparables, plusieurs
centaines de Mo à plus d'1 Go une fois construite — **au-delà de ce que cette
session pouvait risquer sans mettre en péril le reste du travail (git, push,
tests)**. Elle n'a donc **pas** été construite ici. C'est une limite
mesurée, dite, jamais contournée par une simulation.

**Ce qui a en revanche réellement tourné, dans cette session :**

1. `docker build -f Dockerfile.cased` — le control-plane, Python pur
   (`python:3.12-slim` + fastapi/uvicorn/docker-sdk/cryptography/mcp), ~215
   Mo. Réussi (après avoir routé `pip` à travers le proxy sortant de cette
   session — réseau applicatif du conteneur, sans rapport avec Case
   lui-même).
2. `docker run` de `cased` (control-plane), avec `/var/run/docker.sock`
   monté, `CASE_TOKEN` défini, `CASE_IMAGE=case-desk:0.1` (jamais construite
   — délibérément, pour mesurer le comportement réel d'un manque).
3. `docker run` du service MCP, même image, `CASE_MCP_HTTP=1`.

**Résultats réels, mesurés en direct** (pas une simulation, curl/pytest
réels, session du 11/09/2026) :

| Appel | Résultat réel |
|---|---|
| `GET /health` sans jeton | `{"ok":true}` — porte ouverte, comme documenté |
| `GET /health` avec jeton | `{"ok":true,"computers":0,"docker":true,...}` — **`docker:true` : cased voit réellement le Docker de cette session** |
| `GET /v1/computers` sans jeton | **401** réel |
| `GET /v1/computers` avec mauvais jeton | **401** réel |
| `GET /v1/computers` avec bon jeton | `{"computers":[]}` |
| `POST /v1/computers` (créer) | **`{"error":{"code":"create_failed","message":"create failed: ImageNotFound"}}`** — l'échec réel et honnête attendu, sans image de bureau |
| `GET /v1/computers/absent` | **404** réel |
| `core/mcp/transport.py::ClientMcp` (le client MCP DÉJÀ présent d'ARENA, **zéro ligne neuve**) contre le serveur MCP réel | Poignée de main réelle, **25 outils réels listés** (`computer_create`, `computer_exec`, `computer_navigate`, `computer_file_put`/`get`, `computer_sleep`, `handoff_request`…) |

Le connecteur ARENA (`core/connectors/case_computer.py`) a ensuite été testé
**contre cette même instance réelle** — `tests/core/test_connecteur_
case_computer.py::TestContreUneVraieInstanceCase` (marquée `integration`,
3 tests, tous verts) et `tests/agents/test_dioumtoukay_case.py::
TestContreUneVraieInstanceCase` (1 test, la boucle ENTIÈRE de Dioumtoukay,
vert) : la sonde de santé réussit réellement, `lister` réussit réellement,
`créer` échoue réellement et honnêtement (`ImageNotFound`), rapporté tel
quel jusqu'au compte-rendu final de Dioumtoukay — jamais transformé en
succès.

## Ce qui a été délibérément REJETÉ, et pourquoi

- **L'agent intégré de Case (« Drive »)** : jamais utilisé comme cerveau.
  ARENA parle directement à `cased`/MCP — Dioumtoukay reste le seul agent,
  Case reste l'ordinateur (mission §8, « Case is not the agent »).
- **MCP comme SEUL chemin** : `wake` et `destroy` n'existent pas côté MCP
  (vérifié en listant les 25 outils — délibéré côté Case, même discipline
  que « MCP has no credential-write tool »). Le connecteur ARENA utilise
  donc **REST**, qui porte le cycle de vie complet dans un seul contrat —
  mission §28, choisir par opération, jamais forcer un seul chemin partout.
- **Duplication d'Agent-Reach/Fuji/Lightpanda** : aucun des trois n'a été
  touché. Case ajoute un ORDINATEUR (terminal + fichiers + navigateur
  persistants dans un conteneur), pas une seconde intelligence de
  navigation — la distinction que la mission demande explicitement (§20).
- **Gestion des identifiants dans ce connecteur** : aucune capacité
  `credential`/`login` déclarée (voir Sécurité, ci-dessus) — reste
  entièrement du côté Case (Drive UI, `/fill`), jamais un modèle ARENA.
- **VPS/déploiement distant** : non tenté. Rien dans l'architecture du
  connecteur (`USMAN_CASE_URL` configurable) ne suppose le local — mais
  aucune mesure réelle contre un VPS n'a eu lieu ici (mission §47, préparé,
  pas construit).
- **Windows** : cette session tourne sur Linux (cloud). La compatibilité
  Docker Desktop/Windows de Case n'a **pas** été mesurée — dite comme
  inconnue, jamais supposée (mission §10).

## Ce que ça coûte si c'est faux

Le connecteur suppose que `cased` protège correctement ses propres
frontières (Host/Origin, `CASE_TOKEN`, réseau `case-desks` séparé) — vérifié
en LISANT le code et en mesurant le comportement réel (401 sur mauvais
jeton, health ouvert sans jeton), jamais en l'auditant en profondeur pour
des vulnérabilités non documentées par `SECURITY.md` lui-même. Le
`USMAN_CASE_TOKEN` d'ARENA transite en clair dans l'en-tête `Authorization`
de chaque requête — comme `USMAN_GITHUB_TOKEN` pour le connecteur GitHub,
même modèle de confiance, pas d'audit cryptographique supplémentaire ici.
Aucune image de bureau n'ayant tourné dans cette session, la persistance
réelle (§13/§55 de la mission), l'isolation entre deux ordinateurs (§58) et
le test de handoff (§56) **restent non mesurés** — le connecteur est écrit
pour eux (l'API les couvre), mais rien ne les a fait tourner pour de vrai
ici. C'est la limite honnête de cette mission dans cet environnement.
