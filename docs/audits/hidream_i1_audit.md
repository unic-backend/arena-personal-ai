# Audit — HiDream-ai/HiDream-I1

**Dépôt étudié** : https://github.com/HiDream-ai/HiDream-I1
**Commit audité** : `5f92bab45f1dfb1e794ee357286a5b837eaf4400` (16/07/2025,
tête du dépôt au 10/09/2026).
**Licence du code et des poids** : **MIT** — vérifiée à DEUX endroits, pas
un seul : le `LICENSE` du clone réel, et le tag `license: mit` affiché
directement sur les pages HuggingFace `HiDream-ai/HiDream-I1-Full` et
`HiDream-ai/HiDream-I1-Fast`.
**Méthode** : clone réel, lecture directe de `inference.py`,
`hi_diffusers/pipelines/hidream_image/pipeline_hidream_image.py` (726
lignes), `hi_diffusers/models/transformers/transformer_hidream_image.py`,
`requirements.txt` ; tailles de checkpoints relevées directement sur les
pages HuggingFace (`HiDream-I1-Full`, `HiDream-I1-Dev`, `HiDream-I1-Fast`).
Rien pris sur la seule foi du README.

---

## Ce que le dépôt est réellement

Un modèle de diffusion texte→image, **17 milliards de paramètres**,
transformer **Mixture-of-Experts épars** (4 experts routés, 2 activés par
jeton — `hi_diffusers/models/moe.py`), 16 couches. Trois variantes
publiées — **Full** (50 pas, guidance 5.0), **Dev** (28 pas, distillée,
guidance 0.0), **Fast** (16 pas, distillée, guidance 0.0) — même
architecture, même script d'inférence. Intégré **officiellement** dans
`diffusers` depuis le 11/04/2025 (`HiDreamImagePipeline`) : la voie
recommandée par le README amont lui-même n'exige donc pas de vendorer
`hi_diffusers/`.

**Quatre encodeurs texte**, pas un ni deux : CLIP-L, OpenCLIP-bigG, T5-XXL
(les trois dans le dépôt HiDream) et **`meta-llama/Meta-Llama-3.1-8B-
Instruct`** en quatrième — chargé séparément, jamais empaqueté avec le
modèle, gated sur HuggingFace (licence communautaire Llama 3.1, **pas**
MIT).

## Tailles réelles, mesurées sur HuggingFace (pas estimées)

| Composant | Taille |
|---|---|
| HiDream-I1-Full (dépôt HF complet : transformer + 3 encodeurs + VAE) | **47.2 Go** |
| HiDream-I1-Dev (même mesure) | **47.2 Go** |
| HiDream-I1-Fast | 17B paramètres confirmés, taille non re-mesurée séparément (même architecture) |
| `meta-llama/Meta-Llama-3.1-8B-Instruct` (bf16, 8B params) | **~16 Go** (connu publiquement, pas empaqueté) |
| **Total par variante, bf16, sans offload** | **~63 Go** disque et VRAM |

## Matrice de validation

| Capacité annoncée | Vérifié comment | État |
|---|---|---|
| Texte→image, prompt/negative_prompt | `pipeline_hidream_image.py:512-538`, 4 encodeurs, `negative_prompt`×4 variantes | **IMPLEMENTED** |
| Résolutions multiples | 7 résolutions fixes dans `inference.py` (`RESOLUTION_OPTIONS`) | **IMPLEMENTED**, liste fermée |
| Seed/reproductibilité | `torch.Generator("cuda").manual_seed(seed)` | **IMPLEMENTED** |
| Guidance scale / steps configurables | Paramètres du `__call__`, valeurs par défaut fixées par variante | **IMPLEMENTED** |
| CPU offload | `model_cpu_offload_seq` déclaré (ligne 112) — active `enable_model_cpu_offload()`/`enable_sequential_cpu_offload()` (API diffusers générique) | **IMPLEMENTED au niveau pipeline, JAMAIS utilisé dans `inference.py`** (`.to("cuda")` direct, sans offload) |
| VAE slicing/tiling | `enable_vae_slicing()`/`enable_vae_tiling()` définies (lignes 436, 450) | **IMPLEMENTED**, non utilisées dans le script de référence |
| Quantification (bitsandbytes/quanto/INT8/INT4) | Recherche exhaustive : aucune trace dans le dépôt | **NOT_PRESENT en amont** — faisable en théorie via `diffusers`/`transformers` génériques, **jamais vérifié sur cette architecture MoE par ce dépôt** |
| LoRA/adaptateurs | `PeftAdapterMixin` sur la classe transformer (ligne 231) — support au niveau MODÈLE, mais **aucun `LoraLoaderMixin`/`load_lora_weights()`** sur le pipeline | **IMPLEMENTED partiellement** : adaptateur PEFT manuel possible, pas de raccourci pipeline |
| Image-à-image / édition | Absent du `__call__` (aucun paramètre `image`) | **NOT_PRESENT dans HiDream-I1** — existe dans le dépôt séparé `HiDream-E1`/`E1-1`, hors périmètre de cette mission |
| Génération par lot | `num_images_per_prompt` existe au niveau pipeline, fixé à 1 dans `inference.py` | **IMPLEMENTED au niveau pipeline** |
| Flash Attention | Recommandée par le README, jamais imposée dans le code | **OPTIONAL**, sonde honnête nécessaire |

## Ce qui est réellement réutilisable (idées, jamais code)

1. **L'intégration diffusers officielle** — reprise directement (le worker
   `tools/image/hidream/serveur_hidream.py` importe `HiDreamImagePipeline`
   depuis `diffusers`, jamais depuis `hi_diffusers/`) : c'est le README
   amont lui-même qui recommande cette voie.
2. **La configuration par variante** (`MODEL_CONFIGS` dans `inference.py` :
   guidance/steps fixés par variante) — reprise à l'identique dans
   `CONFIGS_VARIANTE` du worker, valeurs vérifiées ligne à ligne contre le
   dépôt étudié.
3. **`model_cpu_offload_seq`** — le worker active
   `enable_sequential_cpu_offload()` (jamais utilisé dans le script amont,
   mais réellement supporté par la classe pipeline) : c'est la SEULE voie
   qui pourrait faire tenir un modèle de cette taille sur une carte de
   12 Go — voir Local Acceptance Decision.

## Ce qui n'a pas été repris, et pourquoi

- **`hi_diffusers/` (le paquet Python du dépôt)** : non vendoré — la voie
  diffusers-native le rend inutile, et vendorer 2989 lignes d'un dépôt
  tiers pour un composant déjà maintenu en amont aurait été le choix
  exactement inverse de ce que ce dépôt fait pour KrillinAI/Xaar
  Kaname/CSM (sous-processus/HTTP, jamais un import).
- **`gradio_demo.py`** : une démo web, hors périmètre — ARENA a déjà son
  interface.
- **La quantification** : aucune n'existe en amont pour cette architecture
  précise ; `core/production/hidream_strategie.py` l'ESTIME (diviseur
  documenté 3.5, jamais mesuré) plutôt que de l'implémenter à l'aveugle —
  mission §7, « ne pas implémenter de tricks non vérifiés ».

## Local Acceptance Decision — le calcul, pas une estimation à l'œil

RTX A2000 12 Go + 32 Go RAM (matériel réel de ce projet) :

- **bf16 complet (LOCAL_FULL)** : nécessite ~63 Go de VRAM. 12 Go < 63 Go.
  **Refusé.**
- **Quantifié (LOCAL_QUANTIZED)** : estimation ~18 Go même en INT4 (diviseur
  3.5, jamais vérifié sur cette architecture MoE). 12 Go < 18 Go. **Refusé.**
- **Offload séquentiel (LOCAL_OFFLOAD)** : ne demande qu'un minimum de VRAM
  résidente (~6 Go, estimé), MAIS exige que la RAM SYSTÈME totale porte les
  poids déchargés — **63 Go > 32 Go de RAM disponible sur cette machine.**
  **Refusé — et c'est la RAM, pas la VRAM, qui bloque ici.**
- **Aucune des trois strategies locales ne tient**, même avec toutes les
  optimisations documentées appliquées à la fois.

Vérifié par code (`core/production/hidream_strategie.py::decider_strategie`),
pas à la main :

```
$ python3 -c "..." (voir tests/core/test_hidream_strategie.py::TestMaterielReelDuProprietaire)
full -> UNSUPPORTED : materiel mesure insuffisant ...
dev  -> UNSUPPORTED : materiel mesure insuffisant ...
fast -> UNSUPPORTED : materiel mesure insuffisant ...
```

**Classification finale : E — SERVER_ONLY_RECOMMENDED.**

Ce n'est pas un échec de mission (mission §34) : l'architecture complète
(détection matérielle réelle, décision déterministe, refus propre avant
tout envoi, worker prêt pour un serveur distant par le simple changement de
`HIDREAM_WORKER_URL`) est livrée, testée, et fonctionne — elle rejette
correctement une exécution qui échouerait.

## Ce que ça coûte si c'est faux

Les seuils de `hidream_strategie.py` (marge VRAM 85 %, marge RAM 80 %,
diviseur de quantification 3.5, plancher d'offload 6 Go) sont des
ESTIMATIONS documentées, jamais mesurées sur un vrai GPU par ce dépôt
(aucun GPU disponible dans cet environnement de développement). Si le
proprietaire branche un jour une carte 16-24 Go, `LOCAL_QUANTIZED` pourrait
se déclencher sans qu'aucune quantification réelle n'ait été testée sur
l'architecture MoE de HiDream — la génération pourrait échouer à l'usage
malgré une décision « GO » du calcul. Le worker le rapporterait alors
honnêtement (`state: "failed"`, erreur capturée), jamais un succès inventé
— mais le premier essai sur une telle carte doit être traité comme un test,
pas une certitude.
