# Audit — OpenCut comme moteur de montage d'ARENA VIDEO

*Demandé le 01/09/2026 : intégrer OpenCut comme moteur de montage réel sous
l'espace VIDEO existant, avec une couche d'opérations structurées pilotable
par l'intelligence vidéo. Audit d'abord, rien installé avant preuve.*

Tout ce qui suit a été **mesuré**, pas lu dans une annonce. Les deux dépôts
ont été clonés, les licences ouvertes, et la question qui décide de
l'architecture a été tranchée par un test réel.

---

## 1. Les deux dépôts, mesurés

### OpenCut — la réécriture (`OpenCut-app/OpenCut`)

| | |
|---|---|
| Licence | **MIT** (`LICENSE`, « Copyright 2026 OpenCut ») + `license = "MIT"` dans `Cargo.toml` |
| Taille | 1,6 Mo |
| Code | **15 fichiers Rust**, 65 fichiers TS/TSX |
| Dernier commit | `400f097`, **2026-08-01** — « feat(desktop): add foundational GPUI primitives » |

**Les capacités annoncées n'existent pas encore.** Recherche sur tout le
dépôt :

| Capacité annoncée | Fichiers qui la mentionnent |
|---|---|
| MCP (pilotage par agent IA) | **0** |
| Headless | **0** |
| Editor API | **0** |
| Timeline | 3 |
| Plugin | 3 |

Les 65 occurrences de « export » sont le mot-clé JavaScript, pas une capacité
d'export vidéo. `apps/api/` contient **4 fichiers**, dont un `index.ts` et une
configuration Cloudflare.

Le README du dépôt le dit lui-même :

> « You can still find the previous version at opencut-classic, **which is the
> one to reach for today**. opencut.app still runs the classic version. »

**Conclusion : intégrer la réécriture aujourd'hui reviendrait à intégrer une
intention.** Ce que la mission interdit explicitement.

### OpenCut classic (`OpenCut-app/opencut-classic`)

| | |
|---|---|
| Licence | **MIT** (« Copyright 2025-2026 OpenCut ») |
| Taille | 16 Mo |
| Dernier commit | `cf5e79e`, **2026-05-17** — « docs: readme ». Dépôt **archivé** |
| Architecture | Application **Next.js 16**, ~45 domaines (`timeline/`, `rendering/`, `effects/`, `masks/`, `subtitles/`, `wasm/`…) |

C'est un éditeur réel et complet. Son moteur de rendu
(`apps/web/src/services/renderer/scene-exporter.ts`) est **natif navigateur** :

- `mediabunny` pour le muxage (Mp4/WebM),
- `CanvasRenderer` sur un canvas HTML,
- `opencut-wasm` pour le temps et les fréquences d'image.

**Aucun chemin headless ni serveur** : recherche `headless|puppeteer|playwright`
dans tout `apps/web/src` → une seule occurrence, dans `site/external-tools.ts`,
sans rapport avec le rendu.

---

## 2. Licences — le détail qui compte

| Composant | Licence | Conséquence |
|---|---|---|
| OpenCut (réécriture) | MIT | Compatible, avis de copyright à préserver |
| OpenCut classic | MIT | Idem |
| `opencut-wasm` 0.2.10 | MIT | Compatible |
| **`mediabunny` 1.55.5** | **MPL-2.0** | **Copyleft faible, au fichier.** L'utiliser tel quel comme dépendance n'oblige à rien ; **modifier ses fichiers** obligerait à publier ces modifications. À ne jamais forker sans le savoir. |

Aucune licence incompatible trouvée. La seule à surveiller est `mediabunny`,
et elle n'est pas MIT contrairement à ce que le dépôt principal laisse croire.

---

## 3. La mesure qui décide de l'architecture

Si le rendu d'OpenCut est natif navigateur, la seule façon de l'exécuter sans
interface est un navigateur piloté. **Est-ce que ça marche vraiment ici ?**

Testé avec le Chromium de cette machine, page servie en contexte sécurisé :

```
vp8            : supporté   → 15 images réellement encodées
vp09.00.10.08  : supporté
av01.0.04M.08  : supporté
avc1.42001f    : NON supporté   (H.264 absent de ce Chromium)
```

Premier test fait sur `about:blank` : `VideoEncoder` indéfini. **C'était un
faux négatif** — WebCodecs exige un contexte sécurisé. Re-testé sur
`http://127.0.0.1`, l'API est là. Conclusion inversée par la re-mesure.

**Ce que ça établit :**
1. Un rendu headless par navigateur est techniquement possible — en **WebM
   (VP8/VP9/AV1)**, jamais en MP4/H.264 directement.
2. Le MP4 reste atteignable : ARENA a déjà ffmpeg pour transcoder.
3. Le coût est réel : Next.js 16 + un navigateur + WASM, pour rendre une
   timeline.

---

## 4. Ce qu'ARENA a déjà — inventaire vérifié

| Capacité | Existe | Où |
|---|---|---|
| Découpe, extraction audio, incrustation de sous-titres | **Oui** | `tools/video/ffmpeg_tool.py` (`cut_video`, `extract_audio`, `burn_subtitles`) |
| Passage en 9:16 | **Oui** | `tools/video/crop_tool.py::convert_to_vertical_9_16` |
| Transcription mot à mot | **Oui** | `tools/audio/transcription_tool.py` (faster-whisper) |
| Sous-titres ASS style TikTok | **Oui** | `tools/video/subtitle_tool.py` |
| Choix des extraits | **Oui** | `agents/clip_selector/` |
| Analyse de contenu vidéo | **Oui** | `agents/video_analyzer/` |
| Génération de vidéo | **Oui** | connecteurs `wan2gp` et `moneyprinter` |
| Audit de prompt vidéo | **Oui** | `tools/video/prompt_audit.py` (DEC-0015) |
| **Projet / timeline éditable** | **NON** | — |
| **Composition multi-pistes** (logo + texte + audio superposés) | **NON** | — |
| **Couche d'opérations structurées pilotable par l'IA** | **NON** | — |

**ARENA n'a aucune notion de projet ni de timeline.** Ses outils sont des
appels ffmpeg ponctuels : une entrée, une sortie, rien entre les deux. C'est
exactement le trou qu'un éditeur comble.

---

## 5. Ce que je recommande, et ce que je refuse

### Refusé — la réécriture OpenCut, aujourd'hui
MCP, headless et Editor API sont annoncés et **absents du code**. La mission
l'interdit en toutes lettres : « DO NOT blindly integrate an unfinished
rewrite merely because it contains attractive future architecture. »

### Refusé — copier l'interface d'OpenCut classic dans ARENA
Deux éditeurs vidéo concurrents dans le même produit, dont un archivé et
fondé sur Next.js 16 que le dépôt n'utilise nulle part ailleurs. La mission
l'interdit aussi.

### Refusé — forker `mediabunny`
MPL-2.0 au fichier. À utiliser tel quel ou pas du tout.

### Retenu — le MODÈLE de projet, pas le moteur
Ce qui manque à ARENA n'est pas un encodeur : elle en a un (ffmpeg, local,
compatible RTX A2000). Ce qui manque est une **représentation de projet
éditable** et une **couche d'opérations validées** que l'IA pilote.

OpenCut classic sert de **référence d'implémentation** pour ce modèle —
c'est le rôle que la mission lui assigne — et le rendu reste sur ffmpeg,
déjà présent, déjà local, déjà testé.

La frontière est posée pour que le moteur de rendu soit **remplaçable** : le
jour où la réécriture OpenCut livre son Editor API et son MCP, elle se
branche derrière la même couche d'opérations, sans toucher à l'intelligence
vidéo.

---

## Ce que ça coûte si cet audit est faux

Si je me trompe en refusant le rendu par navigateur, ARENA se prive de la
composition riche d'OpenCut (masques, effets, transitions avancées) et devra
les réimplémenter une par une sur ffmpeg — lentement. Si je me trompais en
l'acceptant, ARENA embarquerait un navigateur, Next.js 16 et un dépôt archivé
dans le chemin de rendu de chaque vidéo, sur une machine à une seule carte
graphique. Le second risque est plus cher et plus difficile à défaire : c'est
pourquoi la frontière remplaçable existe.
