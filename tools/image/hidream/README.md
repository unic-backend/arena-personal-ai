# Worker HiDream-I1 d'ARENA

Mission ARENA x HIDREAM-I1 (DEC-0085). Genere des images haute qualite avec
[HiDream-I1](https://github.com/HiDream-ai/HiDream-I1) (17B parametres, MIT),
dans un environnement Python **isole** de l'environnement principal d'ARENA.
`core/connectors/hidream.py` lui parle par HTTP — aucune ligne de ce dossier
n'est importee par le reste du depot.

Rapport d'audit complet, chiffres materiels et decision finale sur le
materiel du proprietaire → `docs/audits/hidream_i1_audit.md`.

## Avant d'installer : ce que ça exige reellement

Mesure directement sur HuggingFace (pas suppose) :

| Composant | Taille |
|---|---|
| HiDream-I1-Full / Dev / Fast (chacune) | 47.2 Go (transformer 17B bf16 + 3 encodeurs texte + VAE) |
| `meta-llama/Meta-Llama-3.1-8B-Instruct` (4e encodeur texte, obligatoire, **jamais empaquete**) | ~16 Go bf16 |
| **Total par variante** | **~63 Go sur disque**, ~autant en VRAM sans offload |

**RTX A2000 12 Go + 32 Go RAM (le materiel de ce projet) ne peut PAS charger
un HiDream complet, meme quantifie, meme en offload — la RAM systeme seule
(32 Go) est plus petite que le modele (~63 Go).** Voir l'audit pour le
detail du calcul (`core/production/hidream_strategie.py`). Ce worker
demarre quand meme : `/health` mesure honnetement ce dont IL dispose, et
`core/connectors/hidream.py` refuse `generer` avant tout essai si le
materiel rapporte ici ne suffit pas — jamais un OOM decouvert en route.

## Licence — deux licences, pas une

- **HiDream-I1** (code de ce worker inclus) : MIT.
- **`meta-llama/Meta-Llama-3.1-8B-Instruct`** : licence communautaire Llama
  3.1 de Meta — **PAS MIT**. Acceptation obligatoire sur HuggingFace avant
  tout telechargement (voir plus bas).

## Installer

```sh
cd tools/image/hidream
python3.11 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate sous Windows
pip install -r requirements.txt
huggingface-cli login            # accepter la licence Llama 3.1 sur HuggingFace d'abord
python serveur_hidream.py        # ecoute sur 127.0.0.1:8090 par defaut
```

Variables d'environnement :

| Variable | Defaut | Role |
|---|---|---|
| `HIDREAM_HOST` / `HIDREAM_PORT` | `127.0.0.1` / `8090` | Ou le worker ecoute |
| `HIDREAM_CACHE_DIR` | `~/.cache/hidream-arena` | Ou verifier l'espace disque |
| `HIDREAM_OUTPUT_DIR` | `<cache>/sorties` | Ou les images produites sont ecrites |
| `HIDREAM_UNLOAD_AFTER_S` | `600` | Dechargement apres inactivite (0 = jamais) |

Cote ARENA (`core/connectors/hidream.py`) :

| Variable | Defaut | Role |
|---|---|---|
| `HIDREAM_WORKER_URL` | `http://127.0.0.1:8090` | Ou joindre ce worker — change pour un serveur GPU distant (mission §23-24) sans toucher au code |
| `HIDREAM_WORKER_API_KEY` | (vide) | Jeton `x-api-key`, si le worker est expose au-dela de `localhost` |

## Contrat HTTP

- `GET /health` — jamais de chargement lourd ; rend `model_loaded`,
  `variantes_disponibles` (deja en cache local), et `materiel`
  (`gpu`/`ram`/`disque` mesures a l'instant de l'appel).
- `POST /generate` — `{prompt, variante, negative_prompt?, width?, height?,
  seed?, num_inference_steps?, guidance_scale?}` -> `{job_id, state}`,
  immediatement (le chat ARENA n'attend jamais).
- `GET /jobs/{id}` — `{state, images, seed, error, ...}`.
- `POST /jobs/{id}/cancel` — annulation cooperative (best-effort sur une
  tache deja en generation, effective sur une tache encore en attente).

## Tester la couche HTTP/gestion de taches (sans GPU)

`_generer_en_fond`/`_charger_pipeline` n'importent torch/diffusers qu'EN
INTERNE — la couche HTTP se teste donc sans les installer :

```sh
pip install fastapi httpx pytest
pytest test_server.py -q
```

`pyproject.toml` d'ARENA (`testpaths = ["tests"]`) ne scanne pas ce
dossier : ces tests sont invisibles a la suite principale, volontairement.
