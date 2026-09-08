"""`architecture_3d` : la capacité, jamais le moteur qui la rend.

ARENA ne possède pas de moteur d'architecture. Elle en pilote un — aujourd'hui
Pascal (`backend_pascal.py`), demain un autre — et **ce fichier est la
frontière** : il décrit ce qu'ARENA sait demander, en français et en termes
de bâtiment, sans qu'aucun nom de moteur n'y apparaisse.

---

## Pourquoi une capacité et pas « un connecteur Pascal »

Un modèle qui apprendrait à appeler `create_wall` avec `levelId` et
`thickness` deviendrait dépendant de Pascal. Le jour où Pascal change de nom
d'outil — ou disparaît —, il faudrait réapprendre à chaque modèle. C'est la
raison d'être de ce module : le vocabulaire ci-dessous (`OPERATIONS`) est un
**contrat d'ARENA**, stable par décision, et la traduction vers les outils
réels du moteur vit dans le backend, à un seul endroit.

Conséquence directe : **aucun nom de modèle n'a le droit d'apparaître ici.**
Pas de `if modele == ...`, pas de `if fournisseur == ...`. Un test le vérifie
(`tests/core/test_capacite_architecture_3d.py`). La sélection se fait sur la
capacité demandée, la disponibilité du backend et les permissions — jamais
sur qui appelle.

---

## Les sessions ne se mélangent pas

Un moteur d'architecture porte un état : la scène en cours, sa pile
d'annulation, son projet. Deux chantiers ouverts en même temps ne doivent
jamais se retrouver dans la même scène. Une session ARENA = **un moteur à
elle**, ouvert paresseusement au premier besoin et fermé explicitement.

C'est la même règle que le transport MCP en processus (`core/mcp/
stdio_transport.py`, règle 2) : le processus EST la session. Ici, on va plus
loin — le dictionnaire des sessions est la seule chose qui les tient, et
`fermer_tout()` existe pour qu'un arrêt n'abandonne pas de processus.

---

## Ce qui est mesuré à chaque opération

Chaque appel rend une `Mesure` : capacité, backend, opération, session,
durée, succès ou échec, et la raison. C'est ce qui permet de savoir *après
coup* quel moteur a produit quoi — et la capacité reste agnostique du modèle
appelant, qui est journalisé par la couche au-dessus, pas décidé ici.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Protocol

logger = logging.getLogger("usman.architecture")

#: Le vocabulaire d'ARENA. Chaque entrée dit ce que l'opération FAIT, jamais
#: comment le moteur s'y prend, et si elle MODIFIE la scène — c'est cette
#: colonne-là que la couche de permissions lit.
#:
#: Toutes ont été mesurées comme réellement disponibles sur le backend Pascal
#: le 07/09/2026 (46 outils exposés) : aucune n'est promise sur la foi d'une
#: documentation.
OPERATIONS: Dict[str, Dict[str, Any]] = {
    "creer_projet":   {"ecrit": True,  "quoi": "Ouvre un projet neuf : terrain, bâtiment, premier niveau."},
    "creer_niveau":   {"ecrit": True,  "quoi": "Ajoute un niveau au bâtiment."},
    "creer_mur":      {"ecrit": True,  "quoi": "Trace un mur entre deux points d'un niveau."},
    "creer_coque":    {"ecrit": True,  "quoi": "Ferme une emprise : murs de pourtour, dalle et plafond."},
    "poser_porte":    {"ecrit": True,  "quoi": "Perce une porte dans un mur existant."},
    "poser_fenetre":  {"ecrit": True,  "quoi": "Perce une fenêtre dans un mur existant."},
    "creer_piece":    {"ecrit": True,  "quoi": "Délimite une pièce par son polygone."},
    "poser_objet":    {"ecrit": True,  "quoi": "Place un objet du catalogue dans la scène."},
    "supprimer":      {"ecrit": True,  "quoi": "Supprime un élément de la scène."},
    "annuler":        {"ecrit": True,  "quoi": "Annule la dernière modification."},
    "refaire":        {"ecrit": True,  "quoi": "Rétablit la modification annulée."},
    "enregistrer":    {"ecrit": True,  "quoi": "Enregistre la scène sous un nom."},
    "charger":        {"ecrit": True,  "quoi": "Recharge une scène enregistrée."},
    "inspecter":      {"ecrit": False, "quoi": "Rend la scène entière : nœuds, hiérarchie, géométrie."},
    "lister_murs":    {"ecrit": False, "quoi": "Liste les murs d'un niveau avec leurs longueurs."},
    "lister_zones":   {"ecrit": False, "quoi": "Liste les pièces et zones d'un niveau."},
    "lister_niveaux": {"ecrit": False, "quoi": "Liste les niveaux du bâtiment."},
    "lister_scenes":  {"ecrit": False, "quoi": "Liste les scènes enregistrées."},
    "mesurer":        {"ecrit": False, "quoi": "Mesure la distance entre deux éléments."},
    "valider":        {"ecrit": False, "quoi": "Vérifie la cohérence de la scène."},
    "exporter_json":  {"ecrit": False, "quoi": "Rend la scène au format JSON du moteur."},
    "exporter_glb":   {"ecrit": False, "quoi": "Rend la scène en glTF binaire (GLB)."},
}

#: Les opérations qui modifient la scène. Dérivé de `OPERATIONS`, jamais
#: recopié — une liste tenue à la main aurait divergé au premier ajout.
ECRITURES = frozenset(nom for nom, o in OPERATIONS.items() if o["ecrit"])


class OperationInconnue(ValueError):
    """Le vocabulaire d'ARENA ne contient pas cette opération."""


class BackendIndisponible(RuntimeError):
    """Aucun moteur ne peut rendre cette capacité, et on dit pourquoi."""


@dataclass
class Mesure:
    """Ce qu'une opération a fait, et ce qu'elle a coûté. Rien n'est supposé."""

    capacite: str
    backend: str
    operation: str
    session: str
    duree_ms: int
    ok: bool
    detail: Dict[str, Any] = field(default_factory=dict)
    raison: str = ""

    def journal(self) -> Dict[str, Any]:
        """La ligne d'observabilité, sans le contenu de la scène.

        Le détail d'une scène pèse des kilo-octets ; le journal doit rester
        lisible. Ce qui est gardé, c'est ce qui permet de répondre à « qui a
        produit quoi, avec quel moteur, en combien de temps ».
        """
        return {"capability": self.capacite, "backend": self.backend,
                "action": self.operation, "session": self.session,
                "duration_ms": self.duree_ms,
                "status": "success" if self.ok else "error",
                "erreur": self.raison}


class Backend3D(Protocol):
    """Ce qu'un moteur doit savoir faire pour rendre `architecture_3d`.

    Trois méthodes, et aucune ne connaît le vocabulaire d'ARENA autrement que
    par `executer` : c'est le backend qui traduit, pas la capacité.
    """

    nom: str

    def sonder(self) -> tuple:
        """`(disponible, ce_qui_manque)` — mesuré, jamais supposé."""
        ...

    def executer(self, session: str, operation: str,
                 parametres: Dict[str, Any]) -> tuple:
        """`(ok, detail, raison)` pour une opération du vocabulaire d'ARENA."""
        ...

    def fermer(self, session: str) -> None:
        """Libère ce que cette session tenait. Idempotent."""
        ...


class Capacite3D:
    """`architecture_3d` : le point d'entrée unique, quel que soit le moteur.

    Elle ne sait pas qui l'appelle — un modèle local, un modèle distant, un
    test, une route HTTP. Elle sait ce qu'on lui demande, sur quelle session,
    et lequel de ses backends peut le faire.
    """

    nom = "architecture_3d"

    def __init__(self, backend: Backend3D) -> None:
        self.backend = backend

    def sonder(self) -> tuple:
        return self.backend.sonder()

    def executer(self, operation: str, session: str = "defaut",
                 **parametres: Any) -> Mesure:
        """Exécute une opération du vocabulaire d'ARENA sur une session.

        Raises:
            OperationInconnue: le nom ne fait pas partie du contrat. Refuser
                ici plutôt que de laisser passer au moteur : une opération
                inventée doit échouer sur le contrat d'ARENA, pas produire une
                erreur du moteur que personne ne saura relier au vocabulaire.
        """
        if operation not in OPERATIONS:
            connues = ", ".join(sorted(OPERATIONS))
            raise OperationInconnue(
                f"« {operation} » n'est pas une operation d'architecture_3d. "
                f"Connues : {connues}.")

        debut = time.perf_counter()
        try:
            ok, detail, raison = self.backend.executer(session, operation, parametres)
        except Exception as erreur:  # noqa: BLE001 — un moteur externe ne fait jamais tomber ARENA
            logger.exception("architecture_3d/%s a leve", operation)
            ok, detail, raison = False, {}, f"{erreur.__class__.__name__}: {erreur}"

        mesure = Mesure(
            capacite=self.nom, backend=self.backend.nom, operation=operation,
            session=session, duree_ms=int((time.perf_counter() - debut) * 1000),
            ok=ok, detail=detail or {}, raison=raison)
        logger.info("architecture_3d %s", mesure.journal())
        return mesure

    def fermer(self, session: str) -> None:
        self.backend.fermer(session)
