"""Connecteur sécurité chantier — appelle SiteGuard (C-Nekopedia/SiteGuard,
MIT) par HTTP, un programme SÉPARÉ installé à côté de ce dépôt, jamais dedans.

**Licence, vérifiée avant d'écrire une ligne.** Le code de SiteGuard est MIT.
Mais SiteGuard s'appuie lui-même sur Ultralytics YOLO — dual licence
AGPL-3.0 (open source) / licence commerciale Ultralytics (usage
propriétaire fermé sans les obligations AGPL). C'est SA dépendance, dans SON
processus : ARENA ne l'importe jamais, il appelle son API REST comme
n'importe quel service tiers — même frontière que VoiceStudio (AGPL,
`core/connectors/audio_voix.py`) et Formbricks (AGPLv3, DEC-0052). Les poids
du modèle livrés par SiteGuard (`yolo26n_ppe.pt`) sont entraînés sur un jeu
de données lui-même AGPL-3.0 : une question de licence distincte (mission
§12, « licences des modèles/datasets séparément des licences des dépôts »)
qui reste entièrement du côté de SiteGuard — ARENA ne télécharge, ne copie
ni ne redistribue ce fichier de poids, il appelle un service déjà en place.

**Une détection, jamais un verdict** (mission §6) : les résultats restent
des observations probabilistes — `core/production/securite_chantier.py`
porte le rappel de prudence dans chaque rapport. Aucune image n'est
persistée par ce connecteur : elle est envoyée telle quelle à SiteGuard pour
la durée de l'appel HTTP, jamais écrite sur disque ici.
"""
import base64
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.securite_chantier import depuis_detection, formater

logger = logging.getLogger("usman.connecteurs.securite_chantier")

#: Aucune URL par défaut (DEC-0002) : un service local installé à côté,
#: jamais deviné. Lu à l'appel (pas au chargement du module) pour que les
#: tests puissent le fixer par variable d'environnement.
def _base_url() -> str:
    return os.getenv("SITEGUARD_BASE_URL", "").strip().rstrip("/")


CE_QUI_MANQUE = (
    "SiteGuard n'est pas configuré : installer C-Nekopedia/SiteGuard à côté "
    "(jamais dans ce dépôt), le lancer (`uvicorn app.main:app --port 8000` "
    "depuis apps/server/, voir son README), puis "
    "SITEGUARD_BASE_URL=http://127.0.0.1:8000 dans .env."
)

DUREE_SONDE_SECONDES = 60.0

#: Au-delà, on refuse plutôt que d'envoyer une image énorme à un service
#: local — aucune photo de chantier n'approche cette taille.
TAILLE_MAX_OCTETS = 25 * 1024 * 1024


class ConnecteurSecuriteChantier(Connecteur):
    """Détecte personnes/EPI sur une photo de chantier, via SiteGuard."""

    service = "securite_chantier"
    nom = "securite_chantier"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "analyser": Capacite(
                nom="analyser", action="read",
                description=(
                    "Détecte personnes et équipements de sécurité (casque, gilet...) "
                    "sur une photo de chantier via SiteGuard."),
                ecriture=False),
        }

    def authentifier(self) -> bool:
        """Vrai : un appel HTTP local, aucun identifiant à présenter."""
        return True

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        base_url = _base_url()
        if not base_url:
            sante = Sante(etat=EtatSante.NON_CONFIGURE, message="SITEGUARD_BASE_URL absent.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            try:
                with httpx.Client(timeout=5.0) as client:
                    reponse = client.get(f"{base_url}/health")
                if reponse.status_code == 200:
                    sante = Sante(etat=EtatSante.OPERATIONNEL,
                                 message="SiteGuard répond.", mesure_le=_maintenant())
                else:
                    sante = Sante(etat=EtatSante.EN_PANNE,
                                 message=f"SiteGuard répond {reponse.status_code}.",
                                 mesure_le=_maintenant())
            except httpx.HTTPError as erreur:
                sante = Sante(etat=EtatSante.NON_CONFIGURE,
                             message=f"SiteGuard injoignable : {erreur}",
                             ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        image_base64 = str(parametres.get("image_base64") or "").strip()
        nom_fichier = str(parametres.get("nom_fichier") or "chantier.jpg").strip()
        if not image_base64:
            return echec(action=capacite.nom, cible=self.nom, message="Aucune image fournie.")

        try:
            octets = base64.b64decode(image_base64)
        except Exception as erreur:  # noqa: BLE001 — un base64 invalide est un echec, jamais un crash
            return echec(action=capacite.nom, cible=self.nom, message=f"Image illisible : {erreur}")

        if len(octets) > TAILLE_MAX_OCTETS:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=(f"Image trop volumineuse ({len(octets) // (1024 * 1024)} Mo, "
                         f"plafond {TAILLE_MAX_OCTETS // (1024 * 1024)} Mo)."))

        base_url = _base_url()
        try:
            with httpx.Client(timeout=30.0) as client:
                reponse = client.post(
                    f"{base_url}/api/v1/detection/image",
                    files={"file": (nom_fichier, octets)})
        except httpx.HTTPError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"SiteGuard injoignable : {erreur}")

        if reponse.status_code != 200:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"SiteGuard a refusé l'analyse ({reponse.status_code}) : {reponse.text}")

        detail = reponse.json()
        rapport = depuis_detection(nom_fichier, detail)
        return succes(
            action=capacite.nom, cible=self.nom,
            message=formater(rapport), preuve=nom_fichier,
            personnes=rapport.personnes,
            risques=[
                {"type": r.type, "niveau": r.niveau, "message": r.message, "compte": r.compte}
                for r in rapport.risques],
            resume=formater(rapport),
        )
