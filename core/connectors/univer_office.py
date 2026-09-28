"""Office local-first pour ARENA, basé sur Univer CLI.

Mission: intégrer les capacités utiles de dream-num/univer-workspace sans
embarquer un second serveur, un second agent ni un second système
d'authentification. Le produit Workspace s'appuie lui-même sur les briques
Univer CLI/SDK ; ARENA réutilise donc le CLI public local `univer-cli` comme
moteur et garde son propre orchestrateur, son registre et ses permissions.

Règles structurelles :
- aucun shell : argv uniquement ;
- tous les .univer restent dans data/univer/ ;
- les exports restent dans media/rendered/office/ ;
- les imports sont locaux et bornés aux répertoires ARENA autorisés ;
- le JavaScript Facade n'est PAS un bac à sable : capacité séparée `execute`,
  protégée par EXECUTE_COMMANDS dans la politique ;
- merge/discard sont des capacités séparées et confirmables ;
- chaque succès retourne une preuve réelle (fichier, revision ou résultat JSON).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from apps.backend.config import (
    APP_ENV,
    BASE_DIR,
    MEDIA_DIR,
    RENDERED_DIR,
    UNIVER_WORKSPACE_DIR,
)
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.univer_office")

VERSION_ATTENDUE = "0.5.0"
DELAI_DEFAUT = 120.0
DELAI_LONG = 300.0
TAILLE_CODE_MAX = 200_000
TYPES_UNITES = frozenset({"sheet", "doc", "slide", "base", "board"})
CIBLES_INSPECTION = frozenset({
    "workbook", "worksheet", "range", "document", "paragraph",
    "presentation", "slide", "base", "board", "board-element",
})
FORMATS_EXPORT = frozenset({"xlsx", "csv", "tsv", "docx", "pptx"})
EXTENSIONS_IMPORT = frozenset({
    ".xls", ".xlsx", ".xlsm", ".csv", ".tsv", ".doc", ".docx",
    ".ppt", ".pptx", ".pptm", ".ppsx", ".ppsm", ".potx",
})

CE_QUI_MANQUE = (
    f"Univer CLI {VERSION_ATTENDUE} n'est pas disponible. "
    f"Installer le paquet public épinglé `univer-cli@{VERSION_ATTENDUE}` "
    "avec Node.js 24+ ; dans l'image ARENA il est installé par Docker."
)
LICENCE_PRODUCTION_MANQUANTE = (
    "Univer CLI embarque une licence runtime de développement localhost de "
    "90 jours. APP_ENV=production exige donc UNIVER_LICENSE : la licence "
    "de développement n'est jamais présentée comme une licence de production."
)


def _slug(value: str) -> str:
    propre = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip(".-_")
    return propre[:80] or "document"


def _est_dans(chemin: Path, racines: Iterable[Path]) -> bool:
    resolu = chemin.resolve()
    for racine in racines:
        try:
            resolu.relative_to(Path(racine).resolve())
            return True
        except ValueError:
            continue
    return False


class ConnecteurUniverOffice(Connecteur):
    """Un seul moteur Office : fichiers .univer + Worktrees + export Office."""

    service = "office_univer"
    nom = "univer_office"

    def __init__(
        self,
        dossier: Optional[Path] = None,
        dossier_rendus: Optional[Path] = None,
        binaire: Optional[str] = None,
        racines_import: Optional[Sequence[Path]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier is not None else UNIVER_WORKSPACE_DIR
        self.dossier_rendus = (
            Path(dossier_rendus) if dossier_rendus is not None
            else RENDERED_DIR / "office"
        )
        self.binaire = (binaire or os.getenv("UNIVER_CLI_BIN", "").strip() or "univer")
        self.racines_import = tuple(
            Path(p) for p in (
                racines_import
                if racines_import is not None
                else (MEDIA_DIR, self.dossier, BASE_DIR / "data")
            )
        )

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "etat": Capacite(
                nom="etat", action="read",
                description="Mesure la version et la disponibilité réelle d'Univer CLI."),
            "fichiers": Capacite(
                nom="fichiers", action="read",
                description="Liste les conteneurs .univer persistants de cette instance."),
            "creer": Capacite(
                nom="creer", action="document",
                description="Crée un conteneur Office local .univer vide.", ecriture=True),
            "importer": Capacite(
                nom="importer", action="document",
                description="Importe un XLS/XLSX/CSV/DOC/DOCX/PPT/PPTX local dans un .univer.",
                ecriture=True),
            "statut": Capacite(
                nom="statut", action="read",
                description="Lit les Units et l'état d'un fichier .univer."),
            "worktree_creer": Capacite(
                nom="worktree_creer", action="document",
                description="Crée un brouillon Worktree isolé depuis le trunk.", ecriture=True),
            "worktrees": Capacite(
                nom="worktrees", action="read",
                description="Liste les Worktrees réels d'un fichier .univer."),
            "unite_creer": Capacite(
                nom="unite_creer", action="document",
                description="Crée une Unit Sheet/Doc/Slide/Base/Board dans un Worktree.",
                ecriture=True),
            "unites": Capacite(
                nom="unites", action="read",
                description="Liste les Units du trunk ou d'un Worktree."),
            "executer": Capacite(
                nom="executer", action="execute",
                description=(
                    "Exécute du JavaScript Facade de confiance dans un Worktree. "
                    "Ce n'est pas un bac à sable."),
                ecriture=True),
            "inspecter": Capacite(
                nom="inspecter", action="read",
                description="Relit le modèle Office structuré après modification."),
            "pret": Capacite(
                nom="pret", action="document",
                description="Gèle un Worktree en état ready pour revue.", ecriture=True),
            "reouvrir": Capacite(
                nom="reouvrir", action="document",
                description="Rouvre un Worktree ready pour le corriger.", ecriture=True),
            "fusionner": Capacite(
                nom="fusionner", action="merge",
                description="Fusionne un Worktree revu dans le trunk.", ecriture=True),
            "abandonner": Capacite(
                nom="abandonner", action="destroy",
                description="Abandonne un Worktree sans toucher au trunk déjà fusionné.",
                ecriture=True),
            "exporter": Capacite(
                nom="exporter", action="document",
                description="Exporte une Unit en XLSX/CSV/TSV/DOCX/PPTX local téléchargeable.",
                ecriture=True),
            "imprimer_pdf": Capacite(
                nom="imprimer_pdf", action="document",
                description="Rend une Unit en PDF local via le moteur de rendu Univer.",
                ecriture=True),
            "lint_mise_en_page": Capacite(
                nom="lint_mise_en_page", action="read",
                description="Vérifie géométriquement la mise en page d'une Slide."),
            "ouvrir": Capacite(
                nom="ouvrir", action="document",
                description=(
                    "Démarre le Viewer local Univer et rend son URL de revue. "
                    "Cette opération démarre un runtime local ; elle n'est donc "
                    "pas déguisée en lecture pure."
                ),
                ecriture=True),
            "daemon_statut": Capacite(
                nom="daemon_statut", action="read",
                description="Lit l'état réel du daemon et de la Gateway Univer."),
            "daemon_arreter": Capacite(
                nom="daemon_arreter", action="document",
                description="Arrête proprement le daemon Univer de cette instance.",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        if APP_ENV == "production":
            return bool(os.getenv("UNIVER_LICENSE", "").strip())
        return True

    def _env(self) -> Dict[str, str]:
        """Environnement minimal : aucun secret ARENA n'entre dans le runtime JS.

        `execute` lance du JavaScript de confiance et l'amont précise que ce
        n'est pas un bac à sable. Hériter de tout `os.environ` exposerait les
        clés API du backend au code Facade. La liste ci-dessous est donc une
        whitelist, pas une copie filtrée après coup.
        """
        home = (self.dossier / ".home").resolve()
        cache = home / "cache"
        temporaire = home / "tmp"
        for chemin in (home, cache, temporaire):
            chemin.mkdir(parents=True, exist_ok=True)

        env = {
            "PATH": os.getenv("PATH", ""),
            "HOME": str(home),
            "UNIVER_HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "TMPDIR": str(temporaire),
            "NO_COLOR": "1",
            "CI": "1",
            "LANG": os.getenv("LANG", "C.UTF-8"),
            "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
            "TZ": os.getenv("TZ", "UTC"),
        }
        licence = os.getenv("UNIVER_LICENSE", "").strip()
        if licence:
            env["UNIVER_LICENSE"] = licence
        chromium = shutil.which("chromium") or shutil.which("chromium-browser")
        if chromium:
            env["UNIVER_RENDER_BROWSER"] = chromium
        cache_navigateur = os.getenv("UNIVER_RENDER_BROWSER_CACHE", "").strip()
        if cache_navigateur:
            env["UNIVER_RENDER_BROWSER_CACHE"] = cache_navigateur
        return env

    def _binaire(self) -> Optional[str]:
        candidat = Path(self.binaire)
        if candidat.is_absolute() or "/" in self.binaire or "\\" in self.binaire:
            return str(candidat) if candidat.is_file() else None
        return shutil.which(self.binaire)

    def sonder(self) -> Sante:
        if APP_ENV == "production" and not os.getenv("UNIVER_LICENSE", "").strip():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Runtime Univer non licencié pour la production.",
                ce_qui_manque=LICENCE_PRODUCTION_MANQUANTE,
                mesure_le=_maintenant(),
            )

        binaire = self._binaire()
        if binaire is None:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Univer CLI introuvable.",
                ce_qui_manque=CE_QUI_MANQUE,
                mesure_le=_maintenant(),
            )
        try:
            resultat = subprocess.run(
                [binaire, "--version"],
                env=self._env(), capture_output=True, text=True,
                timeout=20.0, check=False,
            )
        except (OSError, subprocess.SubprocessError) as erreur:
            return Sante(
                etat=EtatSante.EN_PANNE,
                message=f"Univer CLI ne répond pas : {type(erreur).__name__}.",
                mesure_le=_maintenant(),
            )
        if resultat.returncode != 0:
            return Sante(
                etat=EtatSante.EN_PANNE,
                message=f"Univer CLI répond en erreur (code {resultat.returncode}).",
                mesure_le=_maintenant(),
            )
        version = (resultat.stdout or resultat.stderr or "").strip()
        trouvee = re.search(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", version)
        if trouvee is None or trouvee.group(1) != VERSION_ATTENDUE:
            return Sante(
                etat=EtatSante.EN_PANNE,
                message=(
                    f"Version Univer incompatible : {version or 'inconnue'} ; "
                    f"ARENA attend exactement {VERSION_ATTENDUE}."
                ),
                mesure_le=_maintenant(),
            )

        licence_production = bool(os.getenv("UNIVER_LICENSE", "").strip())
        regime = (
            "licence runtime explicitement configurée"
            if licence_production
            else "runtime de développement localhost (90 jours)"
        )
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"Univer CLI {VERSION_ATTENDUE} répond ; {regime}.",
            mesure_le=_maintenant(),
        )

    def _fichier(self, brut: str, *, doit_exister: bool = True) -> Path:
        valeur = (brut or "").strip()
        if not valeur:
            raise ValueError("FICHIER .univer manquant.")
        candidat = Path(valeur)
        if not candidat.is_absolute():
            candidat = self.dossier / candidat
        if candidat.suffix.lower() != ".univer":
            candidat = candidat.with_suffix(".univer")
        candidat = candidat.resolve()
        if not _est_dans(candidat, (self.dossier,)):
            raise ValueError("Le fichier Office doit rester dans l'espace Univer d'ARENA.")
        if doit_exister and not candidat.is_file():
            raise FileNotFoundError(f"Fichier .univer introuvable : {candidat.name}")
        return candidat

    def _source_import(self, brut: str) -> Path:
        valeur = (brut or "").strip()
        if not valeur:
            raise ValueError("SOURCE à importer manquante.")
        if re.match(r"^[a-z][a-z0-9+.-]*://", valeur, flags=re.IGNORECASE):
            raise ValueError(
                "Les imports réseau sont désactivés : joins d'abord le fichier à ARENA."
            )
        candidat = Path(valeur)
        if not candidat.is_absolute():
            candidat = (BASE_DIR / candidat).resolve()
        else:
            candidat = candidat.resolve()
        if not _est_dans(candidat, self.racines_import):
            raise ValueError("La source est hors des répertoires de fichiers autorisés.")
        if not candidat.is_file():
            raise FileNotFoundError(f"Source introuvable : {candidat}")
        if candidat.suffix.lower() not in EXTENSIONS_IMPORT:
            raise ValueError(f"Format Office non pris en charge : {candidat.suffix or '(sans extension)'}")
        return candidat

    def _sortie(self, nom: str, extension: str) -> Path:
        self.dossier_rendus.mkdir(parents=True, exist_ok=True)
        ext = extension.lower().lstrip(".")
        tige = _slug(nom)
        for index in range(10_000):
            suffixe = "" if index == 0 else f"-{index}"
            candidat = (self.dossier_rendus / f"{tige}{suffixe}.{ext}").resolve()
            if not candidat.exists():
                return candidat
        raise OSError("Impossible de réserver un nom de sortie Office libre.")

    @staticmethod
    def _verifier_sortie(chemin: Path, format_cible: str) -> Optional[str]:
        """`None` si l'artefact est structurellement lisible, raison sinon."""
        if not chemin.is_file() or chemin.stat().st_size == 0:
            return "Le fichier produit est absent ou vide."

        ext = format_cible.lower().lstrip(".")
        if ext == "pdf":
            try:
                if chemin.read_bytes()[:5] != b"%PDF-":
                    return "Le rendu produit n'a pas de signature PDF valide."
            except OSError as erreur:
                return f"Le PDF produit est illisible : {erreur}"
            return None

        if ext in {"xlsx", "docx", "pptx"}:
            attendu = {
                "xlsx": "xl/workbook.xml",
                "docx": "word/document.xml",
                "pptx": "ppt/presentation.xml",
            }[ext]
            try:
                if not zipfile.is_zipfile(chemin):
                    return f"Le fichier {ext.upper()} produit n'est pas une archive Office valide."
                with zipfile.ZipFile(chemin) as archive:
                    noms = set(archive.namelist())
                if "[Content_Types].xml" not in noms or attendu not in noms:
                    return (
                        f"Le fichier {ext.upper()} produit ne contient pas "
                        "la structure Office attendue."
                    )
            except (OSError, zipfile.BadZipFile) as erreur:
                return f"Le fichier {ext.upper()} produit est illisible : {erreur}"
            return None

        if ext in {"csv", "tsv"}:
            try:
                chemin.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as erreur:
                return f"Le fichier texte produit est illisible : {erreur}"
            return None

        return f"Format de sortie non vérifiable : {ext or '(vide)'}."

    def _lancer(
        self,
        arguments: Sequence[str],
        *,
        delai: float = DELAI_DEFAUT,
        json_attendu: bool = True,
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        binaire = self._binaire()
        if binaire is None:
            return None, CE_QUI_MANQUE
        self.dossier.mkdir(parents=True, exist_ok=True)
        commande = [binaire, *[str(x) for x in arguments]]
        if json_attendu and "--json" not in commande:
            commande.append("--json")
        logger.info("Univer CLI : %s", " ".join(arguments[:3]))
        try:
            resultat = subprocess.run(
                commande,
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=delai,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, f"Univer CLI a dépassé le délai de {delai:g} s."
        except OSError as erreur:
            return None, f"Impossible de lancer Univer CLI : {type(erreur).__name__}: {erreur}"

        if resultat.returncode != 0:
            brut = (resultat.stderr or resultat.stdout or "").strip()
            message = brut.splitlines()[-1] if brut else f"code {resultat.returncode}"
            try:
                charge = json.loads(brut)
                message = str(charge.get("error", {}).get("message") or message)
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
            return None, f"Univer CLI a échoué (code {resultat.returncode}) : {message[:800]}"

        if not json_attendu:
            return {"sortie": (resultat.stdout or "").strip()}, None
        brut = (resultat.stdout or "").strip()
        try:
            charge = json.loads(brut)
        except json.JSONDecodeError:
            return None, "Univer CLI a réussi sans rendre le JSON contractuel attendu."
        if not isinstance(charge, dict):
            return None, "Univer CLI a rendu un résultat JSON de forme inattendue."
        return charge, None

    @staticmethod
    def _id(parametres: Dict[str, Any], nom: str) -> str:
        valeur = str(parametres.get(nom) or "").strip()
        if not valeur:
            raise ValueError(f"{nom} manquant.")
        if len(valeur) > 200 or not re.fullmatch(r"[A-Za-z0-9._:-]+", valeur):
            raise ValueError(f"{nom} invalide.")
        return valeur

    def _resultat_json(
        self,
        capacite: str,
        message: str,
        preuve: str,
        charge: Dict[str, Any],
        **detail: Any,
    ) -> ResultatAction:
        return succes(
            action=capacite, cible=self.nom, message=message, preuve=preuve,
            resultat=charge, **detail,
        )

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        try:
            if capacite.nom == "etat":
                sante = self.sonder()
                if not sante.utilisable:
                    return non_configure(
                        action=capacite.nom, cible=self.nom,
                        ce_qui_manque=sante.ce_qui_manque or sante.message,
                    )
                return succes(
                    action=capacite.nom, cible=self.nom, message=sante.message,
                    preuve=sante.mesure_le or "univer-version",
                    sante=sante.to_dict(),
                    version_attendue=VERSION_ATTENDUE,
                    licence_runtime=(
                        "configured"
                        if os.getenv("UNIVER_LICENSE", "").strip()
                        else "bundled_development_90_day"
                    ),
                    production_license_verified=bool(
                        os.getenv("UNIVER_LICENSE", "").strip()
                    ),
                )

            if capacite.nom == "fichiers":
                self.dossier.mkdir(parents=True, exist_ok=True)
                fichiers = []
                for chemin in sorted(self.dossier.glob("*.univer")):
                    try:
                        stat = chemin.stat()
                    except OSError:
                        continue
                    fichiers.append({
                        "nom": chemin.name,
                        "chemin": str(chemin.resolve()),
                        "taille_octets": stat.st_size,
                        "modifie_le": stat.st_mtime,
                    })
                return self._resultat_json(
                    capacite.nom,
                    f"{len(fichiers)} espace(s) Office trouvé(s).",
                    f"{self.dossier}:office-files",
                    {"fichiers": fichiers},
                    fichiers=fichiers,
                )

            if capacite.nom == "daemon_statut":
                charge, erreur = self._lancer(["daemon", "status"])
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, "État du runtime Univer mesuré.",
                    "univer-daemon-status", charge or {},
                )

            if capacite.nom == "daemon_arreter":
                charge, erreur = self._lancer(["daemon", "stop"], delai=30.0)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, "Daemon Univer arrêté proprement.",
                    "univer-daemon-stopped", charge or {},
                )

            if capacite.nom == "creer":
                nom = _slug(str(parametres.get("nom") or "document"))
                fichier = self._fichier(f"{nom}.univer", doit_exister=False)
                if fichier.exists():
                    return echec(capacite.nom, self.nom, f"{fichier.name} existe déjà.")
                fichier.parent.mkdir(parents=True, exist_ok=True)
                charge, erreur = self._lancer(["new", str(fichier)])
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                if not fichier.is_file() or fichier.stat().st_size == 0:
                    return echec(capacite.nom, self.nom, "Aucun .univer réel n'a été créé.")
                return self._resultat_json(
                    capacite.nom, f"Espace Office créé : {fichier.name}", str(fichier),
                    charge or {}, fichier=str(fichier), taille_octets=fichier.stat().st_size,
                )

            if capacite.nom == "importer":
                source = self._source_import(str(parametres.get("source") or ""))
                nom = _slug(str(parametres.get("nom") or source.stem))
                fichier = self._fichier(f"{nom}.univer", doit_exister=False)
                worktree = str(parametres.get("worktree") or "").strip()
                if fichier.exists() and not worktree:
                    return echec(
                        capacite.nom, self.nom,
                        f"{fichier.name} existe déjà : fournis un Worktree ou un autre nom.",
                    )
                fichier.parent.mkdir(parents=True, exist_ok=True)
                args = ["import", str(fichier), "--file", str(source)]
                nom_unite = str(parametres.get("nom_unite") or source.stem).strip()[:120]
                if nom_unite:
                    args += ["--name", nom_unite]
                type_unite = str(parametres.get("type") or "").strip().lower()
                if type_unite:
                    if type_unite not in TYPES_UNITES - {"board"}:
                        return echec(capacite.nom, self.nom, f"TYPE import invalide : {type_unite}")
                    args += ["--type", type_unite]
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                charge, erreur = self._lancer(args, delai=DELAI_LONG)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                if not fichier.is_file() or fichier.stat().st_size == 0:
                    return echec(capacite.nom, self.nom, "L'import n'a produit aucun .univer réel.")

                # Les pièces Office de la PWA sont un staging, pas un second
                # stockage documentaire. Une fois les octets réellement
                # importés dans .univer, on retire ce doublon.
                staging = (self.dossier / "imports").resolve()
                source_supprimee = False
                try:
                    source.relative_to(staging)
                    source.unlink(missing_ok=True)
                    source_supprimee = True
                except ValueError:
                    # Une source utilisateur déjà durable (data/ ou media/)
                    # n'est jamais supprimée par effet de bord.
                    pass

                return self._resultat_json(
                    capacite.nom, f"{source.name} importé dans {fichier.name}",
                    str(fichier), charge or {}, fichier=str(fichier), source=str(source),
                    staging_supprime=source_supprimee,
                )

            fichier = self._fichier(str(parametres.get("fichier") or ""))

            if capacite.nom == "statut":
                args = ["status", str(fichier)]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                charge, erreur = self._lancer(args)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, f"État Office lu pour {fichier.name}",
                    f"{fichier}:status", charge or {}, fichier=str(fichier),
                )

            if capacite.nom == "worktree_creer":
                nom = _slug(str(parametres.get("nom") or "arena"))
                charge, erreur = self._lancer(
                    ["worktree", "add", str(fichier), "--name", nom]
                )
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                wid = str((charge or {}).get("worktreeId") or "")
                if not wid:
                    return echec(capacite.nom, self.nom, "Le Worktree créé n'a pas d'identifiant.")
                return self._resultat_json(
                    capacite.nom, f"Worktree « {nom} » créé.", wid,
                    charge or {}, fichier=str(fichier), worktree=wid,
                )

            if capacite.nom == "worktrees":
                charge, erreur = self._lancer(["worktree", "list", str(fichier)])
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, f"Worktrees lus pour {fichier.name}",
                    f"{fichier}:worktrees", charge or {}, fichier=str(fichier),
                )

            if capacite.nom == "unite_creer":
                wid = self._id(parametres, "worktree")
                type_unite = str(parametres.get("type") or "").strip().lower()
                if type_unite not in TYPES_UNITES:
                    return echec(
                        capacite.nom, self.nom,
                        f"TYPE doit être l'un de : {', '.join(sorted(TYPES_UNITES))}.",
                    )
                nom = str(parametres.get("nom") or type_unite).strip()[:120]
                charge, erreur = self._lancer([
                    "unit", "add", str(fichier), "--worktree", wid,
                    "--type", type_unite, "--name", nom,
                ])
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                uid = str((charge or {}).get("unitId") or "")
                if not uid:
                    return echec(capacite.nom, self.nom, "L'Unit créée n'a pas d'identifiant.")
                return self._resultat_json(
                    capacite.nom, f"Unit {type_unite} « {nom} » créée.", uid,
                    charge or {}, fichier=str(fichier), worktree=wid, unit=uid,
                )

            if capacite.nom == "unites":
                args = ["unit", "list", str(fichier)]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                else:
                    args += ["--trunk"]
                charge, erreur = self._lancer(args)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, f"Units lues pour {fichier.name}",
                    f"{fichier}:units", charge or {}, fichier=str(fichier),
                )

            if capacite.nom == "executer":
                wid = self._id(parametres, "worktree")
                uid = self._id(parametres, "unit")
                code = str(parametres.get("code") or "")
                if not code.strip():
                    return echec(capacite.nom, self.nom, "CODE Facade vide.")
                if len(code) > TAILLE_CODE_MAX:
                    return echec(
                        capacite.nom, self.nom,
                        f"CODE Facade trop long ({len(code)} > {TAILLE_CODE_MAX}).",
                    )
                charge, erreur = self._lancer(
                    ["execute", str(fichier), "--worktree", wid, "--unit", uid, "--code", code],
                    delai=DELAI_LONG,
                )
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                revision = (charge or {}).get("revision")
                preuve = f"{fichier}:{wid}:{uid}:rev-{revision}" if revision is not None else (
                    f"{fichier}:{wid}:{uid}:read"
                )
                return self._resultat_json(
                    capacite.nom,
                    ("Modification Office exécutée et enregistrée."
                     if (charge or {}).get("committed") else
                     "Code Facade exécuté en lecture seule."),
                    preuve, charge or {}, fichier=str(fichier), worktree=wid, unit=uid,
                )

            if capacite.nom == "inspecter":
                uid = self._id(parametres, "unit")
                cible = str(parametres.get("cible") or "").strip().lower()
                if cible not in CIBLES_INSPECTION:
                    return echec(
                        capacite.nom, self.nom,
                        f"CIBLE d'inspection invalide : {cible or '(vide)'}.",
                    )
                selecteurs_bruts = parametres.get("selecteurs") or []
                if isinstance(selecteurs_bruts, str):
                    selecteurs = [x.strip() for x in selecteurs_bruts.splitlines() if x.strip()]
                elif isinstance(selecteurs_bruts, (list, tuple)):
                    selecteurs = [str(x).strip() for x in selecteurs_bruts if str(x).strip()]
                else:
                    return echec(capacite.nom, self.nom, "SELECTEURS doit être une liste ou du texte.")
                if len(selecteurs) > 20 or any(len(x) > 200 for x in selecteurs):
                    return echec(capacite.nom, self.nom, "SELECTEURS d'inspection trop nombreux ou trop longs.")
                args = ["inspect", cible, *selecteurs, str(fichier), "--unit", uid]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                else:
                    args += ["--trunk"]
                worksheet = str(parametres.get("worksheet") or "").strip()
                if worksheet:
                    args += ["--worksheet", worksheet]
                charge, erreur = self._lancer(args)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, f"Contenu {cible} relu.", f"{fichier}:{uid}:inspect",
                    charge or {}, fichier=str(fichier), unit=uid,
                )

            if capacite.nom in {"pret", "reouvrir", "fusionner", "abandonner"}:
                wid = self._id(parametres, "worktree")
                commande = {
                    "pret": "ready", "reouvrir": "reopen",
                    "fusionner": "merge", "abandonner": "discard",
                }[capacite.nom]
                charge, erreur = self._lancer(
                    ["worktree", commande, str(fichier), "--worktree", wid],
                    delai=DELAI_LONG,
                )
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, f"Worktree {wid} : {commande}.",
                    f"{fichier}:{wid}:{commande}", charge or {},
                    fichier=str(fichier), worktree=wid,
                )

            if capacite.nom == "exporter":
                uid = str(parametres.get("unit") or "").strip()
                format_cible = str(parametres.get("format") or "").strip().lower().lstrip(".")
                if format_cible not in FORMATS_EXPORT:
                    return echec(
                        capacite.nom, self.nom,
                        f"FORMAT doit être l'un de : {', '.join(sorted(FORMATS_EXPORT))}.",
                    )
                nom_sortie = str(parametres.get("nom") or fichier.stem)
                sortie = self._sortie(nom_sortie, format_cible)
                args = ["export", str(fichier), str(sortie)]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                if uid:
                    args += ["--unit", self._id(parametres, "unit")]
                charge, erreur = self._lancer(args, delai=DELAI_LONG)
                if erreur:
                    sortie.unlink(missing_ok=True)
                    return echec(capacite.nom, self.nom, erreur)
                souci_sortie = self._verifier_sortie(sortie, format_cible)
                if souci_sortie:
                    sortie.unlink(missing_ok=True)
                    return echec(capacite.nom, self.nom, souci_sortie)
                return self._resultat_json(
                    capacite.nom, f"Export {format_cible.upper()} créé : {sortie.name}",
                    str(sortie), charge or {}, fichier=str(sortie),
                    taille_octets=sortie.stat().st_size,
                    url=f"/media/rendered/office/{sortie.name}",
                )

            if capacite.nom == "imprimer_pdf":
                uid = str(parametres.get("unit") or "").strip()
                nom_sortie = str(parametres.get("nom") or fichier.stem)
                sortie = self._sortie(nom_sortie, "pdf")
                args = ["print-pdf", str(fichier), str(sortie)]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                if uid:
                    args += ["--unit", self._id(parametres, "unit")]
                charge, erreur = self._lancer(args, delai=DELAI_LONG)
                if erreur:
                    sortie.unlink(missing_ok=True)
                    return echec(capacite.nom, self.nom, erreur)
                souci_sortie = self._verifier_sortie(sortie, "pdf")
                if souci_sortie:
                    sortie.unlink(missing_ok=True)
                    return echec(capacite.nom, self.nom, souci_sortie)
                return self._resultat_json(
                    capacite.nom, f"PDF Office créé : {sortie.name}",
                    str(sortie), charge or {}, fichier=str(sortie),
                    taille_octets=sortie.stat().st_size,
                    url=f"/media/rendered/office/{sortie.name}",
                )

            if capacite.nom == "lint_mise_en_page":
                uid = self._id(parametres, "unit")
                args = ["lint", "--file", str(fichier), "--unit", uid]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                charge, erreur = self._lancer(args, delai=DELAI_LONG)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                return self._resultat_json(
                    capacite.nom, "Vérification de mise en page terminée.",
                    f"{fichier}:{uid}:layout-lint", charge or {},
                    fichier=str(fichier), unit=uid,
                )

            if capacite.nom == "ouvrir":
                args = ["open", str(fichier)]
                worktree = str(parametres.get("worktree") or "").strip()
                if worktree:
                    args += ["--worktree", self._id(parametres, "worktree")]
                unit = str(parametres.get("unit") or "").strip()
                if unit:
                    args += ["--unit", self._id(parametres, "unit")]
                charge, erreur = self._lancer(args, delai=DELAI_LONG)
                if erreur:
                    return echec(capacite.nom, self.nom, erreur)
                url = str((charge or {}).get("openUrl") or "")
                if not url:
                    return echec(capacite.nom, self.nom, "Le Viewer n'a rendu aucune URL.")
                est_loopback = bool(
                    re.match(r"^https?://(?:127\.0\.0\.1|localhost)(?::|/)", url)
                )
                return self._resultat_json(
                    capacite.nom,
                    (
                        "Viewer Univer prêt sur la machine qui exécute ARENA."
                        if est_loopback
                        else "Viewer Univer prêt."
                    ),
                    url, charge or {}, viewer_url=url,
                    local_only=est_loopback,
                )

            return echec(capacite.nom, self.nom, "Capacité Univer inconnue.")

        except (ValueError, FileNotFoundError, OSError) as erreur:
            return echec(capacite.nom, self.nom, str(erreur))
