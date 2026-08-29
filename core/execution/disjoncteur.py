"""Un disjoncteur : apres des echecs consecutifs reels, il arrete d'essayer.

**Ce qu'il resout, et qu'aucun module existant ne resout** : `LimiteurDebit`
(`apps/backend/rate_limit.py`) plafonne un DEBIT — combien d'appels par
minute — pas une SANTE. Un service tombe (MoneyPrinterTurbo arrete, OpenTakeoff
jamais construit sur cette machine, WanGP injoignable) et chaque demande
suivante repaie le meme delai d'attente complet pour le meme echec — jusqu'a
`DELAI_SECONDES` par appel, pour un service dont la premiere reponse a deja
dit qu'il ne repond pas. `sonder()` a bien son propre cache
(`DUREE_SONDE_SECONDES`), mais uniquement pour la SANTE affichee ; l'execution
elle-meme retente a chaque fois.

**Le premier consommateur reel du registre de crochets**
(`core/execution/hooks.py`) : `avant_execution` pour couper court, apres
qu'un connecteur soit tombe assez de fois de suite ; `apres_execution` pour
compter les echecs et rouvrir des qu'un vrai succes revient.

**Trois regles :**

1. **Seul un `ECHEC` reel compte.** `NOT_CONFIGURED`, `DENIED`,
   `NEEDS_CONFIRMATION`, `NOT_IMPLEMENTED` ne disent rien de la sante du
   service exterieur — rien n'a ete tente contre lui. Ni compteur ni remise a
   zero pour ces etats : seul un appel qui a vraiment echoue, ou vraiment
   reussi, fait bouger le compteur.

2. **Le repos a une fin.** Passe `repos_secondes`, le disjoncteur se referme
   de lui-meme et laisse une chance reelle au prochain appel — jamais coupe
   pour de bon sur la foi d'echecs anciens.

3. **Chaque connecteur/capacite a son propre compteur.** Un plaquiste en
   echec ne doit pas couper OpenTakeoff.
"""
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from core.actions.resultat import ResultatAction, Statut

#: Nombre d'echecs consecutifs avant ouverture. En dessous de 2, un seul echec
#: isole (reseau instable une fois) couperait un service par ailleurs sain.
SEUIL_PAR_DEFAUT = 3

#: Combien de temps le disjoncteur reste ouvert avant de redonner sa chance.
REPOS_SECONDES = 60.0


@dataclass
class _Etat:
    echecs_consecutifs: int = 0
    ouvert_jusqua: Optional[float] = None


class Disjoncteur:
    """Suit les echecs consecutifs par `(connecteur, capacite)`, et coupe court."""

    def __init__(self, seuil: int = SEUIL_PAR_DEFAUT, repos_secondes: float = REPOS_SECONDES) -> None:
        if seuil < 1:
            raise ValueError("Un disjoncteur qui s'ouvre a zero echec n'en attend aucun.")
        self.seuil = seuil
        self.repos_secondes = repos_secondes
        self._etats: Dict[Tuple[str, str], _Etat] = {}

    def _etat_de(self, connecteur: str, capacite: str) -> _Etat:
        return self._etats.setdefault((connecteur, capacite), _Etat())

    def avant_execution(self, connecteur: str, capacite: str,
                        parametres: Dict[str, Any]) -> Optional[str]:
        """Crochet `avant_execution` (voir `hooks.py`) : rend une raison si le
        disjoncteur est ouvert, `None` sinon."""
        etat = self._etat_de(connecteur, capacite)
        if etat.ouvert_jusqua is None:
            return None
        maintenant = time.monotonic()
        if maintenant < etat.ouvert_jusqua:
            restant = int(etat.ouvert_jusqua - maintenant) + 1
            return (
                f"Disjoncteur ouvert sur {connecteur}.{capacite} : "
                f"{etat.echecs_consecutifs} echec(s) consecutif(s). "
                f"Reessai possible dans {restant}s."
            )
        # Le repos est passe : redonne une chance reelle plutot qu'un essai a
        # l'aveugle sur un compteur perime.
        etat.ouvert_jusqua = None
        etat.echecs_consecutifs = 0
        return None

    def apres_execution(self, connecteur: str, capacite: str,
                        resultat: ResultatAction) -> None:
        """Crochet `apres_execution` : ajuste le compteur selon ce qui s'est
        vraiment passe (voir la regle 1 du module)."""
        etat = self._etat_de(connecteur, capacite)
        if resultat.statut is Statut.ECHEC:
            etat.echecs_consecutifs += 1
            if etat.echecs_consecutifs >= self.seuil and etat.ouvert_jusqua is None:
                etat.ouvert_jusqua = time.monotonic() + self.repos_secondes
        elif resultat.a_eu_lieu:
            etat.echecs_consecutifs = 0
            etat.ouvert_jusqua = None
        # NOT_CONFIGURED / DENIED / NEEDS_CONFIRMATION / NOT_IMPLEMENTED :
        # rien n'a ete tente contre le service, le compteur ne bouge pas.

    def etat_public(self, connecteur: str, capacite: str) -> Dict[str, Any]:
        """Ce qu'un tableau de bord peut montrer, sans exposer l'objet interne."""
        etat = self._etats.get((connecteur, capacite))
        if etat is None:
            return {"echecs_consecutifs": 0, "ouvert": False}
        ouvert = etat.ouvert_jusqua is not None and time.monotonic() < etat.ouvert_jusqua
        return {"echecs_consecutifs": etat.echecs_consecutifs, "ouvert": ouvert}
