"""Le canal par lequel un espace de la PWA en interroge un autre.

Chaque agent partage deja le meme contrat (`BaseAgent.run`, un seul point
d'entree pour tous). Ce module ne fait qu'exploiter ce contrat pour permettre
un appel direct : au lieu que « Video » et « Usman Coder » s'importent l'un
l'autre (un couplage cache, invisible tant qu'on ne renomme pas un fichier),
les deux passent par un registre commun, qui ne connait chaque agent que par
son identifiant d'espace — le meme que celui choisi dans la barre laterale
de la PWA (VOLET « espaces separes »).

Ce module ne construit AUCUN agent et n'importe AUCUN agent concret : il
resterait sinon a la merci d'un import circulaire des qu'un agent voudrait a
son tour demander une capacite (`apps/backend/runtime.py`, qui construit
tous les agents, est aussi celui qui remplit ce registre — jamais l'inverse).
Le registre est rempli une fois, au demarrage, par ce module de composition.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol

logger = logging.getLogger("usman.agent.capacites")


class Capacite(Protocol):
    """Ce qu'un espace doit savoir faire pour etre appelable — le contrat de
    `BaseAgent.run`, sans en dependre : un objet qui le respecte suffit."""

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ...


class CapaciteInconnue(KeyError):
    """L'espace demande n'est enregistre nulle part.

    Une `KeyError` nue aurait fait la meme chose, mais sans dire QUELS espaces
    existent reellement — l'appelant devrait alors deviner s'il a fait une
    faute de frappe ou demande quelque chose qui n'a jamais existe.
    """

    def __init__(self, espace: str, connus: List[str]):
        super().__init__(
            f"Aucune capacite enregistree pour l'espace {espace!r}. "
            f"Espaces connus : {', '.join(sorted(connus)) or '(aucun)'}."
        )
        self.espace = espace
        self.connus = connus


class RegistreCapacites:
    """Rempli une fois au demarrage, interroge par n'importe quel agent ensuite.

    Aucune capacite n'est enregistree par defaut : un registre vide dit
    honnetement qu'aucun espace n'est encore joignable, plutot que de pretendre
    en connaitre un par erreur d'implementation.
    """

    def __init__(self) -> None:
        self._capacites: Dict[str, Capacite] = {}

    def enregistrer(self, espace: str, capacite: Capacite) -> None:
        """Associe un espace a l'agent qui le sert reellement.

        Ecrase une entree existante plutot que de la refuser : au demarrage,
        c'est `apps/backend/runtime.py` qui decide, et un module reimporte en
        test ne doit pas laisser une ancienne entree perimee derriere lui.
        """
        self._capacites[espace] = capacite

    def connait(self, espace: str) -> bool:
        return espace in self._capacites

    def obtenir(self, espace: str) -> Optional[Capacite]:
        """L'agent enregistre sous `espace`, ou `None`."""
        return self._capacites.get(espace)

    def cle_de(self, capacite: Any) -> Optional[str]:
        """La cle sous laquelle CET objet est enregistre, ou `None`.

        Par identite, jamais par nom : `CoderAgent` est enregistre sous
        `code`, et une chaine de delegation qui retenait `CoderAgent` ne
        reconnaissait jamais qu'on lui redemandait `code` (26/09/2026).
        """
        for espace, enregistre in self._capacites.items():
            if enregistre is capacite:
                return espace
        return None

    def espaces(self) -> List[str]:
        return list(self._capacites)

    # --- L'ecosysteme d'agents (DEC-0145) -----------------------------------

    def enregistrer_agent(self, agent: Any) -> str:
        """Inscrit un agent sous l'identifiant qu'il declare, et le branche.

        C'est la seule porte pour un agent ajoute plus tard : construit, puis
        inscrit ici — par la decouverte au demarrage (`peupler`) ou par un
        appel direct pour un agent cree en cours de route. Un `BaseAgent`
        inscrit recoit ce registre comme collaborateurs : il peut consulter
        tous les autres, et tous peuvent le consulter.
        """
        from core.agent.base_agent import BaseAgent
        from core.agent.decouverte import identifiant_de

        cle = identifiant_de(agent)
        deja = self._capacites.get(cle)
        if deja is not None and deja is not agent:
            # Deux agents ne partagent jamais un identifiant en silence.
            nouvelle = f"{cle}_{type(agent).__name__.lower()}"
            logger.warning("Identifiant %r deja pris par %s : %s inscrit sous %r.",
                           cle, type(deja).__name__, type(agent).__name__, nouvelle)
            cle = nouvelle
        self._capacites[cle] = agent
        if isinstance(agent, BaseAgent):
            agent.collaborateurs = self
        return cle

    def peupler(self, espace_de_noms: Dict[str, Any]) -> List[str]:
        """Inscrit TOUS les agents trouves dans `espace_de_noms` (DEC-0145).

        Aucune liste : un agent construit dans le module de composition est
        trouve, qu'il existe aujourd'hui ou qu'il soit ajoute demain.
        """
        from core.agent.decouverte import decouvrir

        return [self.enregistrer_agent(agent) for agent in decouvrir(espace_de_noms)]

    def retirer(self, espace: str) -> None:
        """Retire un agent (il quitte l'ecosysteme). Absent : rien a faire."""
        self._capacites.pop(espace, None)

    def fiche(self, espace: str):
        """La fiche de l'agent `espace`, lue sur l'agent lui-meme."""
        from core.agent.decouverte import fiche_de

        capacite = self._capacites.get(espace)
        if capacite is None:
            raise CapaciteInconnue(espace, self.espaces())
        fiche = fiche_de(capacite)
        fiche.id = espace
        return fiche

    def fiches(self) -> List[Any]:
        return [self.fiche(espace) for espace in self.espaces()]

    def rechercher(self, besoin: str, nombre: int = 3,
                   exclure: Iterable[str] = ()) -> List[Any]:
        """Les agents les plus competents pour `besoin`, meilleur d'abord.

        Deterministe, sans modele (`core/agent/decouverte.py::classer`) : la
        recherche marche meme quand aucun modele ne repond.
        """
        from core.agent.decouverte import classer

        exclus = set(exclure)
        candidats = [f for f in self.fiches() if f.id not in exclus]
        return [fiche for fiche, _score in classer(besoin, candidats)[:max(0, nombre)]]

    async def demander(
        self, espace: str, requete: str, contexte: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Confie `requete` a l'agent de `espace`, et rend son resultat tel quel.

        Rien n'est resume ni reformule ici : le resultat structure de l'agent
        appele est la seule chose que l'appelant doit interpreter. Une erreur
        de l'agent appele n'est pas rattrapee — elle doit remonter, exactement
        comme si l'espace avait ete appele directement depuis la passerelle.
        """
        capacite = self._capacites.get(espace)
        if capacite is None:
            raise CapaciteInconnue(espace, self.espaces())
        logger.info("Capacite demandee : %s -> %r", espace, requete[:60])
        return await capacite.run(requete, context=contexte)


def adaptateur_synchrone(
    fonction: Callable[[str], str],
    nom_agent: str,
    est_un_echec: Optional[Callable[[str], bool]] = None,
    description: str = "",
    identifiant: str = "",
) -> Capacite:
    """Enveloppe un outil synchrone (`fn(texte) -> str`) dans le contrat `run`.

    La fonction synchrone est executee dans un thread via `asyncio.to_thread` :
    certains outils font de l'I/O ou du calcul et ne doivent jamais bloquer la
    boucle asyncio qui sert simultanement les autres requetes du backend.

    `est_un_echec` : un outil qui rend une chaine ne peut pas dire « j'ai
    echoue » autrement. Sans ce predicat, l'adaptateur annoncait
    `status: "success"` en portant « ❌ Erreur … No module named 'lightrag' » —
    un echec presente comme une reponse (mesure du 01/09/2026). Le predicat
    appartient a l'outil, jamais a l'appelant.
    """

    class _Adaptateur:
        async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            reponse = await asyncio.to_thread(fonction, user_input)
            rate = bool(est_un_echec and est_un_echec(reponse))
            return {"status": "error" if rate else "success",
                    "agent": nom_agent, "response": reponse}

    adaptateur = _Adaptateur()
    # Lue par `BaseAgent._liste_des_collegues` : un collegue sans description
    # est un nom que le modele ne sait pas quand appeler.
    adaptateur.description = description
    # Un outil qui declare un identifiant accepte d'etre consulte par tous :
    # la decouverte le trouve (`core/agent/decouverte.py::est_un_agent`).
    if identifiant:
        adaptateur.identifiant = identifiant
        adaptateur.name = nom_agent
    return adaptateur
