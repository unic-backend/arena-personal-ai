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

import logging
from typing import Any, Callable, Dict, List, Optional, Protocol

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

    def espaces(self) -> List[str]:
        return list(self._capacites)

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
    fonction: Callable[[str], str], nom_agent: str
) -> Capacite:
    """Enveloppe un outil synchrone (`fn(texte) -> str`) dans le contrat `run`.

    Necessaire pour 'documents' : `LightRAGTool.query` rend une chaine, pas le
    dictionnaire structure `{status, agent, response, ...}` que tous les
    agents rendent. Plutot que de faire porter cette difference a chaque
    appelant, elle est absorbee ici, une seule fois.
    """

    class _Adaptateur:
        async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return {"status": "success", "agent": nom_agent, "response": fonction(user_input)}

    return _Adaptateur()
