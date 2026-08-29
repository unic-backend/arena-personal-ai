# CARTE DU PROJET — ARENA / Usman

*Mémoire opérationnelle. Elle existe pour éviter de relire le dépôt à chaque
session. Mise à jour : 2026-08-28.*

**Ce fichier ne contient aucun code.** Il dit où aller, pas ce qu'il y a dedans.

---

## Ce que c'est

IA personnelle de **Ousmane Diop (Saer)**, propriétaire d'**UniC Plaquiste**
(cloisons, BA13, plafonds — Dakar). Le modèle tourne **chez lui**, sur sa RTX
A2000. Rien ne part chez un fournisseur d'IA (DEC-0002).

Python 3.11 · FastAPI · Ollama · SQLite · PWA React (compilée, servie par ARENA).

## Points d'entrée réels

| Chemin | Rôle |
|---|---|
| `apps/backend/main.py` | le serveur : routes racine, `/health`, montage des routeurs |
| `apps/backend/runtime.py` | **le câblage** — tout objet partagé naît ici, une seule fois |
| `apps/backend/routers/pwa_gateway.py` | `/agent/stream` : le chemin que son interface emprunte |
| `apps/backend/routers/chat.py` | `dispatch_request` : intention → agent |
| `agents/orchestrator/orchestrator_agent.py` | classement en intention (modèle, puis repli mots-clés) |

Un module qu'aucun de ces quatre n'atteint est un orphelin :
`python scripts/orphelins.py`.

## Répertoires

| | |
|---|---|
| `core/actions/` | résultat, journal, file d'attente, chronologie |
| `core/permissions/` | politique par service × action × risque, coupe-circuits |
| `core/connectors/` | base + 8 connecteurs (voir DEPENDENCIES.md) |
| `core/mcp/` | deux transports MCP : HTTP (`transport.py`, WanGP) et stdio (`stdio_transport.py`, OpenTakeoff) |
| `core/memory/` | mémoire personnelle, récupération lexicale, sémantique, consolidation |
| `core/execution/` | voies (budgets), mesures (chronométrage), travaux de fond, coordination (tâches à état), crochets + disjoncteur (DEC-0013) |
| `core/guardian/` | diagnostics + file de maintenance + cycle (DEC-0014) — DÉCOUVRE et RAPPORTE, ne MODIFIE jamais le dépôt |
| `core/models/` | fournisseur Ollama |
| `core/security/` | frontière de confiance (`trust.py`) |
| `core/reasoning/` | moteur Plan & Solve (bac à sable) |
| `agents/` | 15 agents ; les vivants : orchestrator, plaquiste, video_analyzer, email, fresh_info, coder, researcher… |
| `apps/backend/` | serveur, routeurs, sécurité, prompts, studio |
| `apps/pwa/` | son interface (compilée) — `apps/pwa/server/` (second serveur mort) supprimé le 29/08/2026, sur sa décision |
| `tools/` | documents, recherche, vidéo, audio, code, rag, navigateur |
| `config/` | `permissions.yaml`, `permissions_services.yaml`, `unic_plaquiste.yaml` (ses prix) |
| `scripts/` | `doctor.py`, `orphelins.py`, `mesurer_performances.py`, installateurs |
| `docs/` | plan, décisions, reprise, règles de travail |
| `tests/` | 1953 tests (1932 hors ligne + 21 marqués `integration`) |

## Les trois documents historiques (autorité, pas mémoire)

| Fichier | Autorité sur |
|---|---|
| `CLAUDE.md` | comment travailler ici — **à lire en premier** |
| `docs/REGLES_DE_TRAVAIL.md` | comment lui parler (il n'écrit pas de code) |
| `docs/DECISIONS.md` | les décisions architecturales (DEC-0001 → DEC-0008) |
| `docs/REPRISE.md` | le journal chronologique du travail |
| `docs/PLAN_ARENA_OS.md` | les 21 phases, et où on en est |

`PROJECT_MEMORY/` ne les remplace pas : il les **indexe** pour éviter de tout
relire.

## Commandes qui mesurent (jamais raconter à leur place)

```
python -m ruff check .
python -m pytest tests/ -q
python scripts/doctor.py          # 16 vérifications de la machine
python scripts/orphelins.py       # ce que le chemin de réponse atteint
```
