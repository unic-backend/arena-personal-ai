"""Connecteur Formbricks : sondages/feedback, par une instance EXTERNE — jamais du code copie.

Demande directe, derniere des trois integrations mises en attente (avec
OpenUI/DEC-0050 et txtai/DEC-0051) : integrer Formbricks (formbricks/
formbricks) comme capacite de sondage/feedback.

**La licence commande la forme, verifiee avant d'ecrire une ligne** (clone
reel, `formbricks/formbricks` @ `4f597cb`, 05/09/2026) : le coeur du produit
est **AGPLv3** ; `apps/web/modules/ee/` (Enterprise) sous licence separee ;
seuls `packages/js`, `packages/android`, `packages/ios`, `packages/api`
(des SDK clients, pas le serveur) sont MIT. Le README de Formbricks dit
lui-meme ne proposer aucune licence de « white-labeling ». **Aucune ligne de
code de ce depot n'est copiee ici** — ce fichier appelle son API REST
management, documentee et publique (`openapi.yml`, et les routes reelles
sous `apps/web/app/api/v1/management/`, verifiees dans le code source),
par HTTP — la meme frontiere que VoiceStudio (AGPL-3.0,
`core/connectors/audio_voix.py`) : une simple agregation par appel externe
n'etend pas les obligations de l'AGPL a qui l'appelle ; copier son code
le ferait.

**Aucune URL par defaut.** Contrairement a VoiceStudio (qui suppose
`127.0.0.1`), Formbricks n'a pas d'adresse par defaut : `FORMBRICKS_BASE_URL`
doit etre fournie explicitement — l'absence est `NON_CONFIGURE`, jamais
une URL cloud (`https://app.formbricks.com`) devinee. Utiliser une instance
cloud (plutot qu'auto-hebergee) envoie de vraies donnees de reponse
(potentiellement client/personnelles, mission §23) chez un tiers — c'est
au proprietaire de le choisir explicitement, jamais un defaut d'ARENA
(DEC-0002).

**Deux regles supplementaires :**

1. **`creer` est une CONFIRMATION**, pas une lecture : publier un sondage
   est une action visible d'un tiers (l'instance Formbricks, et quiconque y
   repond), comme une generation video ou un envoi de mail.
2. **Les reponses ne sont jamais ecrites dans la memoire personnelle
   d'ARENA.** Ce connecteur rend les donnees brutes a l'appelant ; les
   injecter dans `core/memory/` sans autorisation explicite serait exactement
   ce que la mission interdit (§22).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.formbricks")

DELAI_SECONDES = 15.0

#: Un seul type de question v1, volontairement : couvre le cas reel de la
#: mission (« un petit questionnaire de feedback »). Le schema complet de
#: Formbricks (packages/types/surveys/types.ts) porte une vingtaine de types
#: de questions — en ajouter un second sans besoin reel serait une capacite
#: decorative.
TYPE_QUESTION_OUVERTE = "openText"


def _configuration() -> Optional[Dict[str, str]]:
    base_url = os.getenv("FORMBRICKS_BASE_URL", "").strip()
    cle_api = os.getenv("FORMBRICKS_API_KEY", "").strip()
    workspace_id = os.getenv("FORMBRICKS_WORKSPACE_ID", "").strip()
    if not (base_url and cle_api and workspace_id):
        return None
    return {"base_url": base_url.rstrip("/"), "cle_api": cle_api, "workspace_id": workspace_id}


class ConnecteurFormbricks(Connecteur):
    """Sondages/feedback via une instance Formbricks EXTERNE, jamais du code vendu."""

    service = "formbricks"
    nom = "formbricks"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "creer": Capacite(
                nom="creer", action="survey",
                description="Cree un sondage a une question (texte libre) sur l'instance configuree.",
                ecriture=True),
            "lister": Capacite(
                nom="lister", action="read",
                description="Liste les sondages de l'instance configuree.",
                ecriture=False),
            "obtenir": Capacite(
                nom="obtenir", action="read",
                description="Un sondage par identifiant.",
                ecriture=False),
            "reponses": Capacite(
                nom="reponses", action="read",
                description="Les reponses brutes d'un sondage — jamais ecrites dans la memoire.",
                ecriture=False),
            "analyser": Capacite(
                nom="analyser", action="read",
                description="Compte/agrege les reponses deja recues — calcule ici, pas par Formbricks.",
                ecriture=False),
        }

    def sonder(self) -> Sante:
        config = _configuration()
        if config is None:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Aucune instance Formbricks configuree.",
                ce_qui_manque="FORMBRICKS_BASE_URL, FORMBRICKS_API_KEY et FORMBRICKS_WORKSPACE_ID "
                              "(auto-hebergee de preference — DEC-0002)",
                mesure_le=_maintenant())
        try:
            with httpx.Client(timeout=10.0) as client:
                reponse = client.get(f"{config['base_url']}/api/v1/management/me",
                                     headers={"x-api-key": config["cle_api"]})
        except httpx.HTTPError as erreur:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"Instance Formbricks injoignable : {erreur.__class__.__name__}.",
                         ce_qui_manque=f"une instance reellement joignable sur {config['base_url']}",
                         mesure_le=_maintenant())
        if reponse.status_code == 401:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="FORMBRICKS_API_KEY refusee par l'instance.",
                         ce_qui_manque="une cle API valide",
                         mesure_le=_maintenant())
        if reponse.status_code >= 400:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"Instance Formbricks a repondu {reponse.status_code}.",
                         ce_qui_manque="une instance en bon etat",
                         mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message=f"Instance Formbricks joignable sur {config['base_url']}.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : l'identifiant est la cle API, verifiee par `sonder()`, pas ici."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        config = _configuration()
        if config is None:
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque="FORMBRICKS_BASE_URL, FORMBRICKS_API_KEY, FORMBRICKS_WORKSPACE_ID")

        methode = getattr(self, f"_{capacite.nom}", None)
        if methode is None:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Capacite « {capacite.nom} » non implementee.")
        try:
            return methode(config, **parametres)
        except httpx.HTTPError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Instance Formbricks injoignable : {erreur.__class__.__name__}.")

    def _en_tetes(self, config: Dict[str, str]) -> Dict[str, str]:
        return {"x-api-key": config["cle_api"]}

    def _creer(self, config: Dict[str, str], **parametres: Any) -> ResultatAction:
        titre = str(parametres.get("titre") or "").strip()
        question = str(parametres.get("question") or "").strip()
        if not titre or not question:
            return echec(action="creer", cible=self.nom, message="titre et question sont requis.")

        corps = {
            "name": titre,
            "workspaceId": config["workspace_id"],
            "questions": [{
                "id": "q1", "type": TYPE_QUESTION_OUVERTE,
                "headline": {"default": question}, "required": bool(parametres.get("requis", True)),
            }],
        }
        with httpx.Client(timeout=DELAI_SECONDES) as client:
            reponse = client.post(f"{config['base_url']}/api/v1/management/surveys",
                                  headers=self._en_tetes(config), json=corps)
        if reponse.status_code >= 400:
            return echec(action="creer", cible=self.nom,
                         message=f"Creation refusee ({reponse.status_code}) : {reponse.text[:300]}")
        donnees = reponse.json()
        survey_id = donnees.get("data", donnees).get("id")
        if not survey_id:
            return echec(action="creer", cible=self.nom,
                         message="Reponse sans identifiant de sondage exploitable.")
        return succes(action="creer", cible=self.nom,
                     message=f"Sondage « {titre} » cree.", preuve=str(survey_id),
                     survey_id=survey_id)

    def _lister(self, config: Dict[str, str], **parametres: Any) -> ResultatAction:
        with httpx.Client(timeout=DELAI_SECONDES) as client:
            reponse = client.get(f"{config['base_url']}/api/v1/management/surveys",
                                 headers=self._en_tetes(config))
        if reponse.status_code >= 400:
            return echec(action="lister", cible=self.nom,
                         message=f"Liste refusee ({reponse.status_code}).")
        donnees = reponse.json().get("data", [])
        return succes(action="lister", cible=self.nom,
                     message=f"{len(donnees)} sondage(s).", preuve=str(len(donnees)),
                     sondages=donnees)

    def _obtenir(self, config: Dict[str, str], **parametres: Any) -> ResultatAction:
        survey_id = str(parametres.get("survey_id") or "").strip()
        if not survey_id:
            return echec(action="obtenir", cible=self.nom, message="survey_id est requis.")
        with httpx.Client(timeout=DELAI_SECONDES) as client:
            reponse = client.get(f"{config['base_url']}/api/v1/management/surveys/{survey_id}",
                                 headers=self._en_tetes(config))
        if reponse.status_code == 404:
            return echec(action="obtenir", cible=self.nom, message=f"Sondage {survey_id} introuvable.")
        if reponse.status_code >= 400:
            return echec(action="obtenir", cible=self.nom,
                         message=f"Lecture refusee ({reponse.status_code}).")
        return succes(action="obtenir", cible=self.nom, message=f"Sondage {survey_id}.",
                     preuve=survey_id, sondage=reponse.json().get("data", reponse.json()))

    def _reponses(self, config: Dict[str, str], **parametres: Any) -> ResultatAction:
        survey_id = str(parametres.get("survey_id") or "").strip()
        if not survey_id:
            return echec(action="reponses", cible=self.nom, message="survey_id est requis.")
        with httpx.Client(timeout=DELAI_SECONDES) as client:
            reponse = client.get(f"{config['base_url']}/api/v1/management/responses",
                                 headers=self._en_tetes(config),
                                 params={"surveyId": survey_id})
        if reponse.status_code >= 400:
            return echec(action="reponses", cible=self.nom,
                         message=f"Lecture refusee ({reponse.status_code}).")
        donnees = reponse.json().get("data", [])
        return succes(action="reponses", cible=self.nom,
                     message=f"{len(donnees)} reponse(s) pour {survey_id}.",
                     preuve=str(len(donnees)), reponses=donnees)

    def _analyser(self, config: Dict[str, str], **parametres: Any) -> ResultatAction:
        """Compte/agrege ce que `_reponses` a reellement rendu — jamais un
        chiffre de satisfaction invente : Formbricks ne rend pas de score
        « analytics » pret a l'emploi sur cette API (verifie dans le
        source), donc ARENA calcule sur les donnees brutes, honnetement."""
        brut = self._reponses(config, **parametres)
        if brut.statut.value != "SUCCESS":
            return brut
        reponses: List[Dict[str, Any]] = brut.detail.get("reponses") or []
        return succes(action="analyser", cible=self.nom,
                     message=f"{len(reponses)} reponse(s) analysee(s).",
                     preuve=str(len(reponses)),
                     total_reponses=len(reponses),
                     terminees=sum(1 for r in reponses if r.get("finished")))
