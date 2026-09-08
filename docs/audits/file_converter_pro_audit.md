# Audit File_Converter_Pro — ce qu'ARENA avait, ce qui manquait, ce qui s'est fusionné

*Mesuré le 08/09/2026. Dépôt audité : `Hyacinthe-primus/File_Converter_Pro`
(clone superficiel), licence **GPLv3**.*

Mission du propriétaire : exploiter les capacités utiles de File_Converter_Pro
pour en faire une capacité `file_conversion` opérationnelle d'ARENA — jamais
une deuxième application, jamais un deuxième système documentaire, jamais un
deuxième moteur vidéo/PDF. Ce document est l'étape « auditer → comparer »
avant tout code ; la décision est `docs/DECISIONS.md`, DEC-0074.

---

## 1. Audit File_Converter_Pro — ce qu'il est réellement

**Une application de bureau Windows** (PySide6, packagée en `.exe` via
PyInstaller — `packaging/build.spec`), pas un service. La conversion réelle
vit dans quatre modules :

| Fichier | Rôle mesuré |
|---|---|
| `src/converter/registry.py` (103 lignes) | Une table plate `"txt_to_pdf" -> ("_txt_to_pdf", "pdf")` — nom de méthode et extension cible. **Aucune métadonnée de disponibilité, version, plateforme ou limite de qualité** : ce que le §3 de la mission demande n'existe pas ici. |
| `src/converter/converters.py` + `advanced_conversions.py` (778 lignes) | Les méthodes de conversion elles-mêmes, une par ligne du registre. |
| `src/external_binaries.py` (434 lignes) | Résolution de binaires externes (ffmpeg, Ghostscript, ImageMagick, LibreOffice, wkhtmltopdf, pandoc) — PATH système, dossier applicatif, fichier de config INI. Une bonne idée de *forme* (jamais supposer un binaire présent) ; l'implémentation est spécifique à un `.exe` Windows gelé (`sys._MEIPASS`, `LOCALAPPDATA`). |
| `src/tasks/watcher.py` (634 lignes) + `src/tasks/scheduler.py` (378 lignes) | Dossiers surveillés (`watchdog.Observer`) et tâches planifiées (`APScheduler.BackgroundScheduler`), lus depuis `automation/*.toml`. |

**Le reste du dépôt (la majorité des lignes) n'a rien à voir avec la
conversion** : un système de hauts-faits/succès gamifiés complet
(`src/achievements/`, 5 modules, sons `.ogg`, popups, rangs), des effets
sonores, des thèmes, un centre de dons, une fenêtre de menu contextuel
Windows. Rien de tout ça n'entre dans ARENA — non demandé, et hors sujet
pour un assistant, pas une application de bureau à gamifier.

**Dépendances** (`requirements.txt`, `pyproject.toml`) : `PySide6` (GUI),
`PyMuPDF`, `pypdf`, `pdf2docx`, `pikepdf`, `reportlab`, `docx2pdf` (COM
Windows), `Pillow`, `pillow-heif`, `rawpy`, `CairoSVG`, `psd-tools`,
`ebooklib`, `pypandoc`, `weasyprint`, `ffmpeg-python`, `pyzipper`,
`matplotlib`, `watchdog`, `APScheduler`. Plusieurs sont spécifiques à
Windows (`comtypes`, `pywin32`, `winotify`) ou à l'exécutable gelé.

---

## 2. Ce qu'ARENA avait déjà (audit avant tout code)

- **Aucune capacité de conversion générale.** `tools/documents/reader.py`
  **lit** PDF/DOCX/TXT/MD/CSV/XLSX/PPTX pour le RAG (jamais n'écrit un
  fichier converti). `agents/plaquiste/devis_pdf.py` génère un PDF depuis un
  gabarit `reportlab` fixe — un cas d'usage métier précis, pas une
  conversion. **Aucune image, aucune archive, aucun format audio/vidéo ne se
  convertissait.**
- **FFmpeg existe déjà et sert la vidéo** (`tools/video/ffmpeg_tool.py`,
  `core/montage/`) — le point le plus sensible de la mission (§14) :
  « ne crée surtout pas un deuxième moteur vidéo parallèle ». `FFmpegTool`
  a reçu une méthode générique en plus, `convertir()`, plutôt qu'un second
  wrapper.
- **`pypdf` et `pypdfium2` sont déjà des dépendances** (lecture PDF, rendu de
  page en image pour l'OCR) — réutilisées telles quelles, jamais réinstallées.
- **Aucun WeasyPrint.** Le devis a son propre gabarit `reportlab` : les deux
  ne se recouvrent pas (un gabarit fixe à la charte UniC contre un rendu
  HTML/Markdown quelconque fourni par l'appelant).
- **`core/execution/travaux.py` (`FileDeTravaux`) existe déjà** — le patron
  « travail de fond, jamais bloquant, progression réelle » que le §6 de la
  mission demande. Un seul autre usage réel avant celui-ci :
  `core/connectors/suivi_video.py`.
- **Aucun scheduler, aucun watcher de dossier.** Ni `APScheduler` ni
  `watchdog` ni équivalent — voir §4 ci-dessous, « ce qui n'a pas été
  intégré ».

---

## 3. Comparaison, capacité par capacité

| Capacité | ARENA (avant) | File_Converter_Pro | Verdict |
|---|---|---|---|
| Conversion de documents (Office, HTML, Markdown, TXT) | Absente | `converters.py` + LibreOffice/pypandoc/weasyprint | **BETTER FILE_CONVERTER_PRO** — capacité neuve, construite avec LibreOffice headless (déjà présent sur cette machine) et WeasyPrint |
| Conversion d'images | Absente (`Pillow` n'était même pas une dépendance) | Pillow + pillow-heif/rawpy/CairoSVG/psd-tools | **BETTER FILE_CONVERTER_PRO** — PNG/JPG/WEBP/BMP/TIFF/GIF construits et testés ; HEIC/RAW/PSD/AVIF **non repris**, dépendances non mesurées fonctionnelles ici (voir §4) |
| Conversion audio/vidéo | FFmpeg déjà présent, méthodes ad hoc (`extract_audio`, `cut_video`) | `ffmpeg-python` | **COMBINE** — `FFmpegTool.convertir()` générique ajouté au moteur EXISTANT, jamais un second |
| Registre de conversions | Absent | Table plate nom→méthode, sans métadonnée | **BETTER ARENA (construit)** — `EntreeMoteur` porte disponibilité mesurée, version, limites de qualité, comme le §3 de la mission l'exige ; leur registre ne le fait pas |
| Résolution de binaires externes | `shutil.which` ad hoc par outil | `external_binaries.py`, config INI, %ENVVAR% | **NOT USEFUL tel quel** — pensé pour un `.exe` PyInstaller gelé (`sys._MEIPASS`) ; ARENA sonde par `shutil.which`, suffisant et déjà le patron du dépôt |
| Validation de sortie | Absente | Aucune vérification au-delà de l'existence de fichier mesurée dans le code lu | **BETTER ARENA (construit)** — `validation.py` rouvre chaque sortie dans son propre format ; a trouvé un vrai défaut LibreOffice pendant l'écriture (voir DEC-0074) |
| Sécurité fichiers (parcours de chemin, zip bomb) | Absente | Non trouvée dans le code lu (`converters.py`, `advanced_conversions.py`) | **BETTER ARENA (construit)** — `securite.py`, sabotage-vérifié |
| Watch folders / tâches planifiées | Absent | `watchdog` + `APScheduler`, lu depuis TOML | **NOT USEFUL ici** — adopter l'un ou l'autre serait le « deuxième ordonnanceur » que la mission interdit (§15, §2) ; ARENA n'a AUCUN scheduler à étendre — voir §4 |
| Interface graphique | PySide6 complète (+ gamification) | — | **NOT USEFUL** — ARENA a sa propre interface (§24 de la mission) ; rien de la GUI n'entre |
| Batch / file d'attente | `ConversionWorker` (thread Qt) | — | **COMBINE** — `core/execution/travaux.py` (`FileDeTravaux`), déjà existant, réutilisé tel quel (`core/production/conversion/lot.py`) |
| Licence | GPLv3 | — | **Aucun code copié** — voir §5 |

---

## 4. Ce qui n'a délibérément PAS été intégré, et pourquoi

- **Watch folders et tâches planifiées.** ARENA ne porte aujourd'hui aucun
  scheduler ni surveillance de dossier — ni `APScheduler`, ni `watchdog`, ni
  équivalent. Les adopter pour cette seule capacité serait exactement le
  « deuxième moteur d'orchestration » que la mission interdit au niveau le
  plus profond. **SUGGESTION — NON IMPLÉMENTÉE** : si le besoin réel se
  présente (« dès qu'un PDF arrive dans ce dossier, convertis-le »), il
  demande d'abord un scheduler ARENA lui-même, une décision qui dépasse
  cette mission.
- **HEIC, AVIF, RAW, PSD, EPUB, SVG→PDF (CairoSVG l'a, non branché ici).**
  Chacun demande soit un système de codecs non mesuré fonctionnel sur cette
  machine (`pillow-heif`/`rawpy` : dépendent de bibliothèques système non
  vérifiées), soit une dépendance neuve non demandée explicitement
  (`ebooklib` pour EPUB). Le registre ne les déclare pas : un format absent
  du registre est un format que ce dépôt refuse de promettre, jamais un
  format silencieusement cassé.
- **`docx2pdf` (COM Windows) et l'intégration menu contextuel Windows.**
  Windows-only par construction ; ARENA vise Linux/conteneur d'abord
  (Dockerfile, CI). LibreOffice headless couvre le même besoin,
  multiplateforme.
- **`external_binaries.py` tel quel.** Écrit pour un exécutable PyInstaller
  gelé (`sys._MEIPASS`, `%ENVVAR%`). `shutil.which()` (déjà le patron
  d'ARENA — `tools/video/ffmpeg_tool.py`) suffit et reste cohérent avec le
  reste du dépôt.
- **Le système de hauts-faits/gamification, les thèmes, les dons, les
  sons.** Hors sujet pour une capacité d'ARENA.

---

## 5. Licence

File_Converter_Pro est **GPLv3** (`LICENSE.md`). ARENA est un logiciel
**propriétaire, tous droits réservés** (`LICENSE` du dépôt) — les deux
licences sont incompatibles pour toute copie de code.

**Aucune ligne de code de File_Converter_Pro n'a été copiée.** Chaque moteur
de `core/production/conversion/moteurs.py` est une implémentation neuve
d'ARENA contre une bibliothèque tierce ou un binaire externe — au même
titre que `core/connectors/ifc_generation.py` contre IfcOpenShell (LGPL) ou
`core/connectors/github.py` contre l'API GitHub. Ce qui a été repris de
l'audit du dépôt externe, c'est une **idée générale** (un registre
source→cible avec fallback, une résolution de binaire par sonde plutôt que
par supposition) — pas une ligne, pas une structure de fichier, pas un nom
de fonction.

Les nouvelles dépendances de cette mission (`requirements.txt`) portent
chacune leur propre licence, vérifiée avant ajout :

| Dépendance | Licence | Compatible avec un dépôt propriétaire ? |
|---|---|---|
| Pillow | MIT-CMU | Oui — permissive |
| WeasyPrint | BSD-3-Clause | Oui — permissive |
| Markdown | BSD-3-Clause | Oui — permissive |
| CairoSVG | LGPL-3.0-or-later | Oui — bibliothèque appelée, jamais modifiée ni recopiée (même régime qu'IfcOpenShell) |
| LibreOffice (`soffice`) | MPL-2.0 | Oui — binaire système invoqué en sous-processus, jamais lié ni distribué avec ARENA |

---

## 6. Décision

Voir `docs/DECISIONS.md`, **DEC-0074**.

Résumé : une capacité canonique `file_conversion`, portée par un connecteur
unique (`core/connectors/file_conversion.py`) suivant le contrat
`Connecteur` déjà existant, avec un registre déclaratif
(`core/production/conversion/registre.py`) qui sait exactement quel moteur
sert quel couple de formats, sa disponibilité RÉELLEMENT mesurée sur cette
machine, et ses limites de qualité connues. Six moteurs, tous déjà présents
ou ajoutés avec une licence compatible : LibreOffice, Pillow, CairoSVG,
WeasyPrint, pypdfium2 (déjà une dépendance), et le `FFmpegTool` déjà
existant, étendu d'une méthode générique plutôt que dupliqué. Le lot passe
par `FileDeTravaux`, déjà existant. Dioumtoukay reçoit une nouvelle action
(`ACTION: convertir`) qui appelle le connecteur — le chemin par lequel
n'importe quel modèle atteint la capacité, sans en connaître le moteur.
