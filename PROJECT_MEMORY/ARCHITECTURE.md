# ARCHITECTURE — comment les morceaux se parlent

*Mémoire opérationnelle. Aucun code recopié ici. Mise à jour : 2026-08-28.*

---

## Le chemin d'une phrase, de bout en bout

```
son interface (PWA)
  └─ POST /agent/stream          apps/backend/routers/pwa_gateway.py
       ├─ orchestrator.analyze_intent()      → une intention parmi 15
       ├─ voie_pour(intention)               → budget autorisé (core/execution/voies)
       ├─ si intention spécialisée → dispatch_request()   routers/chat.py
       │     └─ l'agent concerné → registre → connecteur → service externe
       └─ sinon → prompt_systeme() → fast_provider.generate_stream()
             ├─ souvenirs_pertinents()  → sémantique + consolidation
             └─ contenu des pièces jointes, enveloppé (trust.py)
  puis : la durée du tour entre au rapport de mesures (core/execution/mesures)
```

## Sous-systèmes

### Résultat d'action — `core/actions/resultat.py`
7 statuts. **Un `SUCCESS` sans preuve ne se construit pas** (le constructeur
lève). Tout connecteur en dépend. Ne pas toucher sans raison.

### Journal — `core/actions/journal.py`
Les 9 champs de toute action à effet externe, secrets masqués avant écriture.
SQLite, même base que la mémoire, table à part. **Lu par l'agent vidéo** pour
retrouver l'identifiant de la dernière génération.

### Permissions — `core/permissions/`
Deux couches : 9 coupe-circuits généraux (`config/permissions.yaml`) et une
politique fine compte × service × action × risque
(`config/permissions_services.yaml`). **La plus stricte gagne.** C'est elle qui
transforme `action="send"` ou `"create"` ou `"generate"` en CONFIRMATION.

### File d'attente — `core/actions/attente.py`
Déposer n'exécute rien. Confirmer deux fois n'exécute qu'une fois. Une
confirmation périmée ne part pas.

### Connecteurs — `core/connectors/base.py`
Classe de base qui garantit, dans cet ordre : capacité déclarée → permission →
**confirmation** → santé → quota → exécution → journal. Une sous-classe ne peut
pas contourner ces contrôles en oubliant de les appeler.

> **Conséquence à retenir** : la confirmation tombe **avant** que
> `_executer()` ne soit appelé. Un connecteur n'a aucun moyen d'envoyer sans
> demander. C'est structurel, pas une politesse.

### Mémoire — `core/memory/`
`personnelle` (4 types × 4 natures) → `recuperation` (4 signaux lexicaux) →
`semantique` (5ᵉ signal, embeddings locaux ; retombe en `MODE_LEXICAL` sans
Ollama) → `consolidation` (une chose dite une fois).
L'**index des vecteurs vit dans `runtime.py`** et dure : recréé à chaque
question, son cache serait vide à chaque question.

### Exécution — `core/execution/`
`voies` : 4 régimes et leurs budgets, consultés par l'orchestrateur juste après
le classement ; le budget mémoire du prompt en découle.
`mesures` : chronomètre chaque tour et le confronte à la cible de sa voie ;
servi par `GET /api/observability`.
`travaux` : file de fond bornée ; le chat ne l'attend jamais.

### Frontière de confiance — `core/security/trust.py`
Tout texte étranger (pièce jointe, e-mail, page web) entre **enveloppé** au
niveau `EXTERNAL`/`DOCUMENT`. Un sujet d'e-mail est une donnée, pas une consigne.

## Intégrations externes (services séparés, jamais dans ce dépôt)

| Service | Connecteur | Contrat |
|---|---|---|
| Ollama | `core/models/ollama_provider.py` | HTTP local, 11434 |
| WanGP | `core/connectors/wan2gp.py` | MCP local, 8765 |
| MoneyPrinterTurbo | `core/connectors/moneyprinter.py` | HTTP local, 8080, `/api/v1` |
| Gmail | `core/connectors/gmail.py` | API Google + `google_oauth.py` |
| Google Calendar | `core/connectors/calendrier.py` | idem, **même identifiant OAuth** |
| GalsenAPI | `core/connectors/galsen.py` | API publique, sans clé |
| Devis PDF | `core/connectors/devis.py` | local (reportlab) |

**Règle d'intégration (DEC-0008)** : un projet tiers tourne **à côté**, avec ses
dépendances et ses clés ; ARENA lui parle par son API. Aucune ligne, aucune clé
n'entre ici.

## Contraintes qui ne se négocient pas

1. Une capacité absente se **rapporte** (`NOT_CONFIGURED`, `UNKNOWN`), elle ne
   se simule pas.
2. Un champ absent vaut `None`, jamais `0`.
3. Aucun secret dans le dépôt, aucun `.env` versionné, jamais de push direct
   sur `master`.
4. Toute garantie déclarée doit avoir été **sabotée** une fois pour prouver
   qu'un test la tient.
