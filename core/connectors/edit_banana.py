"""Connecteur ARENA pour le moteur Edit-Banana — conversion d'images de diagrammes en DrawIO.

Le moteur Edit-Banana reste un moteur externe (DEC-0008, DEC-0039) sous licence
GNU AGPL-3.0. Il s'exécute dans un processus séparé avec son propre environnement
Python et ses poids SAM3.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.diagramme.edit_banana import (
    ConfigurationEditBanana,
    ErreurEditBanana,
    ServiceEditBanana,
)

logger = logging.getLogger("usman.connecteurs.edit_banana")


class ConnecteurEditBanana(Connecteur):
    """Connecteur permettant de transformer des diagrammes/images en documents DrawIO (.drawio)."""

    service = "edit_banana"
    nom = "edit_banana"

    def __init__(
        self,
        configuration: Optional[ConfigurationEditBanana] = None,
        service_moteur: Optional[ServiceEditBanana] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.configuration = configuration or ConfigurationEditBanana.depuis_environnement()
        self.service_moteur = service_moteur or ServiceEditBanana(self.configuration)

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "diagram_to_drawio": Capacite(
                nom="diagram_to_drawio",
                action="document",
                description="Transforme une image de diagramme ou schéma en document DrawIO modifiable (.drawio).",
                ecriture=True,
            ),
        }

    def authentifier(self) -> bool:
        return self.service_moteur.etat().disponible

    def sonder(self) -> Sante:
        """Mesure l'état opérationnel du moteur Edit-Banana et de SAM3."""
        etat = self.service_moteur.etat()
        if etat.disponible:
            avertissement = " (Mode CPU - exécution lente)" if etat.cpu_lent else ""
            return Sante(
                etat=EtatSante.OPERATIONNEL,
                message=f"Edit-Banana opérationnel{avertissement} (révision: {etat.version[:7]}).",
                mesure_le=_maintenant(),
            )

        if (
            not self.configuration.licence_acceptee
            or self.configuration.racine is None
            or self.service_moteur._python() is None
            or not etat.sam3_disponible
        ):
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=etat.raison,
                ce_qui_manque=etat.ce_qui_manque,
                mesure_le=_maintenant(),
            )

        return Sante(
            etat=EtatSante.EN_PANNE,
            message=etat.raison,
            ce_qui_manque=etat.ce_qui_manque,
            mesure_le=_maintenant(),
        )

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom != "diagram_to_drawio":
            return echec(capacite.nom, self.nom, f"Capacité non gérée : {capacite.nom}")

        image = parametres.get("image") or parametres.get("entree") or parametres.get("chemin")
        if not image:
            return echec("diagram_to_drawio", self.nom, "Aucune image de diagramme fournie.")

        nom_source = str(parametres.get("nom_source") or "")
        if not nom_source and isinstance(image, (str, Path)):
            nom_source = Path(image).name

        try:
            # Exécution dans une boucle d'événements existante ou nouvelle
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Création d'une tâche ou exécution via un runner dédié
                fut = asyncio.run_coroutine_threadsafe(
                    self.service_moteur.convertir(image, nom_source=nom_source), loop
                )
                resultat = fut.result()
            else:
                resultat = asyncio.run(self.service_moteur.convertir(image, nom_source=nom_source))
        except ErreurEditBanana as erreur:
            logger.warning("Échec de conversion Edit-Banana : %s", erreur)
            return echec("diagram_to_drawio", self.nom, str(erreur))
        except Exception as erreur:  # noqa: BLE001
            logger.exception("Erreur inattendue dans ConnecteurEditBanana")
            return echec("diagram_to_drawio", self.nom, f"Erreur interne ({type(erreur).__name__}: {erreur}).")

        detail = {
            "moteur": "Edit-Banana",
            "format_cible": "drawio",
            "taille_apres_octets": resultat.taille_octets,
            "url": resultat.url,
            "device": resultat.device,
            "duree_secondes": resultat.duree_secondes,
            "limites_qualite": resultat.limites_qualite,
            "source_sha256": resultat.source_sha256,
        }

        return succes(
            "diagram_to_drawio",
            self.nom,
            message=f"Diagramme converti en document DrawIO « {resultat.sortie.name} » ({resultat.taille_octets} octets).",
            preuve=str(resultat.sortie),
            **detail,
        )
