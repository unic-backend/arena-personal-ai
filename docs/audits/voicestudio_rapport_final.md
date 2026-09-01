# VoiceStudio — rapport final de mission

*Nuit du 01/09/2026. Audit détaillé → `docs/audits/voicestudio_audit.md`.
Audit général d'ARENA qui a suivi → `docs/audits/audit_general_2026-09-01.md`.*

Les dix points demandés, dans l'ordre. **Chaque chiffre a été mesuré dans la
session qui l'écrit.** Ce qui ne l'a pas été porte `UNKNOWN` et le dit.

---

## 1. Résultats de l'audit

VoiceStudio est un backend FastAPI de **38 routeurs**, port **3900** en boucle
locale, **sans aucune authentification** (son propre code l'explique). Il
déclare 16 moteurs TTS et 11 ASR.

**Déclaré n'est pas disponible.** Après installation sur cette machine :

```
/engines/tts  -> 1 disponible sur 16 : kittentts
/engines/asr  -> 3 disponibles sur 11 : faster-whisper,
                 faster-whisper-isolated, sherpa-onnx-asr
```

Trois défauts d'amont mesurés, **aucun corrigé dans son source** (le modifier
créerait les obligations AGPL) — contournés par la configuration :

1. `torchaudio.set_audio_backend` a disparu après torch 2.0 et
   `backend/main.py:626` l'appelle sans garde ; `pyproject.toml` autorise
   `>=2.4`, donc une installation conforme **ne démarre pas**. Seul `uv.lock`
   (`==2.8.0`) fonctionne.
2. `pip install kittentts` installe `0.1.3` ; le code appelle
   `generate(clean_text=…)`, qui n'existe qu'en `0.8.1`, distribuée seulement
   par une release GitHub.
3. `sherpa-onnx` ne peut pas charger les modèles Piper que sa doc annonce :
   `services/tts_backend.py` ne passe ni `data_dir` ni `lexicon`, et le
   processus **tombe en entier**.

## 2. Version et commit utilisés

`0.5.1`, commit **`a30b7166`** (30/08/2026).

## 3. Licences

| Composant | Licence | Utilisé |
|---|---|---|
| **VoiceStudio** | **AGPL-3.0-only** | comme **processus séparé**, jamais copié |
| `omnivoice/` (Han Zhu) | Apache-2.0 | non — paquet absent |
| `kittentts` 0.8.1 | Apache-2.0 | **oui** |
| `faster-whisper` / CTranslate2 | MIT | **oui** |
| `Systran/faster-whisper-base` | MIT | **oui** |
| `vits-piper-fr_FR-siwis` | dataset CC-BY 4.0 | non (défaut 3) |

**Aucune licence incompatible.** ARENA est « All rights reserved » : copier du
source AGPL, ou l'importer comme bibliothèque, ferait d'ARENA une œuvre
dérivée et l'obligerait à passer sous AGPL en entier.

*Analyse d'ingénierie, pas un avis juridique.*

## 4. Architecture d'intégration

```
ARENA  →  agents/audio/  →  core/connectors/audio_voix.py
       →  HTTP sur 127.0.0.1:3900  →  VoiceStudio (processus séparé, AGPL)
       →  fichier audio  →  re-sondé par ffprobe  →  ARENA
```

Trois règles portent le connecteur :

1. **Une voix ne sort pas de la machine.** Toute adresse non locale est
   refusée (`AdresseNonLocale`).
2. **Parler est une écriture** : file de confirmation, comme le devis PDF.
3. **Un `200` n'est pas un succès** : le WAV est re-sondé, et une durée
   illisible efface le fichier et rend un échec.

## 5. Capacités intégrées

| Capacité | État |
|---|---|
| Text-to-speech | **Vérifié** (kittentts) |
| Speech-to-text | **Vérifié** (faster-whisper `base`) |
| Choix du moteur par disponibilité mesurée | **Vérifié** |
| Voix off dans une vidéo montée | **Vérifié de bout en bout** |
| Repli de transcription pour l'analyse vidéo | **Vérifié** |
| Diagnostic (`scripts/doctor.py`) | **Vérifié** |

## 6. Capacités délibérément non intégrées

Clonage de voix, voice design, dictée, doublage vidéo, diarisation, séparation
voix/fond, lots, narration multi-locuteurs, audiobooks, long-form.

**Une seule raison** : leurs moteurs ne sont pas installables ici (venvs
séparés, `git clone`, modèles de plusieurs Go, GPU). Les brancher sans pouvoir
les exécuter aurait déclaré une capacité qui ne marche pas.

## 7. Composants ARENA réutilisés

`Connecteur` et ses capacités · `ControleAcces` · `FileDAttente` ·
`ResultatAction` · `JournalDesActions` · `FFmpegTool` · le registre ·
l'aiguilleur et `core/execution/voies.py` · `core/montage/` (VOLET OpenCut).

**Aucune dépendance nouvelle. Aucun paquet ajouté à `requirements.txt`.**

## 8. Ce qui n'a pas été dupliqué

- **Les sous-titres restent au studio**, qui les fabrique déjà de bout en bout.
  L'intention `AUDIO` les lui prenait : régression attrapée par la suite
  existante, corrigée, et un test fixe la frontière.
- **`tools/audio/transcription_tool.py` n'est pas touché.** Il reste le chemin
  normal de l'analyse vidéo — il ne dépend d'aucun autre programme. VoiceStudio
  n'intervient qu'en repli, et le repli est annoncé.

## 9. Tests et workflows réellement exécutés

```
python -m ruff check .                                      -> All checks passed!
python -m pytest tests/ -q                                  -> 2586 passed, 44 deselected
OMNIVOICE_URL=http://127.0.0.1:9 python -m pytest tests/ -q -> 2586 passed  (conditions CI)
python -m pytest -m integration (audio)                     -> 4 passed, contre le vrai service
```

**Chaîne complète, texte → voix → texte**, à travers le registre d'ARENA :

```
Santé      : OPERATIONAL | VoiceStudio 0.5.1 sur 127.0.0.1:3900 (cpu)
Transcrire : SUCCESS | "Hello, this is Unic Placquist. We install drywall
                       partitions in Dakar."
Parler     : NEEDS_CONFIRMATION -> confirmée -> SUCCESS
             5742 ms, 275678 octets, amplitude max 26029 (pas du silence)
```

**Audio + vidéo** : voix off → piste audio de la timeline → MP4 final
`h264` 1080×1920 **+ `aac`**, `duration=5.000000`, audio extrait du fichier
final à **25892** d'amplitude.

**Repli de transcription** : un vrai MP4 à piste AAC, audio extrait par
ffmpeg, modèle local levant `ModeleAbsent`, VoiceStudio rendant le texte.

## 10. VRAM, performances, limites

**`UNKNOWN` — la VRAM.** Cette machine n'a **pas de GPU**
(`gpu_name: ""`, `vram_total_gb: 0.0`). Aucune observation n'est possible sur
la RTX A2000, et **aucune n'a été inventée**.

ARENA **n'ajoute aucune politique VRAM** : VoiceStudio a la sienne
(`min_vram_gb` par moteur, `routing_status`, `/model/unload/{id}`, éviction).
Deux politiques concurrentes valent moins qu'une seule qui marche.

**`UNKNOWN` — une voix française.** Le seul moteur TTS installable ici est
anglais, et `/engines/tts` **n'expose aucune information de langue** : ARENA ne
peut pas router par langue. Le message de succès **nomme le moteur qui a
parlé**, pour que le propriétaire voie qu'un moteur anglais a lu son texte.

**Limite** : VoiceStudio n'est ni installé ni démarré par ARENA — c'est un
programme séparé sous une autre licence. Sans lui, ARENA répond
`NOT_CONFIGURED` et dit ce qui manque. Il ne simule rien.

---

## Ce que la mission a produit en plus

L'audit général qui a suivi a trouvé **dix défauts réels sur une suite verte**
— `/health` qui taisait six agents, un flux qui mourait en silence, des
sous-titres qui s'inventaient, une détection annoncée sans analyse. Détail et
preuves → `docs/audits/audit_general_2026-09-01.md`.
