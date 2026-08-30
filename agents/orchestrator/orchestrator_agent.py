import datetime
import logging
import re
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.execution.voies import budget_de, voie_pour
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.orchestrator")

# Les espaces de la PWA (VOLET « espaces separes »). Chaque espace choisi
# dans l'interface route DIRECTEMENT vers son agent — sans appeler le modele
# classeur, qui ne fait alors que deviner ce que l'utilisateur a deja dit en
# choisissant son espace. `null` (Usman general) n'a pas d'entree ici : sans
# espace choisi, le classement habituel s'applique, inchange.
#
# Les deux controles determinstes (question personnelle, controle date)
# passent AVANT cette table, dans `analyze_intent` : choisir "UniC Plaquiste"
# ne doit pas empecher de reconnaitre "qui suis-je" ou une question d'actualite,
# que l'espace ne peut pas deviner mieux qu'une phrase ordinaire.
INTENTION_PAR_ESPACE = {
    "code": "CODE_EXECUTION",
    "plaquiste": "PLAQUISTE",
    "video": "VIDEO_ANALYSIS",
    "web": "FRESH_INFO",
    "documents": "RAG_DOCS",
}

# Liste fermée : toute réponse du modèle hors de cet ensemble est rejetée.
INTENTIONS = {
    "CHAT",
    "CODE_EXECUTION",
    "FRESH_INFO",
    "STUDIO",
    "PLAQUISTE",
    "BROWSER",
    "SWE_FIX",
    "REPO_ENGINEERING",
    "RAG_DOCS",
    "GRAPHRAG",
    "DEEP_REASONING",
    "DEEP_RESEARCH",
    "TREND_SEARCH",
    "VIDEO_ANALYSIS",
    "EMAIL",
    "SOCIAL",
    "VISION",
}

#: Ce qui parle de ses RESEAUX SOCIAUX. Teste avant le metier : « une
#: publication sur mon chantier » contient « chantier » et partirait chez
#: l assistant devis, qui n a jamais su ecrire pour LinkedIn.
RESEAUX = (
    "publication", "publications", "post linkedin", "un post", "mes posts",
    "sur linkedin", "sur instagram", "sur facebook", "reseaux sociaux",
    "réseaux sociaux", "mon profil linkedin", "accroche", "accroches",
    "idees de contenu", "idées de contenu", "ma voix", "mon style d'ecriture",
    "carrousel", "un reel", "miniature youtube",
)

#: Ce qui parle de SON AGENDA, sans ambiguite possible. Teste avant tout le
#: reste : « suis-je libre cette semaine ? » contient « cette semaine », qui est
#: un mot d actualite — la question porte pourtant sur ses chantiers, pas sur
#: les nouvelles du monde. Son agenda est son metier : il va a l assistant
#: metier, qui connait ses chantiers.
AGENDA = (
    "suis-je libre", "suis je libre", "mon agenda", "dans mon agenda",
    "quand puis-je", "quand est-ce que je peux", "creneau", "créneau",
    "creneaux", "créneaux", "mes disponibilites", "mes disponibilités",
)

#: Ce qui parle de SA BOITE, et non d une lettre a ecrire. La difference n est
#: pas un detail : « ecris un mail au client pour le chantier de Diamniadio »
#: appartient a l assistant metier, qui connait la grille de prix et
#: l entreprise — un test du proprietaire le tient depuis le 27/08. Ces
#: formulations-ci designent le courrier RECU, celui qu il faut ouvrir.
COURRIER = (
    "mes mails", "mes e-mails", "mes emails", "mon courrier", "ma boite mail",
    "ma boîte mail", "du courrier", "boite de reception", "boîte de réception",
    "reponds a ce mail", "réponds à ce mail", "reponds a ce message",
    "réponds à ce message", "j'ai recu un mail", "j'ai reçu un mail",
    "nouveaux messages", "mes messages recus", "mes messages reçus",
)

#: Fabriquer une video sur un sujet. Teste AVANT le metier, pour la meme raison
#: que le suivi : « fais-moi une video sur les cloisons BA13 » contient « ba13 »
#: et partait chez l assistant devis, qui n a jamais su faire une video.
FABRIQUER_VIDEO = (
    "fais-moi une vidéo", "fais moi une video", "fais-moi une video",
    "fais moi une vidéo", "génère une vidéo", "genere une video",
    "crée une vidéo", "cree une video", "fabrique une vidéo",
    "fabrique une video", "monte une vidéo", "monte une video",
    "fais-moi un short", "fais moi un short", "crée un short", "cree un short",
    "génère un short", "genere un short",
)

#: Analyser une IMAGE — une photo, un plan, une capture d ecran. Distinct de
#: RAG_DOCS (texte deja indexe) et de VIDEO_ANALYSIS (fichier video) : une
#: image est comprise directement par le modele de vision (DEC-0019), jamais
#: par extraction de texte. Teste tot : « analyse cette photo du chantier »
#: contient « chantier » et partirait sinon chez l assistant devis.
VISION = (
    "analyse cette image", "analyse cette photo", "que montre cette image",
    "que montre cette photo", "que vois-tu sur cette image",
    "qu'est-ce qu'il y a sur cette photo", "qu'est ce qu'il y a sur cette photo",
    "lis le texte de cette image", "lis ce qui est ecrit", "lis ce qui est écrit",
    "extrait le tableau de cette image", "cette capture d'ecran",
    "cette capture d'écran", "ce screenshot", "analyse ce plan de construction",
    "analyse ce dessin", "analyse ce schema", "analyse ce schéma",
    "decris cette image", "décris cette image", "decris cette photo",
    "décris cette photo", "analyse ce document scanne", "analyse ce document scanné",
)

#: Preparer le prompt d une scene precise pour WanGP — distinct de FABRIQUER_VIDEO,
#: qui fabrique une video COMPLETE sur un sujet (MoneyPrinterTurbo, aucun audit).
#: Teste AVANT FABRIQUER_VIDEO : « prepare » est un verbe partage par les deux.
PLANIFIER_SCENE = (
    "prépare le prompt", "prepare le prompt", "écris le prompt", "ecris le prompt",
    "storyboard", "plan de tournage", "découpe en plans", "decoupe en plans",
)

#: « Ou en est ma video ? » n est pas une analyse de fichier : c est le suivi d une
#: generation lancee sur la carte graphique. Meme agent, autre travail — et teste
#: avant le metier, parce que « la video du chantier » contient « chantier ».
SUIVI_VIDEO = (
    "où en est ma vidéo", "ou en est ma video", "où en est la vidéo",
    "ou en est la video", "où en est ta vidéo", "où en est la génération",
    "ou en est la generation", "ma génération vidéo", "ma generation video",
    "génération vidéo", "generation video", "avancement de la vidéo",
    "avancement de la video",
)

# --- Contrôle daté, évalué AVANT le modèle -------------------------------------
# Le tri d'intention est fait par un modèle. Or un modèle dont les connaissances
# s'arrêtent avant l'année en cours ne peut pas reconnaître qu'une question porte
# sur son propre futur : « qui a gagné la coupe du monde 2026 » lui paraît être
# une conversation ordinaire, et il répond de mémoire. Mesuré le 2026-08-26 sur
# la machine du propriétaire — la réponse a été « je n'ai pas les informations
# récentes », alors que le pipeline d'information fraîche existait pour cela.
#
# La date du système, elle, ne se trompe pas. Ce contrôle est donc déterministe
# et passe avant toute question posée au modèle.

# Questions sur l utilisateur ou sur Usman lui-meme. La reponse est dans la
# memoire du systeme, jamais sur Internet.
#
# Mesure du 2026-08-26 : « qui suis-je » a ete classee FRESH_INFO par le modele
# classeur, donc envoyee sur le web. Reponse obtenue : « les sources ne
# contiennent aucune information qui reponde a la question », apres ~30 s. Le
# modele n a pas tort de se tromper — il devine ; c est de lui demander de
# deviner sur ce point qui est l erreur.
QUESTIONS_PERSONNELLES = (
    "qui suis-je", "qui suis je", "qui suije",
    "je suis qui", "c'est qui moi",
    "qui es-tu", "qui es tu", "tu es qui", "t'es qui",
    "mon nom", "ton nom", "comment je m'appelle", "comment je m appelle",
    "comment tu t'appelles", "comment tu t appelles",
)


# Salutations pures — jamais suffisantes pour declencher un agent specialise.
#
# Mesure le 30/08/2026, sur le serveur en ligne, apres la phase 2 (routage
# direct par espace) : un simple « bonjour » envoye depuis l'espace UniC
# Plaquiste forcait PLAQUISTE, et PlaquisteAgent — qui n'a qu'un mode, ecrire
# un devis — a redige un email de cloture complet avec une reference et des
# details de client fabriques, pour une phrase qui n'en demandait aucun. Sa
# regle absolue (« n'invente jamais un prix ») ne dit rien de « n'invente
# jamais un devis » quand rien n'en a demande un.
#
# Avant le routage par espace, « bonjour » retombait sur CHAT par le
# classement habituel — cette regression est celle du routage direct, pas de
# PlaquisteAgent lui-meme, qu'on se garde de modifier ici pour un defaut qui
# n'est pas le sien.
SALUTATIONS_PURES = (
    "bonjour", "bonsoir", "salut", "coucou", "hello", "hi", "yo",
    "merci", "ça va", "ca va", "ça va ?", "ca va ?",
    "comment vas-tu", "comment vas tu", "comment allez-vous", "comment allez vous",
)


ANNEE = re.compile(r"\b(19|20)\d{2}\b")

# Formulations qui portent sur un état ou un résultat courant. Elles ne
# déclenchent la vérification que si aucune année passée n'est citée : « qui a
# gagné la coupe du monde 1998 » est un fait acquis, pas une actualité.
FORMULATIONS_COURANTES = (
    # Résultats et compétitions
    "qui a gagné", "qui a gagne", "qui a remporté", "qui a remporte",
    "vainqueur", "gagnant", "résultat", "resultat", "score",
    "coupe du monde", "meilleur joueur", "championnat",
    # États et responsables du moment
    "qui est le", "qui est la", "qui sont les",
    "en ce moment", "actuellement", "aujourd'hui", "cette semaine",
    # Chiffres qui bougent
    "population", "combien coûte", "combien coute", "prix de", "cours de",
    # Versions et actualité
    "dernière version", "derniere version", "dernier modèle", "dernier modele",
    "actualité", "actualite", "dernières nouvelles", "dernieres nouvelles",
    # Demande explicite de l'utilisateur : elle prime toujours
    "cherche sur le web", "cherche sur internet",
)


PROMPT_CLASSIFICATION = """Tu es un classifieur d'intention. Tu ne réponds jamais à la demande.
Choisis UNE seule étiquette parmi cette liste, et réponds UNIQUEMENT par cette étiquette :

CHAT            : conversation, question générale, explication, avis.
FRESH_INFO      : question dont la réponse a pu changer récemment — actualité,
                  dernière version d'un logiciel, prix, résultat, qui occupe un poste,
                  météo, cours, événement en cours. Tout ce qui demande de vérifier.
CODE_EXECUTION  : écrire ou exécuter du code, un script, un programme.
DEEP_REASONING  : résoudre un problème mathématique ou une démonstration.
DEEP_RESEARCH   : produire une étude, un rapport documenté, une recherche approfondie.
TREND_SEARCH    : chercher des tendances ou des idées de contenu vidéo.
VIDEO_ANALYSIS  : analyser, découper ou reformater un fichier vidéo ; fabriquer
                  une vidéo ; suivre une génération ; préparer le prompt d'une scène.
EMAIL           : lire, trier ou répondre à son courrier.
SOCIAL          : écrire, relire ou préparer une publication pour ses réseaux.
PLAQUISTE       : metier du proprietaire — devis, facture, mail client,
                  argumentaire, planning de chantier, BA13, cloison, plafond.
STUDIO          : traiter une vidéo de bout en bout — vertical 9:16 et
                  sous-titres incrustés, en une seule demande.
BROWSER         : ouvrir un site, naviguer, remplir un formulaire.
SWE_FIX         : corriger un bug dans un fichier existant.
REPO_ENGINEERING: travailler sur plusieurs fichiers d'un dépôt à la fois.
RAG_DOCS        : répondre à partir des documents de l'utilisateur.
GRAPHRAG        : question sur les liens entre les documents.
VISION          : comprendre une image, une photo, un plan ou une capture
                  d'écran — décrire, lire un texte qui y figure (OCR),
                  extraire un tableau, analyser un dessin ou un schéma.

Attention : parler DE code, DE maths ou D'une erreur n'est pas demander d'en produire.
« Explique-moi le code de la route » est CHAT, pas CODE_EXECUTION.
Une question sur un fait qui peut avoir change depuis est FRESH_INFO, pas CHAT :
« Quelle est la derniere version de Python ? » demande de verifier, pas de se souvenir.

Demande : {demande}

Étiquette :"""

class OrchestratorAgent(BaseAgent):
    """Agent principal de décision et de routage universel."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="OrchestratorAgent",
            description="Agent principal de décision et de routage des tâches.",
            provider=provider,
            memory=memory
        )

    @staticmethod
    def exige_verification(user_input: str, aujourd_hui: Optional[datetime.date] = None) -> bool:
        """Dit si la question porte sur quelque chose que le modèle ne peut pas savoir.

        Deux cas, et un seul suffit :

        1. Une année **égale ou postérieure à l'année en cours** est citée. Aucun
           modèle déployé ne connaît l'issue de son propre futur.
        2. La question porte sur un état ou un résultat courant (« qui a gagné »,
           « dernière version », « prix de ») **et** ne cite aucune année passée.

        La date vient de l'horloge, jamais du modèle. `aujourd_hui` n'existe que
        pour que les tests fixent une date au lieu de dépendre du jour où ils
        tournent.
        """
        aujourd_hui = aujourd_hui or datetime.date.today()
        texte = user_input.lower()

        annees = [int(m.group()) for m in ANNEE.finditer(texte)]
        if any(annee >= aujourd_hui.year for annee in annees):
            return True

        if annees:  # une année est citée, et elle est passée : le fait est acquis
            return False

        return any(formulation in texte for formulation in FORMULATIONS_COURANTES)

    @staticmethod
    def question_personnelle(user_input: str) -> bool:
        """Dit si la question porte sur l utilisateur ou sur Usman lui-meme.

        Elle est evaluee avant tout le reste : ni le web ni le modele classeur
        n ont leur mot a dire sur l identite du proprietaire.
        """
        return any(motif in (user_input or "").lower() for motif in QUESTIONS_PERSONNELLES)

    @staticmethod
    def salutation_pure(user_input: str) -> bool:
        """Vrai seulement si la phrase ENTIERE n'est que la salutation.

        Un simple `in` prendrait « bonjour, peux-tu me faire un devis » pour
        une salutation — la ponctuation finale est retiree, rien d'autre.
        Deux `strip()` : « salut ! » laisse une espace en trop entre le retrait
        du « ! » et la comparaison, sans le second passage.
        """
        texte = (user_input or "").strip().lower().rstrip("!.?").strip()
        return texte in SALUTATIONS_PURES

    async def analyze_intent(self, user_input: str, espace: Optional[str] = None) -> str:
        """Détermine vers quel agent envoyer la demande.

        `espace` vient de la PWA : l'espace choisi dans la barre laterale
        (VOLET « espaces separes »). Un espace connu route directement vers
        son agent, sans appeler le modele classeur — l'utilisateur a deja dit
        ou il voulait aller en cliquant dessus.

        Trois controles determinstes passent avant l'espace, dans cet ordre :
        question personnelle, salutation pure, puis controle date. Aucun des
        trois ne coute rien, et chacun rattrape ce que l'espace ne peut pas
        savoir mieux qu'une phrase ordinaire — une salutation depuis « UniC
        Plaquiste » ne doit pas faire rediger un devis fabrique.

        Ensuite seulement l'espace, puis le modele. S'ils sont indisponibles ou
        repondent autre chose qu'une etiquette connue, on retombe sur les
        mots-cles — un repli moins fin, mais annonce dans les journaux plutot
        que silencieux.
        """
        if self.question_personnelle(user_input):
            logger.info("Question personnelle : reponse par la memoire, sans web ni classeur")
            return "CHAT"

        if self.salutation_pure(user_input):
            logger.info("Salutation pure : CHAT, quel que soit l'espace")
            return "CHAT"

        if self.exige_verification(user_input):
            logger.info("Contrôle daté : la question demande une vérification -> FRESH_INFO")
            return "FRESH_INFO"

        if espace and espace in INTENTION_PAR_ESPACE:
            logger.info("Espace %s choisi dans l'interface -> %s", espace, INTENTION_PAR_ESPACE[espace])
            return INTENTION_PAR_ESPACE[espace]

        intention = await self._classer_par_modele(user_input)
        if intention is not None:
            return intention

        logger.warning("Classification par le modèle indisponible : repli sur les mots-clés.")
        return self._classer_par_mots_cles(user_input)

    async def _classer_par_modele(self, user_input: str) -> Optional[str]:
        """Interroge le modèle rapide. Renvoie None si sa réponse n'est pas exploitable."""
        try:
            brut = await self.provider.generate(
                prompt=PROMPT_CLASSIFICATION.format(demande=user_input)
            )
        except Exception as e:
            logger.warning(f"Le modèle n'a pas pu classer la demande : {e}")
            return None

        # Le modèle bavarde parfois : on ne garde que le premier mot en majuscules
        # qui appartient à la liste fermée. Rien d'autre n'est accepté.
        for mot in brut.replace("\n", " ").replace("*", " ").replace("`", " ").split():
            candidat = mot.strip(".,:;!?\"'").upper()
            if candidat in INTENTIONS:
                return candidat

        logger.warning(f"Réponse de classification inexploitable : {brut[:80]!r}")
        return None

    def _classer_par_mots_cles(self, user_input: str) -> str:
        """Repli hors ligne : aiguillage par mots-clés, instantané mais approximatif."""
        text = user_input.lower()

        # Son agenda. Teste en premier : ces formulations ne veulent jamais dire
        # autre chose, et plusieurs contiennent des mots de temps qui les
        # enverraient chercher l actualite sur le web.
        if any(k in text for k in AGENDA):
            return "PLAQUISTE"

        # Information fraiche : la reponse a pu changer depuis l'entrainement du modele.
        fresh_keywords = [
            "dernière version", "derniere version", "dernier modèle", "dernier modele",
            "aujourd'hui", "en ce moment", "actuellement", "actualité", "actualite",
            "cette semaine", "ce mois-ci", "cette année", "cette annee",
            "prix actuel", "cours de", "météo", "meteo", "qui est le président",
            "qui est le president", "quoi de neuf", "dernières nouvelles",
            "dernieres nouvelles", "récemment", "recemment",
        ]
        if any(k in text for k in fresh_keywords):
            return "FRESH_INFO"

        # Trend Search UNIQUEMENT si demande explicite de vidéo/tendances
        if "idée de vidéo" in text or "tendance tiktok" in text or "sujet chaud" in text or "stratégie vidéo" in text:
            return "TREND_SEARCH"

        # Raisonnement profond & Maths complexes
        reasoning_keywords = ["équation", "equation", "résous", "resous", "matrice", "intégrale", "dérivée", "démontre", "démontrer", "calcul complexe", "preuve"]
        if any(k in text for k in reasoning_keywords):
            return "DEEP_REASONING"

        # Code & Programmation
        code_keywords = ["code", "python", "script", "fonction", "programme", "calcule", "factorielle", "fibonacci", "algorithme", "bug", "erreur", "écris un"]
        if any(k in text for k in code_keywords):
            return "CODE_EXECUTION"

        # Recherche Profonde
        research_keywords = ["étude complète", "rapport détaillé", "recherche approfondie", "étude de marché", "dossier complet"]
        if any(k in text for k in research_keywords):
            return "DEEP_RESEARCH"

        # Ses reseaux. Teste AVANT le metier, pour la meme raison que la video :
        # le sujet d une publication est souvent son metier.
        if any(k in text for k in RESEAUX):
            return "SOCIAL"

        # Le courrier. Teste AVANT le metier : « reponds au client par mail »
        # contient « client » sans etre une demande de devis.
        if any(k in text for k in COURRIER):
            return "EMAIL"

        # Analyser une image. Teste AVANT le metier : le sujet d une photo est
        # souvent le chantier lui-meme, sans etre une demande de devis.
        if any(k in text for k in VISION):
            return "VISION"

        # Planifier une scene. Teste AVANT FABRIQUER_VIDEO : « prepare » est un
        # verbe partage, et celle-ci est la demande la plus specifique des deux.
        if any(k in text for k in PLANIFIER_SCENE):
            return "VIDEO_ANALYSIS"

        # Fabriquer une video. Teste AVANT le metier : le sujet d une video est
        # souvent son metier, et la demande n en est pas une pour autant.
        if any(k in text for k in FABRIQUER_VIDEO):
            return "VIDEO_ANALYSIS"

        # Ou en est une generation video. Teste AVANT le metier : « ou en est la
        # video du chantier » contient « chantier » sans etre une demande de
        # devis. Ce qui touche a la video va a l agent video.
        if any(k in text for k in SUIVI_VIDEO):
            return "VIDEO_ANALYSIS"

        # Metier du proprietaire. Teste tot : « devis » et « chantier » sont
        # sans ambiguite chez lui, et ces demandes ne doivent jamais partir sur
        # le web ni chez un agent generaliste.
        if any(k in text for k in [
            "devis", "facture", "chantier", "ba13", "ba 13", "placo",
            "cloison", "faux plafond", "plaquiste", "client", "metre carre", "m2",
            # Planifier un chantier est du metier ; les formulations d agenda
            # sans ambiguite sont deja traitees plus haut (AGENDA).
            "planifie", "planifier", "disponibilite", "disponibilité",
        ]):
            return "PLAQUISTE"

        # Capacites autrefois joignables uniquement en choisissant leur nom
        # dans le menu. Le menu n en propose plus que deux : elles doivent donc
        # etre atteignables depuis une phrase ordinaire.
        if any(k in text for k in ["navigue", "ouvre le site", "va sur http", "navigateur"]):
            return "BROWSER"
        if any(k in text for k in ["corrige le bug", "erreur dans le code", "corrige le fichier"]):
            return "SWE_FIX"
        if any(k in text for k in ["architecture du projet", "dépôt", "depot", "plusieurs fichiers"]):
            return "REPO_ENGINEERING"
        # Interroger ses documents, ET les indexer : les deux passent par le
        # moteur documentaire. Sans les verbes d indexation ici, la seule phrase
        # qui remplit l index n arrivait jamais jusqu a lui.
        if any(k in text for k in ["dans mes documents", "d'après mon fichier", "mes devis", "mes factures"]):
            return "RAG_DOCS"
        if any(k in text for k in [
            "indexe mes documents", "indexer mes documents", "indexe les documents",
            "réindexe", "reindexe", "indexation de mes documents",
            "mets à jour mes documents", "mets a jour mes documents",
        ]):
            return "RAG_DOCS"
        if any(k in text for k in ["graphe de connaissance", "liens entre mes documents", "graphrag"]):
            return "GRAPHRAG"

        # Studio complet : une seule demande, toute la chaine.
        # Teste avant VIDEO_ANALYSIS : « sous-titre cette video » est un studio,
        # pas une analyse — l attente de l utilisateur est un fichier rendu.
        studio_keywords = [
            "studio", "transforme la vidéo", "transforme la video",
            "sous-titre", "sous titre", "9:16", "short tiktok", "reformatte",
        ]
        if any(k in text for k in studio_keywords):
            return "STUDIO"

        # Vidéo. Les demandes de FABRICATION sont deja traitees plus haut.
        video_keywords = ["découpe cette vidéo", "analyse cette vidéo"]
        if any(k in text for k in video_keywords):
            return "VIDEO_ANALYSIS"

        return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Ousmane"

        # La classification coûte un appel au modèle : si l'appelant l'a déjà
        # faite, on la réutilise au lieu de la refaire.
        intent = (context or {}).get("intent") or await self.analyze_intent(user_input)

        # La voie dit ce que cette demande a le droit de couter. Elle est
        # consultee ici, juste apres le classement : c'est le seul endroit ou
        # l'intention est connue avant que la reponse ne commence. Une intention
        # inconnue prend la voie la moins chere qui puisse encore repondre,
        # jamais la plus puissante.
        voie = voie_pour(intent)
        budget = budget_de(voie)
        logger.info("Intention %s -> voie %s (cible %.1f s, %s appel(s) modele).",
                    intent, voie.value, budget.objectif_secondes, budget.appels_modele_max)

        history = self.memory.get_recent_history(session_id=session_id, limit=6) if self.memory else []

        # PROMPT MONDIAL SANS BIAIS LOCAL FORCÉ
        system_prompt = (
            f"Tu es Usman, une intelligence artificielle internationale de haut niveau, au service de {owner_name}.\n"
            f"Contexte temporel : Nous sommes en 2026.\n"
            f"Règles strictes :\n"
            f"1. Réponds STRICTEMENT et DIRECTEMENT à la question posée sans dériver vers d'autres sujets.\n"
            f"2. Ne parle du Sénégal QUE si la question concerne explicitement le Sénégal.\n"
            f"3. Pour les événements futurs (ex: Coupe du Monde 2026), rappelle poliment que l'événement n'a pas encore eu lieu et donne les faits historiques connus si pertinents.\n"
            f"4. Réponds en français fluide, naturel et professionnel."
        )

        prompt_lines = []
        for msg in history:
            role_label = owner_name if msg["role"] == "user" else "Usman"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{owner_name}: {user_input}")
        prompt_lines.append("Usman:")

        reply = await self.provider.generate(prompt="\n".join(prompt_lines), system_prompt=system_prompt)
        return {
            "intent": intent,
            # La voie voyage avec la reponse : sans elle, personne en aval ne
            # peut dire ce que ce tour avait le droit de couter.
            "voie": voie.value,
            "budget": {
                # `objectif_secondes` est une CIBLE, pas une mesure : rien n'a
                # ete chronometre ici.
                "objectif_secondes": budget.objectif_secondes,
                "appels_modele_max": budget.appels_modele_max,
                "etapes_outils_max": budget.etapes_outils_max,
                "memoire_caracteres": budget.memoire_caracteres,
                "reseau_autorise": budget.reseau_autorise,
            },
            "agent": self.name,
            "response": reply.strip()
        }
