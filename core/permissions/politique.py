"""Permissions par compte, service, action et risque.

Les neuf booleens de `PermissionManager` restent en place et continuent de
gouverner ce qu'ils gouvernaient. Ce module ne les remplace pas : il repond a une
question qu'ils ne savent pas poser.

`SEND_MESSAGES: true` ne peut pas dire « lecture autorisee sur ce compte Gmail,
envoi soumis a confirmation, suppression interdite ». Un booleen unique n'a pas
d'adresse ; une permission en a une, et elle en a quatre morceaux : le compte,
le service, l'action, et le risque que l'action porte.

Trois regles portent ce module :

1. **Une action inconnue est refusee.** C'est la seule regle qui ne se configure
   pas. Une capacite nouvelle n'est jamais autorisee par oubli, et une faute de
   frappe dans le fichier ne devient jamais une ouverture.

2. **Le plus precis gagne, dans les deux sens.** Une regle de compte l'emporte
   sur celle du service — pour ouvrir comme pour fermer. Le proprietaire peut
   autoriser l'envoi automatique sur son compte professionnel et interdire toute
   lecture sur son compte prive.

3. **Le risque ne decide rien.** Il est porte par l'action et affiche au moment
   de demander la confirmation. Un risque eleve n'interdit pas ; il fait voir ce
   qu'on autorise. C'est la decision, et elle seule, qui laisse passer ou non.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.fichier_suivi import date_de

logger = logging.getLogger("usman.security.politique")

FICHIER_POLITIQUE = Path(__file__).resolve().parents[2] / "config" / "permissions_services.yaml"


class Decision(str, Enum):
    """Ce qui arrive a une action demandee."""

    AUTORISE = "ALLOWED"           # elle part
    CONFIRMATION = "CONFIRMATION"  # elle est preparee et attend un « oui »
    REFUSE = "DENIED"              # elle ne part pas


class Risque(str, Enum):
    """Ce que l'action peut couter si elle part a tort."""

    FAIBLE = "LOW"
    MOYEN = "MEDIUM"
    ELEVE = "HIGH"


# Ce que rend une action introuvable. Ecrit ici plutot que dans le fichier : une
# regle de repli qu'on peut configurer n'est plus un repli.
DECISION_PAR_DEFAUT = Decision.REFUSE
RISQUE_INCONNU = Risque.ELEVE


@dataclass(frozen=True)
class Autorisation:
    """La reponse rendue, avec de quoi expliquer d'ou elle vient.

    Attributes:
        decision: laisser passer, demander, ou refuser.
        risque: ce que porte l'action, pour l'afficher a la confirmation.
        service: le service interroge.
        action: l'action interrogee.
        compte: le compte concerne, s'il y en avait un.
        origine: quelle regle a tranche — « compte », « service » ou « defaut ».
            Sans cela, un refus est indiscutable et donc incomprehensible.
    """

    decision: Decision
    risque: Risque
    service: str
    action: str
    compte: Optional[str] = None
    origine: str = "defaut"

    @property
    def autorise(self) -> bool:
        """Vrai seulement si l'action peut partir sans rien demander."""
        return self.decision is Decision.AUTORISE

    @property
    def demande_confirmation(self) -> bool:
        """Vrai si tout peut etre prepare, mais que l'envoi attend un accord."""
        return self.decision is Decision.CONFIRMATION

    @property
    def refuse(self) -> bool:
        """Vrai si l'action ne partira pas, meme confirmee."""
        return self.decision is Decision.REFUSE

    def to_dict(self) -> Dict[str, Any]:
        """Forme transportable, pour l'API et le journal des actions."""
        return {
            "decision": self.decision.value,
            "risque": self.risque.value,
            "service": self.service,
            "action": self.action,
            "compte": self.compte,
            "origine": self.origine,
        }

    def __str__(self) -> str:
        cible = f"{self.compte} / {self.service}" if self.compte else self.service
        return f"{cible} · {self.action} → {self.decision.value} (risque {self.risque.value})"


def _lire_decision(valeur: Any, ou: str) -> Optional[Decision]:
    """Convertit une valeur du fichier, ou rend None en le signalant.

    Une valeur illisible ne devient jamais `ALLOWED` : elle disparait, et le
    repli refuse. Une faute de frappe ferme, elle n'ouvre pas.
    """
    try:
        return Decision(str(valeur).strip().upper())
    except ValueError:
        logger.error(
            "Politique de permissions : decision illisible %r dans %s. "
            "Cette regle est ignoree, donc l'action est refusee.", valeur, ou,
        )
        return None


def _lire_risque(valeur: Any, ou: str) -> Risque:
    """Convertit un niveau de risque, ou retombe sur le plus eleve."""
    try:
        return Risque(str(valeur).strip().upper())
    except ValueError:
        logger.warning(
            "Politique de permissions : risque illisible %r dans %s. "
            "Traite comme HIGH.", valeur, ou,
        )
        return RISQUE_INCONNU


class PolitiqueDePermissions:
    """Repond a « ce compte peut-il faire cette action sur ce service ? ».

    Le fichier est relu quand sa date de modification change.

    Il ne l'etait pas. Mesure du 01/09/2026 : le proprietaire durcissait
    `email/read` en `HIGH` + confirmation obligatoire dans le fichier, et la
    politique continuait d'appliquer `ALLOWED / LOW` jusqu'au redemarrage du
    serveur — `PolitiqueDePermissions` etant un singleton cree a l'import de
    `apps/backend/runtime.py`.

    Le sens du risque compte : une regle **assouplie** qui n'est pas vue ne
    fait rien de dangereux. Une regle **durcie** qui n'est pas vue laisse
    passer ce que le proprietaire venait d'interdire. Et cette docstring
    annoncait exactement la capacite qui manquait — `recharger()` existait,
    etait testee, et personne ne l'appelait.
    """

    def __init__(self, chemin: Optional[Path] = None) -> None:
        # Resolu ici, pas dans la signature : un defaut d'argument est fige a
        # l'import.
        self.chemin = Path(chemin) if chemin is not None else FICHIER_POLITIQUE
        self._services: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._comptes: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.recharger()
        self._date = date_de(self.chemin)

    def _relire_si_change(self) -> None:
        """Relit la politique quand le fichier a change. Jamais sur une horloge."""
        date = date_de(self.chemin)
        if date != self._date:
            self.recharger()
            self._date = date
            logger.info("Politique de permissions relue (%s).",
                        "fichier absent" if date is None else "fichier modifie")

    # --- Lecture du fichier ---------------------------------------------------

    def recharger(self) -> None:
        """Relit le fichier. Un fichier absent ou illisible refuse tout.

        Refuser tout est bruyant et sera remarque tout de suite. Autoriser tout
        par defaut ne se remarque que le jour ou quelque chose est parti.
        """
        try:
            donnees = yaml.safe_load(self.chemin.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            logger.error(
                "Politique de permissions introuvable (%s) : toute action a effet "
                "externe est refusee.", self.chemin,
            )
            donnees = {}
        except Exception as erreur:
            logger.error(
                "Politique de permissions illisible (%s) : toute action a effet "
                "externe est refusee.", erreur,
            )
            donnees = {}

        self._services = donnees.get("services") or {}
        self._comptes = donnees.get("comptes") or {}

    # --- Interrogation --------------------------------------------------------

    def regle(self, service: str, action: str) -> Optional[Dict[str, Any]]:
        """La regle declaree pour une action, telle qu'elle est ecrite, ou None.

        Publique parce que `ControleAcces` a besoin d'y lire le coupe-circuit
        associe. Passer par l'attribut prive marcherait aussi, et se casserait
        au premier remaniement.
        """
        self._relire_si_change()
        regle = (self._services.get(service) or {}).get(action)
        return regle if isinstance(regle, dict) else None

    def _decision_du_compte(
        self, compte: Optional[str], service: str, action: str
    ) -> Optional[Decision]:
        if not compte:
            return None
        self._relire_si_change()
        brute = ((self._comptes.get(compte) or {}).get(service) or {}).get(action)
        if brute is None:
            return None
        # Une regle de compte peut s'ecrire « ALLOWED » ou {decision: ALLOWED}.
        valeur = brute.get("decision") if isinstance(brute, dict) else brute
        return _lire_decision(valeur, f"comptes.{compte}.{service}.{action}")

    def decider(
        self, service: str, action: str, compte: Optional[str] = None
    ) -> Autorisation:
        """Rend l'autorisation pour une action, en disant quelle regle a tranche.

        Args:
            service: `email`, `calendar`, `website`, `social`…
            action: `read`, `send`, `publish`, `delete`…
            compte: l'adresse ou l'identifiant du compte, quand il y en a un.

        Returns:
            Une `Autorisation`. Jamais `None` : une action inconnue est refusee,
            pas ignoree.
        """
        regle = self.regle(service, action)
        risque = _lire_risque(regle.get("risque"), f"{service}.{action}") if regle else RISQUE_INCONNU

        decision_compte = self._decision_du_compte(compte, service, action)
        if decision_compte is not None:
            return Autorisation(decision_compte, risque, service, action, compte, "compte")

        if regle is not None:
            decision = _lire_decision(regle.get("decision"), f"{service}.{action}")
            if decision is not None:
                return Autorisation(decision, risque, service, action, compte, "service")

        logger.info(
            "Aucune regle pour %s.%s : refuse par defaut.", service, action,
        )
        return Autorisation(DECISION_PAR_DEFAUT, risque, service, action, compte, "defaut")

    # --- Lecture d'ensemble ---------------------------------------------------

    def services(self) -> List[str]:
        """Les services declares, tries."""
        return sorted(self._services)

    def actions(self, service: str) -> List[str]:
        """Les actions declarees pour un service, triees."""
        return sorted(self._services.get(service) or {})

    def resume(self, compte: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Toute la politique telle qu'elle s'applique, pour l'afficher.

        Le proprietaire doit pouvoir voir ce qu'ARENA a le droit de faire sans
        relire un fichier YAML — et le voir *resolu*, regles de compte comprises.
        """
        return {
            service: {
                action: self.decider(service, action, compte).to_dict()
                for action in self.actions(service)
            }
            for service in self.services()
        }
