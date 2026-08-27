"""Le point unique ou l'on demande « ai-je le droit ? ».

Deux couches decident, et **la plus stricte gagne, toujours** :

- les neuf booleens de `config/permissions.yaml` sont des **coupe-circuits
  generaux**. `PUBLISH: false` veut dire : rien ne se publie, nulle part, quoi
  que dise le reste. Le proprietaire doit pouvoir tout eteindre d'une ligne.
- `config/permissions_services.yaml` decide finement, par compte, service et
  action, a l'interieur de ce que les coupe-circuits laissent passer.

L'ordre importe. Si la politique fine pouvait passer devant, une modification du
fichier des services rallumerait ce que le proprietaire a eteint globalement —
et il ne le saurait pas. Un interrupteur general qu'une configuration peut
contourner n'est pas un interrupteur.

Effet de bord voulu : sept des neuf booleens ne gouvernaient rien du tout
(mesure le 2026-08-27). `SEND_MESSAGES`, `DELETE` et `PUBLISH` gouvernent
desormais dix actions, declarees dans le fichier des services et non ici.
"""
import logging
from typing import Optional

from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import (
    Autorisation,
    Decision,
    PolitiqueDePermissions,
)

logger = logging.getLogger("usman.security.controle")

# Origine rendue quand c'est le coupe-circuit qui a tranche. Elle est distincte
# de « service » et « compte » pour qu'un refus dise ou aller le lever.
ORIGINE_COUPE_CIRCUIT = "coupe-circuit"

# Liens qu'aucune configuration ne peut defaire.
#
# Le fichier des services declare quel coupe-circuit gouverne quelle action, et
# c'est bien : le proprietaire doit pouvoir en ajouter. Mais si ce meme fichier
# pouvait **retirer** un lien, il suffirait d'effacer une ligne pour qu'un
# `PUBLISH: false` cesse de proteger quoi que ce soit. Un interrupteur general
# qu'une configuration peut debrancher n'est pas un interrupteur.
#
# Ce plancher vit donc dans le code, comme la regle « action inconnue = refusee ».
# Le fichier peut l'etendre ; il ne peut pas l'entamer.
INTERRUPTEURS_OBLIGATOIRES = {
    ("social", "publish"): "PUBLISH",
    ("social", "schedule"): "PUBLISH",
    ("website", "publish"): "PUBLISH",
    ("business_profile", "update"): "PUBLISH",
    ("email", "send"): "SEND_MESSAGES",
    ("social", "reply"): "SEND_MESSAGES",
    ("business_profile", "reply"): "SEND_MESSAGES",
    ("email", "delete"): "DELETE",
    ("calendar", "delete"): "DELETE",
    ("website", "delete"): "DELETE",
}


class ControleAcces:
    """Reunit les coupe-circuits generaux et la politique fine.

    Les deux objets sont injectes plutot que fabriques : un test doit pouvoir
    fournir les siens, et `runtime.py` fournit ceux de la plateforme.
    """

    def __init__(
        self,
        permissions: Optional[PermissionManager] = None,
        politique: Optional[PolitiqueDePermissions] = None,
    ) -> None:
        self.permissions = permissions or PermissionManager()
        self.politique = politique or PolitiqueDePermissions()

    def interrupteur_de(self, service: str, action: str) -> Optional[str]:
        """Le coupe-circuit qui gouverne cette action, s'il y en a un.

        Le plancher du code est consulte en premier : ce que le proprietaire
        ajoute dans son fichier s'y ajoute, mais rien ne l'en retire.
        """
        oblige = INTERRUPTEURS_OBLIGATOIRES.get((service, action))
        if oblige:
            return oblige

        regle = self.politique.regle(service, action)
        if regle is None:
            return None
        nom = regle.get("interrupteur")
        return str(nom) if nom else None

    def verifier(
        self, service: str, action: str, compte: Optional[str] = None
    ) -> Autorisation:
        """Rend l'autorisation finale, coupe-circuit compris.

        Args:
            service: `email`, `calendar`, `website`, `social`…
            action: `read`, `send`, `publish`, `delete`…
            compte: le compte concerne, quand il y en a un.

        Returns:
            Une `Autorisation`. Si un coupe-circuit est eteint, la decision est
            `DENIED` et `origine` vaut « coupe-circuit » — le refus dit ainsi ou
            aller le lever, ce qu'un simple « DENIED » ne dirait pas.
        """
        autorisation = self.politique.decider(service, action, compte)

        interrupteur = self.interrupteur_de(service, action)
        if interrupteur and not self.permissions.is_allowed(interrupteur):
            logger.warning(
                "%s.%s refuse par le coupe-circuit general %s.", service, action, interrupteur,
            )
            return Autorisation(
                decision=Decision.REFUSE,
                risque=autorisation.risque,
                service=service,
                action=action,
                compte=compte,
                origine=f"{ORIGINE_COUPE_CIRCUIT}:{interrupteur}",
            )

        return autorisation
