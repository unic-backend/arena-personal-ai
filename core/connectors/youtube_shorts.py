"""Connecteur AI-Youtube-Shorts-Generator — long-form video -> shorts classes.

**Ce que le depot amont est reellement devenu, verifie avant d'ecrire une
ligne** (clone reel, `Anil-matcha/AI-Youtube-Shorts-Generator` @
`a57bb938ba50bf9654c2d5ca2af1295163454349`, 30/09/2026 ; `SamurAIGPT/...`
redirige vers ce nom) : ce n'est plus le gros projet MoviePy/Whisper d'origine,
c'est **1 281 lignes de Python** en deux modes.

- `--mode api` envoie la video et la transcription a **MuAPI**, un service
  tiers payant (`MUAPI_API_KEY`). Ce mode n'est **pas** branche ici, et ce
  fichier ne peut pas l'atteindre : l'argument `--mode` est ecrit en dur a
  `local`. Sortir un media du proprietaire vers un tiers n'est pas une
  capacite qu'ARENA acquiert par commodite.
- `--mode local` fait le travail sur la machine : decoupe ffmpeg, recadrage
  9:16 suivant les visages (cascade Haar OpenCV), classement des extraits par
  un LLM. C'est **ce mode-la, et seulement lui**, que ce connecteur appelle.

**Pourquoi ce moteur alors qu'ARENA decoupe deja des clips.** `agents/
clip_selector` rend **un** extrait, cadre au centre, sans classement. Le delta
reel mesure ici : **N extraits classes** (score de viralite, hook, raison,
dedoublonnage par recouvrement > 50 %, decoupage des videos > 30 min en
tranches) et un **recadrage qui suit le visage** image par image. Rien de cela
n'existait. Aucune capacite ARENA n'est remplacee : `clip_selector` reste.

**Six regles, au-dela du contrat commun `Connecteur` :**

1. **Aucune ligne du moteur n'entre dans ce depot** (DEC-0039, meme frontiere
   que KrillinAI/VoiceStudio/Xaar Kaname). MIT l'aurait permis ; la regle est
   la meme pour tous les moteurs. Il vit a cote, `YOUTUBE_SHORTS_PATH` le
   designe, et il est appele par **sous-processus** — jamais importe.

2. **Aucune seconde transcription.** `transcript_srt` est **obligatoire** :
   ARENA transcrit deja (FasterWhisper, `tools/audio/transcription_tool.py`).
   Le SRT fourni est depose dans le cache du moteur (`<sortie>/<stem>.srt`,
   contrat lu dans `shorts_generator/local/transcriber.py`), ce qui lui evite
   de charger un second modele Whisper sur la meme carte. Meme raisonnement
   que la regle 2 de `krillinai.py`.

3. **Aucun telechargement implicite.** Une URL en entree exige
   `autoriser_telechargement=True` explicite, et yt-dlp present. Par defaut
   l'entree est un **fichier local**.

4. **Environnement minimal.** Le sous-processus ne recoit pas `os.environ` :
   il recoit un dictionnaire construit ici (PATH, HOME, dossier de sortie, et
   les seules variables LLM). Aucun secret ARENA, aucun jeton de connecteur,
   aucune cle Google/GitHub ne traverse cette frontiere, et aucune cle n'entre
   dans un resultat.

5. **Un succes exige des fichiers.** Le moteur rend `clip_url: null` +
   `error` par extrait rate ; un code retour 0 ne suffit jamais. Chaque MP4
   annonce est verifie sur disque (existe, non vide) avant d'etre credite.
   Zero artefact verifie = ECHEC, meme si le processus a rendu 0.

6. **Chaque execution a son dossier.** `media/rendered/shorts-<uuid8>/` :
   deux executions concurrentes ne peuvent pas ecrire `short_01.mp4` l'une
   sur l'autre (le moteur numerote a partir de 1, toujours). Les fichiers
   intermediaires du moteur (`*.cut.mp4`, `*.silent.mp4`) sont nettoyes.

**Limite mesuree, pas supposee** (30/09/2026, banc d'essai reel) : le moteur
epingle `opencv-python>=4.8.0`. Avec OpenCV **5.0.0**, `cv2.CascadeClassifier`
n'existe plus et tous les extraits echouent. La sonde de sante le **mesure**
dans l'interpreteur du moteur et rend NON_CONFIGURE avec la version a
installer — elle ne le suppose pas.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.youtube_shorts")

#: Revision epinglee auditee (docs/audits/ai_youtube_shorts_audit_2026-09-30.md).
#: Jamais « latest » : la sonde compare et le dit quand ca diverge.
COMMIT_AUDITE = "a57bb938ba50bf9654c2d5ca2af1295163454349"
DEPOT_AMONT = "https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator"

#: Ou le moteur est installe, a cote d'ARENA. Jamais clone ni installe par ce
#: fichier : absent -> NON_CONFIGURE avec la marche a suivre.
VARIABLE_DOSSIER = "YOUTUBE_SHORTS_PATH"
VARIABLE_PYTHON = "YOUTUBE_SHORTS_PYTHON"

CE_QUI_MANQUE = (
    f"cloner {DEPOT_AMONT} a cote d'ARENA (commit auditee {COMMIT_AUDITE[:12]}), creer son "
    "propre environnement virtuel, y installer requirements-local.txt avec "
    "opencv-python-headless>=4.8,<5 (OpenCV 5 a retire CascadeClassifier), puis definir "
    f"{VARIABLE_DOSSIER} vers ce dossier et {VARIABLE_PYTHON} vers son interpreteur"
)

#: Formats acceptes. Le moteur accepte n'importe quel « w:h » ; on borne a ce
#: qui a un sens court-format et a ete mesure.
FORMATS_AUTORISES = frozenset({"9:16", "1:1", "4:5"})

#: Bornes du nombre d'extraits. Au-dela, un appel occupe la machine des
#: dizaines de minutes sans que personne l'ait voulu.
CLIPS_MIN, CLIPS_MAX = 1, 10

#: Delai maximal d'une generation. Recadrer suit les visages image par image :
#: c'est lent, mais ca ne doit pas etre infini.
DELAI_SECONDES = float(os.getenv("YOUTUBE_SHORTS_TIMEOUT", "1800"))
#: Delai de la sonde : elle doit rendre la main tout de suite.
DELAI_SONDE_SECONDES = 30.0


def _dossier_moteur() -> str:
    return os.getenv(VARIABLE_DOSSIER, "").strip()


def _python_moteur() -> str:
    """L'interpreteur du moteur — son venv, jamais celui d'ARENA.

    Les dependances du moteur (opencv, yt-dlp, faster-whisper, openai) ne sont
    pas celles d'ARENA et n'ont pas a l'etre : elles restent dans son
    environnement.
    """
    return os.getenv(VARIABLE_PYTHON, "").strip() or "python3"


def _est_une_url(valeur: str) -> bool:
    return urlparse(valeur).scheme in ("http", "https")


class ConnecteurYoutubeShorts(Connecteur):
    """Une video longue -> N shorts verticaux classes. Mode local uniquement."""

    service = "youtube_shorts"
    nom = "youtube_shorts"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else RENDERED_DIR

    # --- Declaration ---------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "generate_shorts": Capacite(
                nom="generate_shorts",
                action="generate",
                description=(
                    "Decoupe une video longue en N shorts verticaux classes par potentiel "
                    "viral, recadres en suivant les visages. La transcription est fournie "
                    "par ARENA (aucune seconde transcription)."
                ),
                ecriture=True,
            ),
            "inspecter_moteur": Capacite(
                nom="inspecter_moteur",
                action="read",
                description=(
                    "Rend la revision reellement installee du moteur, la revision auditee, "
                    "et les binaires/versions mesures. Aucune generation."
                ),
                ecriture=False,
            ),
        }

    # --- Sante mesuree -------------------------------------------------------

    def sonder(self) -> Sante:
        dossier = _dossier_moteur()
        if not dossier:
            return Sante(EtatSante.NON_CONFIGURE,
                         message=f"{VARIABLE_DOSSIER} n'est pas defini.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        racine = Path(dossier)
        for attendu in ("main.py", "shorts_generator/pipeline.py",
                        "shorts_generator/local/clipper.py"):
            if not (racine / attendu).is_file():
                return Sante(EtatSante.NON_CONFIGURE,
                             message=f"{dossier} ne ressemble pas au moteur : {attendu} absent.",
                             ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        if shutil.which("ffmpeg") is None:
            return Sante(EtatSante.NON_CONFIGURE,
                         message="Le moteur est la, mais ffmpeg n'est pas sur le PATH.",
                         ce_qui_manque="installer ffmpeg (deja une dependance d'ARENA)",
                         mesure_le=_maintenant())

        # On INTERROGE l'interpreteur du moteur : presence d'OpenCV, version, et
        # existence reelle de CascadeClassifier. « Installe » ne vaut pas « marche ».
        sonde = (
            "import json\n"
            "try:\n"
            "    import cv2\n"
            "    d = {'cv2': cv2.__version__, 'cascade': hasattr(cv2, 'CascadeClassifier')}\n"
            "except Exception as e:\n"
            "    d = {'cv2': None, 'cascade': False, 'erreur': str(e)[:200]}\n"
            "print(json.dumps(d))\n"
        )
        try:
            acheve = subprocess.run(
                [_python_moteur(), "-c", sonde],
                capture_output=True, text=True, timeout=DELAI_SONDE_SECONDES,
                check=False, cwd=str(racine), env=self._environnement(racine / "out"),
            )
        except (subprocess.TimeoutExpired, OSError) as erreur:
            return Sante(EtatSante.EN_PANNE,
                         message=f"L'interpreteur du moteur n'a pas repondu : {erreur}",
                         mesure_le=_maintenant())

        mesure = self._json_final(acheve.stdout) or {}
        if not mesure.get("cv2"):
            return Sante(EtatSante.NON_CONFIGURE,
                         message="OpenCV est absent de l'environnement du moteur.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        if not mesure.get("cascade"):
            return Sante(
                EtatSante.NON_CONFIGURE,
                message=(f"OpenCV {mesure['cv2']} n'expose pas CascadeClassifier : "
                         "le recadrage echouerait sur chaque extrait."),
                ce_qui_manque="installer opencv-python-headless>=4.8,<5 dans l'environnement du moteur",
                mesure_le=_maintenant())

        if not self._llm_configure():
            return Sante(
                EtatSante.NON_CONFIGURE,
                message="Moteur et OpenCV prets ; aucun point d'acces LLM n'est declare.",
                ce_qui_manque=("definir YOUTUBE_SHORTS_LLM_BASE_URL (endpoint compatible OpenAI, "
                               "l'Ollama local par exemple) et YOUTUBE_SHORTS_LLM_MODEL"),
                mesure_le=_maintenant())

        return Sante(
            EtatSante.OPERATIONNEL,
            message=(f"Moteur present, OpenCV {mesure['cv2']} avec CascadeClassifier, "
                     "ffmpeg sur le PATH, LLM declare."),
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : aucun compte a ouvrir. Le mode MuAPI (le seul qui exige une
        cle tierce) n'est pas atteignable depuis ce fichier."""
        return True

    # --- Execution -----------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "inspecter_moteur":
            return self._inspecter()
        if capacite.nom == "generate_shorts":
            return self._generer(parametres)
        return echec(action=capacite.nom, cible=self.nom,
                     message=f"Capacite « {capacite.nom} » non implementee.")

    def _inspecter(self) -> ResultatAction:
        dossier = _dossier_moteur()
        if not dossier or not (Path(dossier) / "main.py").is_file():
            return non_configure(action="inspecter_moteur", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)
        revision = ""
        try:
            acheve = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dossier,
                                    capture_output=True, text=True,
                                    timeout=DELAI_SONDE_SECONDES, check=False)
            revision = acheve.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            revision = ""
        return succes(
            action="inspecter_moteur", cible=self.nom,
            message=("Moteur installe a la revision auditee."
                     if revision == COMMIT_AUDITE else
                     "Moteur installe a une revision differente de celle auditee."),
            preuve=dossier,
            revision_installee=revision or "inconnue",
            revision_auditee=COMMIT_AUDITE,
            conforme=revision == COMMIT_AUDITE,
            depot=DEPOT_AMONT,
            mode="local",
        )

    def _generer(self, parametres: Dict[str, Any]) -> ResultatAction:
        dossier = _dossier_moteur()
        if not dossier or not (Path(dossier) / "main.py").is_file():
            return non_configure(action="generate_shorts", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)

        entree = str(parametres.get("video") or "").strip()
        if not entree:
            return echec(action="generate_shorts", cible=self.nom,
                         message="Aucune video en entree (parametre « video »).")

        # Regle 3 : rien n'est telecharge sans que ce soit demande.
        if _est_une_url(entree):
            if not bool(parametres.get("autoriser_telechargement", False)):
                return echec(action="generate_shorts", cible=self.nom,
                             message=("Entree distante : autoriser_telechargement=True est "
                                      "requis explicitement. Rien n'a ete telecharge."))
        elif not Path(entree).is_file():
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"Video introuvable : {entree}")

        # Regle 2 : la transcription vient d'ARENA, jamais d'un second Whisper.
        srt = str(parametres.get("transcript_srt") or "").strip()
        if not srt:
            return echec(
                action="generate_shorts", cible=self.nom,
                message=("transcript_srt est requis : ARENA transcrit deja (FasterWhisper) et "
                         "ne charge pas un second modele Whisper dans le moteur."))
        chemin_srt = Path(srt)
        if not chemin_srt.is_file() or chemin_srt.stat().st_size == 0:
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"Transcription introuvable ou vide : {srt}")
        if _est_une_url(entree):
            return echec(
                action="generate_shorts", cible=self.nom,
                message=("Une entree distante et une transcription locale ne peuvent pas etre "
                         "appariees : le moteur nomme son cache d'apres le fichier telecharge. "
                         "Telecharge la video d'abord, puis passe le chemin local."))

        nombre = parametres.get("nombre_clips", 3)
        try:
            nombre = int(nombre)
        except (TypeError, ValueError):
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"nombre_clips doit etre un entier, recu {nombre!r}.")
        if not CLIPS_MIN <= nombre <= CLIPS_MAX:
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"nombre_clips doit etre entre {CLIPS_MIN} et {CLIPS_MAX}.")

        format_sortie = str(parametres.get("format") or "9:16").strip()
        if format_sortie not in FORMATS_AUTORISES:
            return echec(action="generate_shorts", cible=self.nom,
                         message=(f"format « {format_sortie} » refuse. "
                                  f"Valeurs autorisees : {sorted(FORMATS_AUTORISES)}."))

        if not self._llm_configure():
            return non_configure(
                action="generate_shorts", cible=self.nom,
                ce_qui_manque=("YOUTUBE_SHORTS_LLM_BASE_URL et YOUTUBE_SHORTS_LLM_MODEL "
                               "(endpoint compatible OpenAI, l'Ollama local par exemple)"))

        # Regle 6 : un dossier par execution.
        travail = self.dossier / f"shorts-{uuid.uuid4().hex[:8]}"
        travail.mkdir(parents=True, exist_ok=True)

        # Le moteur lit son cache de transcription a `<sortie>/<stem>.srt` et la
        # source doit vivre a cote pour que la comparaison de dates tienne.
        source = travail / Path(entree).name
        try:
            shutil.copy2(entree, source)
            cache = travail / (source.stem + ".srt")
            shutil.copy2(chemin_srt, cache)
            os.utime(cache, None)  # cache >= source : sinon le moteur re-transcrit.
        except OSError as erreur:
            self._nettoyer(travail)
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"Preparation du dossier de travail impossible : {erreur}")

        resultat_json = travail / "result.json"
        arguments = [
            _python_moteur(), "main.py", str(source),
            "--mode", "local",                       # Regle 1 : jamais « api ».
            "--num-clips", str(nombre),
            "--aspect-ratio", format_sortie,
            "--output-json", str(resultat_json),
        ]
        langue = str(parametres.get("langue") or "").strip()
        if langue:
            arguments += ["--language", langue]

        try:
            acheve = subprocess.run(
                arguments, capture_output=True, text=True, timeout=DELAI_SECONDES,
                check=False, cwd=dossier, env=self._environnement(travail),
            )
        except subprocess.TimeoutExpired:
            self._nettoyer_intermediaires(travail)
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"Le moteur n'a pas rendu la main sous {DELAI_SECONDES:.0f}s.",
                         dossier=str(travail))
        except OSError as erreur:
            self._nettoyer(travail)
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"Le moteur n'a pas pu etre lance : {erreur}")

        self._nettoyer_intermediaires(travail)

        if not resultat_json.is_file():
            self._nettoyer(travail)
            return echec(
                action="generate_shorts", cible=self.nom,
                message=(f"Le moteur n'a produit aucun resultat (code {acheve.returncode}) : "
                         f"{(acheve.stderr or acheve.stdout).strip()[:300]}"))
        try:
            brut = json.loads(resultat_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erreur:
            self._nettoyer(travail)
            return echec(action="generate_shorts", cible=self.nom,
                         message=f"Resultat du moteur illisible : {erreur}")

        return self._rendre(brut, travail, format_sortie, source)

    # --- Traduction du resultat ----------------------------------------------

    def _rendre(self, brut: Dict[str, Any], travail: Path, format_sortie: str,
                source: Path) -> ResultatAction:
        """Regle 5 : ne credite que des fichiers qui existent vraiment."""
        clips: List[Dict[str, Any]] = []
        erreurs: List[str] = []
        for rang, court in enumerate(brut.get("shorts") or [], start=1):
            chemin = str(court.get("clip_url") or "")
            fichier = Path(chemin) if chemin else None
            if fichier is None or not fichier.is_file() or fichier.stat().st_size == 0:
                erreurs.append(str(court.get("error") or
                                   f"extrait {rang} annonce sans fichier sur disque"))
                continue
            clips.append({
                "rang": rang,
                "chemin": str(fichier),
                "mime_type": "video/mp4",
                "titre": str(court.get("title") or ""),
                "debut": court.get("start_time"),
                "fin": court.get("end_time"),
                "score": court.get("score"),
                "hook": str(court.get("hook_sentence") or ""),
                "raison": str(court.get("virality_reason") or ""),
                "format": format_sortie,
                "octets": fichier.stat().st_size,
            })

        if not clips:
            self._nettoyer(travail)
            return echec(
                action="generate_shorts", cible=self.nom,
                message=("Le moteur s'est termine mais aucun short n'existe sur disque."
                         + (f" Cause : {erreurs[0]}" if erreurs else "")),
                erreurs=erreurs)

        # La source copiee a servi ; elle n'a pas a rester en double.
        try:
            source.unlink(missing_ok=True)
        except OSError:
            pass

        return succes(
            action="generate_shorts", cible=self.nom,
            message=(f"{len(clips)} short(s) {format_sortie} produits et verifies sur disque"
                     + (f" ({len(erreurs)} extrait(s) en echec)." if erreurs else ".")),
            preuve=clips[0]["chemin"],
            clips=clips,
            candidats=len(brut.get("highlights") or []),
            dossier=str(travail),
            mode="local",
            erreurs=erreurs,
        )

    # --- Frontieres ----------------------------------------------------------

    def _llm_configure(self) -> bool:
        return bool(os.getenv("YOUTUBE_SHORTS_LLM_BASE_URL", "").strip()
                    and os.getenv("YOUTUBE_SHORTS_LLM_MODEL", "").strip())

    def _environnement(self, sortie: Path) -> Dict[str, str]:
        """Regle 4 : un environnement construit, jamais `os.environ` recopie.

        Le moteur recoit de quoi tourner et rien d'autre : pas les jetons des
        connecteurs, pas les identifiants Google, pas les cles des modeles
        d'ARENA. La cle LLM qui lui est passee est la sienne
        (`YOUTUBE_SHORTS_LLM_API_KEY`), volontairement distincte de
        `OPENAI_API_KEY` d'ARENA.
        """
        return {
            "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.getenv("HOME", str(sortie)),
            "LANG": os.getenv("LANG", "C.UTF-8"),
            "PYTHONIOENCODING": "utf-8",
            "LOCAL_OUTPUT_DIR": str(sortie),
            "LLM_PROVIDER": "openai",
            "OPENAI_BASE_URL": os.getenv("YOUTUBE_SHORTS_LLM_BASE_URL", "").strip(),
            "OPENAI_MODEL": os.getenv("YOUTUBE_SHORTS_LLM_MODEL", "").strip(),
            # Un endpoint local n'en demande pas ; le client OpenAI exige une
            # valeur non vide. Jamais la cle d'ARENA.
            "OPENAI_API_KEY": os.getenv("YOUTUBE_SHORTS_LLM_API_KEY", "").strip() or "local",
        }

    def _nettoyer_intermediaires(self, travail: Path) -> None:
        """Les fichiers de passage du moteur, y compris ceux d'un run interrompu."""
        for motif in ("*.cut.mp4", "*.silent.mp4"):
            for reste in travail.glob(motif):
                try:
                    reste.unlink()
                except OSError:
                    logger.warning("Fichier intermediaire non supprime : %s", reste)

    def _nettoyer(self, travail: Path) -> None:
        """Aucun short produit : le dossier de travail ne survit pas a l'echec."""
        shutil.rmtree(travail, ignore_errors=True)

    @staticmethod
    def _json_final(sortie: str) -> Optional[Dict[str, Any]]:
        for ligne in reversed((sortie or "").splitlines()):
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                valeur = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            if isinstance(valeur, dict):
                return valeur
        return None
