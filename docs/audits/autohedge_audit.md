# Audit — The-Swarm-Corporation/AutoHedge

**Dépôt étudié** : https://github.com/The-Swarm-Corporation/AutoHedge
**Commit audité** : `c549c7950da112286e76725d49f6a25de8fa99bd` (2026-03-05)
**Licence** : MIT (vérifiée directement dans `LICENSE`, Copyright (c) 2023
Eternal Reclaimer) — cohérente avec la déclaration du README.
**Méthode** : lecture ligne à ligne de `autohedge/`, `autohedge/tools/`,
`experimental/`, `pyproject.toml`, `requirements.txt`, `.env.example` ;
recherche exhaustive (`grep -rn`) des points d'appel réels entre modules ;
**exécution directe** des fonctions read-only (`get_token_price`,
`get_order`) contre les vraies API Jupiter, sans jamais placer d'ordre réel.
Rien n'a été pris pour acquis sur la seule foi du README.

---

## Ce que le code fait réellement

```
autohedge/main.py : AutoHedge.run(task) -> director_agent.run(task=task)
```

C'est tout. `AutoHedge.run()` appelle **un seul agent**, `director_agent`
(`swarms.Agent`, `model_name="gpt-4.1"`, `handoffs=ALL_AGENTS`). Le
diagramme du README (`Director -> Quant -> Risk -> Execution -> Trade
Output`) décrit un pipeline fixe ; le code ne fixe rien — c'est le LLM
directeur qui décide, à l'exécution, via le mécanisme `handoffs` de
`swarms`, s'il consulte le Quant Agent, le Risk Agent, l'Execution Agent,
ou aucun des trois. Rien ne garantit qu'une analyse en contienne.

## Matrice de validation des affirmations

| Capacité | Affirmation README | Code existe | Câblée dans `AutoHedge.run()` | Testée (ce dépôt) | Fonctionne réellement |
|---|---|---|---|---|---|
| Director Agent | Génération de thèse/stratégie | Oui (`workers.py`) | **Oui — le seul agent réellement appelé** | Lu, non exécuté (clé OpenAI absente) | Probable, mais jamais vérifié ici |
| Quant Agent | Analyse technique/statistique | Oui, **mais un prompt seul** — aucun `tools=` | Conditionnel (le LLM directeur peut ne jamais l'appeler) | Lu | **Non** : `workers.py` ne joint ni `numpy` ni `pandas` ; recherche exhaustive dans tout le dépôt (`grep -rln numpy\|pandas`) : ces bibliothèques n'apparaissent que dans `yahoo_api.py` et `experimental/market_making.py`, tous deux **jamais importés**. Les « scores 0-1 » que le prompt réclame sont devinés par le LLM, jamais calculés. |
| Risk Management Agent | Position sizing, VaR, Expected Shortfall | Oui, prompt seul, aucun outil | Conditionnel | Lu | **Non**, même défaut que le Quant Agent |
| Execution Agent | Génération et exécution d'ordre | Oui, prompt seul, aucun outil | Conditionnel, et même atteint, **ne peut rien exécuter** (zéro `tools=`) | Lu | **Non** : produit du texte décrivant un ordre hypothétique, aucun appel réel possible depuis cet agent |
| Jupiter Price/Search (marché) | Implicite (« Solana : Full autonomous trading ») | Oui, réel (`jupiter_price.py`, `jupiter_search.py`) | **Non** — `tools_registry.get_tools()` n'est importé **nulle part** dans `workers.py`/`main.py`/`cli.py` : code mort du point de vue du produit | **Exécuté en direct** : `get_token_price("So11...112")` a renvoyé un prix SOL réel (101.18 $), cohérent avec CoinGecko (101.24 $) au même instant | Fonctionne **en isolation**, injoignable depuis `AutoHedge` |
| Jupiter Ultra — construction d'ordre | Implicite | Oui, réel (`ultra_tools.get_order`) | Non, même raison | **Exécuté en direct** (portefeuille jetable, non financé) : refuse proprement sans `SOLANA_PRIVATE_KEY` (`ValueError`), puis atteint réellement `POST /ultra/v1/order` et reçoit une vraie réponse HTTP 400 (fonds insuffisants, attendu pour un portefeuille vide) | Le code fonctionne ; injoignable depuis le produit |
| Jupiter Ultra — signature/exécution réelle | « Full autonomous trading on Solana » | Oui, réel et dangereux (`ultra_tools.execute_trade`, signe avec `Keypair` puis `POST /ultra/v1/execute`) | Non, même raison | **Délibérément pas exécuté** — placerait un vrai ordre sur un portefeuille financé, hors du périmètre autorisé par la mission (§10/§14) | Injoignable depuis le produit ; dangereux si quelqu'un le câble à la main |
| Continu / boucle autonome 24-7 | Implicite (« hedge fund autonome ») | **Absent** — aucun `cron`, `asyncio` de fond, ni scheduler dans tout le dépôt | — | `grep` exhaustif, rien trouvé | **Faux** : `run(task)` est un seul appel synchrone ; toute répétition doit venir d'un orchestrateur externe |
| Sortie structurée (JSON/Pydantic) | « Structured Output: JSON-formatted » | `workers.py` promet des « Pydantic output models » dans sa propre docstring, mais `risk_agent`, `execution_agent`, `quant_agent` déclarent tous `output_type="str"` | — | Lu | **Faux** : texte libre, aucun schéma appliqué |
| Actions/actions boursières (equities) | Non mentionné au README | `yahoo_api.py` (259 lignes, `yfinance`) et `polygon_api.py` existent | `yahoo_api.py` : **zéro import, nulle part**. `polygon_api.py` : ré-exporté par `tools/__init__.py` mais jamais consommé par un agent | Lu | Code mort |
| Tests | 5 workflows GitHub (`unit-test.yml`, `test.yml`, `run_test.yml`…) | **Aucun fichier `test_*.py` ni dossier `tests/` dans tout le dépôt** | — | `find . -iname "*test*"` : seuls les noms de workflow contiennent « test » | Les workflows CI n'ont rien à exécuter |
| Modèle agnostique | Non affirmé, mais implicite pour une réutilisation | `model_name="gpt-4o-mini"`/`"gpt-4.1"` codé en dur sur chaque agent | — | Lu | OpenAI uniquement — inutilisable tel quel avec le routeur de modèles d'ARENA |
| Cohérence de configuration | `.env.example` déclare `WALLET_PRIVATE_KEY` | `ultra_tools.py` lit en réalité `SOLANA_PRIVATE_KEY`, un nom **différent** | — | Lu | Bug réel : suivre `.env.example` à la lettre laisserait le trading non authentifié, silencieusement |

## Ce qui est réellement réutilisable

1. **Le principe de séparation des rôles** (Directeur / Quant / Risque /
   Exécution) — une bonne idée de *découpage*, indépendamment de son
   implémentation ici. C'est ce qu'ARENA reprend, adapté à son propre
   cadre d'agents (`core/agent/base_agent.py`), jamais copié.
2. **Le contrat de l'API Jupiter Price/Ultra** (endpoints, paramètres,
   forme des réponses) — utile comme référence pour une éventuelle
   intégration Solana future, **non implémentée ici** (mission §14 : lecture
   seule ou rien ; ARENA ne détient aucune clé de portefeuille).
3. Rien d'autre n'a été copié dans ARENA : ni le code, ni les prompts, ni
   les dépendances (`swarms`, `swarm-models`, `solders` ne sont pas ajoutés
   à `requirements.txt`).

## Ce qui a motivé la conception côté ARENA

L'absence de calcul réel dans le Quant Agent et le Risk Agent est le
défaut structurel central de ce dépôt, et c'est directement ce que
`core/finance/quant.py` et `core/finance/risk.py` corrigent : arithmétique
pure, testée, jamais un chiffre deviné par un modèle. Le manque de
séparation entre données et calcul (aucun endroit dédié à « juste
récupérer un prix ») a motivé `core/connectors/market_data.py` comme
connecteur autonome, avec son propre contrat de santé/permission — chose
qu'AutoHedge n'a pas du tout.

## Solana : classification honnête (mission §14)

| | État |
|---|---|
| `SOLANA_MARKET_DATA` | Fonctionne (chez AutoHedge, en isolation) ; **non repris dans ARENA** — CoinGecko couvre déjà BTC/ETH/SOL sans clé, sans dépendance `solders` |
| `SOLANA_ANALYSIS` | N'existe pas réellement chez AutoHedge (Quant Agent sans outils) |
| `SOLANA_ORDER_BUILDING` | Fonctionne chez AutoHedge en isolation, jamais câblé au produit |
| `SOLANA_REAL_EXECUTION` | Code réel et dangereux chez AutoHedge, injoignable depuis le produit, **jamais implémenté ni testé ici** |

ARENA n'intègre aucune des quatre couches Solana. Une intégration
future — lecture seule, sans clé de portefeuille — resterait à proposer
et à faire accepter séparément (voir *Ce que ça coûte si c'est faux*,
`docs/DECISIONS.md` DEC-0078).
