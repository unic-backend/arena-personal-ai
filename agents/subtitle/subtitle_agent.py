import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.video.subtitle_tool import SubtitleTool

logger = logging.getLogger("usman.agent.subtitle")

#: En dessous, la « correction » reecrit ce qui a ete dit (mesure : « de vie
#: du chantier » -> « devis du chantier » vaut 0,91).
SIMILARITE_MINIMALE = 0.6
LIGNE_NUMEROTEE = re.compile(r"^\s*\[(\d+)\]\s*(.+?)\s*$", re.MULTILINE)

class SubtitleAgent(BaseAgent):
    """Agent chargé de la correction contextuelle et de la génération des sous-titres CapCut/TikTok."""

    #: Comment l'agent se presente au registre (DEC-0145) : lu par la
    #: decouverte, jamais recopie dans une liste centrale.
    identifiant = "sous_titres"
    competences = ('sous-titres', 'correction orthographique', 'formatage de sous-titres')

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="SubtitleAgent",
            description="Agent de correction orthographique contextuelle et formatage de sous-titres CapCut/TikTok.",
            provider=provider,
            memory=memory
        )
        self.sub_tool = SubtitleTool()

    async def correct_words_contextually(
        self, words_or_segments: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
        """Corrige les homophones phonétiques (ex: 'de vie' -> 'devis').

        Rend `(donnees, corrigee, raison)`. `corrigee` n'est vrai que si la
        relecture du modele a ete APPLIQUEE ; sinon `raison` dit pourquoi.

        Deux mensonges successifs sont repares ici. Le 01/09/2026 : « corriges »
        annonce quand le modele etait injoignable. Le 28/09/2026 : en mode
        segments — le cas normal, Whisper rend des segments — la correction du
        modele etait jetee (seules les apostrophes etaient recollees), et en
        mode mots elle l'etait des que le nombre de mots changeait, soit
        exactement le cas vise (« de vie » -> « devis ») ; « corriges » etait
        annonce dans les deux cas.
        """
        if not words_or_segments:
            return [], False, "rien a corriger"
        if "word" in words_or_segments[0]:
            return await self._corriger_les_mots(words_or_segments)
        return await self._corriger_les_segments(words_or_segments)

    @staticmethod
    def _consigne(texte: str, par_ligne: bool) -> str:
        forme = ("Garde exactement les numéros de ligne [n] : une ligne corrigée par ligne reçue.\n"
                 if par_ligne else "Garde la même structure de phrase.\n")
        return (
            "Tu es un correcteur orthographique expert spécialisé dans la correction de transcriptions audio.\n"
            "Ta mission: Corriger les erreurs d'écoute phonétiques évidentes selon le sujet métier de la vidéo.\n"
            "Exemples fréquents: 'de vie' -> 'devis', 'en compétant' -> 'en compétent', 'plaqué' -> 'plaque'.\n"
            "Règles strictes:\n"
            "1. Ne rajoute AUCUNE explication ou commentaire.\n"
            f"2. {forme}"
            "3. N'ajoute aucun mot qui n'a pas été prononcé.\n"
            "4. Réponds UNIQUEMENT avec le texte corrigé.\n\n"
            f"Texte brut:\n{texte}\n"
            "Texte corrigé:"
        )

    @staticmethod
    def _proche(avant: str, apres: str) -> bool:
        """Une correction d'ecoute change quelques lettres, pas le propos.
        Au-dela, le modele a reecrit ce qui a ete dit : on n'applique pas."""
        return SequenceMatcher(None, avant.casefold(), apres.casefold()).ratio() >= SIMILARITE_MINIMALE

    async def _demander(self, prompt: str) -> Optional[str]:
        try:
            logger.info("Correction orthographique contextuelle via l'IA...")
            return (await self.provider.generate(prompt=prompt) or "").strip()
        except Exception as e:
            logger.warning(f"Impossible d'effectuer la correction contextuelle : {e}")
            return None

    async def _corriger_les_segments(
        self, segments: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
        lignes = [s.get("text", "") for s in segments]
        texte = "\n".join(f"[{i + 1}] {ligne}" for i, ligne in enumerate(lignes))
        reponse = await self._demander(self._consigne(texte, par_ligne=True))
        for seg in segments:
            seg["text"] = self.sub_tool.clean_french_text(seg.get("text", ""))
        if reponse is None:
            return segments, False, "le modèle n'a pas répondu"

        proposees = {int(n): t.strip() for n, t in LIGNE_NUMEROTEE.findall(reponse)}
        if not proposees and len(segments) == 1:
            proposees = {1: reponse}
        appliquees = 0
        for i, seg in enumerate(segments, start=1):
            proposition = proposees.get(i)
            if proposition and self._proche(seg["text"], proposition):
                seg["text"] = self.sub_tool.clean_french_text(proposition)
                appliquees += 1
        if not appliquees:
            return segments, False, "la correction proposée s'écartait du texte entendu"
        if appliquees < len(segments):
            logger.info("Correction appliquee a %d segment(s) sur %d.", appliquees, len(segments))
        return segments, True, None

    async def _corriger_les_mots(
        self, mots: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
        avant = [w.get("word", "") for w in mots]
        reponse = await self._demander(self._consigne(" ".join(avant), par_ligne=False))
        if reponse is None:
            return mots, False, "le modèle n'a pas répondu"
        apres = reponse.split()
        if not self._proche(" ".join(avant), " ".join(apres)):
            return mots, False, "la correction proposée s'écartait du texte entendu"

        # Alignement mot a mot : « de vie » -> « devis » remplace deux mots
        # par un, sur la duree des deux. Un mot ajoute n'a pas ete prononce :
        # il n'entre pas ; un mot retire l'a ete : il reste.
        corriges: List[Dict[str, Any]] = []
        for operation, i1, i2, j1, j2 in SequenceMatcher(None, avant, apres).get_opcodes():
            if operation == "replace":
                debut, fin = mots[i1].get("start", 0.0), mots[i2 - 1].get("end", 0.0)
                corriges += self.sub_tool.repartir_les_mots(apres[j1:j2], debut, fin)
            elif operation in ("equal", "delete"):
                corriges += mots[i1:i2]
        return corriges, True, None

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        words = context.get("words") if context else None
        segments = context.get("segments") if context else None
        video_name = context.get("video_name", "output") if context else "output"

        data_to_use = words if words else segments
        if not data_to_use:
            # Sans transcription, il n'y a RIEN a sous-titrer. Deux phrases
            # inventees (« Bienvenue sur Usman ») etaient posees ici et
            # produisaient un vrai fichier .ass annonce comme un succes : de
            # la reclame pouvait finir incrustee sur une video de chantier.
            # Une capacite sans matiere se rapporte, elle ne se simule pas.
            return {
                "status": "error",
                "agent": self.name,
                "response": ("❌ Aucune transcription fournie : je n'invente pas "
                             "de sous-titres. Transcris d'abord la vidéo."),
            }

        # 1. Correction orthographique par l'IA (Qwen 3.5)
        data_to_use, corrigee, raison = await self.correct_words_contextually(data_to_use)

        # 2. Génération des sous-titres .ass CapCut
        output_ass = Path("media/subtitles") / f"{video_name}.ass"
        ass_path = self.sub_tool.generate_capcut_ass(data_to_use, str(output_ass))

        etat = "corrigés et générés" if corrigee else f"générés SANS relecture ({raison})"
        return {
            "status": "success",
            "agent": self.name,
            "ass_path": ass_path,
            "srt_path": ass_path,
            "corrigee": corrigee,
            "response": f"✅ Sous-titres CapCut {etat} : {Path(ass_path).name}"
        }
