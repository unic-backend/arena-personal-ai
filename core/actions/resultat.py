"""Le resultat d'une action qui touche le monde exterieur — et sa preuve.

Ce module existe a cause d'un defaut mesure le 2026-08-27 dans ARENA : le
connecteur TikTok renvoyait `status: "success"` pour une publication qui n'avait
jamais eu lieu. Le mot « simule » figurait bien dans le message, mais le champ
que tout appelant teste — le statut — disait que ca avait marche.

Le probleme n'est pas le connecteur, c'est le vocabulaire : avec seulement
`success` et `error`, une integration absente n'a pas de mot pour se decrire, et
elle finit par emprunter celui de la reussite.

**La regle que ce module rend structurelle : un succes exige une preuve.**
Pas un booleen `verifie=True`, que n'importe quel appelant peut mettre a vrai —
une preuve : un identifiant, une adresse, un code de retour, quelque chose que
le proprietaire peut aller regarder. Sans elle, `ResultatAction` refuse de se
construire.

Et l'inverse est ferme aussi : une action qui n'a pas eu lieu ne peut pas porter
de preuve. Un refus qui exhibe un identifiant de publication est un mensonge
dans l'autre sens.

Ce vocabulaire ne s'applique qu'aux actions **a effet externe** : publier,
envoyer, supprimer, modifier un compte. Un agent qui se contente de rediger du
texte n'a rien a prouver et garde ses propres statuts.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Statut(str, Enum):
    """Les sept issues possibles d'une action a effet externe.

    Les valeurs sont en anglais parce qu'elles traversent l'API ; les noms sont
    en francais parce que le code d'ARENA l'est.
    """

    SUCCES = "SUCCESS"                 # c'est arrive, et c'est prouve
    PARTIEL = "PARTIAL"                # une partie est arrivee, et c'est prouve
    ECHEC = "FAILED"                   # tente, pas arrive
    NON_CONFIGURE = "NOT_CONFIGURED"   # aucune integration reelle : rien n'a ete tente
    REFUSE = "DENIED"                  # refuse par les permissions : rien n'a ete tente
    A_CONFIRMER = "NEEDS_CONFIRMATION"  # prepare, en attente du proprietaire
    NON_IMPLEMENTE = "NOT_IMPLEMENTED"  # le chemin de code n'existe pas


# Les seuls statuts qui affirment un effet dans le monde. Eux seuls exigent —
# et eux seuls acceptent — une preuve.
STATUTS_AVEC_EFFET = frozenset({Statut.SUCCES, Statut.PARTIEL})


@dataclass(frozen=True)
class ResultatAction:
    """Ce qu'une action a reellement fait, avec de quoi le verifier.

    Attributes:
        statut: l'issue, parmi les sept de `Statut`.
        action: ce qui a ete tente, en un mot machine (`publish_video`).
        cible: sur quoi (`TikTok`, `client@example.com`).
        message: la phrase lisible par le proprietaire.
        preuve: ce qui atteste l'effet — identifiant, adresse, code de retour.
            Obligatoire pour un succes, interdit partout ailleurs.
        detail: informations libres, jamais de secret.

    Raises:
        ValueError: si un succes n'a pas de preuve, ou si une action qui n'a pas
            eu lieu en exhibe une.
    """

    statut: Statut
    action: str
    cible: str
    message: str
    preuve: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.statut in STATUTS_AVEC_EFFET and not (self.preuve or "").strip():
            raise ValueError(
                f"{self.statut.value} sans preuve : une action ne peut pas etre declaree "
                f"reussie sans de quoi le verifier ({self.action} -> {self.cible})."
            )
        if self.statut not in STATUTS_AVEC_EFFET and self.preuve is not None:
            raise ValueError(
                f"{self.statut.value} avec une preuve : rien n'a eu lieu, il n'y a rien "
                f"a prouver ({self.action} -> {self.cible})."
            )

    @property
    def a_eu_lieu(self) -> bool:
        """Vrai seulement si quelque chose a change hors d'ARENA."""
        return self.statut in STATUTS_AVEC_EFFET

    def to_dict(self) -> Dict[str, Any]:
        """Forme transportable par l'API. `status` porte la valeur anglaise."""
        corps: Dict[str, Any] = {
            "status": self.statut.value,
            "action": self.action,
            "cible": self.cible,
            "response": self.message,
            "a_eu_lieu": self.a_eu_lieu,
        }
        if self.preuve is not None:
            corps["preuve"] = self.preuve
        if self.detail:
            corps["detail"] = self.detail
        return corps


# --- Constructeurs -------------------------------------------------------------
# Ils existent pour que le statut juste soit le plus court a ecrire. Le seul qui
# demande un argument de plus est le succes : c'est voulu.

def succes(action: str, cible: str, message: str, preuve: str, **detail: Any) -> ResultatAction:
    """L'action a eu lieu, et `preuve` permet d'aller le verifier."""
    return ResultatAction(Statut.SUCCES, action, cible, message, preuve, detail)


def partiel(action: str, cible: str, message: str, preuve: str, **detail: Any) -> ResultatAction:
    """Une partie seulement a eu lieu. Le message dit laquelle."""
    return ResultatAction(Statut.PARTIEL, action, cible, message, preuve, detail)


def echec(action: str, cible: str, message: str, **detail: Any) -> ResultatAction:
    """Tente, pas arrive. Le message dit pourquoi, sans l'adoucir."""
    return ResultatAction(Statut.ECHEC, action, cible, message, detail=detail)


def non_configure(action: str, cible: str, ce_qui_manque: str, **detail: Any) -> ResultatAction:
    """Aucune integration reelle : rien n'a ete tente, et on dit quoi brancher.

    C'est le statut qui manquait. Une capacite absente le declare ; elle ne
    renvoie jamais un resultat plausible a la place.
    """
    return ResultatAction(
        Statut.NON_CONFIGURE, action, cible,
        f"Non configure : {cible} n'est pas connecte. Il manque {ce_qui_manque}. "
        f"Rien n'a ete envoye.",
        detail=detail,
    )


def refuse(action: str, cible: str, permission: str, **detail: Any) -> ResultatAction:
    """Refuse par les permissions. Rien n'a ete tente."""
    return ResultatAction(
        Statut.REFUSE, action, cible,
        f"Refuse : la permission {permission} est bloquee. Rien n'a ete envoye.",
        detail=detail,
    )


def a_confirmer(action: str, cible: str, message: str, **detail: Any) -> ResultatAction:
    """Tout est pret ; il manque le feu vert du proprietaire."""
    return ResultatAction(Statut.A_CONFIRMER, action, cible, message, detail=detail)


def non_implemente(action: str, cible: str, message: str, **detail: Any) -> ResultatAction:
    """Le chemin de code n'existe pas encore. Ce n'est ni une panne ni un refus."""
    return ResultatAction(Statut.NON_IMPLEMENTE, action, cible, message, detail=detail)
