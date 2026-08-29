"""Ce que le cloud coute, compte a la requete, et le plafond qui y met fin.

Le cloud est a l'usage : un agent qui boucle ne fait pas planter ARENA, il
**facture**. Ce module compte ce qui part, estime ce que ca coute quand un tarif
est connu, et dit quand il faut redescendre sur Ollama.

**Cinq regles :**

1. **Un plafond atteint ne casse rien.** Il fait retomber ARENA sur sa machine.
   Refuser de repondre serait le pire des deux mondes : plus de cloud, et plus
   d'assistant non plus.

2. **Un cout inconnu reste inconnu.** Sans tarif configure, `cout_estime` vaut
   `None`, jamais `0.0` — un zero se lirait « gratuit » et laisserait le
   compteur ouvert.

3. **Le journal ne contient pas ses phrases.** On enregistre le fournisseur, le
   modele, le classement, la latence et les jetons. **Pas le prompt.** Un
   compteur d'usage n'est pas un enregistreur de conversations.

4. **La journee est celle de sa machine**, pas une fenetre glissante : « 200
   requetes par jour » doit vouloir dire ce qu'il croit.

5. **Zero veut dire « pas de plafond »**, et c'est un choix qui doit etre ecrit,
   jamais un defaut qu'on subit.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.modeles.usage")

#: Combien d'appels sont gardes en memoire. Au-dela, les plus anciens partent :
#: ce compteur ne doit pas peser plus que ce qu'il compte.
APPELS_GARDES = 500

#: Tarifs connus, en dollars par million de jetons. **Vide par defaut** : un
#: tarif que personne n'a saisi ne s'invente pas, et le cout reste `None`.
#: Le proprietaire les remplit quand il veut voir des montants.
TARIFS: Dict[str, Dict[str, float]] = {}


def _aujourdhui() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass(frozen=True)
class Appel:
    """Un appel distant, tel qu'il sera compte. **Sans le texte de la demande.**"""

    fournisseur: str
    modele: str
    jour: str = field(default_factory=_aujourdhui)
    horodatage: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(
        timespec="seconds"))
    classement: str = ""
    jetons_entree: Optional[int] = None
    jetons_sortie: Optional[int] = None
    secondes: Optional[float] = None
    repli: bool = False
    succes: bool = True

    @property
    def cout_estime(self) -> Optional[float]:
        """Le cout, si et seulement si un tarif est configure pour ce modele.

        `None` n'est pas `0.0`. Un zero se lirait « gratuit ».
        """
        tarif = TARIFS.get(self.modele)
        if not tarif or self.jetons_entree is None or self.jetons_sortie is None:
            return None
        return (self.jetons_entree * tarif.get("entree", 0.0)
                + self.jetons_sortie * tarif.get("sortie", 0.0)) / 1_000_000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fournisseur": self.fournisseur, "modele": self.modele,
            "horodatage": self.horodatage, "classement": self.classement,
            "jetons_entree": self.jetons_entree, "jetons_sortie": self.jetons_sortie,
            "secondes": self.secondes, "repli": self.repli, "succes": self.succes,
            "cout_estime": self.cout_estime,
        }


@dataclass(frozen=True)
class Verdict:
    """Le cloud a-t-il encore le droit de servir aujourd'hui, et pourquoi."""

    autorise: bool
    raison: str


class CompteurUsage:
    """Compte ce qui part vers le cloud, et dit quand il faut s'arreter."""

    def __init__(self, requetes_par_jour: int = 200,
                 budget_journalier: float = 1.0) -> None:
        self.requetes_par_jour = max(0, requetes_par_jour)
        self.budget_journalier = max(0.0, budget_journalier)
        self.appels: List[Appel] = []

    # --- Compter ---------------------------------------------------------------

    def enregistrer(self, appel: Appel) -> Appel:
        """Range un appel. Le journal ne grossit pas sans fin."""
        self.appels.append(appel)
        surplus = len(self.appels) - APPELS_GARDES
        if surplus > 0:
            del self.appels[:surplus]
        return appel

    def du_jour(self, jour: Optional[str] = None) -> List[Appel]:
        """Les appels d'une journee — celle de sa machine, pas 24 h glissantes."""
        reference = jour or _aujourdhui()
        return [appel for appel in self.appels if appel.jour == reference]

    @property
    def requetes_aujourdhui(self) -> int:
        return len(self.du_jour())

    @property
    def cout_aujourdhui(self) -> Optional[float]:
        """Le total du jour, ou `None` si aucun appel n'a de tarif connu."""
        connus = [appel.cout_estime for appel in self.du_jour()
                  if appel.cout_estime is not None]
        return sum(connus) if connus else None

    # --- Decider ----------------------------------------------------------------

    def verdict(self) -> Verdict:
        """Le cloud peut-il encore servir ? Un plafond atteint fait retomber sur Ollama."""
        if self.requetes_par_jour and self.requetes_aujourdhui >= self.requetes_par_jour:
            return Verdict(False, (f"plafond atteint : {self.requetes_aujourdhui} "
                                   f"requete(s) cloud aujourd'hui"))
        depense = self.cout_aujourdhui
        if self.budget_journalier and depense is not None and depense >= self.budget_journalier:
            return Verdict(False, (f"budget atteint : {depense:.4f} $ depenses "
                                   f"aujourd'hui"))
        return Verdict(True, "dans les clous")

    def resume(self) -> Dict[str, Any]:
        """Ce que l'interface peut montrer. Aucune phrase du proprietaire ici."""
        verdict = self.verdict()
        return {
            "requetes_aujourdhui": self.requetes_aujourdhui,
            "plafond_requetes": self.requetes_par_jour or None,
            # `None` quand aucun tarif n'est configure : on ne montre pas un
            # montant qu'on n'a pas calcule.
            "cout_aujourdhui": self.cout_aujourdhui,
            "budget_journalier": self.budget_journalier or None,
            "cloud_autorise": verdict.autorise,
            "raison": verdict.raison,
        }
