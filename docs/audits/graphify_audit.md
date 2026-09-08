# Audit — Graphify comme graphe structurel du dépôt

*Demandé le 04/09/2026 : intégrer Graphify (Graphify-Labs) comme capacité de
graphe de connaissances/intelligence documentaire d'ARENA. Mesuré, pas lu
dans une description — le dépôt amont a été cloné et sa version réellement
installée a été testée sur le code de ce dépôt.*

---

## 1. Provenance (équivalent SOURCE.md)

| | |
|---|---|
| Dépôt officiel | https://github.com/Graphify-Labs/graphify |
| Révision intégrée | `33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2` (2026-08-30) |
| Date d'intégration | 2026-09-04 |
| Licence vérifiée | **Apache-2.0** (`LICENSE`, en-tête « Apache License, Version 2.0 ») — confirmée sur CETTE révision, pas supposée depuis une ancienne. `NOTICE` : « Copyright 2026 Safi Shamsi and the Graphify contributors. » Des portions antérieures à la relicence restent disponibles sous MIT (`LICENSE-MIT`), conservé dans le dépôt amont. |
| Distribution | Paquet PyPI officiel `graphifyy` (nom du paquet ; commande installée : `graphify`), version `0.9.53` |
| Ce qui est intégré | Le paquet `graphifyy==0.9.53` **tel quel depuis PyPI**, en dépendance directe (`requirements.txt`) — **aucun code source n'est copié ni vendu dans ce dépôt**. Contrairement à OpenTakeoff/WanGP/MoneyPrinterTurbo (services externes clonés à côté), Graphify est un paquet Python normal, installable comme `pypdf` ou `python-docx` — le même mécanisme que ces deux-là, pas celui d'un service à part. |
| Ce qui reste externe | Le code source de Graphify lui-même, ses extras optionnels (`[pdf]`, `[video]`, `[mcp]`, `[neo4j]`, tous les fournisseurs LLM) — **aucun n'est installé** ici, voir §3. |
| Modifications | Aucune. Utilisé strictement via sa CLI publique (`graphify update/query/path/explain/god-nodes`), jamais par import direct de ses modules internes. |

## 2. Ce que le paquet fait réellement (mesuré)

Projet Python pur (`pyproject.toml`, `uv.lock` — pas Node/TypeScript malgré la
confusion possible avec d'autres outils du même nom). Dépendances de base :
`networkx`, `numpy`, `rapidfuzz`, et ~25 grammaires `tree-sitter-<langage>`
(dont `tree-sitter-python`). **Extraction structurelle par tree-sitter, sans
appel modèle** — seul l'étiquetage des communautés (`graphify label`) en
demanderait un, jamais invoqué ici.

CLI installée (`graphify --help`) : `update <chemin>` construit/actualise le
graphe (`graphify-out/graph.json`, `graph.html`, `GRAPH_REPORT.md`) ;
`query "<question>"` fait une traversée BFS ; `path "A" "B"` le plus court
chemin ; `explain "X"` un nœud et ses connexions directes, avec provenance
`[EXTRACTED]`/`[INFERRED]` préservée ; `god-nodes` les nœuds les plus
connectés. Le paquet expose aussi des commandes `<ide> install/uninstall`
(Claude Code, Cursor, Codex…) qui écrivent des hooks/skills dans **d'autres**
outils d'IA — **jamais invoquées ici** : ARENA n'installe aucun hook dans
cette session ni dans aucun assistant de code, seule la capacité de graphe
elle-même est utilisée.

## 3. Ce qui n'a PAS été branché, et pourquoi

- **`[pdf]`, `[video]`, `[office]`** (ingestion de documents dans le graphe) :
  non installés. `tools/documents/reader.py` reste l'unique chemin de lecture
  PDF/DOCX/XLSX/PPTX d'ARENA — aucune duplication. L'ingestion de documents
  par Graphify est réelle en amont, mais **rien ne l'a vérifiée ici sur un
  vrai fichier** : `SUGGESTION — NON IMPLÉMENTÉE`, jamais simulée.
- **`[mcp]`** (`graphify-mcp`, serveur MCP dédié) : non installé. ARENA
  garde un seul orchestrateur/registre de connecteurs ; ajouter un second
  cadre MCP pour une capacité déjà accessible par CLI aurait été une
  duplication, pas une valeur ajoutée.
- **`[neo4j]`, `[falkordb]`** (bases de graphe externes) : non installés.
  Le graphe reste un fichier local (`graph.json`), cohérent avec DEC-0002
  (rien ne part chez un tiers).
- **Tout fournisseur LLM** (`kimi`, `openai`, `anthropic`, `gemini`,
  `bedrock`, `ollama`) : non installé. L'étiquetage sémantique des
  communautés (`graphify label`) n'est jamais invoqué — non vérifiable sur
  cette machine (pas d'Ollama, pas de GPU ici) et non nécessaire à la valeur
  mesurée (l'extraction structurelle de base répond déjà aux questions
  d'architecture, voir §4).

## 4. Ce que ça n'est pas

- **Pas un générateur de PDF.** Le devis PDF garde `core/connectors/devis.py`
  et `agents/plaquiste/devis_pdf.py`, inchangés (DEC-0041). Graphify
  cartographie la structure du code ; il n'écrit jamais de document final.
- **Pas un second RAG.** LightRAG et Microsoft GraphRAG (`tools/rag/`)
  résument des DOCUMENTS déposés à la main dans un espace de travail —
  fonction distincte, inchangée. Graphify lit directement le CODE SOURCE, par
  tree-sitter, sans espace de dépôt intermédiaire. Les deux graphes ne
  fusionnent jamais.
- **Pas un second système de permissions.** `core/connectors/graphify.py`
  passe par `ControleAcces`/`ResultatAction` comme tout connecteur — voir
  `config/permissions_services.yaml`, service `graphify`.

## 5. Mesuré pour de vrai, sur ce dépôt

Le graphe a été construit sur l'intégralité du dépôt d'Ousmane (pas un
fixture) via le connecteur réel (`ConnecteurGraphify.executer_confirmee`),
le 04/09/2026 :

```
13338 noeud(s), 25839 lien(s) — 13,9 s (tree-sitter, sans modele)
```

Questions posées et réponses obtenues (traversée BFS réelle, jamais
inventée) :

- *« quel connecteur gère le devis PDF ? »* → trouve `Devis`
  (`agents/plaquiste/devis_pdf.py:113`), `Connecteur`
  (`core/connectors/base.py:132`), et la chaîne réelle jusqu'à
  `DevisConnector`.
- *« qu'est-ce qui hérite de Connecteur ? »* → retrouve `Connecteur`
  (`core/connectors/base.py:132`) et sa docstring réelle (« Classe abstraite
  dont héritent tous les agents spécialisés »).
- **Hubs architecturaux réels** (`god-nodes --top 8`) : `Statut` (148),
  `PlaquisteAgent` (135), `Sante` (122), `ResultatAction` (120), `EtatSante`
  (119), `OrchestratorAgent` (112), `charger_metier()` (109), `succes()`
  (107) — une lecture correcte : ce sont bien les types qui traversent
  chaque connecteur de ce dépôt (`Statut`/`ResultatAction`/`EtatSante`,
  `core/actions/resultat.py` et `core/connectors/base.py`).

Le résultat de cette construction (`graphify-out/`, 28 Mo) n'est **pas**
versionné (`.gitignore`, DEC-0046) : reconstruit en une commande par qui en
a besoin.
