"""Adaptateur local, optionnel et borne vers le CLI officiel CodeFormer.

CodeFormer reste un moteur externe (DEC-0008) avec son environnement Python et
sa licence propres. ARENA ne l'importe donc jamais au demarrage : elle valide
l'image, lance le CLI officiel dans un processus borne, valide le rendu, puis
publie uniquement ce rendu dans son stockage d'artefacts.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from core.production.artefact_image import valider_image
from core.production.materiel import mesurer_gpu

logger = logging.getLogger("usman.restoration.codeformer")

CODEFORMER_COMMIT = "b33cc7d639d6545bfcccc7e0bc6ae51f24e79c2b"
FORMATS_ENTREE = frozenset({"JPEG", "PNG", "WEBP"})


def _entier_env(nom: str, defaut: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(nom, str(defaut))))
    except ValueError:
        logger.warning("%s invalide : valeur par defaut %s utilisee.", nom, defaut)
        return defaut


def _flottant_env(nom: str, defaut: float, minimum: float = 1.0) -> float:
    try:
        return max(minimum, float(os.getenv(nom, str(defaut))))
    except ValueError:
        logger.warning("%s invalide : valeur par defaut %s utilisee.", nom, defaut)
        return defaut


class ErreurRestauration(RuntimeError):
    """Echec attendu, formulable sans exposer de chemin interne."""


@dataclass(frozen=True)
class ConfigurationCodeFormer:
    racine: Optional[Path]
    python: Optional[Path]
    sorties: Path
    timeout_secondes: float = 600.0
    pixels_max: int = 16_000_000
    cote_max: int = 4096
    executions_concurrentes: int = 1
    licence_acceptee: bool = False
    verifier_runtime: bool = True
    verifier_revision: bool = True

    @classmethod
    def depuis_environnement(cls, sorties: Path) -> "ConfigurationCodeFormer":
        brut = os.getenv("USMAN_CODEFORMER_ROOT", "").strip()
        racine = Path(brut).expanduser().resolve() if brut else None
        python_brut = os.getenv("USMAN_CODEFORMER_PYTHON", "").strip()
        python = Path(python_brut).expanduser().resolve() if python_brut else None
        return cls(
            racine=racine,
            python=python,
            sorties=sorties,
            timeout_secondes=_flottant_env("USMAN_CODEFORMER_TIMEOUT_SECONDS", 600.0),
            pixels_max=_entier_env("USMAN_CODEFORMER_MAX_PIXELS", 16_000_000),
            cote_max=_entier_env("USMAN_CODEFORMER_MAX_SIDE", 4096),
            executions_concurrentes=_entier_env("USMAN_CODEFORMER_CONCURRENCY", 1),
            licence_acceptee=os.getenv("USMAN_CODEFORMER_LICENSE_ACCEPTED", "").lower() in {"1", "true", "yes"},
        )


@dataclass(frozen=True)
class EtatCodeFormer:
    disponible: bool
    raison: str
    device: str
    cpu_lent: bool

    def to_dict(self) -> dict:
        return {
            "disponible": self.disponible,
            "raison": self.raison,
            "device": self.device,
            "cpu_lent": self.cpu_lent,
            "version": CODEFORMER_COMMIT,
        }


@dataclass(frozen=True)
class ResultatRestauration:
    sortie: Path
    url: str
    provenance: Path
    largeur: int
    hauteur: int
    taille_octets: int
    fidelity: float
    background_enhancement: bool
    device: str
    duree_secondes: float
    source_sha256: str

    def to_dict(self) -> dict:
        return {
            "sortie": str(self.sortie),
            "url": self.url,
            "provenance": str(self.provenance),
            "largeur": self.largeur,
            "hauteur": self.hauteur,
            "taille_octets": self.taille_octets,
            "fidelity": self.fidelity,
            "background_enhancement": self.background_enhancement,
            "device": self.device,
            "duree_secondes": self.duree_secondes,
            "source_sha256": self.source_sha256,
        }


class ServiceCodeFormer:
    """Frontiere unique entre ARENA et l'inference CodeFormer officielle."""

    def __init__(self, configuration: ConfigurationCodeFormer):
        self.configuration = configuration
        self._semaphore = asyncio.Semaphore(configuration.executions_concurrentes)

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

    def etat(self, *, background_enhancement: bool = False) -> EtatCodeFormer:
        """Sonde le runtime isole sans telecharger ni charger de poids."""
        gpu = mesurer_gpu()
        device = "cuda" if gpu is not None else "cpu"
        if not self.configuration.licence_acceptee:
            return EtatCodeFormer(
                False,
                "La licence NTU S-Lab 1.0 doit etre acceptee explicitement; l'usage commercial exige l'autorisation des contributeurs.",
                device,
                device == "cpu",
            )
        racine = self.configuration.racine
        if racine is None:
            return EtatCodeFormer(False, "USMAN_CODEFORMER_ROOT n'est pas configure.", device, device == "cpu")
        if not (racine / "inference_codeformer.py").is_file():
            return EtatCodeFormer(False, "Le checkout CodeFormer configure est incomplet.", device, device == "cpu")
        python = self._python()
        if python is None or not python.is_file():
            return EtatCodeFormer(False, "L'environnement Python optionnel de CodeFormer est absent.", device, device == "cpu")
        if self.configuration.verifier_revision:
            try:
                revision = subprocess.run(
                    ["git", "-C", str(racine), "rev-parse", "HEAD"],
                    capture_output=True, text=True, check=False, timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired) as erreur:
                return EtatCodeFormer(False, f"Revision CodeFormer non verifiable ({type(erreur).__name__}).", device,
                                      device == "cpu")
            if revision.returncode != 0 or revision.stdout.strip() != CODEFORMER_COMMIT:
                return EtatCodeFormer(False, "Le checkout CodeFormer n'est pas sur la revision approuvee.", device,
                                      device == "cpu")

        requis = [
            racine / "weights" / "CodeFormer" / "codeformer.pth",
            racine / "weights" / "facelib" / "detection_Resnet50_Final.pth",
            racine / "weights" / "facelib" / "parsing_parsenet.pth",
        ]
        if background_enhancement:
            requis.append(racine / "weights" / "realesrgan" / "RealESRGAN_x2plus.pth")
        manquants = [p.name for p in requis if not p.is_file() or p.stat().st_size == 0]
        if manquants:
            return EtatCodeFormer(False, f"Poids manquants : {', '.join(manquants)}.", device, device == "cpu")
        if self.configuration.verifier_runtime:
            sonde = (
                "import json,torch,cv2,torchvision,basicsr,facelib;"
                "print(json.dumps({'cuda': bool(torch.cuda.is_available())}))"
            )
            try:
                runtime = subprocess.run(
                    [str(python), "-c", sonde], cwd=racine, capture_output=True,
                    text=True, check=False, timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired) as erreur:
                return EtatCodeFormer(False, f"Runtime CodeFormer indisponible ({type(erreur).__name__}).", device,
                                      device == "cpu")
            if runtime.returncode != 0:
                detail = (runtime.stderr or runtime.stdout).strip().splitlines()
                raison = detail[-1][:200] if detail else "import impossible"
                return EtatCodeFormer(False, f"Dependance CodeFormer indisponible : {raison}", device,
                                      device == "cpu")
            try:
                device = "cuda" if json.loads(runtime.stdout.strip().splitlines()[-1]).get("cuda") else "cpu"
            except (json.JSONDecodeError, IndexError, AttributeError):
                return EtatCodeFormer(False, "La sonde du runtime CodeFormer a rendu une reponse illisible.",
                                      device, device == "cpu")
        return EtatCodeFormer(True, "CodeFormer est configure.", device, device == "cpu")

    def _valider_entree(self, contenu: bytes) -> tuple[int, int, str]:
        if not contenu:
            raise ErreurRestauration("L'image est vide.")
        try:
            with Image.open(__import__("io").BytesIO(contenu)) as image:
                image.verify()
            with Image.open(__import__("io").BytesIO(contenu)) as image:
                largeur, hauteur = image.size
                format_image = (image.format or "").upper()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as erreur:
            raise ErreurRestauration("Le fichier joint n'est pas une image valide ou il est corrompu.") from erreur
        if format_image not in FORMATS_ENTREE:
            raise ErreurRestauration("CodeFormer accepte ici uniquement JPEG, PNG et WebP.")
        if largeur <= 0 or hauteur <= 0:
            raise ErreurRestauration("Les dimensions de l'image sont invalides.")
        if largeur > self.configuration.cote_max or hauteur > self.configuration.cote_max:
            raise ErreurRestauration(
                f"Image trop grande : {largeur}x{hauteur}, maximum {self.configuration.cote_max} px par cote.")
        if largeur * hauteur > self.configuration.pixels_max:
            raise ErreurRestauration(
                f"Image trop grande : {largeur * hauteur} pixels, maximum {self.configuration.pixels_max}.")
        return largeur, hauteur, format_image

    async def restaurer(
        self,
        contenu: bytes,
        *,
        nom_source: str,
        fidelity: float = 0.5,
        background_enhancement: bool = False,
    ) -> ResultatRestauration:
        try:
            fidelity_mesuree = float(fidelity)
        except (TypeError, ValueError) as erreur:
            raise ErreurRestauration("Le parametre fidelity doit etre un nombre compris entre 0 et 1.") from erreur
        if isinstance(fidelity, bool) or not 0.0 <= fidelity_mesuree <= 1.0:
            raise ErreurRestauration("Le parametre fidelity doit etre compris entre 0 et 1.")
        fidelity = fidelity_mesuree
        largeur_source, hauteur_source, _ = self._valider_entree(contenu)
        # Les imports torch/torchvision de la sonde sont lents et synchrones :
        # ils ne doivent jamais bloquer la boucle FastAPI.
        etat = await asyncio.to_thread(
            self.etat, background_enhancement=background_enhancement)
        if not etat.disponible:
            raise ErreurRestauration(f"Restauration indisponible : {etat.raison}")

        async with self._semaphore:
            return await self._executer(
                contenu, nom_source=nom_source, fidelity=fidelity,
                background_enhancement=background_enhancement, etat=etat,
                dimensions_source=(largeur_source, hauteur_source),
            )

    async def _executer(
        self,
        contenu: bytes,
        *,
        nom_source: str,
        fidelity: float,
        background_enhancement: bool,
        etat: EtatCodeFormer,
        dimensions_source: tuple[int, int],
    ) -> ResultatRestauration:
        racine = self.configuration.racine
        python = self._python()
        assert racine is not None and python is not None  # prouve par etat()
        identifiant = uuid.uuid4().hex
        destination = self.configuration.sorties / f"restauration-{identifiant}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_sha256 = hashlib.sha256(contenu).hexdigest()
        debut = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="arena-codeformer-") as brut:
            travail = Path(brut)
            entree = travail / "source.png"
            resultat_cli = travail / "resultat"
            # Reencodage par Pillow : valide le decodage complet et ne transmet
            # aucun contenu annexe/metadonnee au moteur externe.
            try:
                with Image.open(__import__("io").BytesIO(contenu)) as image:
                    image.convert("RGB").save(entree, format="PNG")
            except (UnidentifiedImageError, OSError, ValueError) as erreur:
                raise ErreurRestauration("L'image n'a pas pu etre decodee completement.") from erreur

            commande = [
                str(python), str(racine / "inference_codeformer.py"),
                "--input_path", str(entree), "--output_path", str(resultat_cli),
                "--fidelity_weight", str(fidelity), "--upscale", "2",
            ]
            if background_enhancement:
                commande.extend(["--bg_upsampler", "realesrgan"])

            logger.info(
                "CodeFormer demarre (device=%s, fond=%s, entree=%sx%s, id=%s).",
                etat.device, background_enhancement, *dimensions_source, identifiant,
            )
            processus = await asyncio.create_subprocess_exec(
                *commande,
                cwd=str(racine),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    processus.communicate(), timeout=self.configuration.timeout_secondes)
            except asyncio.TimeoutError as erreur:
                processus.kill()
                await processus.communicate()
                logger.warning("CodeFormer timeout apres %.1f s (id=%s).",
                               self.configuration.timeout_secondes, identifiant)
                raise ErreurRestauration(
                    f"CodeFormer a depasse le delai de {self.configuration.timeout_secondes:.0f} secondes.") from erreur
            except asyncio.CancelledError:
                processus.kill()
                await processus.communicate()
                logger.info("CodeFormer annule (id=%s).", identifiant)
                raise

            if processus.returncode != 0:
                detail = (stderr or stdout).decode("utf-8", errors="replace").strip().splitlines()
                diagnostic = detail[-1] if detail else f"code {processus.returncode}"
                diagnostic = diagnostic.replace(str(racine), "<codeformer>").replace(str(travail), "<temp>")[:240]
                logger.error("CodeFormer en echec (id=%s) : %s", identifiant, diagnostic)
                raise ErreurRestauration(f"CodeFormer n'a pas produit de rendu ({diagnostic}).")

            produit = resultat_cli / "final_results" / "source.png"
            validation = valider_image(produit)
            if not validation.valide:
                logger.error("Sortie CodeFormer invalide (id=%s) : %s", identifiant, validation.raison)
                raise ErreurRestauration("Le rendu CodeFormer est absent, vide ou illisible.")
            shutil.copyfile(produit, destination)

        validation_finale = valider_image(destination)
        if not validation_finale.valide:
            destination.unlink(missing_ok=True)
            raise ErreurRestauration(f"L'artefact final est invalide : {validation_finale.raison}")

        duree = time.perf_counter() - debut
        provenance = destination.with_suffix(".png.json")
        try:
            provenance.write_text(json.dumps({
                "operation": "image_restoration",
                "engine": "CodeFormer",
                "upstream_commit": CODEFORMER_COMMIT,
                "source_name": Path(nom_source).name,
                "source_sha256": source_sha256,
                "source_dimensions": {"width": dimensions_source[0], "height": dimensions_source[1]},
                "fidelity": fidelity,
                "background_enhancement": background_enhancement,
                "background_engine": "Real-ESRGAN" if background_enhancement else None,
                "device": etat.device,
                "duration_seconds": round(duree, 3),
                "output": destination.name,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            # Sans provenance, la sortie n'est pas publiable : les deux sont
            # une seule transaction logique.
            destination.unlink(missing_ok=True)
            provenance.unlink(missing_ok=True)
            raise
        logger.info("CodeFormer termine en %.2f s (id=%s, %sx%s, %s octets).",
                    duree, identifiant, validation_finale.largeur, validation_finale.hauteur,
                    validation_finale.taille_octets)
        return ResultatRestauration(
            sortie=destination,
            url=f"/media/rendered/restorations/{destination.name}",
            provenance=provenance,
            largeur=validation_finale.largeur or 0,
            hauteur=validation_finale.hauteur or 0,
            taille_octets=validation_finale.taille_octets or 0,
            fidelity=fidelity,
            background_enhancement=background_enhancement,
            device=etat.device,
            duree_secondes=duree,
            source_sha256=source_sha256,
        )
