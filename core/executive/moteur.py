"""Le moteur d'Executive Intelligence — l'unique point d'entree (mission §5).

Flux : contexte metier -> selection dynamique des roles -> consultation
PARALLELE et independante -> synthese avec desaccord preserve -> memoire
concise. Aucune etape ne re-implemente une capacite qu'ARENA possede deja
(mission §4/§47) ; ce module ne fait que les COORDONNER.

**Une question simple ne convoque personne (§10/§42).** `selectionner()` rend
une liste vide pour « quelle heure est-il » — ce module repond alors
directement, sans fan-out, sans le gabarit de decision complet. C'est la
meme regle de sobriete que `core/specialistes/selection.py` (« zero est une
reponse »), appliquee cote affaires.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from core.executive.contexte_affaires import charger_contexte_affaires, preuves_documentaires
from core.executive.contrat import AnalyseSpecialiste, DecisionExecutive, Position
from core.executive.extraction import extraire_scenario_projet
from core.executive.memoire import bloc_decisions_recentes, enregistrer_decision
from core.executive.selection import RoleExecutif, selectionner
from core.executive.specialistes import CONSULTANTS, ConsultationEntree
from core.executive.synthese import synthetiser
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.executive.moteur")

#: Un role qui ne rend rien apres ce delai est traite comme indisponible —
#: jamais attendu sans fin (mission §28/§42).
DELAI_ROLE_SECONDES = 45.0


def _erreur_pour(role: RoleExecutif, message: str) -> AnalyseSpecialiste:
    return AnalyseSpecialiste(
        role=role.identifiant, domaine=role.domaine, position=Position.INDISPONIBLE,
        confiance="FAIBLE", erreur=message,
        inconnues=[f"le role {role.identifiant} n'a pas repondu : {message}"],
    )


async def _consulter_un_role(role: RoleExecutif, entree: ConsultationEntree) -> AnalyseSpecialiste:
    """Un role qui leve, plante ou depasse son delai devient une analyse
    INDISPONIBLE — jamais une exception qui remonte et casse les autres
    (mission §28 : un role en panne n'emporte pas les autres)."""
    consultant = CONSULTANTS.get(role.identifiant)
    if consultant is None:
        return _erreur_pour(role, "aucune capacite reelle enregistree pour ce role")
    try:
        return await asyncio.wait_for(consultant(entree), timeout=DELAI_ROLE_SECONDES)
    except asyncio.TimeoutError:
        logger.warning("Role executif %s : delai depasse (%.0fs)", role.identifiant, DELAI_ROLE_SECONDES)
        return _erreur_pour(role, f"delai depasse ({DELAI_ROLE_SECONDES:.0f}s)")
    except Exception as erreur:  # noqa: BLE001 — filet final, chaque consultant a deja le sien
        logger.exception("Role executif %s en echec inattendu", role.identifiant)
        return _erreur_pour(role, str(erreur))


@dataclass
class MoteurExecutif:
    """Compose les dependances une fois — reprend la convention deja en
    place (`FinanceAgent`, `DeepResearcherAgent`) : un `provider`, une
    `memory` optionnelle, un outil de recherche optionnel, jamais construits
    en dur a l'interieur du moteur."""

    provider: ModelProvider
    memory: Optional[MemoryManager] = None
    lightrag_query: Optional[Callable[[str], str]] = None
    chercheur: Optional[Callable[[str], List[Dict[str, str]]]] = None

    async def analyser(self, question: str) -> DecisionExecutive:
        question = (question or "").strip()
        if not question:
            return DecisionExecutive(
                question=question, simple=True,
                reponse="Aucune question fournie.", confiance="FAIBLE",
            )

        roles = selectionner(question)
        if not roles:
            # §10 : pas de gabarit executif pour une question qui n'en appelle
            # pas — une reponse directe, courte, suffit.
            try:
                reponse = (await self.provider.generate(prompt=question)).strip()
            except Exception as erreur:  # noqa: BLE001
                logger.warning("Reponse directe indisponible : %s", erreur)
                reponse = "Je ne peux pas repondre pour le moment (modele indisponible)."
            return DecisionExecutive(question=question, simple=True, reponse=reponse, confiance="MOYENNE")

        contexte = charger_contexte_affaires()
        scenario = extraire_scenario_projet(question)
        preuves_doc = preuves_documentaires(question, self.lightrag_query)

        entree = ConsultationEntree(
            question=question, contexte=contexte, donnees={"scenario": scenario},
            preuves_documentaires=preuves_doc, provider=self.provider, chercheur=self.chercheur,
        )

        analyses = list(await asyncio.gather(*(_consulter_un_role(r, entree) for r in roles)))

        decision = await synthetiser(question, analyses, self.provider)
        enregistrer_decision(self.memory, decision)
        return decision

    def bloc_memoire_pour_prompt(self) -> str:
        """Expose pour un appelant qui voudrait injecter l'historique de
        decisions dans un prompt plus large — jamais construit a l'interieur
        d'un prompt de role, pour rester une seule source de verite (§15)."""
        return bloc_decisions_recentes(self.memory)


async def analyser_question(
    question: str,
    provider: ModelProvider,
    *,
    memory: Optional[MemoryManager] = None,
    lightrag_query: Optional[Callable[[str], str]] = None,
    chercheur: Optional[Callable[[str], List[Dict[str, str]]]] = None,
) -> DecisionExecutive:
    """Fonction libre pratique pour un appel ponctuel (tests, scripts) — le
    coeur reste `MoteurExecutif`, ceci n'est qu'une construction jetable."""
    moteur = MoteurExecutif(provider=provider, memory=memory, lightrag_query=lightrag_query, chercheur=chercheur)
    return await moteur.analyser(question)
