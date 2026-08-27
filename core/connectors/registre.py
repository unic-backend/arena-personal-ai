"""L'inventaire des connecteurs : paresseux, et tolerant a l'un d'eux qui tombe.

Deux defauts mesures le 2026-08-27 dans ARENA justifient ce module :

- `apps/backend/runtime.py` construit ses dix-sept agents **a l'import**, au
  niveau du module. Ajouter des connecteurs de la meme facon ferait tomber tout
  le serveur pour un seul constructeur en panne — et un connecteur depend d'un
  service exterieur, donc il tombera.
- l'aiguillage est une suite de quatorze `if/elif`. La specification le dit :
  « Do not hard-code everything into the orchestrator. »

Le registre repond aux deux avec la meme idee : **on declare une fabrique, pas
un objet.** Rien n'est construit tant que personne ne s'en sert, et une fabrique
qui leve est retenue comme telle au lieu de remonter.

Trois garanties, chacune verifiable :

1. **Un connecteur casse se degrade seul.** Sa construction est tentee une fois ;
   l'echec est journalise, memorise, et rendu comme une sante `FAILING`. Les
   autres connecteurs ne le savent meme pas.
2. **L'inventaire ne leve jamais.** C'est ce qu'affiche l'interface et ce que
   lit le modele : il doit repondre meme quand la moitie des services est en
   panne.
3. **Un nom inconnu n'est pas une exception, c'est une reponse.** Demander un
   connecteur qui n'existe pas rend `NOT_IMPLEMENTED`, pas une trace de pile.
"""
import logging
from typing import Any, Callable, Dict, List, Optional

from core.actions.resultat import ResultatAction, non_implemente
from core.connectors.base import Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.connecteurs.registre")

#: Une fabrique construit un connecteur au premier usage.
Fabrique = Callable[[], Connecteur]


class RegistreConnecteurs:
    """Declare, construit a la demande, et route vers les connecteurs."""

    def __init__(self) -> None:
        self._fabriques: Dict[str, Fabrique] = {}
        self._construits: Dict[str, Connecteur] = {}
        # Nom -> message d'erreur de construction. Un connecteur qui a echoue
        # n'est pas retente a chaque appel : il repondrait la meme chose, en
        # plus lent, et remplirait les journaux.
        self._casses: Dict[str, str] = {}

    # --- Declaration ----------------------------------------------------------

    def declarer(self, nom: str, fabrique: Fabrique) -> None:
        """Enregistre une fabrique. Rien n'est construit ici.

        Redeclarer un nom remplace la fabrique et oublie ce qui avait ete
        construit — c'est ce qu'on attend apres une correction de configuration.
        """
        self._fabriques[nom] = fabrique
        self._construits.pop(nom, None)
        self._casses.pop(nom, None)

    def noms(self) -> List[str]:
        """Les connecteurs declares, tries. Y compris ceux qui sont casses."""
        return sorted(self._fabriques)

    def est_declare(self, nom: str) -> bool:
        return nom in self._fabriques

    # --- Construction paresseuse ----------------------------------------------

    def obtenir(self, nom: str) -> Optional[Connecteur]:
        """Le connecteur, construit au premier appel. None s'il est absent ou casse.

        Ne leve jamais : un constructeur qui echoue est retenu comme casse.
        """
        if nom in self._construits:
            return self._construits[nom]
        if nom in self._casses or nom not in self._fabriques:
            return None

        try:
            connecteur = self._fabriques[nom]()
        except Exception as erreur:
            self._casses[nom] = str(erreur)
            logger.error(
                "Connecteur %s : construction impossible (%s). Il est marque hors "
                "service ; les autres connecteurs ne sont pas affectes.", nom, erreur,
            )
            return None

        if not isinstance(connecteur, Connecteur):
            self._casses[nom] = (
                f"la fabrique a rendu {type(connecteur).__name__} au lieu d'un Connecteur"
            )
            logger.error("Connecteur %s : %s.", nom, self._casses[nom])
            return None

        self._construits[nom] = connecteur
        return connecteur

    # --- Etat -----------------------------------------------------------------

    def sante(self, nom: str) -> Sante:
        """La sante d'un connecteur, y compris quand il n'a pas pu naitre."""
        if nom not in self._fabriques:
            return Sante(EtatSante.INCONNU, message=f"Aucun connecteur nomme « {nom} ».")

        connecteur = self.obtenir(nom)
        if connecteur is None:
            return Sante(
                EtatSante.EN_PANNE,
                message=f"Construction impossible : {self._casses.get(nom, 'raison inconnue')}",
            )
        return connecteur.sante()

    def inventaire(self) -> List[Dict[str, Any]]:
        """Tous les connecteurs, avec leur sante et leurs capacites.

        Ne leve jamais, quel que soit l'etat des connecteurs : c'est ce que lit
        l'interface, et une page qui plante ne dit rien de ce qui va mal.
        """
        inventaire: List[Dict[str, Any]] = []
        for nom in self.noms():
            connecteur = self.obtenir(nom)
            if connecteur is None:
                inventaire.append({
                    "nom": nom, "service": "", "capacites": [],
                    "sante": self.sante(nom).to_dict(),
                })
                continue
            try:
                inventaire.append(connecteur.to_dict())
            except Exception as erreur:
                logger.error("Inventaire de %s illisible : %s", nom, erreur)
                inventaire.append({
                    "nom": nom, "service": getattr(connecteur, "service", ""),
                    "capacites": [],
                    "sante": Sante(EtatSante.EN_PANNE, message=str(erreur)).to_dict(),
                })
        return inventaire

    # --- Aiguillage -----------------------------------------------------------

    def _absent(self, nom: str, capacite: str) -> ResultatAction:
        motif = f"hors service : {self._casses[nom]}" if nom in self._casses else "non declare"
        return non_implemente(
            action=capacite, cible=nom,
            message=f"Connecteur « {nom} » {motif}. Rien n'a ete tente.",
        )

    def executer(
        self, nom: str, capacite: str, compte: Optional[str] = None, **parametres: Any
    ) -> ResultatAction:
        """Route vers le connecteur. Un nom inconnu est une reponse, pas une exception."""
        connecteur = self.obtenir(nom)
        if connecteur is None:
            return self._absent(nom, capacite)
        return connecteur.executer(capacite, compte=compte, **parametres)

    def executer_confirmee(
        self, nom: str, capacite: str, compte: Optional[str] = None, **parametres: Any
    ) -> ResultatAction:
        """Route une action confirmee. Reserve a `FileDAttente.confirmer()`.

        Sans ce chemin, confirmer relancerait le controle de permission, verrait
        de nouveau CONFIRMATION, et deposerait une **deuxieme** action en
        attente : rien ne partirait jamais. Mesure faite le 2026-08-27 avant
        correction.
        """
        connecteur = self.obtenir(nom)
        if connecteur is None:
            return self._absent(nom, capacite)
        return connecteur.executer_confirmee(capacite, compte=compte, **parametres)
