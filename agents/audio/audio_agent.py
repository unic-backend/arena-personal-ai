"""L'agent audio : la parole et l'ecoute, dans le meme ARENA que le reste.

Le proprietaire ne dit pas « appelle le moteur de synthese ». Il dit « lis-moi
ce texte », « transcris cette video », « fais une voix off pour mon chantier ».
Cet agent traduit ces phrases en capacites du connecteur `audio`, qui pilote
VoiceStudio par HTTP (`core/connectors/audio_voix.py`).

**Ce qu'il ne fait pas**, et qui est le sujet :

- Il **n'invente aucune transcription** et **ne simule aucune voix**.
  VoiceStudio eteint, moteur absent, modele non telecharge : il rapporte ce
  qui manque, avec le message exact de la machine.
- Il **ne choisit pas un fichier de lui-meme**. Le chemin vient de l'appelant,
  qui l'a deja borne au dossier `media/` — meme discipline que le montage
  (`core/montage/planificateur.py`).
- Il **ne parle pas sans confirmation**. `parler` ecrit un fichier : le
  connecteur le fait passer par la file d'attente, comme le devis PDF.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.resultat import Statut
from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.audio")

CONNECTEUR = "audio"

#: Ce qui demande d'ECOUTER un fichier deja la. Teste avant la lecture a voix
#: haute : « transcris ce que je dis dans cette video » contient « dis ».
#: Les sous-titres ne sont PAS ici : `apps/backend/studio.py` les fabrique
#: deja (transcription + incrustation 9:16). Les reprendre aurait double une
#: capacite qui marche — ce que la mission interdit explicitement.
ECOUTER = (
    "transcris", "transcrire", "transcription", "retranscris",
    "qu'est-ce qui est dit", "qu est ce qui est dit", "ce qui se dit",
    "ecris ce qui est dit", "écris ce qui est dit",
)

#: Ce qui demande de PARLER.
PARLER = (
    "lis ce", "lis-moi", "lis moi", "voix off", "voix-off", "en voix",
    "a voix haute", "à voix haute", "transforme ce texte en voix",
    "dis a voix haute", "dis à voix haute", "narration", "narre",
    "genere une voix", "génère une voix", "synthese vocale", "synthèse vocale",
)

#: Ce qui demande de CLONER une voix. Teste avant PARLER : "clone cette voix,
#: dis bonjour" ne doit pas retomber sur la synthese ordinaire.
CLONER = (
    "clone cette voix", "clone la voix", "cloner cette voix", "cloner la voix",
    "clonage vocal", "clone sa voix", "clone ma voix",
)

#: Les extensions qu'un moteur de transcription sait ouvrir. ffmpeg tire la
#: piste audio d'une video, donc les conteneurs video en font partie.
EXTENSIONS_ECOUTABLES = frozenset({
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
})


def genre_de_demande(phrase: str) -> str:
    """`ecouter`, `cloner`, `parler` ou `moteurs` — decide sans appeler le modele.

    Le repli par mots-cles reste le SEUL classificateur quand Ollama est
    eteint, et ces quatre cas se distinguent sans modele.
    """
    texte = (phrase or "").lower()
    if any(mot in texte for mot in ECOUTER):
        return "ecouter"
    if any(mot in texte for mot in CLONER):
        return "cloner"
    if any(mot in texte for mot in PARLER):
        return "parler"
    return "moteurs"


def texte_a_lire(phrase: str) -> str:
    """Ce qu'il veut entendre : ce qui est entre guillemets, sinon la phrase.

    Sans guillemets, l'instruction elle-meme serait lue (« lis-moi bonjour »
    donnerait « lis-moi bonjour »). On retire donc l'amorce reconnue, et ce
    qui reste est le texte.
    """
    for ouvrant, fermant in (("«", "»"), ('"', '"'), ("“", "”")):
        debut = phrase.find(ouvrant)
        fin = phrase.rfind(fermant)
        if debut != -1 and fin > debut:
            entre = phrase[debut + 1:fin].strip()
            if entre:
                return entre

    reste = phrase
    for amorce in sorted(PARLER, key=len, reverse=True):
        motif = re.compile(re.escape(amorce) + r"\s*[:,]?\s*", re.IGNORECASE)
        if motif.search(reste):
            reste = motif.sub("", reste, count=1).strip()
            break
    return reste.strip(" .:!?")


class AudioAgent(BaseAgent):
    """Parler, ecouter — en passant par le connecteur, jamais en direct."""

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        registre: Any = None,
    ):
        super().__init__(
            name="AudioAgent",
            description="Agent audio : lecture a voix haute et transcription (les sous-titres restent au studio).",
            provider=provider,
            memory=memory,
        )
        self.registre = registre

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contexte = context or {}
        if self.registre is None:
            return self._erreur("Le connecteur audio n'est pas branche sur cet agent.")

        genre = genre_de_demande(user_input)
        if genre == "ecouter":
            return self._ecouter(user_input, contexte)
        if genre == "cloner":
            return self._cloner(user_input, contexte)
        if genre == "parler":
            return self._parler(user_input, contexte)
        return self._moteurs()

    # --- Les trois voies ------------------------------------------------------

    def _moteurs(self) -> Dict[str, Any]:
        resultat = self.registre.executer(CONNECTEUR, "moteurs")
        return self._depuis(resultat, action="moteurs")

    def _ecouter(self, phrase: str, contexte: Dict[str, Any]) -> Dict[str, Any]:
        chemin = self._fichier_ecoutable(contexte)
        if chemin is None:
            return self._erreur(
                "Je ne vois aucun fichier audio ou video a transcrire. "
                "Depose-le dans tes medias et redemande."
            )
        resultat = self.registre.executer(
            CONNECTEUR, "transcrire", chemin=str(chemin),
            langue=str(contexte.get("langue") or "fr"))
        return self._depuis(resultat, action="transcrire", source=str(chemin))

    def _parler(self, phrase: str, contexte: Dict[str, Any]) -> Dict[str, Any]:
        texte = str(contexte.get("texte") or "").strip() or texte_a_lire(phrase)
        if not texte:
            return self._erreur("Dis-moi quoi lire : je ne devine pas le texte.")
        # Ecriture : le connecteur la fait passer par la file de confirmation.
        # `usage` absent = commercial (DEC-0069). UniC est une entreprise, et
        # une voix off de chantier est un usage commercial : c'est le defaut
        # sur : se tromper dans ce sens coute une gene, dans l'autre une
        # violation de licence silencieuse. La porte « recherche » existe
        # quand meme, sinon elle serait une capacite morte de plus.
        resultat = self.registre.executer(
            CONNECTEUR, "parler", texte=texte,
            langue=str(contexte.get("langue") or "fr"),
            voix=str(contexte.get("voix") or "default"),
            usage=str(contexte.get("usage") or ""),
            instruct=str(contexte.get("voice_design") or ""))
        return self._depuis(resultat, action="parler", texte_lu=texte)

    def _cloner(self, phrase: str, contexte: Dict[str, Any]) -> Dict[str, Any]:
        """Cloner une voix : jamais sans reference reelle ni autorisation declaree.

        L'appelant fournit les trois — le fichier de reference (deja borne au
        dossier `media/`, meme discipline que `_fichier_ecoutable`), le texte a
        dire, et qui a autorise cette voix. Rien n'est devine : c'est le
        connecteur lui-meme qui refuse en plus une autorisation vide
        (`core/connectors/audio_voix.py::_cloner`), mais l'agent le dit tout de
        suite pour ne pas faire attendre un aller-retour pour rien.
        """
        ref_audio = self._fichier_ecoutable(contexte)
        if ref_audio is None:
            return self._erreur(
                "Je ne vois aucun enregistrement de reference a cloner. "
                "Depose-le dans tes medias et redemande."
            )
        texte = str(contexte.get("texte") or "").strip() or texte_a_lire(phrase)
        if not texte:
            return self._erreur("Dis-moi ce que la voix clonee doit dire.")
        autorisation = str(contexte.get("autorisation") or "").strip()
        if not autorisation:
            return self._erreur(
                "Le clonage vocal exige une autorisation explicite : qui a "
                "autorise l'usage de cette voix ?"
            )
        resultat = self.registre.executer(
            CONNECTEUR, "cloner", texte=texte, ref_audio=str(ref_audio),
            ref_text=str(contexte.get("ref_text") or ""),
            autorisation=autorisation,
            usage=str(contexte.get("usage") or ""),
            langue=str(contexte.get("langue") or "fr"))
        return self._depuis(resultat, action="cloner", ref_audio=str(ref_audio))

    # --- Outils ---------------------------------------------------------------

    def _fichier_ecoutable(self, contexte: Dict[str, Any]) -> Optional[Path]:
        """Le premier media que la transcription sait ouvrir, ou None.

        L'inventaire vient de l'appelant, deja borne au dossier `media/` :
        cet agent n'explore aucun disque de lui-meme.
        """
        candidats = list(contexte.get("medias") or [])
        if contexte.get("video_path"):
            candidats.insert(0, str(contexte["video_path"]))
        for brut in candidats:
            chemin = Path(brut)
            if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS_ECOUTABLES:
                return chemin
        return None

    def _depuis(self, resultat: Any, action: str, **extra: Any) -> Dict[str, Any]:
        """Traduit un `ResultatAction` en reponse d'agent, sans l'adoucir."""
        statut = resultat.statut.value
        reponse: Dict[str, Any] = {
            "agent": self.name, "action": action,
            "response": resultat.message, **extra,
        }
        if statut == "SUCCESS":
            reponse["status"] = "success"
            reponse["preuve"] = resultat.preuve
            reponse.update(resultat.detail)
        elif statut in ("NOT_CONFIGURED", Statut.A_CONFIRMER.value):
            # Une capacite absente et une confirmation en attente sont des
            # etats, pas des erreurs : les presenter comme des echecs ferait
            # croire a une panne.
            reponse["status"] = "warning"
            reponse.update(resultat.detail)
        else:
            reponse["status"] = "error"
        return reponse

    def _erreur(self, message: str) -> Dict[str, Any]:
        return {"status": "error", "agent": self.name, "response": message}
