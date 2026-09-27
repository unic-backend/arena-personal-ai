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
from core.agent.verification_synthese import avertissement_sources, elements_sans_source
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

TERMES_DETAIL_EVENEMENT = frozenset({
    "but", "buts", "buteur", "buteurs", "marque", "marqué", "marquee", "marquée",
    "homme", "mvp", "composition", "compo", "score", "scores",
})
MOTS_LIAISON_EVENEMENT = frozenset({
    "contre", "lors", "pendant", "entre", "avec", "apres", "après",
})

# Mots capitalises d'une reponse qui ne precisent pas l'evenement resolu.
# Les autres noms propres et scores peuvent servir d'INDICES DE RECHERCHE au
# tour suivant, mais jamais de faits : ils devront etre retrouves dans les
# nouvelles sources avant de pouvoir alimenter la synthese.
MOTS_HINT_ASSISTANT = frozenset({
    "le", "la", "les", "un", "une", "selon", "source", "sources", "réponse",
    "reponse", "dernier", "dernière", "derniere", "match", "liga", "ligue",
    "champions", "championnat", "victoire", "score", "usman", "travail",
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
        tokens = {
            t.casefold().strip("'’_-") for t in cls._tokens(question)
            if t.strip("'’_-")
        }
        if not (tokens & TERMES_DETAIL_EVENEMENT):
            return ""

        ancres = [
            a for a in cls._termes_ancrage(question)
            if a not in TERMES_DETAIL_EVENEMENT
            and a not in MOTS_LIAISON_EVENEMENT
        ]
        # Deux entites independantes sont necessaires pour eviter de prendre une
        # zone generale sur un seul club/personne comme si c'etait l'evenement.
        if len(ancres) < 2:
            return ""

        trouvees: Dict[str, int] = {}
        fin = None
        for rang, paragraphe in enumerate(paragraphes):
            bas = paragraphe.casefold()
            for ancre in ancres:
                if ancre in trouvees:
                    continue
                if re.search(rf"(?<!\w){re.escape(ancre)}(?!\w)", bas):
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
        return re.sub(r"\W+", " ", (texte or "").casefold()).strip()

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

            for brut in re.findall(r"(?<!\w)[A-ZÀ-ÖØ-Þ][\wÀ-ÿ-]{2,}", contenu):
                terme = brut.casefold().strip("_-")
                if (
                    terme in ancres_set
                    or terme in MOTS_HINT_ASSISTANT
                    or terme in MOTS_VIDES_ANCRAGE
                    or terme in TERMES_SUIVI_GENERIQUES
                    or terme in TERMES_CONTEXTE_RECHERCHE
                ):
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
        ]).casefold()
        return any(
            re.search(rf"(?<!\w){re.escape(ancre)}(?!\w)", corpus)
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
        indices_evenement = self._indices_evenement_assistant(
            historique, ancres_suivi
        )
        question = await self._reformuler_si_ellipse(user_input, context)
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
