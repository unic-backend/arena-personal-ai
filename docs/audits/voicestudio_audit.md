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

**`uv sync`, et pas `pip install`** — c'est important, et vérifié : deux des
trois défauts du §2 viennent de là.

| | `uv sync` (lit `uv.lock`) | `pip` (lit `pyproject.toml`) |
|---|---|---|
| torch / torchaudio | `==2.8.0` — **démarre** | `>=2.4` — la 2.11 **ne démarre pas** |
| kittentts | roue GitHub `0.8.1` — **fonctionne** | PyPI `0.1.3` — échoue à la synthèse |

Le troisième défaut (sherpa-onnx + modèle Piper) ne dépend pas de la méthode
d'installation : ce moteur-là est à éviter tant que VoiceStudio ne passe pas
`data_dir`.

`uv.lock` tire aussi la variante **CUDA** de torch sur une machine qui en a
une — donc la bonne pour la RTX A2000, sans rien faire de plus.

Sans lui, ARENA répond `NOT_CONFIGURED` et dit ce qui manque. Il ne simule
rien.

---

# Second relevé — VoiceStudio v0.5.2, commit `eaf8bb9` (13/09/2026)

Le premier relevé de ce document porte sur `53ff367` (07/09/2026, v0.5.1).
L'amont a bougé trois jours plus tard. Ce qui suit est **mesuré sur un clone
du dépôt courant**, pas lu dans un changelog.

## Ce qui n'a pas bougé, et qui fonde l'architecture d'ARENA

| Hypothèse écrite en dur dans ARENA | État en `eaf8bb9` |
|---|---|
| Licence applicative **AGPL-3.0** | inchangée — la frontière « processus séparé, HTTP » reste nécessaire |
| Port par défaut **3900** | confirmé (`backend/main.py:1898`, `backend/mcp_server.py:433`) |
| `_REGISTRY` commence par **`omnivoice`** | toujours vrai — le défaut que `routage_tts.py` corrige est toujours là |
| Poids OmniVoice **CC-BY-NC** | toujours écrit dans `LICENSE-NOTICE.md` |

**Les six routes qu'ARENA appelle existent toutes** : `/system/info`,
`/engines/tts`, `/engines/asr`, `/v1/audio/speech`,
`/v1/audio/transcriptions`, `/profiles`. **Aucune rupture d'API.**

## Ce qui a bougé, et qui a exigé un correctif

`_LAZY_REGISTRY` porte un moteur qui n'existait pas au premier relevé :
**`audiocpp`** (audio.cpp / Breeze-TTS-2, 3B, en+zh, clone + design, 24 kHz).

Sa licence, source primaire `docs/engines/audio-cpp.md` :

> - **audio.cpp code:** Apache-2.0.
> - **Breeze-TTS-2 weights** [...] **research and non-commercial use only** [...]
>   **Self-hosted outputs inherit the restriction**

C'est le piège OmniVoice, à l'identique : code permissif, **poids non
commerciaux**, et cette fois la source dit explicitement que **l'audio produit
hérite de la restriction**.

**Mesure du 13/09/2026, avant correction** — `choisir([audiocpp])` en usage
commercial **rendait `audiocpp`**, là où le même appel sur `omnivoice`
refusait. Le moteur tombait sur `LICENCE_INCONNUE`, et la règle 4 du module
laisse délibérément passer `INCONNU` pour qu'ARENA ne se taise pas devant un
moteur neuf. **C'est donc le tableau qu'il fallait corriger, pas la règle.**

Corrigé : entrée `audiocpp` → `Commercial.INTERDIT`, langues `en`/`zh`, avec
sa **propre source** (`_VS_0_5_2`) — les autres entrées viennent de `53ff367`,
les fondre sous une seule étiquette ferait mentir la provenance de l'une des
deux.

## Surface amont qu'ARENA n'exploite pas

L'amont compte **39 routeurs** (`backend/api/routers/`). ARENA en utilise le
noyau — synthèse, transcription, catalogue de moteurs, profils, état système —
et **ne touche à aucun des sous-systèmes suivants** (mesuré : 0 fichier
d'ARENA ne les mentionne) :

| Capacité | Routeur amont | État dans ARENA |
|---|---|---|
| Voice design par description | `describe_voice.py` → `/design/describe` | NOT_PRESENT (ARENA a `instruct`, pas cette route) |
| Doublage vidéo | `dub_core/dub_generate/dub_translate/dub_export`, `sonitranslate` | NOT_PRESENT |
| Dictée | `dictation.py`, `capture_ws.py` | NOT_PRESENT |
| Long-format / audiobook | `audiobook.py`, `longform_jobs.py` | NOT_PRESENT |
| Speech-to-speech | `voice_convert.py` | NOT_PRESENT |
| Streaming TTS | `tts_stream.py`, `events.py` | NOT_PRESENT |
| Lots / travailleurs distants | `batch.py`, `workers.py` | NOT_PRESENT |
| MCP amont | `mcp_bindings.py` | NOT_PRESENT — et c'est **voulu** : ARENA a son propre MCP canonique (mission §45) |

**Ce tableau n'est pas une liste de choses à faire.** C'est l'inventaire de ce
qui est disponible si le propriétaire en a besoin. Chacune de ces lignes
demanderait sa propre mesure de licence des poids, exactement comme `audiocpp`
vient de le montrer.

## Ce que ce relevé n'a PAS pu mesurer

Sur la machine de vérification (conteneur cloud) :

- **aucun GPU** (`nvidia-smi` absent, `torch` non installé) ;
- **15 Go de RAM**, pas 32 ;
- **3,8 Go de disque libre** (90 % occupé) ;
- **VoiceStudio n'y tourne pas**, et aucun poids ne peut y être téléchargé.

Donc : **aucune mesure RTX A2000, aucune synthèse réelle, aucune
transcription réelle, aucun essai de moteur** n'a été faite ici. Les annoncer
serait exactement la faute que `CLAUDE.md` interdit. Ces mesures exigent la
machine du propriétaire.

---

# Troisième relevé — 15/09/2026 : les licences confrontées aux fiches de modèle

Les deux premiers relevés lisaient la colonne « License » du `README.md` de
VoiceStudio. **Une colonne de README est une affirmation, pas une
vérification.** C'est elle qui avait laissé passer `audiocpp` — permissif dans
le tableau, non commercial dans les poids.

Ce relevé-ci prend le problème par l'autre bout : pour chaque moteur, le dépôt
de modèle **réellement chargé** a été lu dans
`backend/services/tts_backend.py` à l'amont `4e55180f` (14/09/2026), puis sa
fiche interrogée sur `https://huggingface.co/api/models/<dépôt>`.

## Couverture

`_REGISTRY` + `_LAZY_REGISTRY` à `4e55180f` déclarent **17 moteurs TTS**. Les
17 figurent dans le tableau `LICENCES` d'ARENA : aucun moteur amont n'est
inconnu du routeur à cette date.

## Le défaut trouvé — `omnivoice-gguf`

| | |
|---|---|
| Dépôt chargé | `Serveurperso/OmniVoice-GGUF` |
| Fiche (15/09/2026) | `license: cc-by-nc-4.0` |
| `license_link` | `https://huggingface.co/k2-fsa/OmniVoice#license` |
| Modèle de base | *« The pre-trained model is licensed under the CC-BY-NC due to constraints from its training data (e.g., Emilia). »* |
| ARENA avant correction | `INCONNU` — « termes du dérivé non vérifiés » |

Le quantificateur **déclare lui-même** hériter des termes du modèle de base.
La fiche a été modifiée le 09/09/2026, soit après le relevé du 07/09 — d'où le
`INCONNU`, honnête à sa date et périmé depuis.

**Pourquoi c'était servi.** La règle 4 n'écarte que `INTERDIT` ; `INCONNU` est
seulement déprécié dans `_rang`. Mesuré avant correction :

```
Seul moteur installé : omnivoice-gguf, usage COMMERCIAL
  choisi        : omnivoice-gguf
  verdict ARENA : INCONNU
omnivoice (mêmes poids, autre emballage) : refusé
```

Troisième fois que ce piège se referme ici, après `omnivoice` et `audiocpp`,
et toujours pour la même raison : **le code est permissif, les poids ne le sont
pas.**

Ce que celui-ci apprend en plus des deux autres : **`INCONNU` n'est pas un état
stable, il vieillit.** Un « non vérifié » écrit un jour reste dans le tableau
quand l'amont, lui, a publié ses termes.

## Trois formulations corrigées — aucun verdict changé

| Moteur | Avant | Mesure du 15/09/2026 |
|---|---|---|
| `kittentts` | « MIT » | Poids `apache-2.0` (`KittenML/kitten-tts-mini-0.8`). MIT est la licence du **code**. |
| `supertonic3` | « OpenRAIL-M (restrictions d'usage, **pas de commerce**) » sous un verdict `AUTORISE` | L'Attachment A du `LICENSE` énumère treize restrictions d'usage — illégalité, mineurs, désinformation, deepfake, harcèlement, discrimination, conseil médical… — et **aucune ne porte sur le commerce**. La phrase disait le contraire de son propre verdict. |
| `sesame-csm-1b` | « Apache-2.0 (code et poids) » | Licence inchangée, mais la fiche est passée `gated: auto`. C'est une **condition d'obtention**, pas une restriction d'usage : les confondre ferait refuser un moteur utilisable. |

## Deux dépôts renommés, licence inchangée

- `OpenMOSS-Team/MOSS-TTS-Nano` → `OpenMOSS-Team/MOSS-TTS-Nano-100M` (`apache-2.0`)
- `rednote-hilab/dots.tts-soar` → `dots-studio/dots.tts-soar` (`apache-2.0`)

## Confirmations

`cosyvoice` (`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`), `voxcpm2`
(`openbmb/VoxCPM2`), `moss-tts-v15` : `apache-2.0`, non *gated*.
`pockettts` (`kyutai/pocket-tts`) : `cc-by-4.0`, `gated: auto` — ce que le
tableau disait déjà. `indextts2` : `other` / `bilibili-model-license`.
`audiocpp` : `other`, cohérent avec BreezeBlue.

## Ce que ce relevé n'a toujours PAS mesuré

Rien n'a été synthétisé, aucun moteur n'a tourné, aucune licence n'a été lue
sur la machine du propriétaire. Ce relevé mesure des **fiches de modèle**, pas
de l'audio. Les trois moteurs sans dépôt par défaut — `confucius4-tts`,
`sherpa-onnx`, `gpt-sovits` — chargent ce que l'utilisateur fournit : leur
licence dépend de ce qui sera installé, et ne peut pas être mesurée d'ici.
