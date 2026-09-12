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
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.execution.boucle import BoucleAgentique, Budget, Observation
from core.execution.coordination import Etape
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

#: Combien de fois au maximum on consulte la liste des roles. 2 = la
#: consultation initiale, puis UNE seconde chance aux seuls roles qui n'ont pas
#: repondu. Pourquoi deux et pas plus : un role indisponible l'est le plus
#: souvent pour une raison qui ne change pas en trois secondes (modele eteint,
#: capacite non enregistree) ; et un role qui a depasse `DELAI_ROLE_SECONDES`
#: a deja coute 45 s. Au-dela, on ferait attendre le proprietaire pour repayer
#: la meme panne.
TOURS_MAX = 2

#: Plafond de temps de la boucle entiere. Large devant un tour (45 s), etroit
#: devant l'attente qu'un troisieme tour imposerait.
SECONDES_MAX = 120.0


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

        analyses = await self._consulter_avec_seconde_chance(roles, entree)

        decision = await synthetiser(question, analyses, self.provider)
        enregistrer_decision(self.memory, decision)
        return decision

    async def _consulter_avec_seconde_chance(
        self, roles: List[RoleExecutif], entree: ConsultationEntree,
    ) -> List[AnalyseSpecialiste]:
        """Consulte les roles, et redonne UNE chance a ceux qui n'ont pas repondu.

        Avant le 12/09/2026, cette consultation etait un unique
        `asyncio.gather` : un role en panne PASSAGERE — modele surcharge,
        recherche qui depasse son delai — trouait la decision definitivement,
        et la synthese se faisait avec ce trou sans que rien ne le retente.

        Ce que la boucle change, et rien d'autre :

        - les roles partent toujours **en parallele** (`parallelisme`), donc un
          tour coute ce qu'il coutait ;
        - **un seul tour** a lieu quand tout le monde repond — c'est le cas
          courant, et il est identique a l'ancien comportement ;
        - un role qui n'a pas repondu est **reconsulte une fois**, seul ;
        - **ce qui arrete, c'est `TOURS_MAX`**, et rien d'autre. Une premiere
          version ajoutait ici une garde « sans progres » : elle etait
          inatteignable, puisqu'avec deux tours `planifier` n'est jamais
          appele une troisieme fois. Un sabotage l'a montre — la retirer n'a
          fait tomber aucun test. Elle est partie : une garde qui ne peut pas
          s'executer donne l'illusion d'une protection.

        Ce que ca ne change pas : un role qui ne repond toujours pas reste
        `INDISPONIBLE`, et ses `inconnues` voyagent jusqu'a la synthese. La
        seconde chance ne comble aucun trou en silence.
        """
        analyses: Dict[str, AnalyseSpecialiste] = {}
        par_identifiant = {role.identifiant: role for role in roles}

        def _a_repondu(analyse: Any) -> Tuple[bool, str]:
            """Verification DETERMINISTE : la position, pas une impression."""
            if not isinstance(analyse, AnalyseSpecialiste):
                return False, "le role n'a pas rendu d'analyse"
            if analyse.position is Position.INDISPONIBLE:
                return False, analyse.erreur or "role indisponible"
            return True, "le role a repondu"

        def _etape_pour(role: RoleExecutif) -> Etape:
            async def _consulter() -> AnalyseSpecialiste:
                analyse = await _consulter_un_role(role, entree)
                # Gardee meme indisponible : c'est elle qui portera l'inconnue
                # jusqu'a la synthese si la seconde chance echoue aussi.
                analyses[role.identifiant] = analyse
                return analyse

            return Etape(nom=role.identifiant, appel=_consulter,
                         facultative=True, verifier=_a_repondu)

        def planifier(objectif: str, observations: List[Observation]) -> List[Etape]:
            if not observations:
                return [_etape_pour(role) for role in roles]
            # Un seul replan possible (`TOURS_MAX`), donc ce chemin n'est
            # atteint qu'une fois : on redonne sa chance a ce qui n'a pas
            # repondu, et `tours_max` arrete la — pas une garde de plus.
            a_reprendre = observations[-1].abandonnees
            return [_etape_pour(par_identifiant[i]) for i in a_reprendre
                    if i in par_identifiant]

        def evaluer(resultat: Any, acquis: Dict[str, Any]) -> Tuple[bool, str]:
            manquants = [i for i in par_identifiant
                         if _a_repondu(analyses.get(i))[0] is False]
            if manquants:
                return False, f"{len(manquants)} role(s) sans reponse : {', '.join(manquants)}"
            return True, "tous les roles ont repondu"

        etat = await BoucleAgentique(
            objectif=f"consulter {len(roles)} role(s) executif(s)",
            planifier=planifier, evaluer=evaluer,
            budget=Budget(etapes_max=max(1, len(roles) * TOURS_MAX),
                          tours_max=TOURS_MAX, secondes_max=SECONDES_MAX),
            parallelisme=max(1, len(roles)),
        ).executer()

        if etat.replanifications:
            logger.info("Executif : %s role(s) reconsulte(s) apres echec — arret %s",
                        len(etat.tours[-1].plan), etat.raison_d_arret.value
                        if etat.raison_d_arret else "sans raison")

        # L'ordre de `roles` est conserve : la synthese ne doit pas dependre de
        # l'ordre d'arrivee des reponses.
        return [analyses[role.identifiant] for role in roles
                if role.identifiant in analyses]

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
