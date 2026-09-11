# Audit — Comfy-Org/ComfyUI

**Dépôt étudié** : https://github.com/Comfy-Org/ComfyUI
**Commit audité** : `6338e4bd428247a4a8843496aa98fb7f2a9d3632` (10/09/2026, tête du
dépôt au 11/09/2026).
**Licence** : **GPL-3.0** — vérifiée sur le fichier `LICENSE` du clone réel, pas sur le
badge du README seul.
**Méthode** : clone réel (`git clone --depth 1`), lecture directe de `server.py` (routes
API), `execution.py` (file d'attente, historique, evenements), `comfy/model_management.py`
(gestion VRAM), `nodes.py` (chargement des extensions), `SECURITY.md` (modèle de menace
officiel), `script_examples/basic_api_example.py` (format JSON réel « API »),
`requirements.txt`. Rien pris sur la seule foi du README.

## Ce que le dépôt est réellement

Un **serveur complet**, pas une bibliothèque — contrairement à HiDream-I1
(`docs/audits/hidream_i1_audit.md`), ARENA n'écrit ici **aucun worker** : ComfyUI expose
déjà sa propre API HTTP + WebSocket, prête à l'emploi.

| Domaine | Fichier(s) | Constat |
|---|---|---|
| API serveur | `server.py` | `POST /prompt` (soumet un graphe « API format »), `GET /queue`, `GET /history/{id}`, `POST /interrupt`, `POST /free` (décharge les modèles), `GET /system_stats` (VRAM/RAM réelles, par appareil), `GET /models/{folder}` (liste les checkpoints installés), `GET /view` (récupère un fichier de sortie) |
| Format de workflow | `script_examples/basic_api_example.py` | Un graphe de nœuds `{id: {class_type, inputs}}` — les `inputs` référencent d'autres nœuds par `[id, index_sortie]`. Aucun schéma déclaré : ComfyUI exécute tout graphe syntaxiquement valide, **sans distinguer un graphe de confiance d'un graphe arbitraire** |
| Progression | `execution.py` | Événements WebSocket réels : `execution_start`, `executing` (par nœud), `executed` (par nœud, avec sa sortie), `execution_error` — jamais une estimation |
| Historique | `execution.py::PromptQueue.task_done` | `history[prompt_id] = {"prompt": [...], "outputs": {noeud: {...}}, "status": {"status_str": "success"\|"error", "completed": bool, "messages": [...]}}` |
| Gestion mémoire | `comfy/model_management.py` | `VRAMState` (NORMAL/LOW/NO_VRAM/HIGH_VRAM/DISABLED/SHARED) — **« smart memory » activée par défaut** : ComfyUI décharge lui-même les poids vers la RAM quand la VRAM manque (`DISABLE_SMART_MEMORY` sinon), sans intervention côté appelant |
| Extensions tierces | `nodes.py::load_custom_node`/`init_external_custom_nodes` | Charge **automatiquement**, via `importlib`, tout module Python posé dans `custom_nodes/` au démarrage — **aucune isolation, aucune revue** |
| Sécurité (modèle officiel) | `SECURITY.md` | Cite textuellement : « Custom nodes are arbitrary Python code and are trusted as much as any other software the user chooses to install » — ComfyUI **ne protège pas** contre un nœud tiers malveillant, il suppose que l'utilisateur ne l'installe pas. Serveur lié à `127.0.0.1` par défaut ; l'exposer (`--listen`) est explicitement hors du périmètre de sécurité amont |
| Dépendances | `requirements.txt` | `torch`, `torchvision`, `torchaudio`, `transformers>=4.50.3`, `safetensors>=0.4.2`, `aiohttp`, `SQLAlchemy` — pile lourde, jamais installée dans l'environnement principal d'ARENA (même raison que HiDream/WanGP/CSM) |

## Ce qui n'a PAS pu être confirmé, ou change la conception

- **Aucun schéma d'entrée déclaré.** ComfyUI ne valide un graphe que syntaxiquement
  (types de nœuds connus, liens cohérents) — jamais « ce paramètre est un entier entre 1
  et 150 ». La mission (§8/§9) exige un schéma contrôlé : **ARENA le construit lui-même**
  (`core/production/comfyui_workflows.py`), ComfyUI ne le fournit pas.
- **Aucune authentification native.** Le modèle de menace amont suppose un usage local,
  monoposte. Un futur worker distant devra porter sa propre couche d'authentification —
  ComfyUI n'en propose aucune (mission §32, documenté comme limite, jamais résolu ici
  faute d'un serveur distant réellement configuré).
- **`/system_stats` ne rapporte pas le disque.** Contrairement à `/health` du worker
  HiDream (qui mesure VRAM+RAM+disque en un seul appel), ComfyUI ne mesure que
  VRAM/RAM. La décision de ressources ComfyUI (`core/production/comfyui_strategie.py`)
  s'appuie donc sur `core/production/materiel.py::mesurer_disque` (mesure locale ARENA)
  pour un plancher d'espace de SORTIE — pas pour vérifier qu'un checkpoint tiendrait sur
  le disque, puisque ComfyUI n'en télécharge jamais aucun via ce connecteur (mission
  §12/§25 : le checkpoint doit déjà être installé, vérifié par `GET /models/checkpoints`
  avant tout envoi).

## Comparaison avec l'architecture ARENA existante (audit préalable, §3)

| Capacité | État ARENA avant cette mission | Verdict |
|---|---|---|
| Image texte→image | `core/connectors/hidream.py` (DEC-0085) — ACTIF, mais un seul modèle (HiDream-I1), classé `SERVER_ONLY_RECOMMENDED` sur ce matériel | Backend ALTERNATIF ajouté (`core/connectors/comfyui.py`), même capacité `image_generation`, jamais un second agent |
| Vidéo | `core/connectors/wan2gp.py`, `core/production/plan_video.py` — ACTIFS | Non couplés au graphe vidéo. `image_to_video` (Stable Video Diffusion, DEC-0088) est **implémenté et STABLE** comme workflow direct du connecteur ComfyUI, mais n'est PAS câblé dans `plan_video.py::CAPACITES_VIDEO` — le routeur existe, le câblage au graphe attend un besoin mesuré (mission §17) |
| Personnages (Agent Heroes-like) | `core/production/personnage_video.py` (DEC-0084) — ACTIF, `core/connectors/xaar_kaname.py` pour le repositionnement de visage | `character_image` (LoRA sur checkpoint standard, DEC-0088) est **implémenté et STABLE**, mais non couplé à `personnage_video.py` — même principe que ci-dessus : le routeur d'abord, jamais un couplage point à point sans besoin mesuré (mission §17/§19) |
| Audio | `core/connectors/audio_voix.py`, `core/connectors/csm.py`, `core/audio/routage_tts.py` — ACTIFS | Non touchés — aucun avantage concret mesuré à faire passer l'audio par ComfyUI (mission §21) |
| 3D | `core/connectors/architecture_3d.py` (DEC-0070, Pascal) — ACTIF, précision BIM | Non touché — la mission distingue explicitement 3D générative et 3D d'ingénierie (§22) ; aucun besoin mesuré de 3D générative créative cette mission |
| Registre d'agents cross-espace | `core/agent/capacites.py` — ACTIF | **Non étendu** — même limite que DEC-0086/DEC-0085 : ce registre ne connaît que les espaces de la barre latérale PWA, "ComfyUI" n'en est pas un |
| Registre de connecteurs | `core/connectors/registre.py` — ACTIF | Réutilisé tel quel : `comfyui` déclaré à côté de `hidream`, `wan2gp`, etc. Zéro second registre |
| Permissions | `config/permissions_services.yaml`, service `image_generation` — ACTIF | Étendu d'UNE action (`unload`, ALLOWED/LOW) — jamais un second service |
| Validation d'artefact | `core/production/artefact_image.py` (DEC-0085) — ACTIF | Réutilisé tel quel pour les sorties ComfyUI — zéro second validateur |
| Job/suivi de tâche | `core/connectors/suivi_video.py::suivre_generation` — ACTIF | Compatible par construction : `etat_travail` rend la même forme `{done, result: {success, generated_files}}` |

**Aucun agent-plateforme dupliqué. Aucun second registre, routeur, ou validateur
d'artefact.**

## Ce qui a été adopté de ComfyUI

1. Le **format « API » du graphe** — repris à l'identique dans le gabarit
   `text_to_image` (`core/production/comfyui_workflows.py`), vérifié ligne à ligne contre
   `script_examples/basic_api_example.py`.
2. La **gestion mémoire automatique** (« smart memory ») — reconnue comme argument
   technique réel en faveur de ComfyUI sur du matériel contraint : elle motive les
   classifications `LOCAL_SLOW`/`LOCAL_OFFLOAD` de `comfyui_strategie.py`, qu'aucune
   estimation HiDream équivalente ne pouvait offrir (le worker HiDream doit implémenter
   son propre offload séquentiel manuel).
3. Le **contrat `/system_stats` par appareil** — traduit directement dans les mêmes
   types que `core/production/materiel.py` (`EtatGpu`/`EtatRam`), jamais un second modèle
   de matériel.

## Ce qui a été explicitement rejeté

1. **Charger des nœuds personnalisés tiers.** Mission §10 : zéro confiance par défaut.
   Aucun `custom_nodes/` n'est installé, référencé, ou recommandé ici — seuls les nœuds
   natifs (`KSampler`, `CheckpointLoaderSimple`, `ControlNetApplyAdvanced`, `LoraLoader`,
   `SVD_img2vid_Conditioning`, etc.) apparaissent dans les six workflows implémentés
   (DEC-0087 puis DEC-0088).
2. **Envoyer un graphe JSON libre.** Rejeté par construction : `core/connectors/comfyui.py`
   n'accepte qu'un `workflow_id` du registre contrôlé + des paramètres nommés, jamais un
   graphe (mission §8/§30).
3. **Automatiser l'interface graphique.** Rejeté — uniquement l'API HTTP (mission §7).
4. **Un second registre de modèles.** Rejeté — `GET /models/checkpoints` interrogé en
   direct à chaque génération, jamais mis en cache dans une base ARENA séparée.
5. **Router HiDream à travers ComfyUI.** Étudié (mission §15) : ComfyUI n'a jamais
   exécuté HiDream-I1 dans cette mission (aucun serveur ComfyUI disponible ici pour le
   mesurer), donc aucune comparaison chiffrée n'existe. Les deux restent des backends
   séparés et indépendants ; une comparaison réelle attend un serveur ComfyUI réellement
   lancé — documentée comme limite, pas devinée.

## Local Acceptance — ce qui a été mesuré, pas supposé

Aucun serveur ComfyUI n'a tourné dans cet environnement de développement (pas de GPU,
pas d'installation ComfyUI ici) : comme pour HiDream-I1, la classification matérielle
finale (RTX A2000 12 Go, 32 Go RAM, mission §13) vient du calcul déterministe
(`core/production/comfyui_strategie.py::decider_strategie`), vérifié par
`tests/core/test_comfyui_strategie.py` avec le materiel réel du propriétaire, jamais
mesuré à l'œil :

```
text_to_image, VRAM libre ~11 Go (rien d'autre charge) -> LOCAL_FAST
text_to_image, VRAM libre ~200 Mo (GPU deja occupe)     -> UNSUPPORTED/LOCAL_OFFLOAD
                                                            (selon la RAM disponible)
```

**Différence qualitative avec HiDream (DEC-0085, classification E) : un workflow
ComfyUI LÉGER (checkpoint SD1.5-like, ~4 Go) peut réellement tenir sur cette carte —
contrairement à HiDream-I1 (~63 Go, RAM système elle-même insuffisante pour l'offload).**
ComfyUI n'est donc PAS classé `SERVER_ONLY_RECOMMENDED` globalement : la classification
dépend du WORKFLOW demandé, jamais d'un moteur monolithique — voir
`docs/DECISIONS.md`, DEC-0087, section Vérification, pour la classification par
workflow.
