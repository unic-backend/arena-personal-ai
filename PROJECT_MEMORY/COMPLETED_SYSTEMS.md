# SYSTÈMES ACHEVÉS — et ce que « vérifié » veut dire ici

*Mise à jour : 2026-08-29. Toute ligne de ce fichier repose sur une commande
lancée, pas sur une impression.*

---

## Deux niveaux de vérification, à ne jamais confondre

| Niveau | Ce que ça prouve | Ce que ça ne prouve pas |
|---|---|---|
| **LOGIQUE VÉRIFIÉE** | les tests hors ligne passent **et** un sabotage a fait tomber un test précis | que ça tourne avec le vrai service |
| **BOUT EN BOUT** | la chose a réellement tourné, avec son service | — |

**Sur la machine de l'assistant (cloud), aucun système dépendant d'un service
externe ne peut atteindre le second niveau** : Ollama, ffmpeg, Docker, WanGP,
MoneyPrinterTurbo, Google et le réseau n'y sont pas. Les 21 tests marqués
`integration` sont désélectionnés pour cette raison.

Preuve du 2026-08-28 :
```
python -m ruff check .      → All checks passed!
python -m pytest tests/ -q  → 1615 passed, 21 deselected
python scripts/orphelins.py → 110 modules, 82 atteints, aucun module réel endormi
```

---

## Statut par sous-système

| Sous-système | Statut | Tests | Bout en bout |
|---|---|---|---|
| `core/actions/resultat.py` | **100% LOGIQUE VÉRIFIÉE** | 24 | sans objet (pur) |
| `core/actions/journal.py` | **100% LOGIQUE VÉRIFIÉE** | 40 | sans objet (SQLite local) |
| `core/actions/attente.py` | **100% LOGIQUE VÉRIFIÉE** | 41 + 24 (route) | sans objet |
| `core/permissions/` | **100% LOGIQUE VÉRIFIÉE** | 51 + 30 | sans objet |
| `core/connectors/base.py` | **100% LOGIQUE VÉRIFIÉE** | 45 | sans objet |
| `core/connectors/registre.py` | **100% LOGIQUE VÉRIFIÉE** | 21 | sans objet |
| `core/memory/personnelle.py` | **100% LOGIQUE VÉRIFIÉE** | 56 | sans objet |
| `core/memory/recuperation.py` | **100% LOGIQUE VÉRIFIÉE** | 43 | sans objet |
| `core/security/trust.py` | **100% LOGIQUE VÉRIFIÉE** | couvert par gateway + gmail | sans objet |
| `core/execution/voies.py` | **100% LOGIQUE VÉRIFIÉE** | 16 + 24 (branchement) | sans objet |
| `core/execution/travaux.py` | **90%** | couvert | file réelle, jamais sous charge |
| `core/execution/mesures.py` | **90%** | 11 (branchement) | durées réelles jamais mesurées chez lui |
| `core/memory/semantique.py` | **75%** | 8 (branchement) | **NON VÉRIFIÉ** — exige Ollama + `bge-m3` |
| `core/memory/consolidation.py` | **100% LOGIQUE VÉRIFIÉE** | 8 (branchement) | sans objet |
| `agents/plaquiste/*` (devis, métré, prix) | **90%** | 38 + 31 + 21 + 20 + 24 + 18 | PDF réel écrit une fois (PR #13) |
| `core/connectors/devis.py` | **90%** | couvert | PDF réel, 3720 octets |
| `core/connectors/gmail.py` | **75%** | 35 | **NON VÉRIFIÉ** — aucun compte Google connecté |
| `core/connectors/calendrier.py` | **75%** | 26 | **NON VÉRIFIÉ** — idem |
| `agents/email/email_agent.py` | **75%** | 23 | **NON VÉRIFIÉ** — dépend de Gmail |
| `core/connectors/moneyprinter.py` | **75%** | 19 | **NON VÉRIFIÉ** — service jamais lancé |
| `core/connectors/wan2gp.py` | **75%** | couvert | **NON VÉRIFIÉ** — WanGP jamais lancé |
| `core/connectors/suivi_video.py` | **90%** | 8 + 31 (agent) | **NON VÉRIFIÉ** avec un vrai générateur |
| `core/connectors/galsen.py` | **90%** | couvert | mesuré une fois chez lui : 558 communes |
| `tools/documents/{indexer,inventory}` | **75%** | 18 + 19 + 17 | **NON VÉRIFIÉ** — exige Ollama + LightRAG |
| `core/reasoning/reasoning_engine.py` | **75%** | 10 (branchement) | **NON VÉRIFIÉ** — exige Ollama + Docker |
| `apps/backend/` (routes, sécurité, débit) | **90%** | 37 (surface) + 20 + 26 | serveur jamais observé chez lui cette session |
| `apps/backend/routers/pwa_gateway.py` | **90%** | 72 | interface **jamais regardée** |
| `scripts/doctor.py` | **100% LOGIQUE VÉRIFIÉE** | 27 | tourne réellement ici, sortie correcte |
| `core/models/confidentialite.py` | **100% LOGIQUE VÉRIFIÉE** | 57 | sans objet (pur) |
| `core/models/openai_compatible.py` | **75%** | 33 | **NON VÉRIFIÉ** — aucun appel réel à Groq/DeepInfra |
| `core/models/routeur.py` | **90%** | 26 | **NON VÉRIFIÉ** avec de vrais services |
| `core/models/usage.py` | **90%** | couvert | tarifs non configurés : coûts `None` |
| `scripts/comparer_fournisseurs.py` | **75%** | 6 | **NON VÉRIFIÉ** — 0 fournisseur mesurable ici |
| `tools/social/regles.py` | **100% LOGIQUE VÉRIFIÉE** | 19 | sans objet (pur comptage) |
| `tools/social/voix.py` | **90%** | couvert | mémoire réelle, jamais remplie par lui |
| `tools/social/idees.py` | **100% LOGIQUE VÉRIFIÉE** | couvert | sans objet (combinatoire) |
| `agents/social/social_agent.py` | **75%** | 36 | **NON VÉRIFIÉ** — jamais tourné avec un vrai modèle |
| `core/execution/coordination.py` | **100% LOGIQUE VÉRIFIÉE** | 18 | sans objet (pur) |
| `core/mcp/stdio_transport.py` | **100% LOGIQUE VÉRIFIÉE** | 10 | **BOUT EN BOUT constaté** — contre le vrai serveur OpenTakeoff, dans cette session |
| `core/connectors/opentakeoff.py` | **100% LOGIQUE VÉRIFIÉE** | 13 | **BOUT EN BOUT constaté une fois** : OpenTakeoff construit dans cette session, plan de démo mesuré (4 pièces, 1751.92 SF), rapport + PDF marqué réellement écrits. Non revérifié depuis chez lui — Node/npm à installer |
| `agents/plaquiste/metre_plan.py` | **100% LOGIQUE VÉRIFIÉE** | 19 + 6 (branchement) | sans objet (conversion pure + branchement testé) |
| `apps/pwa/` (interface) | **NON VÉRIFIÉ** | 25 (fichiers) | **jamais affichée ni cliquée** |

---

## Ce qui n'a jamais tourné en vrai — la liste, nommée

Les 21 tests `integration` désélectionnés disent exactement ce qui manque :

| Ce qui manque | Ce que ça bloque |
|---|---|
| **Ollama** | le chat lui-même, le raisonnement, les embeddings, l'indexation |
| **ffmpeg + Whisper** | analyse vidéo, sous-titres, montage, transcription |
| **Docker** | le bac à sable — ARENA refuse d'exécuter du code sans lui |
| **réseau** | recherche web, navigateur, GalsenAPI |
| **LightRAG** | la recherche dans ses documents |

`python -m pytest -m integration` les fait tourner **sur son PC**. C'est la
commande qui lève la moitié des inconnues.
