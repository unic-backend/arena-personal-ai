# TÂCHE ACTUELLE

ID: TASK-000041
TÂCHE : Audit de sécurité et de fiabilité — v1.7.0
ÉTAT : [x] TERMINÉ

## Ce qui a été corrigé
15 défauts identifiés lors de l'audit, tous vérifiés par un test :
sécurité de la passerelle, validation des chemins, bac à sable Docker,
secrets, LightRAG, GraphRAG, dépendances, base de données, documentation.

## Prochaines pistes possibles
- Indexer des documents dans GraphRAG pour le rendre exploitable.
- Arbitrer le budget VRAM entre les deux modèles Ollama (15,6 Go pour 12 Go).
- Décider si SWEAgent / RepoEngineerAgent doivent pouvoir modifier des fichiers
  (aujourd'hui volontairement en lecture seule).
- Servir Tailwind en local pour que l'interface fonctionne hors ligne.
