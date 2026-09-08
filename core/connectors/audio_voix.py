"""L'audio d'ARENA : parler, transcrire — en pilotant VoiceStudio par HTTP.

**Ce fichier ne contient aucune ligne de VoiceStudio, et c'est une decision
juridique avant d'etre technique.** VoiceStudio est sous **AGPL-3.0-only** ;
`LICENSE` d'ARENA dit « All rights reserved ». Copier son source ici, ou meme
l'importer comme bibliotheque, ferait d'ARENA une oeuvre derivee : ARENA
devrait alors etre publie sous AGPL. La frontiere est donc un **processus
separe**, joint par HTTP sur la boucle locale — l'AGPL n'etend pas ses
obligations a un programme qui se contente d'appeler un service.

Detail complet du raisonnement → `docs/audits/voicestudio_audit.md`.

**Quatre regles :**

1. **Aucune capacite ne s'invente.** Les moteurs disponibles sont demandes a
   VoiceStudio (`/engines/tts`, `/engines/asr`) ; ARENA ne promet que ce que
   la machine repond. Service eteint → `NON_CONFIGURE` avec ce qui manque.

2. **Le succes est le fichier, pas la reponse HTTP.** Un `200` ne suffit
   pas : le fichier est ecrit, puis **re-sonde avec ffprobe**. Une duree
   nulle ou un conteneur illisible est un echec.

3. **Rien ne sort de la machine.** VoiceStudio ecoute sur `127.0.0.1`, et le
   connecteur refuse une adresse qui n'est pas locale — une voix est une
   donnee sensible, et un `OMNIVOICE_URL` pointe vers l'exterieur enverrait
   les enregistrements du proprietaire chez un tiers sans qu'il le sache.

4. **Parler est une ecriture.** Transcrire lit un fichier deja la ; produire
   de l'audio ecrit sur le disque et passe par la confirmation, comme le
   devis PDF ou le rendu video.

5. **Un seul routeur choisit le moteur, et il connait les licences.**
   `core/audio/routage_tts.py` — parler et cloner passent tous les deux par
   lui. Il refuse les poids CC-BY-NC pour un travail commercial : le moteur
   par defaut de VoiceStudio en est un, et UniC est une entreprise (DEC-0069).
"""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.audio.routage_tts import (
    Commercial,
    ErreurDeMoteur,
    MoteurTTS,
    Usage,
    choisir,
    moteurs_depuis,
)
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.connecteurs.audio")

#: Ou VoiceStudio ecoute. 3900 est SON defaut (backend/main.py), pas le notre.
URL_PAR_DEFAUT = "http://127.0.0.1:3900"

#: Ou l'audio produit est ecrit. Un fichier produit doit se retrouver.
DOSSIER_AUDIO = Path("data") / "audio"

#: Synthetiser une minute de parole sur un CPU prend des dizaines de secondes ;
#: transcrire une video longue, davantage. Mesure sur cette machine : 6 s
#: d'audio transcrits en ~4 s avec `faster-whisper base`.
DELAI_SECONDES = 600.0

#: Les hotes acceptes. La regle 3 vit ici, et nulle part ailleurs.
HOTES_LOCAUX = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

CE_QUI_MANQUE = (
    "VoiceStudio ne repond pas sur {url}. C'est un programme separe (AGPL-3.0) "
    "qu'ARENA pilote, jamais un module d'ARENA : demarre-le, puis reessaie."
)


class AdresseNonLocale(ValueError):
    """`OMNIVOICE_URL` sort de la machine. La voix ne part pas."""


def url_de_voicestudio() -> str:
    """L'adresse de VoiceStudio, refusee si elle n'est pas locale.

    Raises:
        AdresseNonLocale: si l'hote configure n'est pas la boucle locale.
    """
    url = os.environ.get("OMNIVOICE_URL", URL_PAR_DEFAUT).rstrip("/")
    hote = urlparse(url).hostname
    if hote not in HOTES_LOCAUX:
        raise AdresseNonLocale(
            f"OMNIVOICE_URL pointe vers « {hote} », hors de cette machine. "
            "Les voix et les enregistrements restent locaux : refuse."
        )
    return url


def ressemble_a_du_wav(chemin: Path) -> bool:
    """Le fichier porte-t-il l'en-tête d'un WAV : « RIFF » … « WAVE » ?

    Ce n'est **pas** une mesure de durée et ne la remplace pas. C'est le seul
    contrôle possible quand `ffprobe` manque, et il suffit à distinguer un son
    d'un message d'erreur que VoiceStudio aurait renvoyé avec un code 200 —
    ce que la règle 2 cherche précisément à attraper.
    """
    try:
        with chemin.open("rb") as flux:
            entete = flux.read(12)
    except OSError:
        return False
    return entete[:4] == b"RIFF" and entete[8:12] == b"WAVE"


def sonder_le_fichier(chemin: Path, ffprobe: str = "ffprobe") -> Dict[str, Any]:
    """Ce que ffprobe mesure sur un fichier audio. Rien n'est suppose.

    Un champ que la sonde ne donne pas reste `None` — jamais `0`, qui se
    lirait comme une mesure.

    `sonde_disponible` dit si `ffprobe` a pu repondre. **Sans lui, `duree_ms`
    vaut `None` pour une raison qui ne concerne pas le fichier**, et confondre
    les deux revenait a jeter un son valide : mesure du 02/09/2026, un WAV
    reel de 2 s et 176 478 octets supprime parce que `ffprobe` manquait.
    """
    inconnu: Dict[str, Any] = {"duree_ms": None, "octets": None, "format": None,
                               "sonde_disponible": None}
    if not chemin.is_file():
        return inconnu
    inconnu["octets"] = chemin.stat().st_size
    try:
        sortie = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration,format_name", "-of", "default=nw=1:nk=1", str(chemin)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as erreur:
        logger.warning("ffprobe indisponible pour %s : %s", chemin, erreur)
        inconnu["sonde_disponible"] = False
        return inconnu

    inconnu["sonde_disponible"] = True
    # L'ordre des lignes n'est PAS celui demande a `-show_entries` : ffprobe
    # rend `format_name` d'abord, `duration` ensuite. Lire « la derniere
    # ligne » comme le format laissait donc ce champ toujours `None`, sur des
    # fichiers parfaitement mesurables (mesure du 02/09/2026). Chaque ligne est
    # maintenant reconnue pour ce qu'elle est, jamais pour sa position.
    for brute in sortie.stdout.splitlines():
        ligne = brute.strip()
        if not ligne:
            continue
        try:
            duree = float(ligne)
        except ValueError:
            if inconnu["format"] is None:
                inconnu["format"] = ligne
        else:
            if inconnu["duree_ms"] is None:
                inconnu["duree_ms"] = int(round(duree * 1000))
    return inconnu


def usage_demande(valeur: str) -> Usage:
    """Traduit ce que l'appelant declare. Un mot inconnu n'est PAS commercial.

    Accepter en silence un `usage` mal orthographie reviendrait a choisir a sa
    place, et dans le seul sens qui coute : celui qui ouvre les poids
    CC-BY-NC. Un mot que ce module ne connait pas est donc refuse.

    Raises:
        ValueError: la valeur ne correspond a aucun usage declare.
    """
    propre = (valeur or "").strip().lower()
    if not propre:
        return Usage.COMMERCIAL
    try:
        return Usage(propre)
    except ValueError:
        connus = ", ".join(u.value for u in Usage)
        raise ValueError(
            f"usage « {valeur} » inconnu. Valeurs possibles : {connus}.") from None


def _tracer(moteur: MoteurTTS) -> Dict[str, Any]:
    """Ce qui doit rester dans le journal a cote d'un fichier audio produit.

    Un WAV retrouve dans six mois ne dit ni sous quelle licence il a ete
    fabrique, ni sur quel appareil. Ces champs le disent, et ils sont mesures :
    `appareil` et `routage` viennent de VoiceStudio a l'instant du choix.
    """
    return {
        "moteur": moteur.identifiant,
        "appareil": moteur.appareil,
        "routage": moteur.routage,
        "licence": moteur.licence.licence,
        "usage_commercial": moteur.licence.commercial.value,
    }


class ConnecteurAudioVoix(Connecteur):
    """Parler et transcrire, en pilotant VoiceStudio sur la boucle locale."""

    service = "audio_voix"
    nom = "audio"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else DOSSIER_AUDIO

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "moteurs": Capacite(
                nom="moteurs", action="read",
                description="Liste les moteurs de voix et de transcription réellement disponibles.",
                ecriture=False),
            "transcrire": Capacite(
                nom="transcrire", action="read",
                description="Transcrit un fichier audio ou vidéo déjà présent sur la machine.",
                ecriture=False),
            "parler": Capacite(
                nom="parler", action="document",
                description="Synthétise un texte en fichier audio, vérifié après écriture.",
                ecriture=True),
            # Action distincte de "parler", et pas une simple variante : cloner
            # une voix risque l'usurpation, jamais seulement un fichier de plus.
            # `config/permissions_services.yaml` lui donne un risque HIGH la ou
            # "parler" reste MEDIUM — la meme confirmation ne doit pas couvrir
            # les deux. Voir `_cloner` : l'autorisation est en plus exigee dans
            # le code meme, avant toute confirmation.
            "cloner": Capacite(
                nom="cloner", action="cloner",
                description=("Clone une voix a partir d'un enregistrement de reference. "
                             "Exige que l'appelant declare qui a autorise cette voix."),
                ecriture=True),
        }

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        """Precise, pour "cloner", la source et l'autorisation avant confirmation."""
        if capacite.nom == "cloner":
            source = parametres.get("ref_audio") or "(aucune reference)"
            autorisation = parametres.get("autorisation") or "(non precisee)"
            return (f"Une voix clonee a partir de « {source} » va parler. "
                    f"Autorisation declaree : {autorisation}.")
        return super().resultat_attendu(capacite, **parametres)

    # --- Sante ----------------------------------------------------------------

    def sonder(self) -> Sante:
        """VoiceStudio repond-il ? Sans lui, aucune voix — et on le dit."""
        from core.connectors.base import _maintenant

        try:
            url = url_de_voicestudio()
        except AdresseNonLocale as erreur:
            return Sante(etat=EtatSante.NON_CONFIGURE, message=str(erreur),
                         ce_qui_manque="une adresse locale pour VoiceStudio",
                         mesure_le=_maintenant())
        try:
            with httpx.Client(timeout=10.0, trust_env=False) as client:
                reponse = client.get(f"{url}/system/info")
                reponse.raise_for_status()
                info = reponse.json()
        except (httpx.HTTPError, ValueError) as erreur:
            logger.info("VoiceStudio injoignable : %s", erreur)
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"VoiceStudio ne repond pas ({erreur.__class__.__name__}).",
                         ce_qui_manque=CE_QUI_MANQUE.format(url=url),
                         mesure_le=_maintenant())

        appareil = info.get("device") or "?"
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=(f"VoiceStudio {info.get('app_version','?')} repond sur {url} "
                     f"({appareil})."),
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : VoiceStudio ecoute en local et ne demande aucun identifiant."""
        return True

    # --- Le coeur -------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        url = url_de_voicestudio()
        if capacite.nom == "moteurs":
            return self._moteurs(url)
        if capacite.nom == "transcrire":
            return self._transcrire(url, **parametres)
        if capacite.nom == "cloner":
            return self._cloner(url, **parametres)
        return self._parler(url, **parametres)

    def _moteurs(self, url: str) -> ResultatAction:
        """Ce que la machine sait faire, demande a la machine.

        Rend aussi, pour chaque moteur de voix, **l'appareil qu'il utilise
        vraiment** (`effective_device`) et son etat d'acceleration
        (`routing_status`). VoiceStudio les publiait deja ; ARENA les jetait.
        C'est la reponse mesuree a « quel appareil sert reellement ? », et
        elle ne se deduit pas de la presence d'un GPU : un moteur compatible
        CUDA peut retomber sur le processeur faute de VRAM, et c'est
        exactement ce que `cpu_fallback` dit.
        """
        try:
            moteurs_voix = self._entrees_tts(url)
            ecoute = self._moteurs_disponibles(url, "asr")
        except (httpx.HTTPError, ValueError) as erreur:
            return echec(action="moteurs", cible=self.nom,
                         message=f"VoiceStudio n'a pas repondu : {erreur}")

        actifs = [m for m in moteurs_voix if m.disponible]
        voix = [m.identifiant for m in actifs]
        if not voix and not ecoute:
            return non_configure(
                action="moteurs", cible=self.nom,
                ce_qui_manque=("aucun moteur installe dans VoiceStudio : ni voix, "
                               "ni transcription. Installe-les de son cote."))

        detail = [{"id": m.identifiant, "appareil": m.appareil,
                   "routage": m.routage, "accelere": m.accelere,
                   "licence": m.licence.licence,
                   "usage_commercial": m.licence.commercial.value}
                  for m in actifs]
        interdits = [m.identifiant for m in actifs
                     if m.licence.commercial is Commercial.INTERDIT]
        appareils = sorted({m.appareil for m in actifs if m.appareil})

        message = (f"Voix : {', '.join(voix) or 'aucune'}. "
                   f"Transcription : {', '.join(ecoute) or 'aucune'}.")
        if appareils:
            message += f" Appareil(s) reellement utilise(s) : {', '.join(appareils)}."
        if interdits:
            message += (f" Usage commercial interdit pour : {', '.join(interdits)} "
                        "— ARENA ne les choisira pas pour un travail d'UniC.")
        return succes(
            action="moteurs", cible=self.nom, message=message,
            preuve=f"{len(voix)} moteur(s) de voix, {len(ecoute)} de transcription",
            tts=voix, asr=ecoute, voix=detail, appareils=appareils,
            non_commerciaux=interdits)

    def _transcrire(self, url: str, chemin: str = "", langue: str = "fr",
                    moteur: str = "whisper-1", **_: Any) -> ResultatAction:
        source = Path(chemin)
        if not chemin or not source.is_file():
            return echec(action="transcrire", cible=self.nom,
                         message=f"Fichier introuvable : « {chemin or '(aucun)'} ».")

        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                with source.open("rb") as flux:
                    reponse = client.post(
                        f"{url}/v1/audio/transcriptions",
                        files={"file": (source.name, flux)},
                        data={"model": moteur, "language": langue,
                              "response_format": "json"})
        except httpx.HTTPError as erreur:
            return echec(action="transcrire", cible=self.nom,
                         message=f"VoiceStudio n'a pas repondu : {erreur}")

        if reponse.status_code == 409:
            # VoiceStudio dit precisement quel modele manque : on le relaie
            # tel quel plutot que de le traduire en « erreur ».
            detail = reponse.json().get("detail", {})
            return non_configure(
                action="transcrire", cible=self.nom,
                ce_qui_manque=str(detail.get("message") or detail))
        if reponse.status_code != 200:
            return echec(action="transcrire", cible=self.nom,
                         message=f"Transcription refusee ({reponse.status_code}) : "
                                 f"{reponse.text[:200]}")

        texte = (reponse.json().get("text") or "").strip()
        if not texte:
            # Un silence n'est pas une transcription : un texte vide se
            # rapporte, il ne se presente pas comme une reussite.
            return echec(action="transcrire", cible=self.nom,
                         message="VoiceStudio n'a rien entendu dans ce fichier.")
        return succes(action="transcrire", cible=self.nom,
                      message=texte,
                      preuve=f"{len(texte)} caracteres depuis {source.name}",
                      texte=texte, source=str(source), moteur=moteur)

    def _entrees_tts(self, url: str) -> List[MoteurTTS]:
        """Ce que VoiceStudio dit de ses moteurs de voix, MAINTENANT.

        Une seule requete rend tout ce dont le routeur a besoin :
        disponibilite, `supports_cloning`, `effective_device` et
        `routing_status`. Ces deux derniers sont la reponse mesuree a
        « quel appareil est reellement utilise ? » — ARENA les lisait
        jusqu'ici sans jamais s'en servir (DEC-0069).
        """
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            return moteurs_depuis(client.get(f"{url}/engines/tts").json())

    def _moteurs_disponibles(self, url: str, genre: str) -> List[str]:
        """Les moteurs que VoiceStudio declare DISPONIBLES, dans son ordre."""
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            donnees = client.get(f"{url}/engines/{genre}").json()
        return [b.get("id") for b in donnees.get("backends", []) if b.get("available")]

    def _choisir_la_voix(self, url: str, demande: str,
                         usage: Usage = Usage.COMMERCIAL,
                         voice_design: bool = False) -> MoteurTTS:
        """Le moteur qui parlera — decide par le routeur unique.

        VoiceStudio garde `omnivoice` comme moteur actif meme quand son
        paquet n'est pas installe : une demande sans `model` partait donc
        vers un moteur absent et revenait en 400. Et quand il EST installe,
        c'est la premiere entree de son registre — donc le moteur par defaut
        d'ARENA, alors que ses poids sont CC-BY-NC.

        Le choix ne se fait plus ici : `core/audio/routage_tts.py` le fait,
        pour parler comme pour cloner (DEC-0069).

        Raises:
            ErreurDeMoteur: aucun moteur ne convient, avec la raison de
                chaque ecarte.
        """
        return choisir(self._entrees_tts(url), usage=usage,
                       voice_design=voice_design, demande=demande)

    def _parler(self, url: str, texte: str = "", moteur: str = "",
                voix: str = "default", langue: str = "fr",
                instruct: str = "", usage: str = "", **_: Any) -> ResultatAction:
        propre = (texte or "").strip()
        if not propre:
            return echec(action="parler", cible=self.nom,
                         message="Aucun texte a lire : rien a synthetiser.")

        try:
            pour = usage_demande(usage)
        except ValueError as erreur:
            return echec(action="parler", cible=self.nom, message=str(erreur))

        try:
            choisi = self._choisir_la_voix(url, moteur, usage=pour,
                                           voice_design=bool(instruct))
        except ErreurDeMoteur as erreur:
            return non_configure(action="parler", cible=self.nom,
                                 ce_qui_manque=str(erreur))
        except (httpx.HTTPError, ValueError) as erreur:
            return echec(action="parler", cible=self.nom,
                         message=f"VoiceStudio n'a pas dit quels moteurs il a : {erreur}")

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"voix-{uuid.uuid4().hex[:8]}.wav"
        corps = {"input": propre, "voice": voix, "response_format": "wav",
                 "language": langue, "model": choisi.identifiant}
        if instruct:
            # Voix design (genre/age/pitch/accent...) : un champ que
            # VoiceStudio transmet tel quel au moteur actif (verifie dans son
            # source, `SpeechRequest.instruct`), jamais invente ici. ARENA ne
            # sait pas quels moteurs l'honorent reellement (le champ n'est pas
            # expose par `/engines/tts`) : demander un moteur precis reste a
            # l'appelant, `_choisir_la_voix` ne devine pas lequel le supporte.
            corps["instruct"] = instruct

        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                reponse = client.post(f"{url}/v1/audio/speech", json=corps)
        except httpx.HTTPError as erreur:
            return echec(action="parler", cible=self.nom,
                         message=f"VoiceStudio n'a pas repondu : {erreur}")

        if reponse.status_code != 200:
            return echec(action="parler", cible=self.nom,
                         message=f"Synthese refusee ({reponse.status_code}) : "
                                 f"{reponse.text[:200]}")

        sortie.write_bytes(reponse.content)
        # Regle 2 : le fichier est re-sonde. Un 200 sur un conteneur illisible
        # resterait un echec, et c'est exactement ce qui arrive quand le
        # moteur renvoie du JSON d'erreur avec le bon code.
        mesures = sonder_le_fichier(sortie)
        if mesures["duree_ms"]:
            return succes(action="parler", cible=self.nom,
                          message=(f"Voix produite par « {choisi.identifiant} » "
                                   f"sur {choisi.appareil or 'un appareil non precise'} : "
                                   f"{mesures['duree_ms']} ms, {mesures['octets']} octets."),
                          preuve=str(sortie), **_tracer(choisi), **mesures)

        # `ffprobe` absent n'est PAS le fichier en cause. Confondre les deux
        # supprimait un son valide et annoncait un echec : mesure du
        # 02/09/2026, un WAV reel de 2 s et 176 478 octets jete parce que la
        # sonde manquait. La regle 2 tient quand meme — l'en-tete du conteneur
        # est verifiee — mais la duree n'est PAS annoncee, puisqu'elle n'a pas
        # ete mesuree.
        if mesures["sonde_disponible"] is False and ressemble_a_du_wav(sortie):
            return succes(
                action="parler", cible=self.nom,
                message=(f"Voix produite par « {choisi.identifiant} » : "
                         f"{mesures['octets']} octets. Duree non verifiee — ffprobe "
                         "n'est pas installe sur cette machine, donc rien ne l'a "
                         "mesuree."),
                preuve=str(sortie), **_tracer(choisi), **mesures)

        sortie.unlink(missing_ok=True)
        return echec(
            action="parler", cible=self.nom,
            message="VoiceStudio a repondu, mais le fichier n'a aucune duree "
                    "lisible : rien n'a ete garde.",
            **mesures)

    # --- Clonage de voix -------------------------------------------------------
    #
    # Deux appels a VoiceStudio, jamais un : son API cree d'abord un « profil
    # de voix » a partir de l'enregistrement de reference (`POST /profiles`),
    # puis ce profil se demande comme n'importe quelle voix a `/v1/audio/speech`
    # (`voice=<profile_id>`). Verifie dans son source (`debpalash/VoiceStudio`,
    # `backend/api/routers/profiles.py` et `openai_compat.py`, audite le
    # 07/09/2026) — jamais suppose : un clonage n'est pas une simple option de
    # `_parler`, une hypothese fausse ici enverrait un fichier ou un champ que
    # VoiceStudio n'attend pas.

    def _choisir_pour_clonage(self, url: str, demande: str,
                              usage: Usage = Usage.COMMERCIAL) -> MoteurTTS:
        """Le moteur qui clonera — le MEME routeur, avec `clonage=True`.

        `supports_cloning` est un champ reel de `/engines/tts` (verifie dans
        `backend/services/tts_backend.py::list_backends`), pas une hypothese.
        `None` (capacite dependant du modele charge, ex. mlx-audio) compte
        comme non prouve : ARENA ne clone que ce qui l'annonce sans ambiguite.

        Raises:
            ErreurDeMoteur: aucun moteur disponible ne clone, ou celui demande
                n'en fait pas partie.
        """
        return choisir(self._entrees_tts(url), usage=usage, clonage=True,
                       demande=demande)

    def _cloner(self, url: str, texte: str = "", ref_audio: str = "",
                ref_text: str = "", autorisation: str = "", moteur: str = "",
                langue: str = "fr", nom_profil: str = "", usage: str = "",
                **_: Any) -> ResultatAction:
        propre = (texte or "").strip()
        if not propre:
            return echec(action="cloner", cible=self.nom,
                         message="Aucun texte a lire : rien a synthetiser.")

        # L'autorisation est exigee ICI, dans le code de la capacite — pas
        # seulement dans le message de confirmation. Meme un appel direct
        # (test, script, futur agent) qui sauterait la lecture du message ne
        # peut pas cloner sans avoir declare qui a autorise cette voix.
        qui = (autorisation or "").strip()
        if not qui:
            return echec(
                action="cloner", cible=self.nom,
                message="Autorisation manquante : indique qui a autorise cette "
                        "voix avant de la cloner. Rien n'a ete tente.")

        source = Path(ref_audio) if ref_audio else None
        if source is None or not source.is_file():
            return echec(action="cloner", cible=self.nom,
                         message=f"Enregistrement de reference introuvable : "
                                 f"« {ref_audio or '(aucun)'} ».")

        try:
            pour = usage_demande(usage)
        except ValueError as erreur:
            return echec(action="cloner", cible=self.nom, message=str(erreur))

        try:
            choisi = self._choisir_pour_clonage(url, moteur, usage=pour)
        except ErreurDeMoteur as erreur:
            return non_configure(action="cloner", cible=self.nom,
                                 ce_qui_manque=str(erreur))
        except (httpx.HTTPError, ValueError) as erreur:
            return echec(action="cloner", cible=self.nom,
                         message=f"VoiceStudio n'a pas dit quels moteurs il a : {erreur}")

        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                with source.open("rb") as flux:
                    creation = client.post(
                        f"{url}/profiles",
                        data={"name": nom_profil or f"arena-{uuid.uuid4().hex[:8]}",
                              "ref_text": ref_text, "language": langue, "kind": "clone"},
                        files={"ref_audio": (source.name, flux)})
        except httpx.HTTPError as erreur:
            return echec(action="cloner", cible=self.nom,
                         message=f"VoiceStudio n'a pas repondu (creation du profil) : {erreur}")

        if creation.status_code not in (200, 201):
            return echec(action="cloner", cible=self.nom,
                         message=f"Creation du profil de voix refusee "
                                 f"({creation.status_code}) : {creation.text[:200]}")

        profil = (creation.json() or {}).get("id")
        if not profil:
            return echec(action="cloner", cible=self.nom,
                         message="VoiceStudio n'a rendu aucun identifiant de profil.")

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"clone-{uuid.uuid4().hex[:8]}.wav"
        corps = {"input": propre, "voice": profil, "response_format": "wav",
                 "language": langue, "model": choisi.identifiant}

        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                reponse = client.post(f"{url}/v1/audio/speech", json=corps)
        except httpx.HTTPError as erreur:
            return echec(action="cloner", cible=self.nom,
                         message=f"VoiceStudio n'a pas repondu (synthese) : {erreur}")

        if reponse.status_code != 200:
            return echec(action="cloner", cible=self.nom,
                         message=f"Synthese clonee refusee ({reponse.status_code}) : "
                                 f"{reponse.text[:200]}")

        sortie.write_bytes(reponse.content)
        mesures = sonder_le_fichier(sortie)
        preuve_de_son = mesures["duree_ms"] or (
            mesures["sonde_disponible"] is False and ressemble_a_du_wav(sortie))
        if not preuve_de_son:
            sortie.unlink(missing_ok=True)
            return echec(
                action="cloner", cible=self.nom,
                message="VoiceStudio a repondu, mais le fichier clone n'a aucune "
                        "duree lisible : rien n'a ete garde.",
                **mesures)

        return succes(
            action="cloner", cible=self.nom,
            message=(f"Voix clonee par « {choisi.identifiant} » a partir de "
                     f"« {source.name} », autorisee par : {qui}."),
            preuve=str(sortie), profil=profil, ref_audio=str(source),
            autorisation=qui, **_tracer(choisi), **mesures)
