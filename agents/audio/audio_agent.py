"""L'agent audio : la parole et l'ecoute, dans le meme ARENA que le reste.

Le proprietaire ne dit pas « appelle le moteur de synthese ». Il dit « lis-moi
ce texte », « transcris cette video », « fais une voix off pour mon chantier »
— et depuis la mission Sesame CSM (DEC-0080), « fais parler deux personnages
qui discutent ». Cet agent traduit ces phrases en capacites de DEUX
connecteurs : `audio` (VoiceStudio, generaliste, multilingue) et `csm`
(Sesame CSM, conversation anglaise). **C'est ici, et nulle part ailleurs, que
les deux se rencontrent** — chaque connecteur reste ignorant de l'autre
(`core/connectors/audio_voix.py` et `core/connectors/csm.py` ne s'importent
jamais entre eux).

**Ce qu'il ne fait pas**, et qui est le sujet :

- Il **n'invente aucune transcription** et **ne simule aucune voix**.
  VoiceStudio eteint, moteur absent, modele non telecharge : il rapporte ce
  qui manque, avec le message exact de la machine. Meme regle pour CSM.
- Il **ne choisit pas un fichier de lui-meme**. Le chemin vient de l'appelant,
  qui l'a deja borne au dossier `media/` — meme discipline que le montage
  (`core/montage/planificateur.py`).
- Il **ne parle pas sans confirmation**. `parler` ecrit un fichier : le
  connecteur le fait passer par la file d'attente, comme le devis PDF.
- Il **ne fait jamais parler CSM avec un fichier de reference fourni**. La
  parole conversationnelle ne prend jamais de voix a cloner ici — voir
  `core/connectors/csm.py` pour pourquoi.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import Statut
from core.agent.base_agent import BaseAgent
from core.audio.routage_tts import ErreurDeMoteur, MoteurTTS, choisir
from core.connectors.audio_voix import usage_demande
from core.connectors.csm import IDENTIFIANT as CSM_IDENTIFIANT
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.audio")

CONNECTEUR = "audio"
CONNECTEUR_CSM = "csm"

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

#: Ce qui demande une parole CONVERSATIONNELLE (mission Sesame CSM, DEC-0080).
#: Teste avant PARLER : "genere une conversation" contient "genere une voix"
#: n'apparait pas, mais un futur mot-cle PARLER pourrait chevaucher — l'ordre
#: dans `genre_de_demande` tranche, pas la liste elle-meme.
CONVERSATION = (
    "conversation entre", "dialogue entre", "discussion entre",
    "fais parler deux", "fais dialoguer", "genere une conversation",
    "génère une conversation", "conversation naturelle",
)

#: Les extensions qu'un moteur de transcription sait ouvrir. ffmpeg tire la
#: piste audio d'une video, donc les conteneurs video en font partie.
EXTENSIONS_ECOUTABLES = frozenset({
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
})


def genre_de_demande(phrase: str) -> str:
    """`ecouter`, `cloner`, `dialogue`, `parler` ou `moteurs` — sans modele.

    Le repli par mots-cles reste le SEUL classificateur quand Ollama est
    eteint, et ces cinq cas se distinguent sans modele. `dialogue` est teste
    avant `parler` : "genere une conversation" ne doit pas retomber sur la
    lecture simple.
    """
    texte = (phrase or "").lower()
    if any(mot in texte for mot in ECOUTER):
        return "ecouter"
    if any(mot in texte for mot in CLONER):
        return "cloner"
    if any(mot in texte for mot in CONVERSATION):
        return "dialogue"
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
        # Un appelant PROGRAMMATIQUE (le pipeline video, `_appeler_narration`)
        # sait deja que c'est une conversation : il le declare dans le
        # contexte plutot que de devoir formuler une phrase magique. Ne
        # prevaut jamais sur "ecouter"/"cloner" : ce sont des actions sur un
        # fichier existant, jamais une simple variante de la parole.
        if bool(contexte.get("conversationnel")) and genre in ("parler", "moteurs"):
            genre = "dialogue"
        if genre == "ecouter":
            return self._ecouter(user_input, contexte)
        if genre == "cloner":
            return self._cloner(user_input, contexte)
        if genre == "dialogue":
            return self._dialogue(user_input, contexte)
        if genre == "parler":
            return self._parler(user_input, contexte)
        return self._moteurs()

    # --- Les voies --------------------------------------------------------

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

    def _dialogue(self, phrase: str, contexte: Dict[str, Any]) -> Dict[str, Any]:
        """Parole CONVERSATIONNELLE : le routeur choisit entre CSM et VoiceStudio.

        **C'est ici, et nulle part ailleurs, que les moteurs des deux
        connecteurs se rencontrent** — ils s'ignorent l'un l'autre
        (`core/connectors/audio_voix.py`/`core/connectors/csm.py`). Le choix
        passe TOUJOURS par `core/audio/routage_tts.py::choisir`, jamais par un
        `if` code en dur : CSM n'est prefere que pour de l'anglais
        conversationnel (mission Sesame CSM §3/§4), et son absence
        (service eteint, HF non authentifie) fait simplement retomber le choix
        sur VoiceStudio, sans que l'appelant ait rien a faire de plus
        (mission §15 — repli propre).

        `contexte["conversation"]` ne porte que du texte + un identifiant de
        locuteur par tour deja echange — jamais un fichier audio : voir
        `core/connectors/csm.py` pour pourquoi aucun chemin ne peut y entrer.
        """
        texte = str(contexte.get("texte") or "").strip() or texte_a_lire(phrase)
        if not texte:
            return self._erreur(
                "Dis-moi ce que ce dialogue doit dire : je ne devine pas le texte.")

        # CSM n'a qu'une vraie force : l'anglais. Un appelant qui ne precise
        # rien obtient donc l'anglais par defaut ICI — pas dans le routeur,
        # qui reste agnostique de tout defaut applicatif.
        langue = str(contexte.get("langue") or "en")
        try:
            usage = usage_demande(str(contexte.get("usage") or ""))
        except ValueError as erreur:
            return self._erreur(str(erreur))

        tours = [t for t in (contexte.get("conversation") or []) if isinstance(t, dict)]

        try:
            choisi = choisir(self._moteurs_combines(), usage=usage, langue=langue,
                             conversationnel=True,
                             demande=str(contexte.get("moteur") or ""))
        except ErreurDeMoteur as erreur:
            return {"agent": self.name, "action": "dialogue", "status": "warning",
                    "response": str(erreur)}

        if choisi.identifiant == CSM_IDENTIFIANT:
            resultat = self.registre.executer(
                CONNECTEUR_CSM, "parler", texte=texte,
                speaker=int(contexte.get("speaker") or 0), conversation=tours,
                max_audio_length_ms=int(contexte.get("max_audio_length_ms") or 10_000))
        else:
            resultat = self.registre.executer(
                CONNECTEUR, "parler", texte=texte, langue=langue,
                voix=str(contexte.get("voix") or "default"),
                usage=str(contexte.get("usage") or ""), moteur=choisi.identifiant)

        return self._depuis(resultat, action="dialogue", texte_lu=texte,
                            moteur_choisi=choisi.identifiant)

    def _moteurs_combines(self) -> "List[MoteurTTS]":
        """Les moteurs des DEUX connecteurs, fusionnes pour un seul `choisir`.

        Un connecteur absent ou non configure n'ecarte que ses propres
        moteurs, jamais toute la liste — c'est exactement ce qui permet le
        repli de la mission §15.
        """
        combines: List[MoteurTTS] = []
        for connecteur in (CONNECTEUR, CONNECTEUR_CSM):
            combines.extend(self._moteurs_de(connecteur))
        return combines

    def _moteurs_de(self, connecteur: str) -> "List[MoteurTTS]":
        try:
            resultat = self.registre.executer(connecteur, "moteurs")
        except Exception:  # noqa: BLE001 — un connecteur en panne n'emporte pas l'autre
            logger.warning("connecteur %s injoignable pour la liste des moteurs", connecteur)
            return []
        if resultat.statut != Statut.SUCCES:
            return []
        moteurs = []
        for entree in (resultat.detail.get("voix") or []):
            identifiant = str(entree.get("id") or "").strip()
            if not identifiant:
                continue
            moteurs.append(MoteurTTS(
                identifiant=identifiant,
                # Deja filtre aux moteurs ACTIFS par chaque connecteur
                # (`_moteurs()` de audio_voix.py et de csm.py ne rendent que
                # ce qui repond vraiment) : redemander "disponible" ici
                # redeciderait ce qui est deja mesure.
                disponible=True,
                clonage=entree.get("clonage"),
                appareil=entree.get("appareil"),
                routage=entree.get("routage"),
                gpu_compatible=tuple(entree.get("gpu_compatible") or ())))
        return moteurs

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
