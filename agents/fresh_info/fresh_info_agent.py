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
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
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
- Quand une source porte une date entre parenthèses, dis-la : « selon [2], le 14/08… ».
- Entre deux sources qui se contredisent, retiens la plus récente et dis pourquoi.
- Réponds en français, de manière directe.

SOURCES :
{sources}

QUESTION : {question}

RÉPONSE (avec les numéros de source) :"""

# Mots qui n'identifient pas un sujet. Ils servent a distinguer une vraie
# entite ("Barcelone", "Python", "Bitcoin") d'un suivi sans sujet
# ("Qui sont les buteurs ?", "Quel etait le score ?").
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

TERMES_SUIVI_GENERIQUES = frozenset({
    "buteur", "buteurs", "score", "scores", "resultat", "résultat", "resultats",
    "résultats", "gagnant", "gagnants", "gagne", "gagné", "gagner", "vainqueur",
    "vainqueurs", "homme", "match", "joueur", "joueurs", "statistique",
    "statistiques", "stats", "classement", "composition", "compo", "details",
    "détails", "autre", "autres", "deuxieme", "deuxième", "premier", "première",
    "apres", "après",
})

DEICTIQUES_SUIVI = frozenset({
    "cela", "ça", "celui", "celle", "ceux", "celles", "cette", "ces", "lui",
    "elle", "eux", "elles",
})

TERMES_CONTEXTE_RECHERCHE = frozenset({
    "dernier", "derniere", "dernière", "match", "score", "version", "prix",
    "cours", "resultat", "résultat", "meteo", "météo", "temps", "president",
    "président", "election", "élection", "finale", "coupe", "championnat",
    "date", "heure", "modele", "modèle", "sortie", "classement",
})


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

    @staticmethod
    def extraire_pertinent(texte: str, question: str, taille: int) -> str:
        """Garde les passages qui parlent de la question, pas le debut de la page.

        Mesure du 2026-08-26 : a « qui a gagne la derniere coupe du monde »,
        Usman a repondu « la derniere Coupe du Monde remportee par l equipe
        francaise a eu lieu en 2018 » — en citant une page de palmares qui
        contient la bonne reponse plus bas. L extrait envoye au modele etait
        les N premiers caracteres, c est-a-dire l introduction.

        Le decoupage est par paragraphe, le classement par nombre de mots de la
        question presents. **L ordre du document est conserve** : un palmares
        lu a l envers se comprend mal. A egalite, le passage le plus haut gagne,
        ce qui redonne le comportement d avant quand rien ne ressort.
        """
        if len(texte) <= taille:
            return texte.strip()

        mots = {
            mot for mot in re.findall(r"[\wàâäéèêëîïôöùûüç]{4,}", (question or "").lower())
        }
        paragraphes = [p.strip() for p in re.split(r"\n\s*\n|\n", texte) if p.strip()]
        if not mots or not paragraphes:
            return texte[:taille].strip()

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
        return re.findall(r"[\\wÀ-ÿ'’-]+", texte or "")

    @classmethod
    def _termes_ancrage(cls, texte: str) -> List[str]:
        """Termes assez specifiques pour identifier le sujet d'une question."""
        termes: List[str] = []
        vus = set()
        for brut in cls._tokens(texte):
            terme = brut.casefold().strip("'’_-")
            if not terme or terme.isdigit() or terme in MOTS_VIDES_ANCRAGE:
                continue
            if terme in TERMES_SUIVI_GENERIQUES or terme in TERMES_CONTEXTE_RECHERCHE:
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
    def _question_de_suivi_sans_ancre(cls, texte: str) -> bool:
        """Vrai quand la phrase depend clairement d'un sujet precedent."""
        bruts = cls._tokens(texte)
        tokens = [t.casefold().strip("'’_-") for t in bruts if t.strip("'’_-")]
        if not tokens:
            return False
        # Un sujet concret dans la phrase du jour prime toujours sur le fil
        # precedent. « Et le score de Barça ? » ne doit pas etre rattache a
        # l'equipe dont on parlait juste avant.
        if cls._termes_ancrage(texte):
            return False
        if tokens[0] == "et" or any(t in DEICTIQUES_SUIVI for t in tokens):
            return True

        contenus = [
            t for t in tokens
            if t not in MOTS_VIDES_ANCRAGE and len(t) >= 3
        ]
        return bool(contenus) and all(t in TERMES_SUIVI_GENERIQUES for t in contenus)

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
        return re.sub(r"\\W+", " ", (texte or "").casefold()).strip()

    @classmethod
    def _dernier_message_avec_ancre(
        cls, historique: List[Dict[str, Any]], user_input: str
    ) -> tuple[str, List[str]]:
        """Dernier tour utilisateur qui nomme vraiment un sujet.

        On saute les suivis eux-memes. Ainsi une chaine
        « Barcelone -> buteurs ? -> homme du match ? » reste rattachee a
        Barcelone au troisieme tour au lieu de s'ancrer sur « buteurs ».
        """
        courant = cls._normaliser_phrase(user_input)
        for message in reversed(historique):
            if message.get("role") != "user":
                continue
            contenu = str(message.get("content") or "").strip()
            if not contenu or cls._normaliser_phrase(contenu) == courant:
                continue
            ancres = cls._termes_ancrage(contenu)
            if ancres:
                return contenu, ancres
        return "", []

    @classmethod
    def _requete_de_suivi(
        cls, precedent: str, user_input: str, ancres: List[str]
    ) -> str:
        """Construit un filet deterministe si le modele perd le sujet."""
        utiles: List[str] = []
        ancres_set = set(ancres)
        for brut in cls._tokens(precedent):
            terme = brut.casefold().strip("'’_-")
            if terme in ancres_set or terme in TERMES_CONTEXTE_RECHERCHE:
                utiles.append(brut)
        prefixe = " ".join(utiles[:12]).strip()
        return f"{prefixe} — {user_input.strip()}" if prefixe else user_input

    @classmethod
    def _ancres_de_suivi(
        cls, user_input: str, historique: List[Dict[str, Any]]
    ) -> List[str]:
        if not cls._question_de_suivi_sans_ancre(user_input):
            return []
        _, ancres = cls._dernier_message_avec_ancre(historique, user_input)
        return ancres

    @staticmethod
    def _source_mentionne_une_ancre(
        page: Dict[str, Any], ancres: List[str]
    ) -> bool:
        corpus = " ".join([
            str(page.get("title") or ""),
            str(page.get("url") or page.get("href") or ""),
            str(page.get("text") or page.get("body") or ""),
        ]).casefold()
        return any(
            re.search(rf"(?<!\\w){re.escape(ancre)}(?!\\w)", corpus)
            for ancre in ancres
        )

    async def _reformuler_si_ellipse(
        self, user_input: str, context: Optional[Dict[str, Any]]
    ) -> str:
        """Complete une question elliptique avec le sujet d'un echange precedent.

        Le modele peut reformuler, mais il n'a plus le droit de perdre un sujet
        deterministe. Si une question de suivi sans ancre reste sans l'entite du
        tour precedent, une requete contextuelle est construite sans modele.
        """
        historique = self._historique_du_contexte(context)
        if not historique:
            return user_input

        precedent, ancres_precedentes = self._dernier_message_avec_ancre(
            historique, user_input
        )
        ancres = (
            ancres_precedentes
            if self._question_de_suivi_sans_ancre(user_input)
            else []
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
        if ancres:
            bas = reformulee.casefold()
            if not any(ancre in bas for ancre in ancres):
                repliee = self._requete_de_suivi(precedent, user_input, ancres)
                logger.warning(
                    "Reformulation sans ancre (%s) : requete rattachee au fil -> %s",
                    ", ".join(ancres),
                    repliee,
                )
                return repliee
        return reformulee

    async def run(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        historique = self._historique_du_contexte(context)
        ancres_suivi = self._ancres_de_suivi(user_input, historique)
        question = await self._reformuler_si_ellipse(user_input, context)
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
        try:
            resultats = await asyncio.wait_for(
                asyncio.to_thread(
                    self.search_tool.search, question,
                    max_results=RESULTATS_RECHERCHE, recent=True,
                ),
                timeout=DELAI_RECHERCHE_SECONDES,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Recherche abandonnee apres {DELAI_RECHERCHE_SECONDES} s")
            resultats = []

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
            # Les resultats dont le titre/extrait mentionne deja le sujet passent
            # devant. On ne jette encore rien : une page peut etre pertinente
            # meme si son snippet ne contient pas l'entite. Le filtre dur vient
            # apres lecture, sur le contenu reel.
            resultats = sorted(
                resultats,
                key=lambda resultat: self._source_mentionne_une_ancre(
                    resultat, ancres_suivi
                ),
                reverse=True,
            )

        pages = await self._lire_les_pages(resultats)
        lues = [p for p in pages if p["status"] == "FETCHED" and p["text"].strip()]

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

        part = self._repartir_le_budget(lues)
        prompt = GABARIT_SYNTHESE.format(
            sources=self._formater_les_sources(lues, part, question), question=question
        )
        reponse = await self.rediger(prompt=prompt)

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
            "response": reponse.strip(),
        }
