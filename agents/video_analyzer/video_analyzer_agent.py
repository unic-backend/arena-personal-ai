"""L'agent video : analyser un fichier, suivre une generation, planifier une scene.

Trois choses, qui ne se ressemblent pas :

- **analyser** une video deja posee sur le disque — extraction audio,
  transcription locale, lecture par le modele ;
- **suivre** une generation lancee sur WanGP, qui dure des minutes et dont le
  proprietaire devrait autrement redemander l'etat ;
- **planifier** une scene precise : auditer son prompt avant de le confier a
  WanGP, pour ne pas depenser la carte graphique sur un prompt structurellement
  incomplet (DEC-0015, methode extraite de Hell-Grind-AIGC-Skill).

Le suivi est branche **ici**, et nulle part ailleurs : ce qui touche a la video
va a l'agent video. Trois regles le tiennent :

1. **Le chat n'attend pas.** Le suivi part dans la file de travaux de fond
   (`core/execution/travaux.py`) ; la conversation continue pendant que la carte
   graphique travaille.
2. **Rien n'est estime.** La progression vient de WanGP, ou elle vaut `None`.
   L'identifiant de la generation vient du journal des actions, la ou WanGP l'a
   depose comme preuve — jamais d'une phrase.
3. **Une capacite absente se rapporte.** Sans connecteur branche, ou avec WanGP
   eteint, la reponse est `NOT_CONFIGURED` avec ce qui manque. Aucun etat n'est
   simule.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.actions.journal import JournalDesActions
from core.actions.resultat import Statut
from core.agent.base_agent import BaseAgent
from core.connectors.base import EtatSante
from core.connectors.registre import RegistreConnecteurs
from core.connectors.suivi_video import suivre_en_fond
from core.execution.travaux import EtatTravail, FileDeTravaux, Travail
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.audio.transcription_tool import TranscriptionTool
from tools.video.ffmpeg_tool import FFmpegTool
from tools.video.prompt_audit import auditer_prompt

logger = logging.getLogger("usman.agent.video_analyzer")

#: Les deux generateurs video declares dans le cablage, et ce qu'ils font.
#: MoneyPrinterTurbo fabrique une video COMPLETE a partir d'un sujet — script,
#: plans, voix, sous-titres, montage. WanGP fabrique des IMAGES a partir d'une
#: description. Ce ne sont pas deux facons de faire la meme chose.
CONNECTEUR_SUJET = "moneyprinter"
CONNECTEUR_SCENE = "wan2gp"
CONNECTEURS_VIDEO = (CONNECTEUR_SUJET, CONNECTEUR_SCENE)

#: Ce qui demande de FABRIQUER une video sur un sujet. Le sujet lui-meme est ce
#: qui reste de la phrase une fois cette demande retiree — il n'est jamais
#: invente : sans sujet, rien n'est lance.
DEMANDE_DE_GENERATION = re.compile(
    r"^\s*(?:est-ce que tu peux |peux-tu |tu peux |j'?ai besoin d'?une |il me faut une )?"
    r"(?:fais|fabrique|cr[ée]e|cree|g[ée]n[éèe]re|genere|monte|prepare|pr[ée]pare)"
    r"(?:[- ]moi)?\s+(?:un |une |le |la |ce |cette )?(?:petit |petite |court |courte )?"
    r"(?:vid[ée]o|short|reel)\s*(?:courte |verticale )?"
    r"(?:sur|a propos de|à propos de|de|pour|qui parle de)?\s*",
    re.IGNORECASE)

#: Ce qui demande OU EN EST une generation, et non l'analyse d'un fichier.
#: « analyse cette video » veut un fichier ; « ou en est ma video ? » veut un
#: etat. Reclamer un chemin a la seconde question, c'est repondre a cote.
DEMANDE_DE_SUIVI = re.compile(
    r"(o[uù]\s+en\s+est"
    r"|avancement"
    r"|est[- ]?(?:ce\s+qu[’']?)?elle\s+(?:est\s+)?(?:pr[eê]te|finie|termin[ée]e)"
    r"|(?:c[’']est|elle\s+est)\s+(?:pr[eê]t[e]?|fini[e]?|termin[ée]e?)"
    r"|(?:ma|la|mon|le)\s+g[ée]n[ée]ration"
    r"|g[ée]n[ée]ration\s+(?:video|vid[ée]o))",
    re.IGNORECASE,
)

#: Le nom sous lequel un suivi entre dans la file. L'identifiant de la tache y
#: figure : c'est ainsi qu'on retrouve un suivi deja en cours, sans tenir un
#: second registre qui pourrait diverger de la file.
PREFIXE_SUIVI = "suivi de la generation"


def demande_de_suivi(texte: str) -> bool:
    """Dit si la phrase demande ou en est une generation video."""
    return bool(DEMANDE_DE_SUIVI.search(texte or ""))


#: Ce qui demande de PREPARER le prompt d'une scene precise pour WanGP —
#: distinct de FABRIQUER_VIDEO : celui-la fabrique une video COMPLETE sur un
#: sujet (MoneyPrinterTurbo, aucun audit de prompt) ; celui-ci envoie une
#: SCENE/un PLAN a WanGP, apres verification structurelle du prompt. Teste
#: AVANT `sujet_de` : « prepare » est un verbe partage par les deux demandes,
#: et celle-ci est la plus specifique des deux.
DEMANDE_DE_PLAN = re.compile(
    r"^\s*(?:est-ce que tu peux |peux-tu |tu peux |j'?ai besoin d'?(?:un |une )?)?"
    r"(?:"
    r"(?:pr[ée]pare|[ée]cris|envoie|g[ée]n[èe]re)(?:[- ]moi)?\s+(?:le |un |ce )?"
    r"prompt\s+(?:de|pour)\s+(?:cette |la |ce )?(?:sc[èe]ne|plan)"
    r"|storyboard"
    r"|plan de tournage"
    r"|d[ée]coupe(?:[- ]la|(?: cette)? sc[èe]ne)? en plans"
    r")\s*(?::|sur|a propos de|à propos de)?\s*",
    re.IGNORECASE)


def description_de_plan(texte: str) -> Optional[str]:
    """La description d'une scene a auditer puis confier a WanGP, ou `None`.

    Meme discipline que `sujet_de` : ce qui reste de la phrase une fois la
    demande retiree, jamais complete ni reformule.
    """
    texte = (texte or "").strip()
    correspondance = DEMANDE_DE_PLAN.match(texte)
    if correspondance is None:
        return None
    return texte[correspondance.end():].strip(" .?!,;:")


def sujet_de(texte: str) -> Optional[str]:
    """Le sujet d'une demande de video, ou `None` si la phrase n'en demande pas.

    Le sujet est ce qui RESTE de sa phrase une fois la demande retiree :
    « fais-moi une video sur les cloisons BA13 » laisse « les cloisons BA13 ».
    Rien n'est complete ni reformule — un sujet invente produirait une video sur
    autre chose que ce qu'il a demande. Une demande sans sujet rend une chaine
    vide, et l'appelant demande de quoi il s'agit.
    """
    texte = (texte or "").strip()
    correspondance = DEMANDE_DE_GENERATION.match(texte)
    if correspondance is None:
        return None
    return texte[correspondance.end():].strip(" .?!,;:")


class VideoAnalyzerAgent(BaseAgent):
    """Agent charge de transcrire, d'analyser, et de suivre ce qui se genere."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 registre: Optional[RegistreConnecteurs] = None,
                 travaux: Optional[FileDeTravaux] = None,
                 journal: Optional[JournalDesActions] = None):
        super().__init__(
            name="VideoAnalyzerAgent",
            description="Agent d'analyse de contenu vidéo et de suivi des générations.",
            provider=provider,
            memory=memory
        )
        self.ffmpeg = FFmpegTool()
        self.transcriber = TranscriptionTool(model_size="tiny")
        # Sans registre, sans file ou sans journal, l'agent analyse encore mais
        # ne suit rien. C'est un etat annonce dans la reponse, pas un silence.
        self.registre = registre
        self.travaux = travaux
        self.journal = journal

    # --- Suivi d'une generation -------------------------------------------------

    def derniere_generation(self) -> Tuple[str, str]:
        """La derniere generation acceptee, et par QUEL generateur.

        Elle est lue dans le journal des actions, la ou le connecteur a depose
        son identifiant comme preuve. Les deux generateurs y ecrivent : on prend
        la plus recente des deux, et on retient lequel l'a produite — suivre une
        tache MoneyPrinter chez WanGP ne rendrait rien.

        Returns:
            `(identifiant, connecteur)`, ou `("", "")` quand il n'y a rien a
            suivre. Aucune tache n'est inventee.
        """
        if self.journal is None:
            return "", ""
        candidates = []
        for connecteur in CONNECTEURS_VIDEO:
            for action in self.journal.dernieres(limite=50, cible=connecteur):
                if (action.action == "generer" and action.resultat == Statut.SUCCES.value
                        and action.preuve):
                    candidates.append((action.horodatage, str(action.preuve), connecteur))
                    break
        if not candidates:
            return "", ""
        _, identifiant, connecteur = max(candidates)
        return identifiant, connecteur

    def _suivi_deja_en_cours(self, job_id: str) -> Optional[Travail]:
        """Le travail qui suit deja cette tache, s'il y en a un.

        Sans cela, chaque « ou en est ma video ? » ouvrirait un suivi de plus sur
        la meme generation.
        """
        if self.travaux is None:
            return None
        nom = f"{PREFIXE_SUIVI} {job_id}"
        for travail in self.travaux.inventaire():
            if travail.nom == nom:
                return travail
        return None

    @staticmethod
    def _rapport(travail: Travail, job_id: str) -> Dict[str, Any]:
        """Ce que la file sait du suivi, et rien de plus.

        `progression` vaut `None` tant que WanGP n'a pas annonce de total : une
        barre a 0 % se lirait « rien n'avance », ce qui est une autre phrase.
        """
        suivi = travail.resultat
        fichiers = [str(chemin) for chemin in (getattr(suivi, "fichiers", None) or [])]
        progression = travail.progression
        avancement = ("avancement encore inconnu" if progression is None
                      else f"{progression * 100:.0f} % des taches annoncees par WanGP")

        if travail.etat in (EtatTravail.EN_ATTENTE, EtatTravail.EN_COURS):
            message = (f"La generation {job_id} tourne toujours ({avancement}). "
                       "Je la suis en fond : tu peux continuer a me parler.")
        elif travail.etat is EtatTravail.ANNULE:
            message = f"Le suivi de la generation {job_id} a ete annule."
        elif travail.etat is EtatTravail.ECHOUE:
            message = f"Le suivi de la generation {job_id} s'est arrete : {travail.raison}"
        elif getattr(suivi, "reussi", False):
            message = (f"La video est prete : {', '.join(fichiers)}." if fichiers
                       else f"WanGP annonce la generation {job_id} terminee, sans nommer "
                            "de fichier.")
        else:
            raison = getattr(suivi, "raison", "") or "raison non rapportee par WanGP"
            message = f"La generation {job_id} n'a pas abouti : {raison}"

        return {
            "statut": travail.etat.value,
            "job_id": job_id,
            "travail": travail.identifiant,
            "progression": progression,
            "fichiers": fichiers,
            "message": message,
        }

    async def suivre_la_generation(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Repond « ou en est ma video ? », et lance le suivi si personne ne suit.

        Args:
            job_id: la tache a suivre. Absente, elle est lue dans le journal.

        Returns:
            Un compte-rendu. `NOT_CONFIGURED` quand la capacite manque, avec ce
            qui manque et la commande qui l'obtient.
        """
        if self.registre is None or self.travaux is None:
            return {"statut": Statut.NON_CONFIGURE.value, "job_id": job_id or "",
                    "message": ("Je peux analyser une video, pas suivre une generation : "
                                "aucun connecteur video n'est branche sur cet agent.")}

        connecteur_nom = CONNECTEUR_SUJET
        if job_id:
            job_id = job_id.strip()
        else:
            job_id, connecteur_nom = self.derniere_generation()
            connecteur_nom = connecteur_nom or CONNECTEUR_SUJET
        if not job_id:
            return {"statut": "AUCUNE", "job_id": "",
                    "message": ("Aucune generation video n'a ete lancee : je n'ai rien a "
                                "suivre. Demande-m'en une, et je la suis jusqu'au fichier.")}

        deja = self._suivi_deja_en_cours(job_id)
        if deja is not None:
            return self._rapport(deja, job_id)

        # La sonde ouvre une connexion : dans un fil separe, sinon elle gele la
        # boucle — et avec elle toutes les autres conversations.
        sante = await asyncio.to_thread(self.registre.sante, connecteur_nom)
        if sante.etat is not EtatSante.OPERATIONNEL:
            return {"statut": Statut.NON_CONFIGURE.value, "job_id": job_id,
                    "message": " ".join(part for part in (sante.message, sante.ce_qui_manque)
                                        if part)}

        connecteur = self.registre.obtenir(connecteur_nom)
        travail = suivre_en_fond(connecteur, self.travaux, job_id,
                                 nom=f"{PREFIXE_SUIVI} {job_id}")
        logger.info("Suivi de la generation %s ouvert (travail %s).",
                    job_id, travail.identifiant)
        return {"statut": travail.etat.value, "job_id": job_id,
                "travail": travail.identifiant, "progression": travail.progression,
                "fichiers": [],
                "message": (f"Je suis la generation {job_id} en fond et je te dis des "
                            "que le fichier est la. Le chat ne l'attend pas.")}

    # --- Fabriquer une video ----------------------------------------------------

    def fabriquer(self, sujet: str) -> Dict[str, Any]:
        """Soumet la fabrication d'une video sur un sujet. **Rien ne part ici.**

        `generer` porte `action="generate"`, que la politique classe en
        CONFIRMATION : une generation occupe la carte graphique plusieurs
        minutes, et c'est lui qui decide de la depenser.

        Un sujet vide n'est jamais complete : on demande de quoi il s'agit.
        """
        if self.registre is None:
            return {"statut": Statut.NON_CONFIGURE.value, "sujet": sujet,
                    "message": ("Je peux analyser une video, pas en fabriquer : aucun "
                                "generateur n'est branche sur cet agent.")}
        if not sujet:
            return {"statut": "INCOMPLET", "sujet": "",
                    "message": ("Sur quoi ? Dis-moi le sujet de la video : je ne le "
                                "devine pas.")}

        resultat = self.registre.executer(CONNECTEUR_SUJET, "generer", sujet=sujet)
        return {"statut": resultat.statut.value, "sujet": sujet,
                "message": resultat.message, "preuve": resultat.preuve}

    # --- Planifier une scene (audit puis WanGP) ---------------------------------

    def planifier_scene(self, description: str) -> Dict[str, Any]:
        """Audite le prompt d'une scene, et ne l'envoie a WanGP que s'il est pret.

        Une generation WanGP occupe la carte graphique plusieurs minutes : un
        prompt sans sujet, sans duree ou sans etat final de camera la depense
        pour un resultat qu'il faudra recommencer. L'audit (voir
        `tools/video/prompt_audit.py`) est deterministe et local — aucun
        reseau, aucun modele appele avant d'avoir un prompt structurellement
        complet.

        Args:
            description: le prompt de la scene, tel qu'il partirait vers WanGP.

        Returns:
            `A_COMPLETER` avec l'audit et les problemes bloquants si le prompt
            n'est pas pret ; sinon le resultat de l'appel a WanGP, avec l'audit
            joint comme preuve qu'il a ete verifie avant l'envoi.
        """
        if self.registre is None:
            return {"statut": Statut.NON_CONFIGURE.value, "description": description,
                    "message": ("Je peux analyser une video, pas planifier une scene : "
                                "aucun generateur n'est branche sur cet agent.")}
        if not description:
            return {"statut": "INCOMPLET", "description": "",
                    "message": ("Decris la scene : sujet, duree, etat final de camera "
                                "et ambiance sonore. Je ne l'invente pas.")}

        audit = auditer_prompt(description, support="video")
        if not audit.pret:
            erreurs = [p.message for p in audit.problemes if p.gravite == "erreur"]
            return {"statut": "A_COMPLETER", "description": description,
                    "audit": audit.to_dict(),
                    "message": (f"Ce prompt n'est pas encore pret pour WanGP "
                                f"({len(erreurs)} probleme(s) bloquant(s)) : "
                                + " ".join(erreurs))}

        resultat = self.registre.executer(CONNECTEUR_SCENE, "generer", source=description)
        return {"statut": resultat.statut.value, "description": description,
                "audit": audit.to_dict(), "message": resultat.message,
                "preuve": resultat.preuve}

    # --- Analyse d'un fichier ---------------------------------------------------

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contexte = context or {}
        job_id = contexte.get("job_id")

        # Planifier une scene : teste AVANT la fabrication, « prepare » est un
        # verbe partage par les deux et celle-ci est la plus specifique.
        plan = description_de_plan(user_input) if not job_id else None
        if plan is not None:
            planification = await asyncio.to_thread(self.planifier_scene, plan)
            return {
                "status": "warning" if planification["statut"] in (
                    Statut.NON_CONFIGURE.value, "INCOMPLET", "A_COMPLETER") else "success",
                "agent": self.name,
                "planification": planification,
                "suivi": None,
                "response": planification["message"],
            }

        # Fabriquer une video : soumis a confirmation, jamais lance d'autorite.
        sujet = sujet_de(user_input) if not job_id else None
        if sujet is not None:
            fabrication = await asyncio.to_thread(self.fabriquer, sujet)
            return {
                "status": "warning" if fabrication["statut"] in (
                    Statut.NON_CONFIGURE.value, "INCOMPLET") else "success",
                "agent": self.name,
                "fabrication": fabrication,
                "suivi": None,
                "response": fabrication["message"],
            }

        # Une question sur l'etat d'une generation ne demande aucun fichier.
        if job_id or demande_de_suivi(user_input):
            suivi = await self.suivre_la_generation(job_id)
            return {
                "status": "warning" if suivi["statut"] == Statut.NON_CONFIGURE.value
                          else "success",
                "agent": self.name,
                "suivi": suivi,
                "response": suivi["message"],
            }

        video_path = contexte.get("video_path")

        if not video_path or not Path(video_path).exists():
            return {
                "status": "error",
                "agent": self.name,
                "response": "❌ Aucune vidéo valide fournie pour l'analyse."
            }

        video_file = Path(video_path)
        audio_output = video_file.parent / f"{video_file.stem}_extracted.wav"

        # 1. Extraction Audio avec FFmpeg
        logger.info(f"Extraction audio de {video_file.name}...")
        extracted = self.ffmpeg.extract_audio(str(video_file), str(audio_output))
        if not extracted:
            return {
                "status": "error",
                "agent": self.name,
                "response": "❌ Échec de l'extraction audio via FFmpeg."
            }

        # 2. Transcription locale avec Whisper
        logger.info("Transcription audio via Whisper...")
        transcription_res = self.transcriber.transcribe(str(audio_output))
        full_text = transcription_res.get("full_text", "")

        # 3. Analyse du contenu par Qwen 3.5
        prompt = f"""Tu es un expert en analyse vidéo. Analyse la transcription suivante et propose :
1. Un résumé concis du contenu.
2. Les thèmes principaux abordés.
3. Une note de potentiel pour en faire un extrait court (Short/TikTok) de 0 à 10.

Transcription: "{full_text}"
Analyse:"""

        ai_analysis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "video_name": video_file.name,
            "duration": transcription_res.get("duration"),
            "transcription": full_text,
            "segments": transcription_res.get("segments"),
            "ai_analysis": ai_analysis.strip(),
            # Aucune generation suivie sur ce chemin : `None`, jamais un etat
            # invente pour remplir le champ.
            "suivi": None,
        }
