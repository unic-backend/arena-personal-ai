# ARCHITECTURE TECHNIQUE - ARENA

## VUE GLOBALE
[Utilisateur] <--> [ARENA Frontend] <--> [Backend API / Orchestrateur]
                                            |
                                 +----------+----------+
                                 |                     |
                          [IA Local / Ollama]   [Agents / Outils]
                                                       |
                                            [Media / Social / Data]

## ABSTRACTION DU MODÈLE (Local-First)
ModelProvider
+-- LocalModel (Ollama - Qwen 3.5 / 2.5)
+-- OptionalCloudModel (Claude / OpenAI)
+-- FutureModel
