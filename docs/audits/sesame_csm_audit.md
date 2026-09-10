# Audit — SesameAILabs/csm

**Dépôt étudié** : https://github.com/SesameAILabs/csm
**Commit audité** : `daed31e6d42cf71873999075de204fa37d2acec3` (2025-05-27,
tête du dépôt au 10/09/2026 — aucun commit plus récent).
**Modèle** : https://huggingface.co/sesame/csm-1b
**Licence** : Apache-2.0 — **code ET poids**, vérifiés séparément :
`LICENSE` du dépôt (Apache-2.0) et `license: apache-2.0` dans les métadonnées
réelles de la fiche HF (`api/models/sesame/csm-1b`, interrogée le
10/09/2026). Différent d'OmniVoice (code Apache-2.0, poids CC-BY-NC) et de
KrillinAI (module Go GPL-3.0) : ici, rien n'interdit juridiquement
d'importer ce code dans ARENA. La frontière retenue (service séparé) est
donc **technique**, pas juridique — voir « Isolation des dépendances ».

**Méthode** : clone réel et lecture ligne à ligne de `generator.py`,
`models.py`, `run_csm.py`, `watermarking.py`, `requirements.txt`, `README.md`
— plus la documentation Hugging Face réelle de l'implémentation
Transformers-native (`docs/source/en/model_doc/csm.md`,
`src/transformers/models/csm/{modeling,generation,processing}_csm.py`,
dépôt `huggingface/transformers`, branche `main`, lus le 10/09/2026). Rien
pris sur la seule foi d'un résumé ou d'une annonce.

---

## Ce que le dépôt est réellement

Le modèle de génération de parole conversationnelle publié par Sesame :
deux décodeurs autorégressifs de style LLaMA (un backbone qui prédit le
premier token de codebook, un décodeur de profondeur pour les suivants), et
le codec audio **Mimi** (Kyutai) pour encoder/décoder la parole en tokens
discrets. Entraîné pour la **conversation multi-tour** : le contexte est une
séquence de segments texte+audio de plusieurs locuteurs.

## Matrice de validation

| Capacité | Affirmation | Vérifié comment | État |
|---|---|---|---|
| Génération de parole depuis du texte | Cœur du produit | `generator.py::Generator.generate`, lu | **IMPLEMENTED** |
| Contexte conversationnel (continuité de voix) | README, exemple « Generate with context » | Lu : `Segment(text, speaker, audio)` accumulés, réinjectés | **IMPLEMENTED** — mais seulement avec de l'audio RÉEL par segment, jamais du texte seul |
| Codec Mimi | « uses the pretrained codec model Mimi » | `loaders.get_mimi(...)`, `set_num_codebooks(32)` | **IMPLEMENTED** |
| Filigrane audio | Commentaire dans `generator.py` : « Please be a responsible AI citizen and keep the watermarking in place » | `watermark()` appelé à CHAQUE `generate()`, sans option pour le désactiver | **IMPLEMENTED**, systématique dans le dépôt original |
| Support multilingue | FAQ : « has some capacity for non-English languages due to data contamination [...] but it likely won't do well » | Lu textuellement dans le README | **PARTIAL, ADMIS FAIBLE PAR SESAME ELLE-MÊME** — pas une mesure d'ARENA, une citation |
| Accès Hugging Face | « Access to the following Hugging Face models: Llama-3.2-1B, CSM-1B » | Confirmé EN DIRECT : `huggingface-cli` non authentifié → `401 Client Error`, « Access to model sesame/csm-1b is restricted » (voir « Test GPU/CPU réel ») | **CONFIRMÉ, gated** |
| CUDA requis | README : « Requirements: A CUDA-compatible GPU » | Le code de `run_csm.py` a pourtant un repli CPU explicite (`device = "cpu"` si `torch.cuda.is_available()` est faux) | **PARTIAL** — le README dit obligatoire, le code dit préféré |
| Support Windows | « The `triton` package cannot be installed in Windows. Instead use `pip install triton-windows` » | Lu textuellement | **IMPLEMENTED avec une étape distincte** |
| Implémentation Transformers-native | README, 2025-05-20 : « CSM is available natively in Hugging Face Transformers [...] as of version 4.52.1 » | Vérifiée réellement installable (`transformers==5.17.0` dans un venv isolé, `CsmForConditionalGeneration`/`AutoProcessor` importables) | **IMPLEMENTED, confirmé en direct** |
| Filigrane dans l'implémentation Transformers-native | Non affirmé nulle part | Recherche directe de « watermark »/« silentcipher » dans `modeling_csm.py`, `generation_csm.py`, et la page de doc HF : **zéro occurrence** | **ABSENT — trouvaille réelle, motive `watermark.py` côté ARENA** |
| Politique de mésusage | « We explicitly prohibit: Impersonation or Fraud [...] without their explicit consent » | Lu textuellement | **IMPLEMENTED en tant que politique** — rien dans le code ne l'impose techniquement, ARENA ne construit donc aucun chemin qui en dépendrait |

## Isolation des dépendances (mission §7)

`requirements.txt` du dépôt original épingle `torch==2.4.0`,
`torchtune==0.4.0`, `torchao==0.9.0`, `moshi==0.2.2`, et un `silentcipher`
tiré par `git+`. Le mélanger à `requirements.txt` d'ARENA créerait
exactement le genre de conflit déjà mesuré une fois (Pillow vs
`browser-use`, DEC-0079). `tools/audio/csm_service/` isole ces dépendances
dans son propre environnement, avec ses propres pins (assouplis :
`transformers>=4.52.1` plutôt que le vieux `4.49.0` du dépôt d'origine,
puisque l'implémentation native est préférée — voir plus bas).

**Vérifié réellement, pas supposé** : `pip install torch torchaudio
transformers>=4.52.1 huggingface_hub fastapi uvicorn pydantic soundfile`
dans un venv isolé (`--index-url .../whl/cpu`, puisque cette machine n'a pas
de GPU) réussit sans conflit. `CsmForConditionalGeneration` et
`AutoProcessor` s'importent. Détail dans « Test GPU/CPU réel ».

## Décision Transformers-native vs runtime original (mission §8)

**Transformers-native retenu.** Trois raisons mesurées, pas devinées :

1. **Maintenance** — `transformers` est déjà une dépendance massivement
   utilisée et activement maintenue par Hugging Face ; le dépôt original
   n'a reçu aucun commit depuis le 27/05/2025.
2. **Dépendances** — le runtime original exige `torchtune`, `torchao`,
   `moshi`, un `silentcipher` tiré par git : quatre paquets de plus,
   étroitement épinglés. L'implémentation native n'a besoin que de
   `transformers` lui-même.
3. **Stabilité de l'API** — `CsmForConditionalGeneration`/`AutoProcessor`
   suivent les conventions `transformers` déjà connues d'ARENA ailleurs
   dans le dépôt (FastAPI, Hugging Face Hub).

**Le prix de ce choix, découvert en le vérifiant** : l'implémentation
native ne filigrane pas l'audio qu'elle produit — recherche directe dans son
code source confirmant zéro trace de la logique de filigrane présente dans
le runtime original. `tools/audio/csm_service/watermark.py` réapplique donc
le filigrane lui-même, en dépendant directement de `silentcipher` (la même
bibliothèque que le dépôt original, jamais son code copié) avec la clef
publique `CSM_1B_GH_WATERMARK` que Sesame publie elle-même pour ce
checkpoint précis. Un test dédié (`test_server.py::
TestLeFiligraneNEstJamaisOptionnel`) — sabotage confirmé, section
« Garanties sabotées » — tient cette garantie.

## Test GPU/CPU réel (mission §6)

**Matériel cible du propriétaire (RTX A2000, 12 Go, Windows) — hors
d'atteinte de ce bac à sable cloud**, qui n'a ni GPU ni pilote NVIDIA
(`nvidia-smi` absent, `torch.cuda.is_available()` mesuré `False`). Ce qui a
pu être vérifié RÉELLEMENT ici, en direct, contre le vrai service :

1. Service HTTP réel démarré (`uvicorn`, `tools/audio/csm_service/server.py`).
2. `GET /health` avant tout chargement : `{"model_loaded": false, ...}` —
   confirmé, le service ne charge rien avant le premier appel.
3. `POST /generate` avec un texte réel : tentative réelle de
   `AutoProcessor.from_pretrained("sesame/csm-1b")`, qui a réellement
   échoué avec :
   ```
   You are trying to access a gated repo.
   401 Client Error [...] Access to model sesame/csm-1b is restricted.
   You must have access to it and be authenticated to access it.
   ```
   Ce message est passé tel quel à travers `core/connectors/csm.py`
   (`sonder()` → `NON_CONFIGURE`, message identique) — vérifié bout en
   bout, pas seulement côté service.
4. `GET /health` après cet échec : `ce_qui_manque` porte désormais le même
   message — l'état persiste correctement entre deux appels.

**Ce qui n'a PAS pu être mesuré ici, et pourquoi c'est dit honnêtement** :
chargement réel du modèle, VRAM réelle, durée de génération réelle,
facteur temps réel. Aucun de ces nombres n'a été inventé — ni dans ce
document, ni dans le code, qui rapporte `device`/`device_is_accelerated`
comme des mesures faites AU MOMENT de l'appel, jamais des constantes. Le
propriétaire, sur sa RTX A2000, obtiendra ces mesures réelles au premier
lancement (`docs.../csm_service/README.md`).

## Tests réels de langue (mission §5)

Aucune génération audio n'a pu être produite ici (accès gated bloqué), donc
**aucune mesure d'intelligibilité française/wolof n'est affirmée** — ce
serait exactement la faute que la mission interdit (« do NOT claim French or
Wolof support simply because audio was generated »). Ce qui est fait à la
place : le FAQ officiel du dépôt (« it likely won't do well » hors anglais)
est pris comme la mesure la plus fiable disponible, et
`core/audio/routage_tts.py::LICENCES["sesame-csm-1b"].langues` restreint ce
moteur à `{"en"}` sur cette seule base — **jamais élargi sans une mesure
réelle**. Une note explicite dans le code dit que ce champ existe pour être
corrigé le jour où le propriétaire mesure autre chose sur sa machine.

## Contexte conversationnel (mission §10)

Le mécanisme réel (`Segment` avec audio, réinjecté) EST utilisé côté ARENA,
mais avec une restriction délibérée : `tools/audio/csm_service/server.py`
ne grandit le contexte qu'avec de l'audio **généré par ce même service, dans
la même requête** — jamais un fichier fourni par l'appelant. Testé (`
test_server.py::TestLeContexteConversationnelNeContientJamaisUnFichier`) :
un tour de conversation transmis avec un texte est régénéré, jamais lu sur
disque ; un tour sans texte est ignoré.

**Conséquence assumée** : la continuité de voix testable ici est
« CSM garde la même identité qu'il vient de créer », jamais « CSM imite la
voix d'un enregistrement fourni ». Voir « Sécurité vocale » pour pourquoi.

## Sécurité vocale (mission §13)

CSM sait faire du « audio prompting » (conditionner sur un `Segment` porteur
d'un enregistrement réel). **Ce chemin n'est jamais exposé côté ARENA.** Le
propriétaire a déjà posé une règle absolue à ce sujet pour KrillinAI
(« si tu vois quelque chose de nouveau [près du deep face], ignore-le, ne le
touche même pas », `core/connectors/krillinai.py`) : la même règle s'applique
ici, pour le même risque (média synthétique imitant une personne réelle).
ARENA a déjà un chemin de clonage vocal **consenti et autorisé**
(`core/connectors/audio_voix.py::_cloner`, autorisation exigée dans le code
même, pas seulement dans un message) — en ouvrir un second, plus faible,
chez CSM aurait été une régression de sécurité déguisée en fonctionnalité.

## Filigrane et provenance (mission §12)

Trois couches, chacune testée et sabotée :

1. `tools/audio/csm_service/watermark.py` — réapplique le filigrane de
   Sesame après une génération Transformers-native (absent nativement, voir
   plus haut).
2. `tools/audio/csm_service/server.py` — refuse `/generate` (500) si le
   filigrane échoue, jamais un fichier renvoyé sans lui.
3. `core/connectors/csm.py` — revérifie l'en-tête `X-CSM-Watermarked` reçu
   du service ; un « false » explicite devient un `ECHEC` côté ARENA, rien
   n'est écrit sur disque.

## Ce qui est réellement réutilisable

1. **L'API Transformers-native** — choisie plutôt que le runtime original
   (raisons ci-dessus), aucune ligne copiée.
2. **La clef de filigrane publique `CSM_1B_GH_WATERMARK`** — reprise
   littéralement (Sesame la publie pour ce checkpoint précis), voir
   `NOTICE.md`.
3. **Le mécanisme de contexte conversationnel** (`Segment` texte+audio) —
   réécrit contre `apply_chat_template` de `transformers`, restreint côté
   ARENA à de l'audio auto-généré (voir « Contexte conversationnel »).

## Ce qui n'a délibérément pas été repris

- **Le runtime original** (`generator.py`, `models.py`, `torchtune`,
  `torchao`, `moshi`) — remplacé par l'implémentation Transformers-native,
  raisons ci-dessus.
- **L'audio prompting par fichier fourni** — jamais exposé (« Sécurité
  vocale »).
- **Aucune tentative de faire de CSM le moteur par défaut d'ARENA** — le
  routeur (`core/audio/routage_tts.py`) ne le préfère que pour de l'anglais
  conversationnel explicitement demandé (`conversationnel=True`), jamais par
  défaut. Voir DEC-0080.

## Garanties sabotées et restaurées

Chacune cassant exactement et seulement son propre test :

1. La restriction de langue de `choisir()` (`core/audio/routage_tts.py`) —
   retirée → un test qui demande du français choisit quand même CSM.
2. Le refus `X-CSM-Watermarked: false` côté connecteur
   (`core/connectors/csm.py`) — retiré → un fichier non filigrané est gardé
   et déclaré succès.
3. Le refus `filigrane_ok is False` côté service
   (`tools/audio/csm_service/server.py`) — retiré → un audio non filigrané
   part avec un code 200.

## Licences et provenance (mission §17)

Apache-2.0 de bout en bout (code du dépôt, poids du modèle). Aucune ligne de
son code Python n'est copiée dans ARENA : seule la clef publique de
filigrane est reprise littéralement, attribuée dans `NOTICE.md`.
`silentcipher` (dépendance du filigrane) est une bibliothèque tierce, jamais
vendue avec ARENA — installée par le propriétaire dans l'environnement isolé
du service, comme le reste de `tools/audio/csm_service/requirements.txt`.
