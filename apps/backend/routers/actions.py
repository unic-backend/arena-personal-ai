"""Les actions : ce qui s'est passe, et ce qui attend un accord.

Deux choses vivent ici, et elles sont volontairement separees.

**La chronologie** (`GET /api/actions`) est le passe : ce qu'ARENA a tente, sur
quoi, et ce qui en est sorti. Lecture seule.

**La file d'attente** (`/api/actions/pending`, `confirm`, `cancel`) est le
present : ce qui est prepare et ne partira que si le proprietaire le dit. C'est
le §18 de la specification — ACTION, CIBLE, RISQUE, RESULTAT ATTENDU, puis
« j'envoie ? ».

Un point qui n'est pas une precaution de style : **confirmer ne rend jamais un
succes fabrique**. La route rend le `ResultatAction` de l'execution, tel quel.
Un envoi refuse, perime ou en panne repond 200 avec un corps qui le dit — le
code HTTP porte le sort de la requete, le corps porte le sort de l'action.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.backend.runtime import acces, file_attente, journal
from apps.backend.security import limiter_debit, verify_api_key
from core.actions.resultat import Statut
from core.actions.timeline import to_dict

logger = logging.getLogger("usman.backend")

router = APIRouter()

# Une chronologie n'est pas un export : au-dela, on pagine plutot que de tout
# charger en memoire.
LIMITE_MAX = 500


@router.get("/api/actions", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_chronologie(
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    cible: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Rend les actions les plus recentes, resume compris.

    Un journal vide rend un resume a zero et une liste vide — jamais une erreur.
    « Rien ne s'est passe » est une reponse, pas une panne.
    """
    return to_dict(journal.dernieres(limite=limite, cible=cible))


@router.get("/api/actions/pending",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_en_attente(
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
) -> Dict[str, Any]:
    """Les actions preparees qui attendent un accord.

    Les actions perimees n'y figurent pas : une liste qui montre des actions
    mortes fait cliquer sur des actions mortes.
    """
    en_attente = file_attente.en_attente(limite=limite)
    return {
        "total": len(en_attente),
        "actions": [action.to_dict() for action in en_attente],
    }


@router.post("/api/actions/{identifiant}/confirm",
             dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def confirmer(identifiant: str) -> Dict[str, Any]:
    """Le « oui ». C'est le seul chemin par lequel une action preparee part.

    Confirmer deux fois n'execute qu'une fois : la seconde reponse rappelle le
    resultat de la premiere au lieu d'agir a nouveau.
    """
    resultat = file_attente.confirmer(identifiant)

    # Un identifiant inconnu est une erreur d'adressage, pas un echec d'action.
    if resultat.statut is Statut.NON_IMPLEMENTE and "Aucune action" in resultat.message:
        raise HTTPException(status_code=404, detail=resultat.message)

    return resultat.to_dict()


@router.post("/api/actions/{identifiant}/cancel",
             dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def annuler(identifiant: str) -> Dict[str, Any]:
    """Abandonne une action preparee. Rien ne part, et rien ne partira."""
    action = file_attente.lire(identifiant)
    if action is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune action en attente sous l'identifiant « {identifiant} ».",
        )

    annulee = file_attente.annuler(identifiant)
    apres = file_attente.lire(identifiant)
    return {
        "annulee": annulee,
        "etat": apres.etat.value if apres else "INCONNU",
        "message": (
            "Action annulee. Rien n'a ete envoye." if annulee
            else f"Action deja {apres.etat.value if apres else 'traitee'} : rien n'a change."
        ),
    }


@router.get("/api/permissions", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_permissions(compte: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Ce qu'ARENA a le droit de faire, resolu, coupe-circuits compris.

    Le proprietaire doit pouvoir le voir sans relire deux fichiers YAML — et le
    voir **applique**, regles de compte comprises. Sans cette route,
    `politique.resume()` existait sans que rien ne la lise : c'est exactement le
    defaut d'`agent_logs`, et il ne recommence pas ici.

    Les regles par compte sont ce que la specification appelle les politiques
    d'automatisation : autoriser franchement `email.send` sur un compte precis,
    c'est declarer qu'ARENA envoie sans demander depuis ce compte-la.
    """
    resolu: Dict[str, Dict[str, Any]] = {}
    for service in acces.politique.services():
        resolu[service] = {}
        for action in acces.politique.actions(service):
            autorisation = acces.verifier(service, action, compte)
            corps = autorisation.to_dict()
            corps["coupe_circuit"] = acces.interrupteur_de(service, action)
            resolu[service][action] = corps

    return {
        "compte": compte,
        "coupe_circuits": dict(acces.permissions.permissions),
        "services": resolu,
    }
