# Audit de `AI-Youtube-Shorts-Generator` — 30 septembre 2026

Décision : **APPROVED_WITH_ADAPTER** (mode `local` uniquement, moteur hors du
dépôt, transcription fournie par ARENA). Justification en fin de document.

## Purpose — ce que le dépôt fait

Découper une vidéo longue en plusieurs *shorts* verticaux : transcription →
détection d'extraits « viraux » par LLM → découpe ffmpeg → recadrage 9:16 →
JSON de métadonnées (titre, hook, score, raison).

## Upstream — provenance et épinglage

- Dépôt demandé : `SamurAIGPT/AI-Youtube-Shorts-Generator`. **Il a été
  renommé** : GitHub redirige (301) vers
  <https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator>.
- Révision épinglée et auditée : **`a57bb938ba50bf9654c2d5ca2af1295163454349`**
  (2026-09-29). Jamais « latest » : `inspecter_moteur` compare la révision
  réellement installée à celle-ci et le dit quand elles divergent.
- Activité : 5 185 étoiles, 25 issues ouvertes, dernier push 29/09/2026 — dépôt
  vivant, non archivé.
- **Le contenu a changé de nature depuis sa réputation** : ce n'est plus le
  gros pipeline MoviePy/Whisper d'origine, mais **1 281 lignes** de colle en
  deux modes.

## License

**MIT** (`LICENSE`, lu directement, © 2026 Anil Chandra Naidu Matcha). Rien
n'interdit de le versionner — il reste néanmoins **dehors**, par la règle
unique du dépôt (DEC-0039, cf. `tests/test_moteurs_externes_restent_dehors.py`) :
une seule règle pour tous les moteurs vaut mieux que deux selon la licence.

## Architecture

```
main.py                      CLI (url|fichier, --mode, --num-clips, --aspect-ratio, --output-json)
shorts_generator/pipeline.py orchestration : download → transcribe → highlights → clip
               /highlights.py prompts viralité, découpage en tranches (>30 min), dédoublonnage
               /muapi.py      mode api : POST + polling chez MuAPI (tiers payant)
               /local/*.py    mode local : yt-dlp, faster-whisper, OpenAI|Gemini, ffmpeg+OpenCV
```

Deux modes, deux frontières très différentes :

| | `--mode api` (défaut amont) | `--mode local` (**retenu**) |
|---|---|---|
| Où part la vidéo | téléversée chez **MuAPI** | reste sur la machine |
| Clé | `MUAPI_API_KEY` (payant) | endpoint compatible OpenAI |
| Coût | par appel | électricité |

## Dependencies

- Cœur : `requests>=2.31`, `python-dotenv>=1.0`.
- Mode local (`requirements-local.txt`) : `yt-dlp`, `faster-whisper`,
  `openai`, `google-genai`, `opencv-python>=4.8.0` (torch optionnel, CUDA).
- **Aucune de ces dépendances n'entre dans `requirements.txt` d'ARENA.** Le
  moteur a son propre environnement virtuel, désigné par
  `YOUTUBE_SHORTS_PYTHON`. Conflits potentiels évités : `openai` (ARENA épingle
  `2.26.0` pour `browser-use`), `opencv` (Pillow/OpenCV ont déjà cassé le
  `requirements.txt` une fois, DEC-0079), `faster-whisper` (ARENA épingle
  `1.2.1`).

## Hardware requirements

CPU suffit. GPU **facultatif** (CUDA seulement pour Whisper, que ce connecteur
n'utilise pas). Le recadrage est du CPU image par image : c'est le poste
coûteux (12 s de 1280×720 → ~10 s de calcul sur le banc d'essai). Disque :
source + clip intermédiaire + clip final par extrait, dans un dossier par job.

## Security

| Risque relevé | Traitement dans l'adaptateur |
|---|---|
| Mode `api` téléverse la vidéo du propriétaire chez un tiers | `--mode local` écrit en dur ; `mode="api"` passé en paramètre est ignoré (test) |
| `load_dotenv()` amont lit tout l'environnement | le sous-processus reçoit un `env` **construit** (7 clés), pas `os.environ` |
| Clé LLM confondue avec celle d'ARENA | variable dédiée `YOUTUBE_SHORTS_LLM_API_KEY`, jamais `OPENAI_API_KEY` d'ARENA |
| Téléchargement réseau implicite (yt-dlp) | une URL exige `autoriser_telechargement=True` explicite |
| `subprocess.run(cmd)` amont — liste d'arguments, pas de shell | conservé : aucun `shell=True` de part et d'autre |
| Exécution non bornée | délai 1 800 s, `TimeoutExpired` → échec structuré + nettoyage |
| Aucun secret dans le dépôt | aucun `.env`, aucune clé ; `.env.example` amont non copié |

## Input / Output

**Entrée** (contrat ARENA) : `video` (chemin local ; URL seulement sur
autorisation explicite), `transcript_srt` (**obligatoire**, produit par ARENA),
`nombre_clips` (1–10), `format` (`9:16`, `1:1`, `4:5`), `langue` (optionnel).

**Sortie** : `ResultatAction` SUCCÈS avec `clips[]` — `chemin`, `mime_type`,
`titre`, `debut`, `fin`, `score`, `hook`, `raison`, `format`, `octets` — plus
`candidats`, `dossier`, `erreurs[]`. Chaque chemin est vérifié sur disque
(existe, non vide) avant d'être crédité.

## Installation test

Environnement virtuel dédié, `pip install -r requirements-local.txt` :
installation réussie. **Deux défauts mesurés, pas supposés** :

1. `opencv-python` (non *headless*) échoue à l'import sur une machine sans
   serveur graphique : `ImportError: libGL.so.1`. Correctif retenu :
   `opencv-python-headless`.
2. `opencv-python>=4.8.0` n'a **pas de borne haute**. `pip` a installé
   **5.0.0**, où `cv2.CascadeClassifier` n'existe plus : *tous* les extraits
   échouent (`module 'cv2' has no attribute 'CascadeClassifier'`). Avec
   `opencv-python-headless==4.10.0.84`, tout passe. La sonde de santé
   **mesure** cet attribut dans l'interpréteur du moteur.

## Runtime test — exécuté réellement, pas lu dans un README

Banc : vidéo ffmpeg `testsrc` 1280×720, 25 fps, 12 s, piste `sine` AAC ;
transcription SRT fournie ; endpoint compatible OpenAI local (bouchon HTTP —
**c'est la seule pièce simulée**, et elle l'est parce qu'aucun modèle n'est
joignable depuis l'environnement d'audit ; le moteur, lui, a bien tourné).

```
[download/local] using local file: src.mp4
[transcribe/local] reusing cached transcript: src.srt   ← aucun Whisper chargé
[highlights] content=podcast density=high duration=12s
[clip/local] 1/2 … 2/2
```

Résultat vérifié à `ffprobe` : `short_01.mp4` **404×720, 4,00 s, audio AAC** ;
`short_02.mp4` **404×720, 3,00 s, audio AAC** ; `result.json` conforme. Codec
vidéo de sortie : **mpeg4** (`cv2.VideoWriter` en `mp4v`), pas H.264 — moins
bien accepté par certaines plateformes ; limitation connue, notée ci-dessous.

Le priming du cache SRT a été vérifié explicitement : la ligne
`reusing cached transcript` prouve que **faster-whisper n'est jamais chargé**
quand ARENA fournit la transcription.

## API / CLI interface

CLI uniquement (`python main.py <source> --mode local …`) plus une fonction
`generate_shorts()` importable. **L'import n'est pas utilisé** : appel par
sous-processus, conformément à la frontière des moteurs externes.

## ARENA compatibility

Ce qu'ARENA possédait déjà, vérifié avant d'écrire une ligne :
`agents/clip_selector` (un extrait, cadrage centre, pas de classement),
`tools/video/ffmpeg_tool.py` (profil `shorts` 1080×1920), `crop_tool`
(9:16 fond flou), transcription FasterWhisper, `core/montage`, connecteurs
KrillinAI / Drift / VectCut / MoneyPrinter / Agnes / Hyperframes.

**Delta réel apporté** : N extraits **classés** (score, hook, raison,
dédoublonnage par recouvrement > 50 %, découpage des vidéos > 30 min) et un
**recadrage qui suit les visages**. Aucune capacité existante n'est remplacée
ni supprimée : `clip_selector` reste en place, inchangé.

**Ce qui n'est pas repris** : la transcription du moteur (ARENA transcrit
déjà), son téléchargement automatique (opt-in explicite), son mode MuAPI.

## Conflicts

Aucun. Aucune dépendance ARENA n'a été ajoutée, montée ou descendue ; aucun
fichier existant n'a changé de comportement. Fichiers touchés hors nouveaux :
`apps/backend/runtime.py` (une déclaration), `config/permissions_services.yaml`
(un service).

## Known limitations

1. Sortie **mpeg4**, pas H.264 (limite de `cv2.VideoWriter` amont).
2. Détection de visages par cascade Haar : frontale uniquement, pas de
   diarisation ni de suivi multi-locuteurs.
3. Le recadrage lit et réécrit chaque image : coûteux en CPU sur une vidéo
   longue.
4. Qualité des extraits = qualité du LLM branché. Avec un petit modèle local,
   le JSON peut être invalide ; le moteur retente 3 fois puis échoue proprement.
5. `opencv >= 5` casse le moteur (mesuré) — borne haute obligatoire.
6. Pas de sous-titres incrustés : c'est `subtitle_tool`/KrillinAI qui font ça.

## Decision

**APPROVED_WITH_ADAPTER.**

Approuvé parce que la capacité « N shorts classés + recadrage suivant les
visages » n'existait pas dans ARENA, que la licence MIT ne pose aucune
contrainte, que le mode local ne fait sortir aucune donnée de la machine, et
que le pipeline a été **réellement exécuté** avec des artefacts vérifiés.

Avec adaptateur, et sous conditions, parce que le moteur brut est inacceptable
tel quel : son mode par défaut téléverse la vidéo chez un tiers payant, il
recharge un second Whisper alors qu'ARENA en a déjà un, il télécharge sans
demander, il lit tout l'environnement, et ses dépendances non bornées le
cassent (OpenCV 5). L'adaptateur `core/connectors/youtube_shorts.py` est la
seule porte ; le moteur reste hors du dépôt, épinglé, appelé par
sous-processus avec un environnement construit.

**Réversible** : supprimer le fichier connecteur, sa déclaration dans
`runtime.py`, son entrée de permissions, son manifeste, ses tests et ce
document. Aucune dépendance à désinstaller, aucune donnée à migrer, aucune
capacité existante à restaurer.
