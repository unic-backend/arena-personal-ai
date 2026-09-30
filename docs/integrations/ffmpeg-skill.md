# Capacités FFmpeg structurées

ARENA utilise un seul moteur : `tools.video.ffmpeg_tool.FFmpegTool`.
L'intégration ne lance jamais les scripts de `ffmpeg-skill` et n'ajoute ni MCP,
routeur, job store, cloud ni clé API.

## Prérequis

Installer `ffmpeg` et `ffprobe` dans `PATH`. Aucun paquet Python supplémentaire
n'est requis. Une absence est rendue avec `status: not_configured` et
`error_code: NOT_CONFIGURED`.

## Appel déterministe depuis un agent

L'agent décide **quoi** faire, puis remet une opération fermée au moteur :

```python
from apps.backend.config import MEDIA_DIR
from tools.video.ffmpeg_tool import FFmpegTool

outil = FFmpegTool()
plan = outil.executer(
    "fit",
    MEDIA_DIR / "incoming" / "interview.mp4",
    MEDIA_DIR / "rendered" / "interview_reel.mp4",
    media_root=MEDIA_DIR,
    options={"width": 1080, "height": 1920, "mode": "blur"},
    dry_run=True,
)
# Après validation/autorisation, même appel avec dry_run=False.
```

Opérations : `trim`, `resize`, `fit`, `rotate`, `mirror`, `reverse`, `speed`,
`normalize_audio`, `extract_audio`, `delivery`. Modes de fit : `pad`, `crop`,
`blur`. Profils : `youtube`, `shorts`, `reels`, `tiktok`, `x`, `linkedin`,
`facebook`.

Aucun prompt ou filtergraph libre n'est accepté. Les chemins d'entrée et sortie
doivent rester sous la racine média fournie. Une sortie existante ou identique
à la source est refusée.

## Cycle et résultat

`executer` suit : validation des chemins/paramètres → plan → probe entrée →
FFmpeg avec délai → probe sortie temporaire → vérification flux/propriétés →
publication atomique. Un succès contient les valeurs réellement mesurées :
`output_path`, `duration`, `width`, `height`, `fps`, `video_codec`,
`audio_codec`, `audio_channels`, `file_size` et `verification`.

Une panne, un timeout, un fichier vide/corrompu ou une propriété incorrecte ne
publie pas l'artefact et nettoie le temporaire. Le moteur ne fabrique pas
d'URL ; le routeur média est seul responsable de convertir un chemin vérifié
en URL ARENA.

## Architecture existante

Pour un montage multi-pistes, continuer à employer `core/montage` et son
planificateur fermé. Pour un projet long/reprenable, employer le journal de
`core/production/journal_projet.py`. Cette API est la couche d'exécution
locale, pas un second orchestrateur ni une seconde persistance.

Audit et choix de portée :
[`docs/audits/ffmpeg_skill_audit_2026-09-30.md`](../audits/ffmpeg_skill_audit_2026-09-30.md).
