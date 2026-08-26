# ARENA — IA Personnelle Autonome

Système d'IA personnelle local-first conçu pour l'analyse de tendances, la compréhension de contenus vidéo/audio, la découpe intelligente et la création de médias format vertical.

## Architecture
- **Chef de Projet & Orchestrateur** : ARENA
- **Cerveau Local** : Ollama (Qwen 3.5 / Qwen 2.5 Coder)
- **Réseau / Matériel** : Windows 11 Pro / RTX A2000 12GB VRAM / 32GB RAM

## Démarrage rapide
Consulter docs/START_HERE.md.

## Configuration des secrets
Aucune clé ne doit figurer dans le dépôt. Copier `.env.example` vers `.env`, puis générer la clé de la passerelle :

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Reporter la valeur dans `ARENA_API_KEY` (fichier `.env`). Elle est lue par le backend (`/v1`), par LibreChat (`librechat.yaml`) et par Open WebUI. Sans elle, la passerelle `/v1` refuse toutes les requêtes.

## Tests et qualité
```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest                 # suite hors ligne
pytest -m integration  # exige Ollama, Docker, ffmpeg, Chromium selon les tests
```

## Documents
Dépose tes documents dans `data/documents/` — sous-dossiers acceptés.

Formats lus : `.pdf`, `.docx`, `.txt`, `.md`, `.csv`. Un fichier d'un autre
format est **ignoré et compté à part**, jamais avalé en silence.

Ce dossier est exclu de Git : tes devis et factures ne partent nulle part.

Pour les indexer :

```bash
python scripts/indexer_documents.py
```

La commande vérifie d'abord qu'Ollama tourne et que le modèle d'embeddings est
installé (`ollama pull nomic-embed-text`). **S'ils manquent, rien n'est indexé et
rien n'est noté** — mieux vaut un refus franc qu'un index à moitié fait.

Elle peut être relancée autant de fois que voulu : un document inchangé n'est
jamais réindexé.

## Scan de secrets
Aucune clé ne doit entrer dans le dépôt. La CI le vérifie à chaque `push` ; pour
le contrôler avant de committer :

```bash
gitleaks detect --source . --no-git --redact --config .gitleaks.toml
```

Les règles propres au projet sont dans `.gitleaks.toml` : les règles standard de
gitleaks ne repéraient pas la clé de `librechat.yaml`, trop courte pour leur
seuil d'entropie.

## Licence
Logiciel propriétaire, **tous droits réservés** (voir `LICENSE`). Le code est
publié à titre de référence uniquement : aucune réutilisation, copie,
modification ni redistribution n'est autorisée sans accord écrit préalable.
