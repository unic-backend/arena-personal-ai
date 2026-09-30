# Netronome — conscience réseau mesurée (optionnelle)

*Intégration décidée le 2026-09-30 (DEC-0202). Statut : optionnelle, désactivée
par défaut. Sans Netronome, ARENA retombe sur une sonde réseau native.*

---

## Pourquoi

ARENA savait diagnostiquer son **code** (`core/guardian/diagnostics.py`) et sa
**machine** (`scripts/doctor.py`), mais rien de son **réseau**. Quand une requête
vers un service externe échoue, ARENA ne pouvait pas distinguer :

```
problème de modèle  ·  problème de fournisseur  ·  problème de réseau  ·  problème local
```

Netronome (autobrr/netronome) mesure la couche qui manquait — latence, débit,
perte de paquets, santé DNS — derrière une API HTTP. ARENA lui parle par cette
API, exactement comme à MoneyPrinterTurbo et WanGP (DEC-0008).

## Ce qu'ARENA utilise réellement

Deux capacités, et deux seulement :

| Capacité | Action | Coût | Ce qu'elle lit / fait |
|---|---|---|---|
| `etat` | `read` (ALLOWED) | bon marché | Dernier débit mesuré, latence, perte de paquets, résumé des moniteurs perte/DNS. **Ne lance aucun test.** |
| `mesurer_debit` | `measure` (CONFIRMATION) | coûteux | Lance un vrai test de débit (download/upload/latence). Occupe la ligne plusieurs dizaines de secondes. |

Ce qu'ARENA **n'utilise pas** de Netronome : le traceroute vers un hôte libre
(risque de scan interne piloté par une entrée non fiable), l'ordonnanceur (ARENA
a le sien), les notifications, la supervision d'agents multi-machines. Ces
capacités existent dans Netronome ; elles ne sont pas exposées ici.

## Architecture

```
        « Mon Internet est lent, vérifie » (chat, PWA)
                        │
        intention RESEAU (déterministe, DEC-0203)
        core/reseau/demande.py — la phrase → etat | mesurer_debit
                        │
        ARENA (chat `_mon_reseau`, route GET /api/reseau/sante)
                        │
        core/reseau/sante_reseau.py   ← l'adaptateur remplaçable
                        │
        ┌───────────────┴────────────────┐
        │                                 │
   Netronome (optionnel)          Sonde native ARENA
   core/connectors/netronome.py   connectivité TCP + DNS,
   → API HTTP locale              bibliothèque standard seule
```

- **`core/connectors/netronome.py`** — le connecteur, service `network`. Suit le
  contrat commun (`core/connectors/base.py`) : capacités déclarées, permission,
  confirmation, santé, quota, journal.
- **`core/reseau/sante_reseau.py`** — l'adaptateur. Le reste d'ARENA ne connaît
  jamais Netronome : il appelle `evaluer_sante_reseau(registre)`, qui choisit
  Netronome quand il répond et retombe sur la sonde native sinon.
- **`apps/backend/routers/reseau.py`** — `GET /api/reseau/sante`, lecture seule,
  protégée par la même clé et le même limiteur que `/api/observability`.
- **`core/reseau/demande.py`** (DEC-0203) — la phrase du propriétaire devient
  l'une des deux capacités, sans agent ni modèle : « mon internet est lent »,
  « diagnostique ma connexion » → `etat` (lecture) ; « lance un test de
  débit », « fais un speedtest » → `mesurer_debit` (CONFIRMATION). Ses réseaux
  SOCIAUX ne passent pas le filtre. Le rendu (`rendre_sante`) sépare le mesuré
  du non mesuré et ne juge jamais la connexion à la place d'une mesure.
- **Intention `RESEAU`** — détectée de façon déterministe par l'orchestrateur
  AVANT le contrôle date (« vérifie » partirait sinon en recherche web),
  aiguillée par `apps/backend/routers/chat.py::_mon_reseau`. **Le chemin de
  conversation ne lance jamais de test de débit** : le diagnostic est une
  lecture ; la mesure coûteuse attend la confirmation du propriétaire.

## Installation (par le propriétaire, sur sa machine)

Netronome n'est **jamais** installé par ARENA et **aucune ligne** n'entre dans ce
dépôt (voir *Licence* plus bas).

1. Installer le binaire depuis `github.com/autobrr/netronome` (release ou build Go).
2. Le lancer : `netronome serve`. Par défaut il écoute sur `127.0.0.1:7575`.
3. Autoriser ARENA à lire son API **sans session** en le whitelistant dans son
   `config.toml` :

   ```toml
   [auth]
   whitelist = ["127.0.0.1/32"]
   ```

   C'est le chemin recommandé pour une intégration locale : ARENA tourne sur la
   même machine et lit l'API depuis `127.0.0.1`.

## Configuration (côté ARENA)

Toutes les variables sont vides/par défaut dans `.env.example` :

| Variable | Rôle | Sans elle |
|---|---|---|
| `NETRONOME_URL` | Où joindre Netronome | défaut `http://127.0.0.1:7575` |
| `NETRONOME_SESSION` | Cookie de session, **seulement** si Netronome n'est pas whitelisté | on compte sur la whitelist |

Permissions (`config/permissions_services.yaml`, service `network`, modifiable par
le propriétaire) : `read` = ALLOWED, `measure` = CONFIRMATION.

## Comportement en dépendance optionnelle

| Situation | Ce que fait ARENA |
|---|---|
| Netronome lancé + whitelisté | `etat` → mesures complètes (débit, latence, perte, DNS), `source: "netronome"` |
| Netronome éteint / injoignable | repli automatique sur la sonde native, `source: "natif"` ; débit/perte/gigue restent `null` |
| Netronome répond mais refuse (401/403) | `NOT_CONFIGURED` avec la commande de whitelist, puis repli natif |
| Netronome branché mais l'appel échoue | statut `FAILED`/`PARTIAL` honnête, repli natif tenté |

**Jamais de mesure simulée.** Un débit non mesuré vaut `null`, jamais `0`. La
sonde native n'invente pas ce que seul Netronome sait prendre.

## Sécurité

- **Aucune cible réseau arbitraire.** `mesurer_debit` vise les serveurs déjà
  configurés dans Netronome (`server_id`), jamais un hôte libre. Le traceroute
  vers un hôte quelconque n'est pas exposé.
- **Confirmation sur le coûteux.** Un test de débit consomme de la bande passante
  réelle → CONFIRMATION + plafond (`MESURES_PAR_MINUTE`).
- **Lecture sur le chemin de conversation, jamais de test.** `GET /api/reseau/sante`
  ne lance aucun débit.
- **Aucun secret dans un résultat.** Le cookie de session éventuel part dans
  l'en-tête, il n'entre dans aucun compte-rendu.
- **Pas de persistance d'infrastructure.** ARENA ne stocke pas d'IP internes, de
  topologie ni d'identifiants réseau : l'état est un diagnostic temporaire.

## Ressources

- `etat` : quelques requêtes HTTP locales bon marché.
- `mesurer_debit` : bande passante réelle + plusieurs dizaines de secondes de
  ligne occupée. À déclencher explicitement, jamais en boucle.
- Aucune dépendance Python ajoutée : `httpx` est déjà présent.

## Licence

Netronome est sous **GPL-2.0-or-later**. ARENA (`LICENSE` : « tous droits
réservés ») **ne copie aucune ligne** de Netronome et communique avec lui par le
réseau, comme deux programmes séparés (agrégation, GPL v2 §2) — ce qui ne crée
pas d'œuvre dérivée. Copier le source de Netronome dans ce dépôt public le
placerait au contraire sous GPL : c'est interdit ici. Attribution :
`THIRD_PARTY_NOTICES.md`.

## Comment le désactiver / retirer

- **Désactiver** : ne pas lancer Netronome. ARENA détecte l'absence et utilise la
  sonde native. Rien d'autre à faire.
- **Interdire une capacité** : mettre `network.measure` (ou `network.read`) à
  `DENIED` dans `config/permissions_services.yaml`.
- **Retirer complètement** : supprimer la déclaration `"netronome"` dans
  `apps/backend/runtime.py`, le connecteur `core/connectors/netronome.py`, et la
  route. L'adaptateur `core/reseau/sante_reseau.py` continue de fonctionner en
  mode natif seul (il gère `registre=None`).

## Vérification

- Tests hors ligne : `pytest tests/core/test_connecteur_netronome.py
  tests/core/test_sante_reseau.py tests/test_reseau_route.py
  tests/core/test_demande_reseau.py`.
- Tests d'intégration contre un vrai Netronome : **BLOCKED** tant que le binaire
  n'est pas lancé sur la machine du propriétaire. Aucun résultat de performance
  n'est revendiqué (`UNKNOWN — non mesuré`).
