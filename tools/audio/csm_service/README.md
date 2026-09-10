# Service CSM d'ARENA

Un serveur HTTP local, minuscule, qu'**ARENA ne lance pas elle-meme** — le
proprietaire le demarre, dans son propre environnement Python isole, sur sa
RTX A2000. `core/connectors/csm.py` (dans le process principal d'ARENA) lui
parle ensuite par HTTP, exactement comme il parle a VoiceStudio.

Pourquoi separe : `docs/audits/sesame_csm_audit.md` (section « Isolation des
dependances »). En bref — `torch`/`transformers` alourdiraient et
fragiliseraient l'environnement principal d'ARENA pour un seul moteur de voix
parmi une quinzaine.

## Installer

```bash
cd tools/audio/csm_service
python3.10 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

Sous Windows, `triton` ne s'installe pas directement : utiliser
`pip install triton-windows` a la place (note du README officiel
`SesameAILabs/csm`, verifiee le 10/09/2026).

## Autoriser l'accès au modèle

CSM-1B est un depot Hugging Face **a acces conditionne** (« gated ») : il
faut un compte HF, accepter les conditions sur les deux pages suivantes, puis
se connecter localement.

1. https://huggingface.co/sesame/csm-1b — accepter les conditions.
2. https://huggingface.co/meta-llama/Llama-3.2-1B — accepter les conditions
   (le tokenizer texte de CSM en depend).
3. `huggingface-cli login` dans le meme environnement virtuel.

Sans ces trois etapes, `/generate` repond `409` avec le message exact de
Hugging Face (verifie en direct le 10/09/2026 dans ce depot — un vrai
`401 Client Error` gated, pas une supposition).

## Lancer

```bash
python server.py
```

Ecoute par defaut sur `127.0.0.1:8901`. Variables d'environnement :

| Variable | Defaut | Effet |
|---|---|---|
| `CSM_HOST` | `127.0.0.1` | Interface d'ecoute |
| `CSM_PORT` | `8901` | Port |
| `CSM_UNLOAD_AFTER_S` | `900` | Decharge le modele apres ce delai d'inactivite (`0` = jamais) |

Le modele ne se charge **pas** au demarrage — seulement au premier appel a
`/generate` (mission §14 : ne pas monopoliser la carte au lancement).

## Tester ce service (pas la suite d'ARENA)

```bash
pip install pytest
pytest test_server.py -q
```

**Ces tests ne font PAS partie de `pytest tests/` d'ARENA** —
`pyproject.toml` y declare `testpaths = ["tests"]`, qui ne descend jamais
dans `tools/`. C'est volontaire : ce dossier depend de `torch`, absent de
l'environnement principal d'ARENA, et l'y forcer casserait la suite
principale pour tout le monde.

## Ce que ce service garantit

Detail complet → docstring de `server.py`. En resume :

1. Le filigrane de Sesame (`watermark.py`) est **toujours** applique — une
   generation dont le filigrane echoue est un `500`, jamais un fichier sans
   provenance renvoye avec un `200`.
2. Le contexte conversationnel ne grandit qu'avec de l'audio que CE service a
   lui-meme genere dans la meme requete — jamais un fichier fourni par
   l'appelant.
3. Rien ne charge avant le premier appel a `/generate`.
