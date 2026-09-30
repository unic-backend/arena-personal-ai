"""Unique FFmpeg capability layer used by ARENA.

The legacy boolean methods remain for their existing callers.  New code should use
``planifier`` / ``executer``: a closed, typed operation is validated, executed without
a shell, written through a staging file, and probed before success is reported.

The structured workflow is inspired by kajisho5/ffmpeg-skill (MIT), audited at
commit df5d2736b171473742b86789e5179bdfb0976373.  No upstream source is copied.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger("usman.tools.video.ffmpeg")

CARACTERES_PIEGES = frozenset("'\\:,;[]")
DELAI_SONDE = 30.0
DELAI_TRAITEMENT = 900.0

PROFILS_LIVRAISON: Dict[str, Dict[str, Any]] = {
    "youtube": {"width": 1920, "height": 1080, "fps": 30, "audio_bitrate": "192k"},
    "shorts": {"width": 1080, "height": 1920, "fps": 30, "audio_bitrate": "192k"},
    "reels": {"width": 1080, "height": 1920, "fps": 30, "audio_bitrate": "192k"},
    "tiktok": {"width": 1080, "height": 1920, "fps": 30, "audio_bitrate": "192k"},
    "x": {"width": 1280, "height": 720, "fps": 30, "audio_bitrate": "128k"},
    "linkedin": {"width": 1920, "height": 1080, "fps": 30, "audio_bitrate": "192k"},
    "facebook": {"width": 1920, "height": 1080, "fps": 30, "audio_bitrate": "192k"},
}
OPERATIONS = frozenset({
    "trim", "resize", "fit", "rotate", "mirror", "reverse", "speed",
    "normalize_audio", "extract_audio", "delivery",
})


@contextmanager
def _chemin_sans_piege(fichier: Path):
    if not (CARACTERES_PIEGES & set(fichier.name)):
        yield fichier
        return
    dossier = Path(tempfile.mkdtemp(prefix="arena-sous-titres-"))
    copie = dossier / f"sous-titres{fichier.suffix}"
    try:
        shutil.copy2(fichier, copie)
        yield copie
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


@dataclass(frozen=True)
class MediaPlan:
    operation: str
    input_path: str
    output_path: str
    command: List[str]
    expected: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MediaResult:
    status: str
    output_path: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_channels: Optional[int] = None
    file_size: Optional[int] = None
    warnings: List[str] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_code: str = ""
    plan: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _fraction(valeur: Any) -> Optional[float]:
    try:
        if valeur in (None, "", "0/0"):
            return None
        if isinstance(valeur, str) and "/" in valeur:
            n, d = valeur.split("/", 1)
            return float(n) / float(d) if float(d) else None
        return float(valeur)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _entier(nom: str, valeur: Any, minimum: int = 1, maximum: int = 7680) -> int:
    if isinstance(valeur, bool):
        raise ValueError(f"{nom} invalide")
    try:
        resultat = int(valeur)
    except (TypeError, ValueError) as erreur:
        raise ValueError(f"{nom} doit etre un entier") from erreur
    if not minimum <= resultat <= maximum:
        raise ValueError(f"{nom} doit etre compris entre {minimum} et {maximum}")
    return resultat


def _nombre(nom: str, valeur: Any, minimum: float, maximum: float) -> float:
    try:
        resultat = float(valeur)
    except (TypeError, ValueError) as erreur:
        raise ValueError(f"{nom} doit etre un nombre") from erreur
    if not math.isfinite(resultat) or not minimum <= resultat <= maximum:
        raise ValueError(f"{nom} doit etre compris entre {minimum} et {maximum}")
    return resultat


def _atempo(vitesse: float) -> str:
    """Compose atempo because each FFmpeg stage only accepts 0.5..2.0."""
    facteurs: List[float] = []
    reste = vitesse
    while reste > 2:
        facteurs.append(2.0)
        reste /= 2
    while reste < 0.5:
        facteurs.append(0.5)
        reste /= 0.5
    facteurs.append(reste)
    return ",".join(f"atempo={f:.8g}" for f in facteurs)


class FFmpegTool:
    """ARENA's single local FFmpeg execution abstraction."""

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        self.ffprobe_path = ffprobe_path or self._find_ffprobe()

    def _find_ffmpeg(self) -> str:
        path = shutil.which("ffmpeg")
        if path:
            return path
        home = Path.home()
        candidats = list(home.glob("AppData/Local/Microsoft/WinGet/Packages/**/ffmpeg.exe"))
        candidats += list(home.glob("AppData/Local/Programs/**/ffmpeg.exe"))
        return str(candidats[0].resolve()) if candidats else "ffmpeg"

    def _find_ffprobe(self) -> str:
        path = shutil.which("ffprobe")
        if path:
            return path
        voisin = Path(self.ffmpeg_path).with_name(
            "ffprobe.exe" if self.ffmpeg_path.lower().endswith(".exe") else "ffprobe")
        return str(voisin) if voisin.exists() else "ffprobe"

    def is_available(self) -> bool:
        try:
            res = subprocess.run(
                [self.ffmpeg_path, "-version"], capture_output=True, timeout=10, check=False)
            return res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def get_executable(self) -> str:
        return self.ffmpeg_path

    def probe(self, path: str | Path, timeout: float = DELAI_SONDE) -> Dict[str, Any]:
        """Return measured metadata, or a structured error; never infer from a suffix."""
        fichier = Path(path)
        base: Dict[str, Any] = {
            "ok": False, "path": str(fichier), "duration": None, "width": None,
            "height": None, "fps": None, "video_codec": None, "audio_codec": None,
            "audio_channels": None, "file_size": None, "streams": [], "error": "",
        }
        if not fichier.is_file():
            base["error"] = "fichier introuvable"
            return base
        try:
            base["file_size"] = fichier.stat().st_size
            proc = subprocess.run(
                [self.ffprobe_path, "-v", "error", "-show_format", "-show_streams",
                 "-of", "json", str(fichier)], capture_output=True, text=True,
                timeout=timeout, check=False)
        except FileNotFoundError:
            base["error"] = "ffprobe introuvable"
            return base
        except subprocess.TimeoutExpired:
            base["error"] = "ffprobe a depasse le delai"
            return base
        if proc.returncode != 0:
            base["error"] = (proc.stderr.strip().splitlines() or ["media illisible"])[-1]
            return base
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            base["error"] = "reponse ffprobe invalide"
            return base
        streams = data.get("streams") or []
        base["streams"] = [s.get("codec_type") for s in streams if s.get("codec_type")]
        duration = (data.get("format") or {}).get("duration")
        base["duration"] = _fraction(duration)
        for stream in streams:
            if stream.get("codec_type") == "video" and base["video_codec"] is None:
                base.update(width=stream.get("width"), height=stream.get("height"),
                            fps=_fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
                            video_codec=stream.get("codec_name"))
                base["duration"] = base["duration"] or _fraction(stream.get("duration"))
            elif stream.get("codec_type") == "audio" and base["audio_codec"] is None:
                base.update(audio_codec=stream.get("codec_name"),
                            audio_channels=stream.get("channels"))
                base["duration"] = base["duration"] or _fraction(stream.get("duration"))
        base["ok"] = bool(streams) and bool(base["file_size"])
        if not base["ok"]:
            base["error"] = "aucun flux media lisible"
        return base

    @staticmethod
    def _dans_racine(path: str | Path, media_root: str | Path) -> Path:
        racine = Path(media_root).resolve()
        chemin = Path(path).resolve()
        try:
            chemin.relative_to(racine)
        except ValueError as erreur:
            raise ValueError(f"chemin hors de MEDIA_DIR: {path}") from erreur
        return chemin

    def planifier(self, operation: str, input_path: str | Path, output_path: str | Path,
                  *, media_root: str | Path, options: Optional[Mapping[str, Any]] = None) -> MediaPlan:
        """Validate a closed operation and return the exact argument array without executing it."""
        if operation not in OPERATIONS:
            raise ValueError(f"operation inconnue: {operation}")
        entree = self._dans_racine(input_path, media_root)
        sortie = self._dans_racine(output_path, media_root)
        if not entree.is_file():
            raise ValueError(f"fichier introuvable: {entree.name}")
        if entree == sortie:
            raise ValueError("la source ne peut jamais etre ecrasee")
        if sortie.exists():
            raise ValueError("la sortie existe deja; choisir un nouvel artefact")
        opts = dict(options or {})
        expected: Dict[str, Any] = {}
        args: List[str] = [self.ffmpeg_path, "-nostdin", "-hide_banner", "-y"]

        start = None
        if operation == "trim":
            start = _nombre("start", opts.get("start", 0), 0, 86400 * 7)
            duration = _nombre("duration", opts.get("duration"), 0.001, 86400 * 7)
            args += ["-ss", f"{start:.6f}"]
            expected["duration"] = duration
        args += ["-i", str(entree)]
        vf: List[str] = []
        af: List[str] = []

        if operation == "trim":
            args += ["-t", f"{expected['duration']:.6f}"]
        elif operation == "resize":
            width = _entier("width", opts.get("width"))
            height = _entier("height", opts.get("height"))
            vf.append(f"scale={width}:{height}")
            expected.update(width=width, height=height)
        elif operation == "fit":
            width = _entier("width", opts.get("width", 1080))
            height = _entier("height", opts.get("height", 1920))
            mode = opts.get("mode", "pad")
            if mode == "crop":
                vf.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
            elif mode == "blur":
                vf.append(
                    f"split[fg][bg];[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},gblur=sigma=30[bg];[fg]scale={width}:{height}:"
                    "force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
            elif mode == "pad":
                vf.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black")
            else:
                raise ValueError("mode doit etre pad, crop ou blur")
            expected.update(width=width, height=height)
        elif operation == "rotate":
            angle = _entier("angle", opts.get("angle"), 90, 270)
            if angle not in {90, 180, 270}:
                raise ValueError("angle doit etre 90, 180 ou 270")
            vf.append({90: "transpose=clock", 180: "hflip,vflip", 270: "transpose=cclock"}[angle])
        elif operation == "mirror":
            axe = opts.get("axis", "horizontal")
            if axe not in {"horizontal", "vertical"}:
                raise ValueError("axis doit etre horizontal ou vertical")
            vf.append("hflip" if axe == "horizontal" else "vflip")
        elif operation == "reverse":
            vf.append("reverse")
            af.append("areverse")
        elif operation == "speed":
            vitesse = _nombre("factor", opts.get("factor"), 0.125, 8.0)
            vf.append(f"setpts=PTS/{vitesse:.8g}")
            af.append(_atempo(vitesse))
        elif operation == "normalize_audio":
            af.append("loudnorm=I=-14:TP=-1:LRA=11")
        elif operation == "extract_audio":
            args += ["-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
            expected["stream"] = "audio"
        elif operation == "delivery":
            profil_nom = str(opts.get("profile", "")).lower()
            if profil_nom not in PROFILS_LIVRAISON:
                raise ValueError("profil de livraison inconnu")
            profil = PROFILS_LIVRAISON[profil_nom]
            width, height = profil["width"], profil["height"]
            mode = opts.get("mode", "pad")
            if mode not in {"pad", "crop"}:
                raise ValueError("mode doit etre pad ou crop")
            if mode == "crop":
                vf.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
            else:
                vf.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black")
            vf += ["setsar=1", f"fps={profil['fps']}"]
            args += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", profil["audio_bitrate"],
                     "-movflags", "+faststart"]
            expected.update(width=width, height=height, fps=profil["fps"], stream="video")

        if vf:
            args += ["-vf", ",".join(vf)]
        if af:
            args += ["-af", ",".join(af)]
        if operation not in {"extract_audio", "delivery"}:
            args += ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac"]
            expected.setdefault("stream", "video")
        # Placeholder is replaced by a same-directory staging path at execution.
        args.append(str(sortie))
        return MediaPlan(operation, str(entree), str(sortie), args, expected)

    def executer(self, operation: str, input_path: str | Path, output_path: str | Path,
                 *, media_root: str | Path, options: Optional[Mapping[str, Any]] = None,
                 timeout: float = DELAI_TRAITEMENT, dry_run: bool = False) -> MediaResult:
        """Inspect -> plan -> execute -> probe -> verify -> atomically publish."""
        try:
            plan = self.planifier(operation, input_path, output_path,
                                  media_root=media_root, options=options)
        except ValueError as erreur:
            return MediaResult("error", error=str(erreur), error_code="INPUT_INVALID")
        plan_dict = plan.to_dict()
        if dry_run:
            return MediaResult("planned", plan=plan_dict,
                               verification={"executed": False, "input_validated": True})
        if not self.is_available():
            return MediaResult("not_configured", error="ffmpeg introuvable",
                               error_code="NOT_CONFIGURED", plan=plan_dict)
        entree_meta = self.probe(plan.input_path)
        if not entree_meta["ok"]:
            return MediaResult("error", error=f"media d'entree invalide: {entree_meta['error']}",
                               error_code="INPUT_INVALID", plan=plan_dict)
        if plan.expected.get("stream") == "video" and not entree_meta["video_codec"]:
            return MediaResult("error", error="la source ne contient aucun flux video",
                               error_code="INPUT_INVALID", plan=plan_dict)
        if operation in {"normalize_audio", "extract_audio"} and not entree_meta["audio_codec"]:
            return MediaResult("error", error="la source ne contient aucun flux audio",
                               error_code="INPUT_INVALID", plan=plan_dict)

        sortie = Path(plan.output_path)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        fd, temporaire_brut = tempfile.mkstemp(prefix=f".{sortie.stem}-", suffix=sortie.suffix,
                                               dir=sortie.parent)
        os.close(fd)
        temporaire = Path(temporaire_brut)
        temporaire.unlink(missing_ok=True)  # ffmpeg creates the container itself
        commande = [str(temporaire) if arg == plan.output_path else arg for arg in plan.command]
        try:
            proc = subprocess.run(commande, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            temporaire.unlink(missing_ok=True)
            return MediaResult("error", error="ffmpeg a depasse le delai",
                               error_code="TIMEOUT", plan=plan_dict)
        except OSError as erreur:
            temporaire.unlink(missing_ok=True)
            return MediaResult("error", error=str(erreur), error_code="FFMPEG_EXECUTION_FAILED",
                               plan=plan_dict)
        if proc.returncode != 0:
            temporaire.unlink(missing_ok=True)
            stderr = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
            return MediaResult("error", error=stderr[-1] if stderr else "ffmpeg a echoue",
                               error_code="FFMPEG_EXECUTION_FAILED", plan=plan_dict)

        meta = self.probe(temporaire)
        verification: Dict[str, Any] = {
            "exists": temporaire.is_file(), "non_empty": bool(meta.get("file_size")),
            "probe_ok": meta["ok"], "expected": dict(plan.expected), "checks": {},
        }
        attendu = plan.expected
        stream = attendu.get("stream")
        verification["checks"]["stream"] = (
            bool(meta["video_codec"]) if stream == "video" else bool(meta["audio_codec"]))
        if "width" in attendu:
            verification["checks"]["width"] = meta["width"] == attendu["width"]
            verification["checks"]["height"] = meta["height"] == attendu["height"]
        if "fps" in attendu:
            verification["checks"]["fps"] = (
                meta["fps"] is not None and abs(meta["fps"] - attendu["fps"]) <= 0.1)
        if "duration" in attendu:
            # Container/frame rounding is expected; a materially wrong cut is not.
            tolerance = max(0.15, 2 / (meta["fps"] or 25))
            verification["checks"]["duration"] = (
                meta["duration"] is not None
                and abs(meta["duration"] - attendu["duration"]) <= tolerance)
        valide = (verification["exists"] and verification["non_empty"]
                  and verification["probe_ok"] and all(verification["checks"].values()))
        if not valide:
            temporaire.unlink(missing_ok=True)
            return MediaResult("error", error="artefact de sortie invalide",
                               error_code="VERIFICATION_FAILED", verification=verification,
                               plan=plan_dict)
        try:
            # A hard link is an atomic no-clobber publication on the same filesystem:
            # unlike ``exists(); os.replace()``, another writer cannot win between the
            # check and the rename and then be overwritten silently.
            os.link(temporaire, sortie)
            temporaire.unlink()
        except OSError as erreur:
            temporaire.unlink(missing_ok=True)
            return MediaResult("error", error=str(erreur), error_code="OUTPUT_INVALID",
                               verification=verification, plan=plan_dict)
        return MediaResult(
            "success", output_path=str(sortie), duration=meta["duration"], width=meta["width"],
            height=meta["height"], fps=meta["fps"], video_codec=meta["video_codec"],
            audio_codec=meta["audio_codec"], audio_channels=meta["audio_channels"],
            file_size=meta["file_size"], verification=verification, plan=plan_dict)

    # Compatibility surface -------------------------------------------------
    def convertir(self, entree: str, sortie: str, timeout: float = 120.0) -> "tuple[bool, str]":
        if not self.is_available():
            return False, f"ffmpeg introuvable ou ne repond pas ({self.ffmpeg_path})"
        try:
            resultat = subprocess.run([self.ffmpeg_path, "-y", "-i", str(entree), str(sortie)],
                                      capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"ffmpeg n'a pas repondu en {timeout:.0f} s"
        if resultat.returncode != 0:
            erreur = resultat.stderr.decode("utf-8", errors="ignore").strip()
            return False, erreur.splitlines()[-1] if erreur else "ffmpeg a echoue sans message"
        meta = self.probe(sortie)
        return (True, "") if meta["ok"] else (False, "ffmpeg a produit un media invalide")

    def extract_audio(self, video_path: str, output_audio_path: str) -> bool:
        if not self.is_available():
            return False
        try:
            subprocess.run([self.ffmpeg_path, "-y", "-i", str(video_path), "-vn", "-acodec",
                            "pcm_s16le", "-ar", "16000", "-ac", "1", str(output_audio_path)],
                           capture_output=True, timeout=DELAI_TRAITEMENT, check=True)
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(self.probe(output_audio_path).get("audio_codec"))

    def cut_video(self, input_path: str, output_path: str, start_sec: float, duration_sec: float) -> bool:
        if not self.is_available():
            return False
        try:
            subprocess.run([self.ffmpeg_path, "-y", "-ss", str(start_sec), "-i", str(input_path),
                            "-t", str(duration_sec), "-c:v", "libx264", "-c:a", "aac",
                            str(output_path)], capture_output=True, timeout=DELAI_TRAITEMENT, check=True)
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(self.probe(output_path).get("video_codec"))

    def burn_subtitles(self, video_path: str, sub_path: str, output_path: str) -> bool:
        if not self.is_available():
            return False
        sub_file = Path(sub_path).resolve()
        if not sub_file.exists():
            return False
        with _chemin_sans_piege(sub_file) as chemin_sur:
            return self._incruster(video_path, sub_file, chemin_sur, output_path)

    def _incruster(self, video_path: str, sub_file: Path, chemin_sur: Path, output_path: str) -> bool:
        clean = str(chemin_sur).replace("\\", "/").replace(":", "\\:")
        filtre = (f"ass='{clean}'" if sub_file.suffix.lower() == ".ass" else
                  f"subtitles='{clean}':force_style='Fontname=Arial,Fontsize=18,"
                  "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
                  "Outline=2,Alignment=2,MarginV=280'")
        try:
            subprocess.run([self.ffmpeg_path, "-y", "-i", str(video_path), "-vf", filtre,
                            "-c:v", "libx264", "-c:a", "copy", str(output_path)],
                           capture_output=True, timeout=DELAI_TRAITEMENT, check=True)
        except (OSError, subprocess.SubprocessError):
            return False
        return bool(self.probe(output_path).get("video_codec"))
