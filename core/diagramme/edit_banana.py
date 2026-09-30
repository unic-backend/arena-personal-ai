"""Adaptateur local, isolé et borné vers le moteur Edit-Banana.

Edit-Banana (BIT-DataLab/Edit-Banana) permet de convertir une image de diagramme
ou schéma statique en document DrawIO éditable (.drawio / XML).

Edit-Banana est sous licence GNU AGPL-3.0 (dans son fichier LICENSE officiel) et
dépend de SAM3 (Segment Anything Model 3) et d'un ensemble de dépendances lourdes
(PyTorch, PaddleOCR, Pix2Text, etc.). Il reste un moteur externe (DEC-0008, DEC-0039)
qui tourne dans un environnement Python isolé, hors du dépôt ARENA.

ARENA valide l'image, lance le CLI officiel dans un sous-processus isolé, valide
rigoureusement le document DrawIO XML produit, puis publie uniquement ce résultat
dans son stockage d'artefacts contrôlé.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from apps.backend.config import RENDERED_DIR
from core.production.materiel import mesurer_gpu

logger = logging.getLogger("usman.diagramme.edit_banana")

EDIT_BANANA_UPSTREAM = "https://github.com/BIT-DataLab/Edit-Banana.git"
EDIT_BANANA_COMMIT = "88c6e288ef8329606114eb91924559c5d1838d2e"
FORMATS_ENTREE_SUPPORTES = frozenset({"PNG", "JPEG", "JPG", "WEBP", "BMP", "TIFF"})

LIMITES_QUALITE_DEFAUT = (
    "Reconstruction géométrique et textuelle par Edit-Banana (SAM3 + OCR). "
    "Les éléments vectorisés et textes détectés sont éditables dans DrawIO. "
    "Les tracés complexes ou formules manuscrites peuvent nécessiter des ajustements manuels."
)


def _entier_env(nom: str, defaut: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(nom, str(defaut))))
    except ValueError:
        logger.warning("%s invalide : valeur par défaut %s utilisée.", nom, defaut)
        return defaut


def _flottant_env(nom: str, defaut: float, minimum: float = 1.0) -> float:
    try:
        return max(minimum, float(os.getenv(nom, str(defaut))))
    except ValueError:
        logger.warning("%s invalide : valeur par défaut %s utilisée.", nom, defaut)
        return defaut


class ErreurEditBanana(RuntimeError):
    """Échec attendu lors de l'exécution ou validation d'Edit-Banana."""


def valider_xml_drawio(contenu_xml: str | bytes) -> tuple[bool, str]:
    """Vérifie qu'une chaîne ou flux d'octets représente un document DrawIO XML valide.

    Un document DrawIO valide est un document XML bien formé dont la racine ou les
    nœuds enfants correspondent aux balises canoniques mxfile / diagram / mxGraphModel.
    """
    if isinstance(contenu_xml, str):
        contenu_xml = contenu_xml.encode("utf-8")
    if not contenu_xml or not contenu_xml.strip():
        return False, "Le document DrawIO est vide."
    try:
        racine = ET.fromstring(contenu_xml)
    except ET.ParseError as erreur:
        return False, f"XML malformé : {erreur}"

    balise_racine = racine.tag.lower()
    if balise_racine in ("mxfile", "diagram", "mxgraphmodel", "root"):
        return True, ""

    if (
        racine.find(".//diagram") is not None
        or racine.find(".//mxGraphModel") is not None
        or racine.find(".//root") is not None
        or racine.find(".//mxCell") is not None
    ):
        return True, ""

    return False, f"Structure DrawIO non reconnue (balise racine <{racine.tag}>)."


def valider_fichier_drawio(chemin: Path) -> tuple[bool, str]:
    """Valide qu'un fichier DrawIO existe, est non vide et contient un XML DrawIO valide."""
    if not chemin.is_file():
        return False, f"Fichier DrawIO introuvable : {chemin}"
    taille = chemin.stat().st_size
    if taille == 0:
        return False, "Le fichier DrawIO écrit est vide (0 octet)."
    try:
        octets = chemin.read_bytes()
    except OSError as erreur:
        return False, f"Impossible de lire le fichier DrawIO : {erreur}"
    return valider_xml_drawio(octets)


@dataclass(frozen=True)
class ConfigurationEditBanana:
    racine: Optional[Path]
    python: Optional[Path]
    sam3_checkpoint: Optional[Path]
    sorties: Path
    timeout_secondes: float = 300.0
    pixels_max: int = 36_000_000
    cote_max: int = 8192
    executions_concurrentes: int = 1
    licence_acceptee: bool = False
    verifier_runtime: bool = True
    verifier_revision: bool = True

    @classmethod
    def depuis_environnement(cls, sorties: Optional[Path] = None) -> ConfigurationEditBanana:
        brut_racine = os.getenv("USMAN_EDIT_BANANA_ROOT", "").strip()
        racine = Path(brut_racine).expanduser().resolve() if brut_racine else None

        brut_python = os.getenv("USMAN_EDIT_BANANA_PYTHON", "").strip()
        python = Path(brut_python).expanduser().resolve() if brut_python else None

        brut_sam3 = os.getenv("USMAN_EDIT_BANANA_SAM3_CHECKPOINT", "").strip()
        sam3_checkpoint = Path(brut_sam3).expanduser().resolve() if brut_sam3 else None

        dossier_sorties = sorties or (RENDERED_DIR / "diagrams")

        return cls(
            racine=racine,
            python=python,
            sam3_checkpoint=sam3_checkpoint,
            sorties=dossier_sorties,
            timeout_secondes=_flottant_env("USMAN_EDIT_BANANA_TIMEOUT_SECONDS", 300.0),
            pixels_max=_entier_env("USMAN_EDIT_BANANA_MAX_PIXELS", 36_000_000),
            cote_max=_entier_env("USMAN_EDIT_BANANA_MAX_SIDE", 8192),
            executions_concurrentes=_entier_env("USMAN_EDIT_BANANA_CONCURRENCY", 1),
            licence_acceptee=os.getenv("USMAN_EDIT_BANANA_LICENSE_ACCEPTED", "").lower() in {"1", "true", "yes"},
        )


@dataclass(frozen=True)
class EtatEditBanana:
    disponible: bool
    raison: str
    ce_qui_manque: str
    device: str
    cpu_lent: bool
    sam3_disponible: bool
    version: str

    def to_dict(self) -> dict:
        return {
            "disponible": self.disponible,
            "raison": self.raison,
            "ce_qui_manque": self.ce_qui_manque,
            "device": self.device,
            "cpu_lent": self.cpu_lent,
            "sam3_disponible": self.sam3_disponible,
            "version": self.version,
        }


@dataclass(frozen=True)
class ResultatDiagramme:
    sortie: Path
    url: str
    provenance: Path
    format_cible: str
    largeur: int
    hauteur: int
    taille_octets: int
    device: str
    duree_secondes: float
    source_sha256: str
    limites_qualite: str

    def to_dict(self) -> dict:
        return {
            "sortie": str(self.sortie),
            "url": self.url,
            "provenance": str(self.provenance),
            "format_cible": self.format_cible,
            "largeur": self.largeur,
            "hauteur": self.hauteur,
            "taille_octets": self.taille_octets,
            "device": self.device,
            "duree_secondes": self.duree_secondes,
            "source_sha256": self.source_sha256,
            "limites_qualite": self.limites_qualite,
        }


class ServiceEditBanana:
    """Service d'isolation et d'orchestration pour le moteur externe Edit-Banana."""

    def __init__(self, configuration: Optional[ConfigurationEditBanana] = None):
        self.configuration = configuration or ConfigurationEditBanana.depuis_environnement()
        self._semaphore = asyncio.Semaphore(self.configuration.executions_concurrentes)

    def _python(self) -> Optional[Path]:
        if self.configuration.python is not None:
            return self.configuration.python
        racine = self.configuration.racine
        if racine is None:
            return None
        candidats = (
            racine / ".venv" / "Scripts" / "python.exe",
            racine / ".venv" / "bin" / "python",
        )
        return next((p for p in candidats if p.is_file()), None)

    def _trouver_checkpoint_sam3(self) -> Optional[Path]:
        if self.configuration.sam3_checkpoint is not None and self.configuration.sam3_checkpoint.is_file():
            return self.configuration.sam3_checkpoint
        racine = self.configuration.racine
        if racine is None:
            return None
        candidats = (
            racine / "models" / "sam3.pt",
            racine / "models" / "sam3_ms" / "sam3.pt",
            racine / "models" / "sam3_large.pt",
        )
        return next((p for p in candidats if p.is_file() and p.stat().st_size > 0), None)

    def etat(self) -> EtatEditBanana:
        """Vérifie l'état opérationnel du moteur sans déclencher d'inférence lourde."""
        gpu = mesurer_gpu()
        device = "cuda" if gpu is not None else "cpu"

        if not self.configuration.licence_acceptee:
            return EtatEditBanana(
                disponible=False,
                raison="La licence GNU AGPL-3.0 d'Edit-Banana doit être acceptée explicitement (USMAN_EDIT_BANANA_LICENSE_ACCEPTED=true).",
                ce_qui_manque="USMAN_EDIT_BANANA_LICENSE_ACCEPTED=true",
                device=device,
                cpu_lent=device == "cpu",
                sam3_disponible=False,
                version=EDIT_BANANA_COMMIT,
            )

        racine = self.configuration.racine
        if racine is None or not racine.is_dir():
            return EtatEditBanana(
                disponible=False,
                raison="USMAN_EDIT_BANANA_ROOT n'est pas configuré ou le dossier n'existe pas.",
                ce_qui_manque="USMAN_EDIT_BANANA_ROOT",
                device=device,
                cpu_lent=device == "cpu",
                sam3_disponible=False,
                version=EDIT_BANANA_COMMIT,
            )

        point_entree = racine / "main.py"
        sam3_ckpt = self._trouver_checkpoint_sam3()
        sam3_disponible = sam3_ckpt is not None

        if not point_entree.is_file():
            return EtatEditBanana(
                disponible=False,
                raison="Le checkout Edit-Banana configuré est incomplet (main.py absent).",
                ce_qui_manque=str(point_entree),
                device=device,
                cpu_lent=device == "cpu",
                sam3_disponible=sam3_disponible,
                version=EDIT_BANANA_COMMIT,
            )

        python = self._python()
        if python is None or not python.is_file():
            return EtatEditBanana(
                disponible=False,
                raison="L'environnement Python isolé d'Edit-Banana est absent.",
                ce_qui_manque="Environnement Python (.venv/bin/python ou USMAN_EDIT_BANANA_PYTHON)",
                device=device,
                cpu_lent=device == "cpu",
                sam3_disponible=False,
                version=EDIT_BANANA_COMMIT,
            )

        if self.configuration.verifier_revision:
            try:
                revision = subprocess.run(
                    ["git", "-C", str(racine), "rev-parse", "HEAD"],
                    capture_output=True, text=True, check=False, timeout=5,
                )
                if revision.returncode != 0:
                    return EtatEditBanana(
                        disponible=False,
                        raison="Impossible de vérifier la révision Git d'Edit-Banana.",
                        ce_qui_manque="git revision check failed",
                        device=device,
                        cpu_lent=device == "cpu",
                        sam3_disponible=False,
                        version=EDIT_BANANA_COMMIT,
                    )
            except (OSError, subprocess.TimeoutExpired) as erreur:
                return EtatEditBanana(
                    disponible=False,
                    raison=f"Révision Edit-Banana non vérifiable ({type(erreur).__name__}).",
                    ce_qui_manque=str(erreur),
                    device=device,
                    cpu_lent=device == "cpu",
                    sam3_disponible=False,
                    version=EDIT_BANANA_COMMIT,
                )

        sam3_ckpt = self._trouver_checkpoint_sam3()
        if sam3_ckpt is None:
            return EtatEditBanana(
                disponible=False,
                raison="Poids SAM3 manquants : le fichier de checkpoint sam3.pt est introuvable sous models/.",
                ce_qui_manque="Checkpoint SAM3 (models/sam3.pt ou USMAN_EDIT_BANANA_SAM3_CHECKPOINT)",
                device=device,
                cpu_lent=device == "cpu",
                sam3_disponible=False,
                version=EDIT_BANANA_COMMIT,
            )

        if self.configuration.verifier_runtime:
            sonde = (
                "import json, sys;"
                "mods = {};"
                "for m in ['torch', 'torchvision', 'PIL', 'yaml']:\n"
                "    try:\n"
                "        __import__(m)\n"
                "        mods[m] = True\n"
                "    except Exception as e:\n"
                "        mods[m] = str(e)\n"
                "try:\n"
                "    import torch\n"
                "    cuda = bool(torch.cuda.is_available())\n"
                "except Exception:\n"
                "    cuda = False\n"
                "print(json.dumps({'modules': mods, 'cuda': cuda}))"
            )
            try:
                runtime = subprocess.run(
                    [str(python), "-c", sonde], cwd=str(racine),
                    capture_output=True, text=True, check=False, timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired) as erreur:
                return EtatEditBanana(
                    disponible=False,
                    raison=f"Runtime Edit-Banana indisponible ({type(erreur).__name__}).",
                    ce_qui_manque=str(erreur),
                    device=device,
                    cpu_lent=device == "cpu",
                    sam3_disponible=True,
                    version=EDIT_BANANA_COMMIT,
                )

            if runtime.returncode != 0:
                detail = (runtime.stderr or runtime.stdout).strip().splitlines()
                raison = detail[-1][:200] if detail else "échec d'exécution de la sonde"
                return EtatEditBanana(
                    disponible=False,
                    raison=f"Dépendance Edit-Banana indisponible : {raison}",
                    ce_qui_manque=raison,
                    device=device,
                    cpu_lent=device == "cpu",
                    sam3_disponible=True,
                    version=EDIT_BANANA_COMMIT,
                )

            try:
                donnees_sonde = json.loads(runtime.stdout.strip().splitlines()[-1])
                modules = donnees_sonde.get("modules", {})
                manquants = [mod for mod, ok in modules.items() if ok is not True]
                if manquants:
                    return EtatEditBanana(
                        disponible=False,
                        raison=f"Modules Python manquants dans l'environnement Edit-Banana : {', '.join(manquants)}",
                        ce_qui_manque=", ".join(manquants),
                        device=device,
                        cpu_lent=device == "cpu",
                        sam3_disponible=True,
                        version=EDIT_BANANA_COMMIT,
                    )
                if donnees_sonde.get("cuda"):
                    device = "cuda"
            except (json.JSONDecodeError, IndexError, AttributeError):
                return EtatEditBanana(
                    disponible=False,
                    raison="La sonde du runtime Edit-Banana a rendu une réponse illisible.",
                    ce_qui_manque="Réponse JSON invalide",
                    device=device,
                    cpu_lent=device == "cpu",
                    sam3_disponible=True,
                    version=EDIT_BANANA_COMMIT,
                )

        return EtatEditBanana(
            disponible=True,
            raison="Edit-Banana est configuré et opérationnel.",
            ce_qui_manque="",
            device=device,
            cpu_lent=device == "cpu",
            sam3_disponible=True,
            version=EDIT_BANANA_COMMIT,
        )

    def _valider_entree(self, contenu: bytes) -> tuple[int, int, str]:
        if not contenu:
            raise ErreurEditBanana("L'image fournie est vide.")
        try:
            with Image.open(__import__("io").BytesIO(contenu)) as img:
                img.verify()
            with Image.open(__import__("io").BytesIO(contenu)) as img:
                largeur, hauteur = img.size
                format_image = (img.format or "").upper()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as erreur:
            raise ErreurEditBanana(f"Le fichier fourni n'est pas une image valide ou est corrompu ({erreur}).") from erreur

        if format_image not in FORMATS_ENTREE_SUPPORTES:
            raise ErreurEditBanana(
                f"Format d'image '{format_image}' non supporté. Formats acceptés : {', '.join(sorted(FORMATS_ENTREE_SUPPORTES))}."
            )
        if largeur <= 0 or hauteur <= 0:
            raise ErreurEditBanana("Les dimensions de l'image sont invalides.")
        if largeur > self.configuration.cote_max or hauteur > self.configuration.cote_max:
            raise ErreurEditBanana(
                f"Image trop grande : {largeur}x{hauteur} px (maximum {self.configuration.cote_max} px par côté)."
            )
        if largeur * hauteur > self.configuration.pixels_max:
            raise ErreurEditBanana(
                f"Image trop grande : {largeur * hauteur} pixels (maximum {self.configuration.pixels_max})."
            )
        return largeur, hauteur, format_image

    async def convertir(
        self,
        source: bytes | Path | str,
        *,
        nom_source: str = "diagramme.png",
    ) -> ResultatDiagramme:
        """Convertit une image en document DrawIO éditable."""
        if isinstance(source, (str, Path)):
            chemin_source = Path(source)
            if not chemin_source.is_file():
                raise ErreurEditBanana(f"Fichier source introuvable : {chemin_source}")
            contenu = chemin_source.read_bytes()
            if not nom_source or nom_source == "diagramme.png":
                nom_source = chemin_source.name
        elif isinstance(source, bytes):
            contenu = source
        else:
            raise ErreurEditBanana(f"Type de source inattendu : {type(source).__name__}")

        largeur_source, hauteur_source, _ = self._valider_entree(contenu)

        etat = await asyncio.to_thread(self.etat)
        if not etat.disponible:
            raise ErreurEditBanana(f"Edit-Banana indisponible : {etat.raison}")

        async with self._semaphore:
            return await self._executer(
                contenu=contenu,
                nom_source=nom_source,
                etat=etat,
                dimensions_source=(largeur_source, hauteur_source),
            )

    async def _executer(
        self,
        contenu: bytes,
        *,
        nom_source: str,
        etat: EtatEditBanana,
        dimensions_source: tuple[int, int],
    ) -> ResultatDiagramme:
        racine = self.configuration.racine
        python = self._python()
        assert racine is not None and python is not None

        identifiant = uuid.uuid4().hex
        self.configuration.sorties.mkdir(parents=True, exist_ok=True)
        destination = self.configuration.sorties / f"diagramme-{int(time.time())}-{identifiant[:8]}.drawio"
        source_sha256 = hashlib.sha256(contenu).hexdigest()
        debut = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="arena-edit-banana-") as temp_dir_str:
            travail = Path(temp_dir_str)
            entree = travail / "input_diagram.png"
            dossier_sortie_cli = travail / "output"
            dossier_sortie_cli.mkdir(parents=True, exist_ok=True)

            # Re-encodage propre via Pillow pour sécuriser le flux
            try:
                with Image.open(__import__("io").BytesIO(contenu)) as img:
                    img.convert("RGB").save(entree, format="PNG")
            except Exception as erreur:
                raise ErreurEditBanana("Impossible de préparer l'image d'entrée.") from erreur

            commande = [
                str(python),
                str(racine / "main.py"),
                "-i", str(entree),
                "--output", str(dossier_sortie_cli),
            ]

            logger.info(
                "Edit-Banana démarré (device=%s, entrée=%sx%s, id=%s).",
                etat.device, *dimensions_source, identifiant,
            )

            try:
                processus = await asyncio.create_subprocess_exec(
                    *commande,
                    cwd=str(racine),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as erreur:
                raise ErreurEditBanana(f"Impossible de lancer le processus Edit-Banana ({erreur}).") from erreur

            try:
                stdout, stderr = await asyncio.wait_for(
                    processus.communicate(), timeout=self.configuration.timeout_secondes
                )
            except asyncio.TimeoutError as erreur:
                processus.kill()
                await processus.communicate()
                logger.warning(
                    "Edit-Banana timeout après %.1f s (id=%s).",
                    self.configuration.timeout_secondes, identifiant,
                )
                raise ErreurEditBanana(
                    f"Edit-Banana a dépassé le délai imparti de {self.configuration.timeout_secondes:.0f} secondes."
                ) from erreur
            except asyncio.CancelledError:
                processus.kill()
                await processus.communicate()
                logger.info("Edit-Banana annulé (id=%s).", identifiant)
                raise

            if processus.returncode != 0:
                detail = (stderr or stdout).decode("utf-8", errors="replace").strip().splitlines()
                diagnostic = detail[-1] if detail else f"code {processus.returncode}"
                diagnostic = diagnostic.replace(str(racine), "<edit_banana>").replace(str(travail), "<temp>")[:240]
                logger.error("Edit-Banana en échec (id=%s) : %s", identifiant, diagnostic)
                raise ErreurEditBanana(f"Edit-Banana n'a pas pu traiter le diagramme ({diagnostic}).")

            # Recherche du fichier DrawIO généré
            candidats = list(dossier_sortie_cli.glob("**/*.drawio")) + list(dossier_sortie_cli.glob("**/*.xml"))
            if not candidats:
                # Vérifier aussi à la racine du temp dir
                candidats = list(travail.glob("*.drawio")) + list(travail.glob("*.xml"))

            if not candidats:
                logger.error("Aucun fichier .drawio ou .xml produit par Edit-Banana (id=%s).", identifiant)
                raise ErreurEditBanana("Edit-Banana s'est terminé sans produire de fichier .drawio exploitable.")

            fichier_produit = candidats[0]
            valide, raison = valider_fichier_drawio(fichier_produit)
            if not valide:
                logger.error("Fichier DrawIO invalide produit par Edit-Banana (id=%s) : %s", identifiant, raison)
                raise ErreurEditBanana(f"Le résultat produit par Edit-Banana n'est pas un DrawIO valide ({raison}).")

            shutil.copyfile(fichier_produit, destination)

        # Validation finale dans l'espace de destination
        valide_finale, raison_finale = valider_fichier_drawio(destination)
        if not valide_finale:
            destination.unlink(missing_ok=True)
            raise ErreurEditBanana(f"L'artefact DrawIO final est invalide : {raison_finale}")

        duree = time.perf_counter() - debut
        provenance = destination.with_suffix(".drawio.json")
        try:
            provenance.write_text(json.dumps({
                "operation": "diagram_to_drawio",
                "engine": "Edit-Banana",
                "upstream_commit": EDIT_BANANA_COMMIT,
                "source_name": Path(nom_source).name,
                "source_sha256": source_sha256,
                "source_dimensions": {"width": dimensions_source[0], "height": dimensions_source[1]},
                "target_format": "drawio",
                "device": etat.device,
                "duration_seconds": round(duree, 3),
                "output": destination.name,
                "limitations_notice": LIMITES_QUALITE_DEFAUT,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            destination.unlink(missing_ok=True)
            provenance.unlink(missing_ok=True)
            raise

        logger.info(
            "Edit-Banana conversion terminée en %.2f s (id=%s, taille=%s octets).",
            duree, identifiant, destination.stat().st_size,
        )

        relative_url = f"/media/rendered/diagrams/{destination.name}" if "diagrams" in destination.parts else f"/media/rendered/{destination.name}"
        return ResultatDiagramme(
            sortie=destination,
            url=relative_url,
            provenance=provenance,
            format_cible="drawio",
            largeur=dimensions_source[0],
            hauteur=dimensions_source[1],
            taille_octets=destination.stat().st_size,
            device=etat.device,
            duree_secondes=duree,
            source_sha256=source_sha256,
            limites_qualite=LIMITES_QUALITE_DEFAUT,
        )
