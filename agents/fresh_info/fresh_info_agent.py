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
- Ne complète pas avec tes connaissances propres : elles peuvent être périmées.
- Quand une source porte une date entre parenthèses, dis-la : « selon [2], le 14/08… ».
- Entre deux sources qui se contredisent, retiens la plus récente et dis pourquoi.
- Réponds en français, de manière directe.

SOURCES :
{sources}

QUESTION : {question}

RÉPONSE (avec les numéros de source) :"""


class FreshInfoAgent(BaseAgent):
    """Répond aux questions d'actualité en lisant réellement le web."""

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

    async def _reformuler_si_ellipse(
        self, user_input: str, context: Optional[Dict[str, Any]]
    ) -> str:
        """Complete une question elliptique avec le sujet d'un echange precedent.

        Sans historique disponible (pas de session, pas de memoire, ou aucun
        tour precedent), la question part telle quelle : rien a completer, et
        un appel modele inutile couterait de la latence pour rien.
        """
        session_id = (context or {}).get("session_id")
        if not session_id or not self.memory:
            return user_input
        historique = self.memory.get_recent_history(session_id=session_id, limit=4)
        if not historique:
            return user_input

        lignes = "\n".join(
            f"{'Utilisateur' if msg['role'] == 'user' else 'Usman'}: {msg['content']}"
            for msg in historique
        )
        prompt = GABARIT_REFORMULATION.format(historique=lignes, question=user_input)
        try:
            reformulee = (await self.provider.generate(prompt=prompt)).strip()
        except Exception as erreur:  # noqa: BLE001 — une reformulation ratee n'annule pas la recherche
            logger.warning(f"Reformulation impossible, question gardee telle quelle : {erreur}")
            return user_input
        return reformulee or user_input

    async def run(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        question = await self._reformuler_si_ellipse(user_input, context)
        if question != user_input:
            logger.info(f"FreshInfoAgent cherche : {question} (reformulee depuis « {user_input} »)")
        else:
            logger.info(f"FreshInfoAgent cherche : {question}")
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

        part = self._repartir_le_budget(lues)
        prompt = GABARIT_SYNTHESE.format(
            sources=self._formater_les_sources(lues, part, question), question=question
        )
        reponse = await self.provider.generate(prompt=prompt)

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
