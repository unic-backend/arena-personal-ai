"""Le cadre commun des connecteurs : ce qu'ils declarent, et ce qu'ils ne peuvent pas.

Un connecteur relie ARENA a un service exterieur — messagerie, agenda, site,
reseau social. La specification en donne la liste des obligations :
authentification, capacites, permissions, sante, lecture, ecriture, erreurs,
quotas, journal. Elles sont toutes ici, et aucune n'est facultative.

L'ancienne base (`social/base/base_connector.py`) declarait deux methodes :
`authenticate` et `publish_video`. Elle ne pouvait porter aucune des sept
autres, et c'est ce qui a permis a un simulateur de se faire passer pour un
connecteur.

**Cinq regles portent ce module, et chacune est une chose qu'un connecteur ne
peut pas faire :**

1. **Executer une capacite qu'il n'a pas declaree.** `capacites()` est la seule
   porte. Un nom absent de ce dictionnaire n'atteint jamais l'implementation :
   un connecteur qui ne declare rien n'expose rien.

2. **Agir avant le controle de permission.** La verification passe avant la
   sante, avant le quota, avant tout. Un refus ne doit meme pas reveler si le
   service est joignable.

3. **Se declarer en bonne sante sans l'avoir mesure.** Une sante qu'on ne sait
   pas dire est `INCONNU`, jamais `OPERATIONNEL`. Une sonde qui leve rend
   `EN_PANNE` avec son erreur — elle ne remonte pas.

4. **Renvoyer autre chose qu'un `ResultatAction`.** Une implementation qui leve,
   ou qui rend un objet libre, devient un `FAILED` portant l'erreur reelle. Rien
   n'est converti en reussite.

5. **Laisser fuir ses identifiants.** Le modele recoit `capacites()`, jamais les
   secrets. Aucune methode publique ne les expose, et le journal les masque.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from apps.backend.rate_limit import LimiteurDebit
from core.actions.attente import FileDAttente
from core.actions.journal import ActionEnregistree, JournalDesActions
from core.actions.resultat import (
    ResultatAction,
    Statut,
    a_confirmer,
    echec,
    non_configure,
    non_implemente,
)
from core.execution.hooks import RegistreDeCrochets
from core.permissions.controle import ControleAcces

logger = logging.getLogger("usman.connecteurs")


class EtatSante(str, Enum):
    """Ce que le connecteur sait de sa propre disponibilite."""

    OPERATIONNEL = "OPERATIONAL"      # interroge, il a repondu
    NON_CONFIGURE = "NOT_CONFIGURED"  # il manque des identifiants ou une declaration
    EN_PANNE = "FAILING"              # configure, mais il ne repond pas
    INCONNU = "UNKNOWN"               # rien n'a ete mesure


@dataclass(frozen=True)
class Sante:
    """L'etat du connecteur, avec la date a laquelle il a ete constate.

    Attributes:
        etat: l'un des quatre etats.
        message: ce qu'un humain doit lire.
        ce_qui_manque: pour `NON_CONFIGURE`, ce qu'il faut fournir.
        mesure_le: horodatage UTC de la mesure, ou None si rien n'a ete mesure.
    """

    etat: EtatSante
    message: str = ""
    ce_qui_manque: str = ""
    mesure_le: Optional[str] = None

    @property
    def utilisable(self) -> bool:
        """Vrai seulement pour un etat mesure et operationnel."""
        return self.etat is EtatSante.OPERATIONNEL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "etat": self.etat.value,
            "message": self.message,
            "ce_qui_manque": self.ce_qui_manque,
            "mesure_le": self.mesure_le,
        }


@dataclass(frozen=True)
class Capacite:
    """Une chose qu'un connecteur sait faire, et sous quelle permission.

    Attributes:
        nom: l'identifiant appele par `executer()`.
        action: l'action telle que la politique de permissions la nomme.
            Distincte du nom : `publish_video` s'autorise via `social.publish`.
        description: une phrase, en francais, lisible par le proprietaire.
        ecriture: True si la capacite modifie quelque chose hors d'ARENA.
        quota_par_minute: plafond d'appels, ou None si le service n'en impose pas.
    """

    nom: str
    action: str
    description: str
    ecriture: bool = False
    quota_par_minute: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Ce que le modele et l'interface voient. Aucun identifiant ici."""
        return {
            "nom": self.nom,
            "action": self.action,
            "description": self.description,
            "ecriture": self.ecriture,
            "quota_par_minute": self.quota_par_minute,
        }


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Connecteur(ABC):
    """Base de tout connecteur vers un service exterieur.

    Une sous-classe fournit trois choses : ses capacites, sa sonde de sante, et
    l'execution d'une capacite. Tout le reste — permissions, quotas, journal,
    traitement des erreurs — est assure ici et ne peut pas etre contourne en
    oubliant de l'appeler.
    """

    #: Nom du service tel que la politique de permissions le connait.
    service: str = ""
    #: Nom lisible du connecteur.
    nom: str = ""

    def __init__(
        self,
        acces: Optional[ControleAcces] = None,
        journal: Optional[JournalDesActions] = None,
        file_attente: Optional[FileDAttente] = None,
        crochets: Optional[RegistreDeCrochets] = None,
    ) -> None:
        self.acces = acces or ControleAcces()
        self.journal = journal
        # Sans file d'attente, une action a confirmer est annoncee mais rien ne
        # la retient : le proprietaire lit « pret a envoyer » et n'a rien a quoi
        # repondre. Avec, elle recoit un identifiant qu'il peut confirmer.
        self.file_attente = file_attente
        # Sans registre, aucun crochet ne tourne : `_conduire()` se comporte
        # exactement comme avant ce module (voir hooks.py).
        self.crochets = crochets
        self._limiteurs: Dict[str, LimiteurDebit] = {}

    # --- Ce qu'une sous-classe doit fournir -----------------------------------

    @abstractmethod
    def capacites(self) -> Dict[str, Capacite]:
        """Les capacites declarees, par nom. Un dictionnaire vide est valide.

        C'est la seule porte : ce qui n'est pas la n'existe pas.
        """

    @abstractmethod
    def sonder(self) -> Sante:
        """Interroge le service et rend son etat reel.

        Ne jamais deduire l'etat de la presence d'un fichier ou d'une variable :
        la question est « repond-il ? », pas « semble-t-il installe ? ».
        """

    @abstractmethod
    def authentifier(self) -> bool:
        """S'authentifie. False tant qu'aucune authentification n'a abouti."""

    @abstractmethod
    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        """Fait le travail. Appele uniquement apres tous les controles."""

    # --- Ce que la base garantit ----------------------------------------------

    def sante(self) -> Sante:
        """Sante mesuree. Une sonde qui leve rend `EN_PANNE`, jamais une exception.

        Un connecteur casse ne doit pas faire tomber l'inventaire des
        connecteurs, ni le serveur qui l'affiche.
        """
        try:
            etat = self.sonder()
        except Exception as erreur:
            logger.error("Sonde de %s en echec : %s", self.nom or self.service, erreur)
            return Sante(
                EtatSante.EN_PANNE,
                message=f"La sonde a echoue : {erreur}",
                mesure_le=_maintenant(),
            )

        if not isinstance(etat, Sante):
            logger.error("Sonde de %s : reponse inexploitable (%r).", self.nom, etat)
            return Sante(EtatSante.INCONNU, message="Sonde inexploitable.")
        return etat

    def _limiteur(self, capacite: Capacite) -> Optional[LimiteurDebit]:
        """Le compteur de la capacite, cree a la premiere utilisation."""
        if not capacite.quota_par_minute:
            return None
        if capacite.nom not in self._limiteurs:
            self._limiteurs[capacite.nom] = LimiteurDebit(capacite.quota_par_minute, 60.0)
        return self._limiteurs[capacite.nom]

    def _journaliser(
        self, resultat: ResultatAction, parametres: Dict[str, Any], niveau: str
    ) -> None:
        """Ecrit l'action. Un journal absent ou en panne n'arrete jamais rien."""
        if self.journal is None:
            return
        self.journal.enregistrer(ActionEnregistree.depuis_resultat(
            resultat, outil=self.nom or self.service,
            parametres=parametres, niveau_permission=niveau,
        ))

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        """Ce qui aura change si l'action part. Affiche avant la confirmation.

        La base rend la description declaree ; une sous-classe precise quand elle
        peut (« un e-mail part vers client@exemple.sn »). Elle ne promet jamais
        un resultat qu'elle ne peut pas connaitre.
        """
        return capacite.description

    def _mettre_en_attente(
        self, capacite: Capacite, cible: str, compte: Optional[str],
        risque: str, parametres: Dict[str, Any],
    ) -> ResultatAction:
        """Depose l'action et rend son identifiant, ou le dit si c'est impossible."""
        message = (f"Pret : {capacite.description}. Risque {risque}. Rien n'est parti.")

        if self.file_attente is None:
            return a_confirmer(action=capacite.nom, cible=cible, message=message, risque=risque)

        try:
            en_attente = self.file_attente.deposer(
                action=capacite.description, cible=cible, risque=risque,
                resultat_attendu=self.resultat_attendu(capacite, **parametres),
                connecteur=self.nom or self.service, capacite=capacite.nom,
                compte=compte, parametres=parametres,
            )
        except ValueError as erreur:
            # Un parametre secret : on refuse la mise en attente plutot que de
            # l'ecrire sur le disque. L'action n'est pas partie non plus.
            logger.error("Mise en attente refusee (%s.%s) : %s", self.nom, capacite.nom, erreur)
            return echec(capacite.nom, cible, f"Mise en attente refusee : {erreur}")

        return a_confirmer(
            action=capacite.nom, cible=cible,
            message=f"{message} Confirme avec l'identifiant {en_attente.identifiant}.",
            risque=risque, en_attente=en_attente.identifiant,
        )

    def executer(
        self, nom_capacite: str, compte: Optional[str] = None, **parametres: Any
    ) -> ResultatAction:
        """Point d'entree normal. Controle, met en attente si besoin, journalise.

        Args:
            nom_capacite: le nom declare dans `capacites()`.
            compte: le compte concerne, quand il y en a un.
            **parametres: les arguments de la capacite.

        Returns:
            Un `ResultatAction`. Jamais None, jamais une exception : une panne
            devient un `FAILED` qui porte son erreur.
        """
        return self._conduire(nom_capacite, compte, parametres, deja_confirmee=False)

    def executer_confirmee(
        self, nom_capacite: str, compte: Optional[str] = None, **parametres: Any
    ) -> ResultatAction:
        """Execute une action **que le proprietaire a confirmee**.

        Reserve a `FileDAttente.confirmer()`. C'est une methode distincte, et non
        un argument `confirmation=True`, pour une raison precise : un argument
        voyagerait dans les `**parametres` d'un appelant quelconque et
        contournerait la confirmation. Une methode, non.

        Ce qu'elle change : une decision `CONFIRMATION` est consideree comme
        satisfaite. Ce qu'elle ne change pas : un `DENIED` refuse toujours. Une
        confirmation repond a une demande d'accord, elle ne leve pas un refus.
        """
        return self._conduire(nom_capacite, compte, parametres, deja_confirmee=True)

    def _conduire(
        self, nom_capacite: str, compte: Optional[str],
        parametres: Dict[str, Any], deja_confirmee: bool,
    ) -> ResultatAction:
        capacite = self.capacites().get(nom_capacite)
        cible = compte or self.nom or self.service

        # 1. Capacite non declaree : elle n'atteint pas l'implementation.
        if capacite is None:
            resultat = non_implemente(
                action=nom_capacite, cible=cible,
                message=f"{self.nom or self.service} ne declare pas la capacite "
                        f"« {nom_capacite} ». Rien n'a ete tente.",
            )
            self._journaliser(resultat, parametres, "INCONNU")
            return resultat

        # 2. Permission avant tout le reste : un refus ne revele meme pas si le
        #    service est joignable.
        autorisation = self.acces.verifier(self.service, capacite.action, compte)
        niveau = autorisation.decision.value

        if autorisation.refuse:
            # Construit directement plutot que par `refuse()` : ce constructeur
            # formule « la permission X est bloquee », ce qui serait faux quand
            # c'est la politique du service, et non un interrupteur, qui refuse.
            resultat = ResultatAction(
                statut=Statut.REFUSE,
                action=capacite.nom, cible=cible,
                message=f"Refuse : {autorisation.origine}. Rien n'a ete envoye.",
                detail={"risque": autorisation.risque.value},
            )
            self._journaliser(resultat, parametres, niveau)
            return resultat

        if autorisation.demande_confirmation and not deja_confirmee:
            resultat = self._mettre_en_attente(capacite, cible, compte,
                                               autorisation.risque.value, parametres)
            self._journaliser(resultat, parametres, niveau)
            return resultat

        # 3. Sante : un connecteur non branche le declare, il ne tente rien.
        etat = self.sante()
        if not etat.utilisable:
            resultat = (
                non_configure(capacite.nom, cible, etat.ce_qui_manque or "une configuration")
                if etat.etat is EtatSante.NON_CONFIGURE
                else echec(capacite.nom, cible, etat.message or f"Service {etat.etat.value}.")
            )
            self._journaliser(resultat, parametres, niveau)
            return resultat

        # 4. Quota : depasser celui d'un service exterieur fait perdre l'acces.
        limiteur = self._limiteur(capacite)
        if limiteur is not None:
            attente = limiteur.secondes_a_attendre(f"{cible}:{capacite.nom}")
            if attente is not None:
                resultat = echec(
                    capacite.nom, cible,
                    f"Quota atteint ({capacite.quota_par_minute}/min). "
                    f"Reessayer dans {int(attente) + 1} s.",
                )
                self._journaliser(resultat, parametres, niveau)
                return resultat

        # 4.5. Crochets avant execution : un veto OPERATIONNEL, jamais une
        #    permission — il tourne apres les quatre controles ci-dessus, il
        #    ne peut en retirer aucun (hooks.py). Sans registre, no-op.
        if self.crochets is not None:
            raison = self.crochets.executer_avant(
                self.nom or self.service, capacite.nom, parametres)
            if raison:
                resultat = echec(capacite.nom, cible, raison)
                self._journaliser(resultat, parametres, niveau)
                return resultat

        # 5. Execution. Une implementation qui leve ne devient jamais un succes.
        try:
            resultat = self._executer(capacite, **parametres)
        except Exception as erreur:
            logger.error("%s.%s a leve : %s", self.nom, capacite.nom, erreur)
            resultat = echec(capacite.nom, cible, f"Erreur pendant l'execution : {erreur}")

        if not isinstance(resultat, ResultatAction):
            logger.error("%s.%s a rendu %r au lieu d'un ResultatAction.",
                         self.nom, capacite.nom, type(resultat).__name__)
            resultat = echec(
                capacite.nom, cible,
                "L'implementation n'a pas rendu de resultat exploitable.",
            )

        # 6. Crochets apres execution : un observateur, jamais un veto — il
        #    voit le resultat deja verifie, il ne peut pas le changer.
        if self.crochets is not None:
            self.crochets.executer_apres(self.nom or self.service, capacite.nom, resultat)

        self._journaliser(resultat, parametres, niveau)
        return resultat

    # --- Inventaire -----------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Ce qu'ARENA expose du connecteur. Aucun identifiant n'y figure.

        C'est ce que voit le modele : des capacites, jamais des secrets.
        """
        return {
            "nom": self.nom,
            "service": self.service,
            "sante": self.sante().to_dict(),
            "capacites": [c.to_dict() for c in self.capacites().values()],
        }
