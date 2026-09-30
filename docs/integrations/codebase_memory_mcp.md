# Intégration — Codebase-Memory MCP dans ARENA

Ce document décrit l'intégration de **Codebase-Memory MCP** (DeusData, MIT, DEC-0201)
dans l'architecture d'ARENA.

---

## 1. Objectif et Rôle

Codebase-Memory MCP est le moteur d'intelligence structurelle de code d'ARENA.
Il transforme l'arborescence et les sources d'un dépôt logiciel en un graphe de connaissances
persistant (SQLite), permettant aux agents d'ingénierie (`RepoEngineerAgent`, `SWEAgent`, `DioumtoukayAgent`)
d'interroger la structure du code sans relire l'intégralité des fichiers texte.

```
Demande utilisateur ("où est gérée la permission d'envoi d'email ?")
        ↓
    Orchestrateur
        ↓
Agent (RepoEngineer / SWEAgent)
        ↓
Registre des connecteurs (`registre.executer("codebase_memory", ...)`)
        ↓
Connecteur Codebase-Memory (`core/connectors/codebase_memory.py`)
        ↓  (JSON-RPC 2.0 stdio via `core/mcp/stdio_transport.py`)
Binaire local `codebase-memory-mcp`
        ↓
Graphe de connaissances SQLite (AST Tree-Sitter + Hybrid LSP)
        ↓
Résultat ciblé enveloppé (`core/security/trust.py`)
        ↓
Raisonnement de l'agent & Réponse précise
```

---

## 2. Architecture de l'Intégration

### 2.1 Le Connecteur (`core/connectors/codebase_memory.py`)
Hérite de `Connecteur` (`core/connectors/base.py`) et applique toutes les garanties ARENA :
- Déclaration stricte des 13 capacités et de leurs permissions associées
- Sonde de santé `sonder()` mesurant la disponibilité réelle du binaire et des outils MCP
- Validation de sécurité des chemins (blocage des chemins sensibles `.env`, `.ssh`, `.gnupg`, etc.)
- Enveloppe de sécurité des données (`TrustLevel.EXTERNAL` via `core.security.trust.wrap`)
- Transport par sous-processus isolé (`ClientMcpStdio`), fermé immédiatement après usage

### 2.2 Inscription au Registre (`apps/backend/runtime.py`)
Le connecteur est enregistré de manière paresseuse sous le nom `"codebase_memory"` :
```python
registre.declarer(
    "codebase_memory",
    lambda: ConnecteurCodebaseMemory(acces=acces, journal=journal, file_attente=file_attente,
                                     crochets=crochets),
)
```

### 2.3 Matrice de Permissions (`config/permissions_services.yaml`)
```yaml
codebase_memory:
  read:        {decision: ALLOWED,      risque: LOW}
  index:       {decision: ALLOWED,      risque: LOW, interrupteur: WRITE_FILES}
  delete:      {decision: CONFIRMATION, risque: HIGH, interrupteur: DELETE}
```
- Toutes les opérations de lecture (`architecture`, `tracer_chemin`, `rechercher_graphe`, `requete_cypher`, etc.) sont en `ALLOWED / LOW`.
- L'indexation locale est en `ALLOWED / LOW` sous coupe-circuit `WRITE_FILES`.
- La suppression d'un index de projet exige une confirmation explicite (`CONFIRMATION / HIGH`) sous coupe-circuit `DELETE`.

---

## 3. Configuration et Variables d'Environnement

| Variable | Rôle | Valeur par défaut |
|---|---|---|
| `USMAN_CODEBASE_MEMORY_BIN` | Chemin absolu ou commande vers le binaire `codebase-memory-mcp` | `codebase-memory-mcp` (cherché dans le PATH) |
| `CODEBASE_MEMORY_BIN` | Alias alternatif pour la variable ci-dessus | `codebase-memory-mcp` |

---

## 4. Comportement de Repli (Fallback)

Si le binaire `codebase-memory-mcp` n'est pas installé ou indisponible :
1. `doctor.py` rapporte honnêtement `[CONF] Mémoire de code (Codebase Memory MCP)` avec la commande d'installation.
2. `RepoEngineerAgent` bascule automatiquement sur `gitingest` (résumé et arborescence), puis sur `repo_tool.get_tree()`.
3. `SWEAgent` bascule automatiquement sur l'outil ACI conventionnel `SWEACITool.search_dir()`.
4. Aucune exception n'est levée et l'ensemble de l'assistant reste pleinement opérationnel.

---

## 5. Cloisonnement des Mémoires

Codebase-Memory MCP est strictement isolé au sein de la mémoire de projet :
- **Mémoire Utilisateur** (`MemoirePersonnelle`, `core/memory/personnelle.py`) : conserve uniquement les préférences, faits et historique de l'utilisateur Ousmane Diop.
- **Mémoire de Projet & Codebase** : conserve les entités du graphe (classes, fonctions, routes, appels).
Aucune donnée issue de l'indexation de code n'est insérée dans la base de données de mémoire personnelle.

---

## 6. Désactivation ou Suppression

Pour désactiver Codebase-Memory MCP :
1. Supprimer ou commenter la ligne correspondante dans `apps/backend/runtime.py` ou retirer le binaire du PATH.
2. Aucun fichier de configuration ni base de données interne d'ARENA n'est altéré.
