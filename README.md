# Usman — IA Personnelle Autonome

Système d'IA personnelle local-first conçu pour l'analyse de tendances, la compréhension de contenus vidéo/audio, la découpe intelligente et la création de médias format vertical.

## Architecture
- **Chef de Projet & Orchestrateur** : Usman
- **Cerveau Local** : Ollama (Qwen 3.5 / Qwen 2.5 Coder)
- **Réseau / Matériel** : Windows 11 Pro / RTX A2000 12GB VRAM / 32GB RAM

## Démarrage rapide
Consulter docs/START_HERE.md.

## Configuration des secrets
Aucune clé ne doit figurer dans le dépôt. Copier `.env.example` vers `.env`, puis générer la clé de la passerelle :

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"