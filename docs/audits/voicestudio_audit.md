# VoiceStudio — audit et intégration

*Mesuré le 01/09/2026. Commit audité : `a30b7166` (30/08/2026), version `0.5.1`.*

Ce document dit ce que VoiceStudio contient vraiment, pourquoi **aucune de ses
lignes n'entre dans ARENA**, et ce que la chaîne a réellement produit.

---

## 1. La licence décide de l'architecture

| | |
|---|---|
| VoiceStudio | **AGPL-3.0-only** (`LICENSE`, `LICENSE-NOTICE.md`, `pyproject.toml`) |
| ARENA | « Copyright (c) 2026 Usman (unic-backend). **All rights reserved.** » |

Ces deux licences ne se mélangent pas. Copier du source VoiceStudio dans
ARENA — ou même l'importer comme bibliothèque — ferait d'ARENA une **œuvre
dérivée** : ARENA devrait alors être publié en entier sous AGPL-3.0, licence
que son propriétaire n'a pas choisie. L'AGPL ajoute en outre une obligation
que la GPL n'a pas : servir une version **modifiée** sur un réseau oblige à en
publier le source.

**La décision** : VoiceStudio tourne comme **processus séparé**, dans son
propre environnement Python, et ARENA le pilote par HTTP sur `127.0.0.1`.
Aucun fichier copié, aucun fichier modifié, aucun import. C'est la voie que la
mission désignait elle-même (« use VoiceStudio as a separately licensed local
service/process controlled by ARENA »), et c'est celle qui préserve la licence
du propriétaire.

**Ce que ça coûte si c'est faux** : si un juriste estimait qu'un appel HTTP
suffit à créer une œuvre dérivée — lecture minoritaire, mais elle existe pour
des couplages très étroits — ARENA devrait passer en AGPL ou acheter la
licence commerciale que VoiceStudio propose (`VoiceStudio@palash.dev`). Le
découplage choisi (HTTP, API OpenAI-compatible, aucune structure de données
partagée) est précisément ce qui rend cette lecture difficile à soutenir.

*Ceci est une analyse d'ingénierie, pas un avis juridique.*

### Les autres licences du lot

| Composant | Licence | Utilisé ici ? |
|---|---|---|
| `omnivoice/` (modèle TTS de Han Zhu) | Apache-2.0 | Non — paquet absent |
| `kittentts` 0.8.1 | Apache-2.0 (KittenML) | **Oui** — moteur de voix |
| `faster-whisper` / CTranslate2 | MIT | **Oui** — moteur de transcription |
| `Systran/faster-whisper-base` | MIT | **Oui** — modèle ASR (148 Mo) |
| `vits-piper-fr_FR-siwis-medium` | dataset SIWIS **CC-BY 4.0** | Non — voir §4 |

Aucune licence incompatible avec un usage commercial. `CC-BY 4.0` demanderait
une attribution si la voix française était utilisée ; elle ne l'est pas.

---

## 2. Ce que VoiceStudio contient réellement

Backend FastAPI, **38 routeurs**, port **3900** en boucle locale par défaut,
**sans aucune authentification** (son propre commentaire de code le dit et
explique pourquoi il ne se lie pas à `0.0.0.0`).

Capacités déclarées : TTS (16 moteurs), ASR (11 moteurs), clonage de voix,
profils de voix, doublage, diarisation, séparation, lots, audiobooks, API
OpenAI-compatible, serveur MCP, workers distants gRPC.

**Déclaré n'est pas disponible.** Sur cette machine, après installation :

```
/engines/tts  -> 1 disponible sur 16 : kittentts
/engines/asr  -> 3 disponibles sur 11 : faster-whisper,
                 faster-whisper-isolated, sherpa-onnx-asr
```

Les treize autres moteurs TTS demandent un `git clone`, un venv séparé, ou un
modèle qui n'existe pas sur cette machine.

### Trois défauts d'amont, mesurés

1. **`torchaudio.set_audio_backend` a disparu** après torch 2.0, et
   `backend/main.py:626` l'appelle sans garde. `pyproject.toml` autorise
   `torchaudio>=2.4` : une installation qui suit cette contrainte **ne
   démarre pas**. Seul `uv.lock` (`==2.8.0`) fonctionne.
2. **`kittentts` de PyPI est incompatible.** PyPI publie `0.1.3` ;
   VoiceStudio appelle `generate(clean_text=…)`, qui n'existe qu'en `0.8.1`,
   distribuée **seulement** par une release GitHub. Le conseil d'installation
   affiché dans l'interface (`pip install kittentts`) mène donc à un moteur
   « disponible » qui échoue à la première synthèse.
3. **`sherpa-onnx` ne peut pas charger un modèle Piper.**
   `docs/engines/sherpa-onnx.md` annonce Piper, mais
   `services/tts_backend.py:2122` construit `OfflineTtsVitsModelConfig` avec
   `model` et `tokens` seulement — sans `data_dir` ni `lexicon`. Le modèle
   français `vits-piper-fr_FR-siwis-medium` **fait tomber le processus
   entier** : `Not a model using characters as modeling unit`.

Ces trois points sont chez VoiceStudio. **Aucun n'a été corrigé dans son
source** — le corriger aurait créé une version modifiée, avec les obligations
AGPL qui vont avec. Ils sont contournés par la **configuration** :
`uv.lock`-conforme pour torch, la roue GitHub pour kittentts, et le moteur
sherpa laissé de côté.

---

## 3. Ce qu'ARENA avait déjà, et ce qui n'a pas été dupliqué

| Capacité | ARENA avant | Décision |
|---|---|---|
| Transcription | `tools/audio/transcription_tool.py` — faster-whisper `tiny`, CPU | **Gardé.** VoiceStudio s'y ajoute pour les moteurs plus gros ; l'outil existant n'est pas touché. |
| Sous-titres | `tools/video/subtitle_tool.py` + `SubtitleAgent` + `STUDIO` (9:16 + incrustation) | **Gardé, et protégé.** L'intention `AUDIO` prenait « sous-titre ma vidéo » au studio : régression trouvée par `test_ces_demandes_vont_au_studio`, corrigée, et un test la fixe désormais. |
| ffmpeg | `tools/video/ffmpeg_tool.py`, `core/montage/rendu.py` | **Gardé.** |
| **Synthèse vocale** | **rien** | **Ajouté.** `tools/social/voix.py` parle de son style d'écriture, pas de parole. |

---

## 4. Ce qui a réellement tourné

**Le tour complet, texte → voix → texte**, à travers le registre d'ARENA et
ses permissions :

```
1. Santé      : OPERATIONAL | VoiceStudio 0.5.1 sur http://127.0.0.1:3900 (cpu)
2. Moteurs    : SUCCESS | Voix : kittentts. Transcription : faster-whisper, …
3. Transcrire : SUCCESS | "Hello, this is Unic Placquist. We install drywall
                          partitions in Dakar."
4. Parler     : NEEDS_CONFIRMATION  (écriture -> file d'attente, comme le devis)
5. Parler ✔   : SUCCESS | Voix produite par « kittentts » : 5742 ms, 275678 octets
```

Le fichier produit a été **re-sondé** : `pcm_s16le`, 24 000 Hz,
`duration=5.741667`. Et vérifié comme n'étant pas du silence : amplitude
maximale **26029** sur 161 800 échantillons.

**Audio + vidéo, jusqu'à une vidéo finale :**

```
1. VOIX  : SUCCESS | 7183 ms produits par kittentts
2. VIDÉO : SUCCESS | 5000 ms, 1080x1920 -> data/montages/projet-eddce1b0.mp4
```

Sondage indépendant du MP4 : `h264` 1080×1920 **+ `aac` 24 000 Hz**,
`duration=5.000000`. Piste audio extraite du fichier final : amplitude
maximale **25892** — la voix est bien dans la vidéo.

### Capacités intégrées

| Capacité | État |
|---|---|
| Text-to-speech | **Vérifié** (kittentts, anglais) |
| Speech-to-text | **Vérifié** (faster-whisper `base`) |
| Choix du moteur par disponibilité | **Vérifié** — voir §5 |
| Voix off dans une vidéo montée | **Vérifié** de bout en bout |

### Capacités délibérément non intégrées

Clonage de voix, voice design, dictée, doublage vidéo, diarisation, séparation
voix/fond, génération par lots, narration multi-locuteurs, audiobooks,
longform. **Aucune n'a été branchée**, et pour une seule raison : leurs moteurs
ne sont pas installables ici (venv séparés, `git clone`, modèles de plusieurs
Go, GPU). Les brancher sans pouvoir les exécuter aurait produit exactement ce
que la mission interdit — une capacité déclarée qui ne marche pas.

---

## 5. Un défaut d'intégration trouvé en jouant la chaîne

VoiceStudio garde `omnivoice` comme moteur **actif** même quand son paquet est
absent. Une demande sans `model` partait donc vers un moteur inexistant :

```
FAILED | Synthèse refusée (400) : Engine 'omnivoice' is not available:
         omnivoice package missing: No module named 'transformers'
```

ARENA choisit désormais **parmi ce que la machine déclare disponible**
(`_choisir_la_voix`), jamais le défaut du service. C'est le routage par
capacité que la mission demandait, et il tient parce qu'il **interroge** au
lieu de supposer.

**Limite mesurée** : `/engines/tts` n'expose **aucune information de langue**
(champs : `id`, `display_name`, `available`, `supports_cloning`,
`supports_emotion`, `gpu_compat`, `min_vram_gb`, `isolation_mode`,
`routing_status`, …). ARENA **ne peut donc pas router par langue**. Le message
de succès nomme toujours le moteur qui a parlé — « Voix produite par
« kittentts » » — pour que le propriétaire voie qu'un moteur anglais a lu son
texte. **Une voix française n'est pas disponible ici** (§2, défaut 3).

---

## 6. Matériel

Machine de mesure : **CPU seul**, 4 cœurs, 15,7 Go de RAM, `gpu_name: ""`,
`vram_total_gb: 0.0`. Aucune observation de VRAM n'est donc possible, et
**aucune n'est inventée**.

Ce qui a été fait pour la RTX A2000 12 Go du propriétaire : rien de spécifique,
délibérément. VoiceStudio porte déjà sa propre gestion (`min_vram_gb` par
moteur, `routing_status`, `/model/unload/{id}`, éviction VRAM dans
`get_model()`), et ARENA la laisse décider plutôt que d'ajouter une seconde
politique qui entrerait en conflit. Les moteurs installés ici (kittentts ONNX,
faster-whisper `base`) sont des moteurs CPU légers.

`OMNIVOICE_URL` **doit rester local** : le connecteur refuse toute autre
adresse (`AdresseNonLocale`), parce qu'une voix est une donnée personnelle.

---

## 7. Comment le propriétaire le démarre

VoiceStudio n'est pas installé par ARENA et ne démarre pas avec lui : c'est un
programme séparé, sous une autre licence. Sur sa machine :

```
git clone https://github.com/debpalash/VoiceStudio
cd VoiceStudio && uv sync
uv run uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900
```

Sans lui, ARENA répond `NOT_CONFIGURED` et dit ce qui manque. Il ne simule
rien.
