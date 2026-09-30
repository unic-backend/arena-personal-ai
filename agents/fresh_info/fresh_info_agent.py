"""Agent d'information fraîche : chercher, lire, répondre en citant.

Écrire « nous sommes en 2026 » dans un prompt ne donne aucune connaissance à un
modèle : cela lui donne seulement de quoi paraître à jour. Pour répondre à une
question d'actualité, il faut aller lire, puis citer ce qu'on a lu.

Chaîne : recherche → lecture des pages → budget de contexte → synthèse → sources.

Deux refus explicites, parce qu'une réponse inventée coûte plus cher qu'une
absence de réponse :

- **aucun résultat de recherche** → le modèle n'est pas appelé ;
- **aucune page lisible** → le modèle n'est pas appelé non plus, et l'agent dit
  ce qu'il a essayé de lire et pourquoi cela a échoué.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.agent.verification_synthese import (
    avertissement_sources,
    elements_sans_source,
    terme_present,
)
from core.memory.conversation import NOM_ASSISTANT
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.security.trust import TrustLevel, wrap
from tools.search.source_fetcher import SourceFetcher
from tools.search.web_search_tool import WebSearchTool

logger = logging.getLogger("usman.agent.fresh_info")

# Le modèle tourne avec num_ctx = 4096 jetons. Envoyer cinq pages entières
# deborderait le contexte et ferait oublier la question elle-meme. Ce budget est
# reparti entre les sources retenues.
BUDGET_CARACTERES = 4500
SOURCES_MAX = 3
RESULTATS_RECHERCHE = 5

# Delai total accorde a la lecture des pages. Elles sont lues en parallele :
# passe ce delai, on repond avec ce qui est arrive, au lieu d attendre la plus
# lente. Une page qui met plus de 6 s ne vaut pas l attente quand deux autres
# ont deja repondu.
DELAI_LECTURE_SECONDES = 6.0

# Delai accorde a la recherche elle-meme. Sans plafond, un moteur qui ne repond
# pas fige la reponse entiere.
#
# 6 s a longtemps suffi, tant que `search(recent=True)` ne faisait qu'un seul
# appel reseau. Ce n'est plus le cas : cette passe enchaine jusqu'a cinq appels
# sequentiels a DDGS (news/jour, news/jour elargie, news/semaine, text/semaine,
# text sans date), et `WebSearchTool` s'accorde elle-meme 25 s
# (`DELAI_TOTAL_SECONDES`) pour les mener a bien. Mesure le 30/08/2026 sur
# Railway : un appel direct et isole au moteur reussit en une seconde, mais une
# question sans actualite au sens strict ("qui est le president du Senegal")
# epuise les passes `news` sans resultat avant d'atteindre la derniere passe
# `text` non datee — celle qui aurait repondu. Coupee a 6 s, la recherche etait
# abandonnee en cours de route et Usman rendait le refus « aucun resultat »
# alors que le moteur, livre a lui-meme, en avait un. Le budget de la voie
# RECHERCHE (`core/execution/voies.py`) vise 180 s pour tout le tour : 30 s
# pour la recherche seule laisse largement la place aux lectures de pages et a
# la synthese, et couvre les 25 s que l'outil peut legitimement prendre.
DELAI_RECHERCHE_SECONDES = 30.0

#: Mesure du 30/08/2026 : « Qui a gagné la coupe du monde 2002 » puis « Celle de
#: 2006 » repondaient juste (CHAT, connaissance du modele). « Celle de 2026 »
#: bascule en FRESH_INFO (annee a venir) et part chercher **« Celle de 2026 »**
#: tel quel : sans le sujet, « Celle » est lu comme la ville allemande, et la
#: reponse cite des faits divers du Landkreis Celle. La question elliptique
#: doit etre completee avec la conversation AVANT de partir en recherche.
GABARIT_REFORMULATION = """Voici les derniers échanges d'une conversation, puis une nouvelle question qui peut être elliptique (elle suppose implicitement le sujet d'un échange précédent, par exemple « et 2006 ? » après une question sur une coupe du monde).

{historique}

Nouvelle question : {question}

Réécris cette question sous une forme autonome et complète, qui garde son sens SANS le reste de la conversation. Si elle est déjà autonome, recopie-la sans rien changer. Réponds UNIQUEMENT par la question réécrite, rien d'autre."""

GABARIT_SYNTHESE = """Tu es Usman. Réponds à la question en t'appuyant UNIQUEMENT sur les sources ci-dessous.

Règles :
- Cite tes sources avec leur numéro entre crochets, par exemple [1].
- Si les sources ne répondent pas à la question, dis-le clairement au lieu de deviner.
- HORS SUJET : ignore. Ne change jamais le sujet demandé.
- Ne complète pas avec tes connaissances propres : elles peuvent être périmées.
- Pour « dernier/plus récent » : compare les dates d'événement ; sans chronologie prouvée, refuse.
- Entre deux sources qui se contredisent, retiens la plus récente et dis pourquoi.
- Réponds en français, de manière directe.

SOURCES :
{sources}

QUESTION : {question}

RÉPONSE (avec les numéros de source) :"""

# ATTENTION, frontiere posee le 29/09/2026 (DEC-0191) : les quatre ensembles
# qui suivent ne servent QU'A la barriere de pertinence des SOURCES
# (DEC-0151/0153) — quelle page repond a la question. Aucun d'eux ne decide
# plus si une question a besoin de la conversation : cette decision-la ne se
# prend plus par vocabulaire, elle se prend en donnant le fil (voir
# `_question_du_tour` et `core/context/fil_pour_agents.py`). Y ajouter un mot
# pour reparer un suivi rate serait revenir a la methode abandonnee.

# Mots qui n'identifient pas un sujet. Ils servent a distinguer une vraie
# entite ("Barcelone", "Python", "Bitcoin") d'une question sans sujet propre
# ("Quelles sont les actualites du jour ?").
MOTS_VIDES_ANCRAGE = frozenset({
    "a", "ai", "au", "aux", "avec", "avait", "ce", "ces", "cet", "cette",
    "comme", "dans", "de", "des", "du", "elle", "elles", "en", "entre", "est",
    "et", "ete", "été", "etait", "était", "eux", "fait", "faire", "il", "ils",
    "la", "le", "les", "leur", "leurs", "lui", "ma", "maintenant", "mes", "mon",
    "ne", "notre", "nous", "ou", "où", "par", "pas", "pour", "que", "quel",
    "quelle", "quelles", "quels", "qui", "sa", "sans", "sera", "serait", "ses",
    "son", "sont", "sur", "ta", "tes", "ton", "tu", "un", "une", "vos", "votre",
    "vous", "web", "internet", "verifie", "vérifie", "rapidement", "parle", "dis",
    "donne", "question", "source", "sources", "fc", "exact", "exacte", "recent",
    "récente", "récent", "aujourd'hui", "aujourd’hui", "pourquoi", "comment",
    "quand", "combien", "lequel", "laquelle", "lesquels", "lesquelles",
})

DEICTIQUES_SUIVI = frozenset({
    "cela", "ça", "celui", "celle", "ceux", "celles", "cette", "ces", "lui",
    "elle", "eux", "elles",
})

#: Ce qu'une page porte de toute facon quand elle parle du sujet : l'exiger
#: d'elle ne prouve rien. Barriere de SOURCES seulement (voir l'avertissement
#: en tete de section).
TERMES_CONTEXTE_RECHERCHE = frozenset({
    "dernier", "derniere", "dernière", "match", "score", "version", "prix",
    "cours", "resultat", "résultat", "meteo", "météo", "temps", "president",
    "président", "election", "élection", "finale", "coupe", "championnat",
    "date", "heure", "modele", "modèle", "sortie", "classement",
})

#: Mots d'une question qui ne nomment pas son sujet (sans accents) : le temps,
#: le genre de la demande, des verbes courants. Voir `_sujet_de_la_question`.
MOTS_SANS_SUJET = frozenset({
    "aujourd", "hui", "jour", "jours", "hier", "demain", "soir", "matin", "semaine",
    "mois", "annee", "maintenant", "actuellement", "actualite", "actualites", "actu",
    "actus", "info", "infos", "information", "informations", "nouvelle", "nouvelles",
    "neuf", "quoi", "dernier", "derniere", "derniers", "dernieres", "recent",
    "recente", "recents", "recentes", "coute", "coutent", "vaut", "valent", "donne",
    "dit", "passe", "arrive", "gagne", "perdu", "joue", "heure", "temps", "prix",
    "remporte", "remportee", "aura", "auront", "lieu", "prochain", "prochaine",
    "prochains", "prochaines",
    # L'issue d'un match, pas son sujet : la page ecrit « s'est impose »,
    # « bat », « but de » — et la majorite stricte (DEC-0153) les exigerait.
    "victoire", "victoires", "defaite", "defaites", "battu", "battue", "bat",
    "marque", "marquee", "contre", "vainqueur", "gagnant", "gagnante",
})
#: Mots (sans accents) qui disent qu'une question porte sur l'ACTUALITE. Sans
#: eux, « population du Senegal » ou « president du Senegal » partaient
#: d'abord dans les actualites du jour et n'en ramenaient que des articles
#: qui citent le pays en passant (mesure du 28/09/2026).
MOTS_D_ACTUALITE = frozenset({
    "aujourd", "hier", "demain", "soir", "semaine", "actuel", "actuelle",
    "actuellement", "actualite", "actualites", "actu", "actus", "nouvelle",
    "nouvelles", "news", "dernier", "derniere", "derniers", "dernieres", "recent",
    "recente", "recents", "recentes", "maintenant", "moment", "live", "direct",
    "meteo", "temps", "cours", "score", "resultat", "resultats",
})
#: Une annee ecrite dans la question fait partie de son sujet.
#: Un mot du sujet ajoute par l'agent se reconnait sous ses autres formes :
#: une page de meteo anglaise ecrit « weather », une francaise « prévisions ».
FORMES_DU_SUJET = {
    "météo": ("météo", "weather", "température", "temperature", "prévisions", "forecast"),
}

ANNEE = re.compile(r"\b(?:19|20)\d{2}\b")

#: « fait-il », « donne-moi », « est-ce » : un verbe et son pronom, pas un sujet.
PRONOM_ACCOLE = re.compile(r"-(?:t-)?(?:il|elle|ils|elles|on|moi|toi|nous|vous|je|tu|ce|y|en|le|la|les|lui|leur)$")


def _sans_accents(mot: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", mot) if not unicodedata.combining(c))


class FreshInfoAgent(BaseAgent):
    """Répond aux questions d'actualité en lisant réellement le web."""

    #: Comment l'agent se presente au registre (DEC-0145) : lu par la
    #: decouverte, jamais recopie dans une liste centrale.
    identifiant = "actualite"
    competences = ('actualite', 'information recente', 'derniere version', 'prix actuel', 'recherche web')

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        search_tool: Optional[WebSearchTool] = None,
        fetcher: Optional[SourceFetcher] = None,
        sources_max: int = SOURCES_MAX,
        budget_caracteres: int = BUDGET_CARACTERES,
        delai_lecture: float = DELAI_LECTURE_SECONDES,
    ):
        super().__init__(
            name="FreshInfoAgent",
            description="Agent de reponse aux questions d'actualite, sources a l'appui.",
            provider=provider,
            memory=memory,
        )
        self.search_tool = search_tool or WebSearchTool()
        self.fetcher = fetcher or SourceFetcher()
        self.sources_max = sources_max
        self.budget_caracteres = budget_caracteres
        self.delai_lecture = delai_lecture

    async def _lire_les_pages(self, resultats: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Lit en parallèle les pages candidates ; l'attente est réseau, pas GPU."""
        candidats = [r for r in resultats if r.get("href")][: self.sources_max]
        if not candidats:
            return []

        # Une tache par page, et un plafond sur le lot. Au dela du delai, seules
        # les lectures **non terminees** sont annulees : celles qui sont arrivees
        # servent. `wait_for` sur un `gather` ne convient pas ici — il annule le
        # lot entier, donc les pages deja lues avec. Mesure du 2026-08-26 : sur
        # trois pages dont une lente, cette version-la rendait 0 source au lieu
        # de 2.
        taches = [
            asyncio.ensure_future(self.fetcher.fetch(r["href"])) for r in candidats
        ]
        _, en_attente = await asyncio.wait(taches, timeout=self.delai_lecture)

        for tache in en_attente:
            tache.cancel()
        if en_attente:
            logger.warning(
                f"{len(en_attente)} page(s) abandonnee(s) apres {self.delai_lecture} s : "
                "la reponse est construite avec celles qui sont arrivees."
            )

        lectures = []
        for tache in taches:
            if tache in en_attente:
                lectures.append(TimeoutError(f"pas de reponse en {self.delai_lecture} s"))
            else:
                lectures.append(tache.exception() or tache.result())

        pages = []
        # strict=True : gather renvoie exactement une entree par candidat.
        # Une divergence serait un defaut, pas un cas a absorber en silence.
        for resultat, lecture in zip(candidats, lectures, strict=True):
            if isinstance(lecture, BaseException):
                logger.warning(f"Lecture interrompue : {resultat['href']} ({lecture})")
                pages.append({
                    "status": "FAILED", "url": resultat["href"],
                    "reason": type(lecture).__name__, "text": "", "title": None,
                })
                continue
            # Le titre du moteur de recherche depanne quand la page n'en a pas.
            lecture.setdefault("title", None)
            lecture["title"] = lecture["title"] or resultat.get("title") or resultat["href"]
            pages.append(lecture)
        return pages

    @staticmethod
    def _sources_de_secours(resultats: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Transforme les extraits du moteur en sources, faute de pages lues.

        Chaque extrait garde son titre, son adresse et sa date quand le moteur
        en donne une. `extract` marque la source comme un extrait et non une
        page : le lecteur doit pouvoir faire la difference.
        """
        secours = []
        for resultat in resultats:
            extrait = (resultat.get("body") or "").strip()
            if not extrait or not resultat.get("href"):
                continue
            date = resultat.get("date")
            secours.append({
                "status": "EXTRACT",
                "url": resultat["href"],
                "title": resultat.get("title") or resultat["href"],
                "text": f"({date}) {extrait}" if date else extrait,
                "truncated": True,
            })
        if secours:
            logger.info(f"Aucune page lisible : {len(secours)} extrait(s) de recherche utilise(s)")
        return secours

    def _repartir_le_budget(self, lues: List[Dict[str, Any]]) -> int:
        """Nombre de caractères accordé à chaque source retenue."""
        return max(500, self.budget_caracteres // max(1, len(lues)))

    @classmethod
    def _bloc_evenement_pertinent(
        cls, paragraphes: List[str], question: str, taille: int
    ) -> str:
        """Conserve une fiche d'evenement comme un bloc, pas ligne par ligne.

        Les pages de match affichent souvent :
        equipe A -> score -> equipe B -> minute -> joueur.
        Le joueur n'a alors aucun mot en commun avec « qui sont les buteurs ? ».
        Un classement lexical par ligne supprimait precisement cette ligne.
        On repere donc les deux entites de l'evenement dans la premiere fiche
        compacte, puis on garde le bloc qui suit dans le budget.
        """
        # Les deux entites de l'evenement, prises a l'orthographe et non a un
        # lexique sportif : l'ancienne paire de listes (TERMES_DETAIL_EVENEMENT,
        # MOTS_LIAISON_EVENEMENT) disait « but », « compo », « mvp » et ne
        # valait que pour le football (DEC-0191). Ce qui garde ce chemin sur
        # de vraies fiches d'evenement, c'est le signal structurel exige plus
        # bas : un score ou une minute de jeu.
        ancres = cls._entites_nommees(question)
        # Deux entites independantes sont necessaires pour eviter de prendre une
        # zone generale sur un seul club/personne comme si c'etait l'evenement.
        if len(ancres) < 2:
            return ""

        trouvees: Dict[str, int] = {}
        fin = None
        for rang, paragraphe in enumerate(paragraphes):
            for ancre in ancres:
                if ancre in trouvees:
                    continue
                # Forme traduite admise : « seville » trouve « Sevilla ».
                if terme_present(ancre, paragraphe):
                    trouvees[ancre] = rang
            if len(trouvees) >= 2:
                fin = rang
                break

        if fin is None:
            return ""
        debut_ancre = min(trouvees.values())
        # Si les deux entites sont tres eloignees, il ne s'agit probablement
        # pas d'une meme fiche d'evenement.
        if fin - debut_ancre > 30:
            return ""

        debut = max(0, debut_ancre - 3)
        retenus: List[str] = []
        total = 0
        for paragraphe in paragraphes[debut:]:
            ajout = len(paragraphe) + (1 if retenus else 0)
            if total + ajout > taille:
                break
            retenus.append(paragraphe)
            total += ajout

        bloc = "\n".join(retenus).strip()
        # Un vrai bloc de match/detail doit contenir au moins un signal
        # structurel (score ou minute), sinon on laisse le classement lexical.
        signal = bool(
            re.search(r"(?<!\d)\d{1,2}\s*[-–—:]\s*\d{1,2}(?!\d)", bloc)
            or re.search(r"\b\d{1,3}(?:\+\d{1,2})?\s*['’]", bloc)
        )
        return bloc if signal else ""

    @classmethod
    def extraire_pertinent(cls, texte: str, question: str, taille: int) -> str:
        """Garde les passages qui repondent sans casser les blocs structures.

        Pour les pages d'evenement (match, score, buteurs, composition), on
        conserve d'abord la fiche compacte autour des entites demandees afin
        que les lignes « minute / joueur / score » survivent ensemble.

        Sinon, le comportement historique reste lexical par paragraphe et
        conserve l'ordre du document.
        """
        if len(texte) <= taille:
            return texte.strip()

        mots = {
            mot for mot in re.findall(r"[\wàâäéèêëîïôöùûüç]{4,}", (question or "").lower())
        }
        paragraphes = [p.strip() for p in re.split(r"\n\s*\n|\n", texte) if p.strip()]
        if not paragraphes:
            return texte[:taille].strip()

        bloc_evenement = cls._bloc_evenement_pertinent(
            paragraphes, question, taille
        )
        if bloc_evenement:
            return bloc_evenement[:taille].strip()

        if not mots:
            return texte[:taille].strip()

        # Une page-tableau (calendrier, classement) arrive une cellule par ligne :
        # « Barcelone », « Getafe », « 10/10 »... Classees une a une, les cellules
        # qui repetent le sujet remplissaient tout le budget et le modele recevait
        # « Barcelone | Barcelone | Barcelone » (mesure du 28/09/2026 sur la page
        # calendrier de footmercato). Les cellules courtes consecutives sont
        # regroupees en lignes de tableau avant d'etre classees.
        paragraphes = cls._regrouper_les_cellules(paragraphes)

        scores = []
        for rang, paragraphe in enumerate(paragraphes):
            bas = paragraphe.lower()
            score = sum(1 for mot in mots if mot in bas)
            scores.append((score, -rang, rang, paragraphe))

        # On retient les meilleurs jusqu au budget, puis on les remet dans l ordre.
        retenus, total = [], 0
        for score, _, rang, paragraphe in sorted(scores, reverse=True):
            if score == 0 and retenus:
                break
            if total + len(paragraphe) > taille and retenus:
                continue
            retenus.append((rang, paragraphe))
            total += len(paragraphe)
            if total >= taille:
                break

        if not retenus:
            return texte[:taille].strip()

        retenus.sort()
        return "\n".join(p for _, p in retenus)[:taille].strip()

    @classmethod
    def _sujet_de_la_question(cls, question: str) -> List[str]:
        """Les mots qui nomment le SUJET d'une question, pour la barriere de
        pertinence d'une premiere question (DEC-0151).

        Plus strict que `_termes_ancrage` : « aujourd'hui » coupe en
        « aujourd » + « hui », « fait-il », « jour », « infos » y passaient.
        Ces mots-la figurent dans n'importe quelle page du jour : ils
        rendaient la barriere passoire, ou lui faisaient refuser une question
        generique (« les dernieres infos ») faute d'un mot qu'aucune page ne
        porte. Une question sans sujet propre n'a pas de barriere.
        """
        # Quand la question NOMME au moins deux choses, ce sont elles, son
        # sujet — les noms communs qui les entourent disent ce qu'on demande
        # a leur propos. Mesure : la fiche LaLiga reelle de la PR #350
        # (« Sevilla 1-3 Barcelona / Raphinha (22') ») nomme les deux clubs
        # et jamais le mot « buteurs » ; exiger ce mot-la de la page faisait
        # refuser la seule source qui repondait. Cette regle-ci ne connait
        # aucun domaine : avant, c'etait la liste de football
        # `TERMES_SUIVI_GENERIQUES` qui ecartait « buteurs » (DEC-0191).
        nommees = cls._entites_nommees(question)
        sujet = nommees if len(nommees) >= 2 else [
            terme for terme in cls._termes_ancrage(question)
            if terme not in DEICTIQUES_SUIVI
            and _sans_accents(terme) not in MOTS_SANS_SUJET
            and not PRONOM_ACCOLE.search(terme)
        ]
        # « Ballon d'or 2025 » : sans l'annee, les pages sur l'edition 2026
        # passaient la barriere (mesure du 28/09/2026). Seulement quand la
        # question a deja un sujet : « quoi de neuf en 2026 » n'en a pas.
        if sujet:
            sujet += [a for a in ANNEE.findall(question or "") if a not in sujet]
            # « Quel temps fait-il a Dakar » : le sujet est la meteo de Dakar,
            # pas Dakar — sinon tout article du site « dakar92 » passait
            # (mesure du 28/09/2026).
            mots = {_sans_accents(m) for m in re.findall(r"[\wÀ-ÿ]+", (question or "").casefold())}
            if mots & {"meteo", "temperature", "pluie"} or {"temps", "fait"} <= mots:
                sujet.append("météo")
        return sujet

    @staticmethod
    def _porte_sur_l_actualite(question: str) -> bool:
        """La question demande-t-elle du frais (DEC-0151) ?"""
        mots = re.findall(r"[\wÀ-ÿ]+", (question or "").casefold())
        return any(_sans_accents(mot) in MOTS_D_ACTUALITE for mot in mots)

    #: Une « cellule » : assez courte pour n'etre qu'un morceau de ligne.
    CELLULE_MAX = 40
    #: Une ligne de tableau regroupee ne depasse pas cette taille.
    LIGNE_DE_TABLEAU_MAX = 200

    @classmethod
    def _regrouper_les_cellules(cls, paragraphes: List[str]) -> List[str]:
        """Joint les paragraphes tres courts consecutifs (« a | b | c »)."""
        regroupes: List[str] = []
        courant: List[str] = []
        for paragraphe in paragraphes:
            if len(paragraphe) <= cls.CELLULE_MAX:
                if courant and len(" | ".join(courant + [paragraphe])) > cls.LIGNE_DE_TABLEAU_MAX:
                    regroupes.append(" | ".join(courant))
                    courant = []
                courant.append(paragraphe)
                continue
            if courant:
                regroupes.append(" | ".join(courant))
                courant = []
            regroupes.append(paragraphe)
        if courant:
            regroupes.append(" | ".join(courant))
        return regroupes

    def _formater_les_sources(self, lues: List[Dict[str, Any]], part: int, question: str = "") -> str:
        blocs = []
        for numero, page in enumerate(lues, 1):
            extrait = self.extraire_pertinent(page["text"], question, part)
            # Le texte vient d'une page que personne ne controle : il entre
            # **enveloppe**, au niveau EXTERNAL. La numerotation reste dehors,
            # sinon les citations [1] que le gabarit demande ne marcheraient plus.
            enveloppe = wrap(extrait, TrustLevel.EXTERNAL, page.get("url") or "page sans adresse")
            blocs.append(f"[{numero}] {page['title']}\n    ({page['url']})\n{enveloppe.text}")
        return "\n\n".join(blocs)

    @staticmethod
    def _tokens(texte: str) -> List[str]:
        # Les apostrophes francaises marquent souvent une contraction
        # grammaticale (l'homme, d'abord, qu'il), pas une entite. Les garder
        # soudées faisait de « l'homme » une fausse ancre et cassait les suivis.
        # O'Connor devient O + Connor : "Connor" reste une ancre suffisante.
        return re.findall(r"[\wÀ-ÿ-]+", texte or "")

    @classmethod
    def _termes_ancrage(cls, texte: str) -> List[str]:
        """Termes assez specifiques pour identifier le sujet d'une question."""
        termes: List[str] = []
        vus = set()
        for brut in cls._tokens(texte):
            terme = brut.casefold().strip("'’_-")
            if not terme or terme.isdigit() or terme in MOTS_VIDES_ANCRAGE:
                continue
            if terme in TERMES_CONTEXTE_RECHERCHE:
                continue
            # Les acronymes courts (OM, UK...) comptent seulement s'ils etaient
            # ecrits en capitales. Les mots ordinaires de deux lettres non.
            if len(terme) < 3 and not (len(brut) >= 2 and brut.isupper()):
                continue
            if terme not in vus:
                vus.add(terme)
                termes.append(terme)
        return termes

    @classmethod
    def _entites_nommees(cls, texte: str) -> List[str]:
        """Ce que la phrase NOMME : noms propres et sigles, rien d'autre.

        Remplace l'ancienne liste `TERMES_SUIVI_GENERIQUES` (« buteur »,
        « score », « vainqueur »...), qui pretendait reconnaitre une question
        elliptique en la comparant a du vocabulaire de football. Cette liste
        ne pouvait pas finir : il aurait fallu y ajouter « chiffre » pour la
        finance, « titre » pour un livre, « combien » pour un chantier, et un
        mot de plus a chaque domaine (DEC-0191).

        Le signal retenu n'appartient a aucun domaine : c'est
        l'**orthographe**. « Barcelone », « Bitcoin », « FC » nomment un
        sujet ; « les buteurs », « un chiffre », « combien » n'en nomment
        aucun, quel que soit le metier dont on parle. Une majuscule de debut
        de phrase ne compte pas — elle vient de la ponctuation, pas du nom —
        et un nombre non plus : « Celle de 2006 ? » reste elliptique.

        Ce n'est qu'un filet : ce qui porte la conversation, c'est le fil
        entier donne au modele juste apres.
        """
        entites: List[str] = []
        vus = set()
        texte = texte or ""
        fin_precedente = 0
        premier = True
        for trouve in re.finditer(r"[\wÀ-ÿ-]+", texte):
            brut = trouve.group(0)
            separateur = texte[fin_precedente:trouve.start()]
            debut_de_phrase = premier or bool(re.search(r"[.!?…\n]", separateur))
            premier = False
            fin_precedente = trouve.end()
            terme = brut.casefold().strip("'’_-")
            if not terme or terme.isdigit():
                continue
            sigle = len(brut) >= 2 and brut.isupper()
            nom_propre = brut[:1].isupper() and not debut_de_phrase
            if not (sigle or nom_propre):
                continue
            if terme not in vus:
                vus.add(terme)
                entites.append(terme)
        return entites

    def _historique_du_contexte(
        self, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        contexte = context or {}
        historique = contexte.get("history")
        session_id = contexte.get("session_id")
        # Un [] autoritatif signifie vraiment « aucun tour precedent ».
        if contexte.get("history_authoritative"):
            return list(historique or [])
        if not historique and session_id and self.memory:
            historique = self.memory.get_recent_history(
                session_id=session_id, limit=8
            )
        return list(historique or [])

    @staticmethod
    def _normaliser_phrase(texte: str) -> str:
        return re.sub(r"\W+", " ", (texte or "").casefold()).strip()

    @classmethod
    def _dernier_message_avec_ancre(
        cls, historique: List[Dict[str, Any]], user_input: str
    ) -> tuple[str, List[str]]:
        """Dernier tour utilisateur qui NOMME un sujet.

        On saute les suivis eux-memes. Ainsi une chaine
        « Barcelone -> buteurs ? -> homme du match ? » reste rattachee a
        Barcelone au troisieme tour au lieu de s'ancrer sur « buteurs » :
        « les buteurs » ne nomme rien, et cela se voit a l'orthographe, sans
        avoir a connaitre le football.
        """
        courant = cls._normaliser_phrase(user_input)
        for message in reversed(historique):
            if message.get("role") != "user":
                continue
            contenu = str(message.get("content") or "").strip()
            if not contenu or cls._normaliser_phrase(contenu) == courant:
                continue
            ancres = cls._entites_nommees(contenu)
            if ancres:
                return contenu, ancres
        return "", []

    @classmethod
    def _requete_de_suivi(
        cls, precedent: str, user_input: str, ancres: List[str]
    ) -> str:
        """Filet deterministe quand le modele perd le sujet : ce que le tour
        precedent NOMMAIT, puis la demande du proprietaire telle quelle.

        Aucun mot de domaine n'est ajoute au passage : seuls les noms deja
        ecrits par le proprietaire reviennent, dans leur ordre d'origine.
        """
        utiles: List[str] = []
        ancres_set = set(ancres)
        for brut in cls._tokens(precedent):
            terme = brut.casefold().strip("'’_-")
            if terme in ancres_set:
                utiles.append(brut)
        prefixe = " ".join(utiles[:12]).strip()
        return f"{prefixe} — {user_input.strip()}" if prefixe else user_input

    @classmethod
    def _indices_evenement_assistant(
        cls, historique: List[Dict[str, Any]], ancres: List[str]
    ) -> List[str]:
        """Indices du dernier evenement resolu, jamais faits de confiance.

        Le tour utilisateur precedent nomme souvent seulement le sujet
        (« dernier match du FC Barcelone »). La reponse sourcee peut avoir resolu
        l'evenement concret (« Seville, 3-1 »). Au suivi « qui sont les buteurs ? »,
        ne pas reutiliser ces identifiants oblige le moteur a retrouver le match
        depuis zero et lui fait remonter des pages generales.

        On ne prend un indice que dans la derniere reponse assistant qui mentionne
        encore une ancre utilisateur. L'indice sert uniquement a CHERCHER puis a
        filtrer ; il doit etre confirme par la nouvelle source.
        """
        if not ancres:
            return []

        ancres_set = {a.casefold() for a in ancres}
        for message in reversed(historique):
            if message.get("role") != "assistant":
                continue
            contenu = str(message.get("content") or "").strip()
            if not contenu:
                continue
            bas = contenu.casefold()
            if not any(
                re.search(rf"(?<!\w){re.escape(ancre)}(?!\w)", bas)
                for ancre in ancres_set
            ):
                continue

            indices: List[str] = []
            vus = set()

            # Un score aide la requete, mais le filtre dur preferera un nom
            # propre s'il en existe car 3-1 peut apparaitre sur plusieurs matchs.
            for score in re.findall(
                r"(?<!\d)\d{1,2}\s*(?:[-–—:]|à)\s*\d{1,2}(?!\d)",
                contenu,
                flags=re.IGNORECASE,
            ):
                normalise = (
                    re.sub(r"\s+", "", score)
                    .replace("–", "-")
                    .replace("—", "-")
                    .replace(":", "-")
                    .replace("à", "-")
                    .replace("À", "-")
                )
                if normalise not in vus:
                    vus.add(normalise)
                    indices.append(normalise)

            # Les noms que la reponse a ajoutes. Une majuscule de debut de
            # phrase (« Le dernier match... », « Selon la source... ») n'en
            # est pas un : c'est la ponctuation qui l'impose. Ce controle-la
            # remplace l'ancienne liste `MOTS_HINT_ASSISTANT`, qui listait
            # « ligue », « championnat », « victoire » — encore du football.
            for terme in cls._entites_nommees(contenu):
                if terme in ancres_set or terme == NOM_ASSISTANT.casefold():
                    continue
                if terme not in vus:
                    vus.add(terme)
                    indices.append(terme)

            return indices[:6]
        return []

    @staticmethod
    def _enrichir_question_avec_indices(question: str, indices: List[str]) -> str:
        """Ajoute les identifiants resolus que la reformulation a oublies."""
        if not indices:
            return question
        bas = question.casefold()
        absents = [
            indice for indice in indices
            if not re.search(rf"(?<!\w){re.escape(indice.casefold())}(?!\w)", bas)
        ]
        if not absents:
            return question
        base = question.strip().rstrip(" ?!.")
        return f"{base} {' '.join(absents)}".strip()

    @staticmethod
    def _indices_pour_filtrage(indices: List[str]) -> List[str]:
        """Un nom d'evenement est plus discriminant qu'un score seul."""
        textuels = [i for i in indices if any(ch.isalpha() for ch in i)]
        return textuels or indices

    @staticmethod
    def _source_mentionne_une_ancre(
        page: Dict[str, Any], ancres: List[str]
    ) -> bool:
        corpus = " ".join([
            str(page.get("title") or ""),
            str(page.get("url") or page.get("href") or ""),
            str(page.get("text") or page.get("body") or ""),
        ])
        # Accents et forme traduite admis (DEC-0150) : l'ancre francaise
        # « barcelone » doit reconnaitre une page qui ecrit « Barcelona »,
        # sinon la barriere refuse a tort une source anglaise du bon match.
        return any(terme_present(ancre, corpus) for ancre in ancres)

    @classmethod
    def _source_parle_du_sujet(cls, page: Dict[str, Any], sujet: List[str]) -> bool:
        """La source nomme au moins la moitie des mots du sujet (DEC-0151).

        Un seul mot ne suffit pas pour un sujet a plusieurs mots : mesure du
        28/09/2026, « Ligue des champions » laissait passer un article sur le
        Venezuela qui portait « Ligue » dans son menu, « population du
        Senegal » des articles sur l'education au Senegal.
        """
        if not sujet:
            return True
        trouves = sum(
            1 for terme in sujet
            if cls._source_mentionne_une_ancre(page, list(FORMES_DU_SUJET.get(terme, (terme,)))))
        # Majorite stricte : pour deux mots, les deux. Mesure du 28/09/2026,
        # « meteo de Dakar » laissait passer tout article nommant Dakar.
        return trouves > len(sujet) // 2

    async def _reformuler_si_ellipse(
        self, user_input: str, context: Optional[Dict[str, Any]]
    ) -> str:
        """La question envoyee au moteur de recherche, fil compris."""
        question, _ = await self._question_du_tour(
            user_input, self._historique_du_contexte(context)
        )
        return question

    async def _question_du_tour(
        self, user_input: str, historique: List[Dict[str, Any]]
    ) -> tuple[str, List[str]]:
        """La question a chercher, et le sujet herite du fil s'il y en a un.

        Le fil ENTIER part au modele, toujours : c'est lui qui sait de quoi
        « qui sont les buteurs ? » parle. Rien ici ne compare la question a
        du vocabulaire (DEC-0191) ; ce qui est verifie apres coup, c'est le
        TRAVAIL DU MODELE, pas le domaine de la question :

        1. la question nomme deja un sujet -> on garde sa reformulation ;
        2. sa reformulation reprend un nom du tour precedent -> le modele a
           resolu l'ellipse, ce sujet-la sera aussi la barriere de sources ;
        3. sa reformulation nomme autre chose -> c'est un nouveau sujet, le
           fil ne doit pas le recouvrir ;
        4. elle ne nomme rien du tout -> le modele n'a rien resolu : le filet
           deterministe rattache la demande, telle quelle, aux noms du tour
           precedent.
        """
        if not historique:
            return user_input, []

        precedent, ancres = self._dernier_message_avec_ancre(
            historique, user_input
        )

        lignes = "\n".join(
            f"{'Utilisateur' if msg['role'] == 'user' else 'Usman'}: {msg['content']}"
            for msg in historique
        )
        prompt = GABARIT_REFORMULATION.format(historique=lignes, question=user_input)
        try:
            reformulee = (await self.provider.generate(prompt=prompt)).strip()
        except Exception as erreur:  # noqa: BLE001
            logger.warning(
                "Reformulation impossible, filet deterministe si necessaire : %s",
                erreur,
            )
            reformulee = user_input

        reformulee = reformulee or user_input
        if self._entites_nommees(user_input) or not ancres:
            return reformulee, []

        bas = reformulee.casefold()
        if any(ancre in bas for ancre in ancres):
            return reformulee, ancres
        if self._entites_nommees(reformulee):
            # Le modele, qui a lu tout le fil, a nomme un autre sujet : c'est
            # une nouvelle question, pas un suivi.
            return reformulee, []

        repliee = self._requete_de_suivi(precedent, user_input, ancres)
        logger.warning(
            "Reformulation sans ancre (%s) : requete rattachee au fil -> %s",
            ", ".join(ancres),
            repliee,
        )
        return repliee, ancres

    async def _chercher(self, question: str, recent: bool) -> List[Dict[str, str]]:
        """Recherche bornee dans le temps, hors de la boucle (`search` bloque)."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self.search_tool.search, question,
                    max_results=RESULTATS_RECHERCHE, recent=recent,
                ),
                timeout=DELAI_RECHERCHE_SECONDES,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Recherche abandonnee apres {DELAI_RECHERCHE_SECONDES} s")
            return []

    async def run(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        historique = self._historique_du_contexte(context)
        question, ancres_suivi = await self._question_du_tour(
            user_input, historique
        )
        indices_evenement = self._indices_evenement_assistant(
            historique, ancres_suivi
        )
        question = self._enrichir_question_avec_indices(
            question, indices_evenement
        )
        if question != user_input:
            logger.info(
                "FreshInfoAgent cherche : %s (reformulee depuis « %s »)",
                question,
                user_input,
            )
        else:
            logger.info("FreshInfoAgent cherche : %s", question)
        # `search` est bloquant : lance tel quel, il fige la boucle et donc tout
        # le serveur. Il part dans un fil d execution, avec un plafond.
        # Filtre de fraicheur seulement pour une question d'actualite : un fait
        # stable (population, president, taux de change) se trouve sur une
        # page de reference, pas dans les articles du jour.
        recente = self._porte_sur_l_actualite(question) or bool(ancres_suivi)
        resultats = await self._chercher(question, recent=recente)
        if not resultats:
            # Un moteur qui ne repond pas (delai, poignee de main TLS) vide une
            # passe entiere ; l'autre mode interroge d'autres pages et d'autres
            # moteurs (mesure du 28/09/2026 : une recherche sur deux vide).
            resultats = await self._chercher(question, recent=not recente)

        if not resultats:
            return {
                "status": "warning",
                "agent": self.name,
                "sources": [],
                "response": (
                    "Aucun resultat de recherche pour cette question. "
                    "Je prefere le dire plutot que repondre de memoire : "
                    "mes connaissances propres peuvent etre perimees."
                ),
            }

        if ancres_suivi:
            # L'evenement resolu au tour precedent (opposant, version, lieu...)
            # passe avant le sujet large. Rien n'est encore jete : le filtre dur
            # travaille ensuite sur le contenu reel de la page.
            indices_filtrage = self._indices_pour_filtrage(indices_evenement)
            resultats = sorted(
                resultats,
                key=lambda resultat: (
                    self._source_mentionne_une_ancre(
                        resultat, indices_filtrage
                    ) if indices_filtrage else False,
                    self._source_mentionne_une_ancre(
                        resultat, ancres_suivi
                    ),
                ),
                reverse=True,
            )

        # Premiere question (pas un suivi) : meme barriere de pertinence que pour
        # un suivi, sur le sujet de la question elle-meme (DEC-0151). Mesure du
        # 28/09/2026 sur le vrai moteur : « derniere version de Python » envoyait
        # un article sur GTA 6 a la synthese, « president du Senegal » un article
        # sur la Guinee, « quel temps a Dakar » un article sur l'IA. Le modele
        # repondait alors a cote — ou inventait.
        ancres_question = [] if ancres_suivi else self._sujet_de_la_question(question)
        if ancres_question:
            pertinents = [r for r in resultats
                          if self._source_parle_du_sujet(r, ancres_question)]
            if not pertinents:
                # La passe « actualites du jour » remplit les resultats avec ce
                # qui s'est publie aujourd'hui, pertinent ou non ; la passe web
                # sans date — celle qui trouve python.org ou Wikipedia — n'a
                # alors jamais lieu (mesure du 28/09/2026). Une seconde
                # recherche, dans l'autre mode (sans filtre de fraicheur apres
                # les actualites, actualites apres le web), lui laisse sa chance.
                logger.info("Aucun resultat sur %s : recherche %s.",
                            ", ".join(ancres_question),
                            "sans date" if recente else "dans les actualites")
                pertinents = [r for r in await self._chercher(question, recent=not recente)
                              if self._source_parle_du_sujet(r, ancres_question)]
            if not pertinents:
                logger.warning("Aucun resultat ne parle de : %s", ", ".join(ancres_question))
                return {
                    "status": "warning",
                    "agent": self.name,
                    "query": question,
                    "sources": [],
                    "response": (
                        "J'ai cherche, mais aucun resultat ne parle de "
                        f"« {', '.join(ancres_question)} ». Je prefere le dire plutot "
                        "que repondre avec des pages hors sujet."
                    ),
                }
            resultats = pertinents

        pages = await self._lire_les_pages(resultats)
        lues = [p for p in pages if p["status"] == "FETCHED" and p["text"].strip()]
        if ancres_question:
            lues = [p for p in lues if self._source_parle_du_sujet(p, ancres_question)]

        # Une page pertinente illisible (403, delai) garde son extrait de
        # recherche : c'etait souvent la bonne source — Wikipedia refusee, un
        # article hors sujet lisible, et c'est lui seul qui partait a la synthese.
        if lues and ancres_question:
            lues_urls = {p["url"] for p in lues}
            candidats = [r for r in resultats if r.get("href")][: self.sources_max]
            lues += [
                secours for secours in self._sources_de_secours(
                    [r for r in candidats if r["href"] not in lues_urls])
                if self._source_parle_du_sujet(secours, ancres_question)
            ]

        if not lues:
            # Les sites d actualite refusent souvent les robots : aucune page
            # lisible ne veut pas dire aucune information. Le moteur rend un
            # extrait par resultat, avec son titre et son adresse — c est une
            # source citable, moins complete qu une page, jamais inventee.
            lues = self._sources_de_secours(resultats)

        if not lues:
            details = "\n".join(
                f"- {p['url']} : {p.get('reason', 'illisible')}" for p in pages
            )
            return {
                "status": "warning",
                "agent": self.name,
                "sources": [],
                "attempted": [p["url"] for p in pages],
                "response": (
                    "J'ai trouve des resultats mais je n'ai pu lire aucune page, "
                    "et le moteur n'a rendu aucun extrait. "
                    "Sans source, je ne reponds pas de memoire.\n\n"
                    f"Pages tentees :\n{details}"
                ),
            }

        # Deuxieme barriere, independante du modele : pour une question de suivi
        # sans sujet explicite, une source doit mentionner au moins une ancre du
        # tour precedent. Le 27/09/2026, « Qui sont les buteurs » apres une
        # question sur le FC Barcelone avait cherche cette phrase seule puis cite
        # une page de hockey. Une consigne de prompt ne peut pas reparer une
        # source qui n'aurait jamais du entrer dans la synthese.
        if ancres_suivi:
            pertinentes = [
                page for page in lues
                if self._source_mentionne_une_ancre(page, ancres_suivi)
            ]
            if not pertinentes:
                logger.warning(
                    "Toutes les sources sont hors sujet pour les ancres : %s",
                    ", ".join(ancres_suivi),
                )
                return {
                    "status": "warning",
                    "agent": self.name,
                    "query": question,
                    "sources": [],
                    "response": (
                        "Les resultats trouves ne concernent pas le sujet de la "
                        "conversation. Je prefere ne pas repondre plutot que "
                        "melanger des personnes ou des evenements differents."
                    ),
                }
            lues = pertinentes

            # Si le tour precedent a resolu un evenement concret, une nouvelle
            # source doit aussi confirmer cet evenement avant la synthese.
            # Exemple production : Barca -> Seville 1-3 -> « buteurs ? ».
            # Une page sur une autre joueuse du Barca partage l'ancre
            # « Barcelone » mais pas l'evenement « Seville » : elle est rejetee.
            indices_filtrage = self._indices_pour_filtrage(indices_evenement)
            if indices_filtrage:
                meme_evenement = [
                    page for page in lues
                    if self._source_mentionne_une_ancre(
                        page, indices_filtrage
                    )
                ]
                if not meme_evenement:
                    logger.warning(
                        "Sources sur le bon sujet mais pas l'evenement resolu : %s",
                        ", ".join(indices_filtrage),
                    )
                    return {
                        "status": "warning",
                        "agent": self.name,
                        "query": question,
                        "sources": [],
                        "response": (
                            "Les sources trouvees parlent du bon sujet, mais pas "
                            "de l'evenement precis identifie au tour precedent. "
                            "Je prefere ne pas melanger deux evenements."
                        ),
                    }
                lues = meme_evenement

        part = self._repartir_le_budget(lues)
        sources_lues = self._formater_les_sources(lues, part, question)
        prompt = GABARIT_SYNTHESE.format(sources=sources_lues, question=question)
        # `consulter=False` (DEC-0150) : un collegue repondrait de SA memoire,
        # pas du web — son avis entrerait dans une reponse dite sourcee.
        reponse = (await self.rediger(prompt=prompt, consulter=False)).strip()
        # Ce qui sort de la synthese est relu contre ce qui y est entre : un nom
        # ou un chiffre absent des extraits recus n'a pas pu en venir.
        sans_source = elements_sans_source(reponse, [user_input, question, sources_lues])
        if sans_source:
            logger.warning("Reponse web : elements sans source %s", sans_source)
            reponse = f"{reponse}\n\n{avertissement_sources(sans_source)}"

        return {
            "status": "success",
            "agent": self.name,
            "query": question,
            "sources_count": len(lues),
            "sources": [
                {
                    "index": numero,
                    "title": page["title"],
                    "url": page["url"],
                    "characters": min(len(page["text"]), part),
                    "truncated": page.get("truncated", False) or len(page["text"]) > part,
                }
                for numero, page in enumerate(lues, 1)
            ],
            "unreadable": [
                {"url": p["url"], "reason": p.get("reason", "illisible")}
                for p in pages if p["status"] != "FETCHED"
            ],
            "sans_source": sans_source,
            "response": reponse.strip(),
        }
