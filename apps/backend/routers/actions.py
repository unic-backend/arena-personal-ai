"""Les actions : ce qui s'est passe, ce qui attend un accord, et ce que ca a coute.

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

from apps.backend.runtime import (
    acces,
    file_attente,
    journal,
    mesures_execution,
    statistiques_routage,
)
from apps.backend.security import limiter_debit, verify_api_key
from core.actions.resultat import Statut
from core.actions.timeline import to_dict
from core.execution.mesures import Rapport, non_lancee, resume_chiffre
from core.execution.voies import ORDRE, budget_de
from core.models.statistiques import LIMITE_PAR_DEFAUT as LIMITE_PASSAGES
from core.observabilite.fil import LONGUEUR_MAX as LONGUEUR_MAX_FIL

logger = logging.getLogger("usman.backend")

router = APIRouter()

# Une chronologie n'est pas un export : au-dela, on pagine plutot que de tout
# charger en memoire.
LIMITE_MAX = 500

#: Ce qu'on repond pour une voie qu'aucune demande n'a encore empruntee. La
#: ligne reste au tableau : c'est elle qui dit ce qui n'a pas ete mesure.
JAMAIS_EMPRUNTEE = "aucune demande n'a encore emprunte cette voie"


def _ligne(mesure) -> Dict[str, Any]:
    """Une mesure en JSON. `secondes` vaut `null` quand il n'y a pas de duree."""
    return {
        "nom": mesure.nom,
        "voie": mesure.voie.value,
        "etat": mesure.etat,
        # Jamais 0 pour une absence : `null` traverse l'API tel quel.
        "secondes": mesure.secondes,
        "cible_secondes": budget_de(mesure.voie).objectif_secondes,
        "verdict": mesure.verdict,
        "detail": mesure.detail,
    }


@router.get("/api/actions", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_chronologie(
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    cible: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None, max_length=LONGUEUR_MAX_FIL),
) -> Dict[str, Any]:
    """Rend les actions les plus recentes, resume compris.

    Un journal vide rend un resume a zero et une liste vide — jamais une erreur.
    « Rien ne s'est passe » est une reponse, pas une panne.

    `request_id` est ce qui rend une demande suivable de bout en bout (13/09/2026) :
    l'identifiant que la reponse HTTP a renvoye dans `X-Request-ID` retrouve
    **exactement** les actions que cette demande-la a causees. Sans lui,
    « ce truc de ce matin n'a pas marche » obligeait a lire trente actions pour
    deviner lesquelles venaient de la phrase du proprietaire.

    Les actions d'avant cette date portent `requete = null`, ce qui est vrai :
    elles n'ont jamais eu de fil. Elles ne sont donc rendues par aucun filtre,
    et c'est voulu — les attribuer a une demande serait une trace fabriquee.
    """
    return to_dict(journal.dernieres(limite=limite, cible=cible, requete_id=request_id))


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


@router.get("/api/models/statistics",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_statistiques_de_routage(
    limite: int = Query(default=LIMITE_PASSAGES, ge=1, le=50_000),
) -> Dict[str, Any]:
    """Ce que chaque type de tache a reellement donne, fournisseur par fournisseur.

    Le manque que ceci comble (audit PHASE 0, section E) : le routeur choisissait
    — d'abord sur la confidentialite, ce qui est la bonne garantie — mais rien ne
    gardait trace de ce que ce choix donnait. Rien ne disait que Groq echoue une
    fois sur trois sur `CODE_EXECUTION` alors qu'il tient sur `CHAT`.

    Trois choses que cette reponse ne fait jamais :

    - **elle ne rend aucun taux sur zero passage.** `null`, jamais `0` : un
      fournisseur jamais essaye n'a pas « 0 % de reussite » ;
    - **elle ne rend aucune qualite.** `qualite` vaut toujours `null`, et le
      rapport dit pourquoi — il n'existe pas de source honnete pour un tel
      score ici ;
    - **elle ne change rien au routage.** Ces mesures ne sont lues par personne
      au moment de choisir : le classement de confidentialite reste seul maitre.
    """
    return statistiques_routage.par_type_de_tache(limite=limite)


@router.get("/api/observability",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_mesures() -> Dict[str, Any]:
    """Ce que les reponses ont reellement coute, face a ce que les voies promettent.

    Le tableau porte les deux : les tours chronometres, et **les voies que
    personne n'a encore empruntees**, marquees `UNKNOWN`. Une cible sans mesure
    n'est ni tenue ni manquee — son verdict est `NON_MESURE`, jamais un chiffre
    fabrique pour remplir la colonne.
    """
    rapport = Rapport(mesures=list(mesures_execution.mesures))

    # Les voies jamais empruntees entrent au rapport comme non lancees : sans
    # elles, le tableau ne montrerait que ce qui a marche.
    empruntees = {mesure.voie for mesure in rapport.mesures}
    for voie in ORDRE:
        if voie not in empruntees:
            rapport.ajouter(non_lancee(f"voie {voie.value}", voie, JAMAIS_EMPRUNTEE))

    mesurees = rapport.mesurees
    return {
        "mesures": [_ligne(mesure) for mesure in rapport.mesures],
        "tableau": rapport.rendre(),
        "resume": {
            "mesurees": len(mesurees),
            "unknown": len(rapport.manquantes),
            "hors_budget": len(rapport.hors_budget),
            # `None` quand rien n'a encore ete mesure : un 0.0 se lirait comme
            # « instantane ».
            "mediane_secondes": resume_chiffre(mesurees),
        },
        "cibles": {voie.value: budget_de(voie).objectif_secondes for voie in ORDRE},
    }
