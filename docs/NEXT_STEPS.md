# PROCHAINES ÉTAPES

*Mis à jour le 26/08/2026. Les étapes précédentes décrivaient encore la Phase 0
(« créer README.md ») alors que la Phase 7 était engagée.*

La liste complète et priorisée vit dans `documents/USMAN_ENGINEERING_WORKLOG.md`,
section `PENDING`. Voici les trois prochaines.

## 1. Rotation de la clé API et purge de l'historique Git — **bloqué**

C'est le dernier point critique. La clé qui protège la passerelle `/v1` est
lisible dans l'historique du dépôt public, au premier commit.

Deux actions, dans cet ordre :

1. **Générer une nouvelle clé** et la mettre dans `.env`. C'est la seule chose
   qui neutralise vraiment l'ancienne.
   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. **Purger l'historique** avec `git filter-repo`. Opération irréversible :
   elle réécrit tous les commits et casse les clones existants.
   **Nécessite l'accord explicite du propriétaire.**

## 2. Scan de secrets en CI

Ajouter `gitleaks` au workflow GitHub Actions, pour qu'un secret commité fasse
échouer la CI au lieu de passer inaperçu.

## 3. Mesurer avant d'optimiser

Aucune mesure de performance n'existe à ce jour. Trois commandes à lancer sur la
machine, une par une, et à recopier dans le worklog :

```
ollama list
ollama ps
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

La première répond à une question ouverte depuis le début : **le modèle
`qwen3.5:9b` existe-t-il réellement ?** S'il n'existe pas, Ollama répond avec un
autre modèle sans rien signaler.
