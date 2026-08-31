# SYSTÈMES ACHEVÉS — et ce que « vérifié » veut dire ici

*Mise à jour : 2026-08-29. Toute ligne de ce fichier repose sur une commande
lancée, pas sur une impression.*

---

## Deux niveaux de vérification, à ne jamais confondre

| Niveau | Ce que ça prouve | Ce que ça ne prouve pas |
|---|---|---|
| **LOGIQUE VÉRIFIÉE** | les tests hors ligne passent **et** un sabotage a fait tomber un test précis | que ça tourne avec le vrai service |
| **BOUT EN BOUT** | la chose a réellement tourné, avec son service | — |

**Sur la machine de l'assistant (cloud), la plupart des systèmes dépendant
d'un service externe ne peuvent pas atteindre le second niveau** : Ollama,
ffmpeg, Docker, WanGP, MoneyPrinterTurbo, Google et le réseau n'y sont pas.
Les 21 tests marqués `integration` sont désélectionnés pour cette raison.
**Une exception mesurée, 2026-08-29** : `node`/`npm` sont présents ici, donc
OpenTakeoff a pu être construit et interrogé pour de vrai — voir sa ligne
dans le tableau plus bas, et `PROJECT_MEMORY/ACTIVE_WORK.md` pour le rapport
`doctor.py` complet, avant/après construction.

Preuve du 2026-08-31 (revue generale : recherche de fautes, puis correction) :
```
python -m ruff check .      → All checks passed!
python -m pytest tests/ -q  → 2342 passed, 22 deselected
python scripts/orphelins.py → 138 modules, 109 atteints, 29 orphelins (tous des __init__.py)
python scripts/doctor.py    → 22 verifications ; sur cette machine (cloud), 13 capacite(s) indisponible(s)
```
Trois defauts trouves et corriges dans cette revue (chacun sabote puis restaure) :
1. `agents/plaquiste/plaquiste_agent.py` — depuis que le metre calcule part
   directement dans le PDF (phase 7), des cotes lues dans un tour PRECEDENT du
   fil pouvaient produire un devis aux quantites d'un AUTRE chantier, en
   silence. Le fil reste lu (c'est voulu) ; l'origine des cotes est desormais
   annoncee avant la confirmation.
2. `tools/audio/transcription_tool.py` — une duree jamais mesuree valait `0.0`
   (« video de zero seconde »), contre la regle « un champ absent n'est pas
   zero ». Vaut `None`.
3. `tools/audio/transcription_tool.py` + `agents/video_analyzer/` —
   `faster_whisper` absent remontait une `ImportError` brute au milieu d'une
   reponse. L'absence se rapporte maintenant (`ModeleAbsent`), comme la
   marche ffmpeg juste au-dessus le faisait deja.

Preuve du 2026-08-29 (fin de session, apres DEC-0020 — diagnostic/réparation) :
```
python -m ruff check .      → All checks passed!
python -m pytest tests/ -q  → 2011 passed, 21 deselected (2006 avant DEC-0020, +5)
python scripts/orphelins.py → 132 modules, 104 atteints, 28 orphelins (tous des __init__.py — apps/pwa/server/ supprime)
python scripts/doctor.py    → sur cette machine (cloud), 13 capacité(s) indisponible(s) par defaut
                               (Modele de vision inclus — qwen3-vl:4b, jamais mesure sans Ollama)
```

Preuve du 2026-08-29 (avant DEC-0020, juste apres DEC-0019) :
```
python -m ruff check .      → All checks passed!
python -m pytest tests/ -q  → 2006 passed, 21 deselected
python scripts/orphelins.py → 132 modules, 104 atteints, 28 orphelins (tous des __init__.py — apps/pwa/server/ supprime)
```

Preuve du 2026-08-28 (historique) :
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
| `core/execution/travaux.py` | **90%** | couvert (+2 DEC-0020) | file réelle, jamais sous charge ; historique des travaux finis désormais plafonné (`TRAVAUX_TERMINES_GARDES`, DEC-0020) |
| `core/execution/mesures.py` | **90%** | 11 (branchement) | durées réelles jamais mesurées chez lui |
| `core/memory/semantique.py` | **75%** | 8 (branchement) | **NON VÉRIFIÉ** — exige Ollama + `bge-m3` |
| `core/memory/consolidation.py` | **100% LOGIQUE VÉRIFIÉE** | 8 (branchement) | sans objet |
| `agents/plaquiste/*` (devis, métré, prix) | **90%** | 38 + 31 + 21 + 20 + 24 + 18 | PDF réel écrit une fois (PR #13) |
| `core/connectors/devis.py` | **90%** | couvert | PDF réel, 3720 octets |
| `core/connectors/gmail.py` | **75%** | 35 | **NON VÉRIFIÉ** — aucun compte Google connecté |
| `core/connectors/calendrier.py` | **75%** | 26 | **NON VÉRIFIÉ** — idem |
| `agents/email/email_agent.py` | **75%** | 23 | **NON VÉRIFIÉ** — dépend de Gmail |
| `core/connectors/moneyprinter.py` | **75%** | 19 | **NON VÉRIFIÉ** — service jamais lancé |
| `core/connectors/wan2gp.py` | **75%** | couvert | **NON VÉRIFIÉ** — WanGP jamais lancé. Premier appelant reel depuis DEC-0015 (`planifier_scene`), mais toujours jamais invoque contre le vrai service |
| `tools/video/prompt_audit.py` | **100% LOGIQUE VÉRIFIÉE** | 20 | sans objet (pur, aucun reseau) |
| `agents/video_analyzer/video_analyzer_agent.py` (`planifier_scene`) | **100% LOGIQUE VÉRIFIÉE** | 15 (branchement + sabotage) | **NON VÉRIFIÉ** avec le vrai WanGP — le gate d'audit avant l'appel est prouve, pas la generation elle-meme |
| `agents/vision/vision_agent.py` (DEC-0019) | **100% LOGIQUE VÉRIFIÉE** | 11 + branchement pwa_gateway/chat | **NON VÉRIFIÉ** — qwen3-vl:4b jamais charge, aucune image reelle analysee, latence/VRAM jamais mesurees |
| `core/models/ollama_provider.py` (`images=`) | **100% LOGIQUE VÉRIFIÉE** | 5 (offline, requete verifiee) | sans objet pour la requete ; l'inference elle-meme reste **NON VÉRIFIÉE** |
| `apps/backend/pieces_jointes.py` (images) | **100% LOGIQUE VÉRIFIÉE** | 8 nouveaux (37 au total) | sans objet (local, deterministe) |
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
| `core/guardian/` (diagnostics, file, gardien) | **100% LOGIQUE VÉRIFIÉE + BOUT EN BOUT constaté** | 25 (unitaires) + 6 (API) | scénario du §27 lancé pour de vrai : un test casse, `pytest`/`ruff` reels tournent en sous-processus, le defaut entre en file, retire, resolu au cycle suivant |
| `core/execution/hooks.py` | **100% LOGIQUE VÉRIFIÉE** | 8 | sans objet (pur) |
| `core/execution/disjoncteur.py` | **100% LOGIQUE VÉRIFIÉE** | 13 + 6 (bout en bout, `test_crochets_integration.py`) | sans objet — le test d'intégration compte les appels REELS a `_executer()`, c'est deja la preuve |
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
