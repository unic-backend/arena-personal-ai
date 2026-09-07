"""`architecture_3d` : la capacité d'architecture d'ARENA, sous ses règles.

Ce connecteur est **la seule porte** par laquelle un modèle atteint un moteur
d'architecture. Il n'expose pas Pascal : il expose le vocabulaire d'ARENA
(`core/architecture/capacite.py`), et c'est le backend qui traduit.

```
modele (n'importe lequel)
  -> orchestrateur ARENA        (intention ARCHITECTURE_3D)
  -> ce connecteur              (permission -> confirmation -> quota -> journal)
  -> Capacite3D                 (vocabulaire stable, sessions isolees)
  -> BackendPascal              (traduction vers les 46 outils reels)
  -> serveur MCP de Pascal      (processus separe, MIT, hors du depot)
```

**Trois règles.**

1. **Lire n'est pas écrire.** `inspecter`, `lister_murs`, `mesurer` ne
   modifient rien : `read`, sans confirmation. Tracer un mur, percer une
   porte, enregistrer une scène : `document`, avec confirmation, comme le
   devis PDF et le rendu vidéo. La séparation vient d'`OPERATIONS`, jamais
   d'une liste tenue à la main ici.

2. **Aucun nom de modèle.** La sélection se fait sur la capacité, la
   disponibilité et les permissions. Un test interdit `if modele ==` dans
   toute la couche architecture.

3. **Une session, une scène.** `session` voyage jusqu'au backend, qui tient
   un moteur par session. Deux chantiers ouverts en même temps ne se
   mélangent pas — et un test le vérifie sur deux vraies scènes.

Le moteur géométrique s'arrête au mur. Ce qu'on en déduit — surfaces de BA13,
ossature, isolation, quantités, prix — reste au métier
(`agents/plaquiste/`), qui lit ce que ce connecteur rend. Mélanger les deux
ferait de la capacité une propriété d'UniC, ce qu'elle n'est pas.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.architecture.backend_pascal import BackendPascal
from core.architecture.capacite import (
    ECRITURES,
    OPERATIONS,
    Capacite3D,
    OperationInconnue,
)
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.architecture_3d")

#: L'action de chaque opération — et **c'est l'action, pas le nom de la
#: capacité, que la politique de permissions interroge**
#: (`core/connectors/base.py`, étape 2 : `acces.verifier(service,
#: capacite.action, ...)`).
#:
#: Mesure du 07/09/2026 : une première version déclarait une règle par
#: opération dans `config/permissions_services.yaml`. Aucune ne pouvait
#: matcher — la politique n'y cherche jamais un nom de capacité — et **toutes
#: les opérations tombaient sur la règle par défaut, donc `DENIED`**. Le
#: symptôme était parfait : permissions écrites, moteur prêt, et rien qui
#: passe. Trois actions valent mieux que vingt-deux règles mortes.
ACTION_DEMOLITION = "demolir"
ACTION_BATIR = "batir"
ACTION_LECTURE = "read"


def action_de(operation: str) -> str:
    """L'action de permission d'une opération. Dérivée, jamais recopiée."""
    if operation == "supprimer":
        # Supprimer un element n'est pas « batir » : c'est le seul geste qui
        # detruit du travail deja fait, et il merite son propre risque.
        return ACTION_DEMOLITION
    return ACTION_BATIR if operation in ECRITURES else ACTION_LECTURE


class ConnecteurArchitecture3D(Connecteur):
    """Créer et interroger un bâtiment — le moteur derrière est interchangeable."""

    service = "architecture_3d"
    nom = "architecture_3d"

    def __init__(self, capacite: Optional[Capacite3D] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        #: Le backend par defaut est Pascal, et c'est le SEUL endroit du
        #: connecteur qui le nomme : un autre moteur se branche ici, sans
        #: toucher ni aux capacites, ni aux permissions, ni aux appelants.
        self.capacite = capacite or Capacite3D(BackendPascal())

    def capacites(self) -> Dict[str, Capacite]:
        """Une capacité ARENA par opération du vocabulaire — dérivées, pas listées.

        Les écrire à la main ici les aurait fait diverger d'`OPERATIONS` au
        premier ajout : c'est exactement comme ça qu'une permission finit par
        manquer sur une opération neuve.
        """
        capacites = {
            nom: Capacite(
                nom=nom, action=action_de(nom),
                description=details["quoi"],
                ecriture=nom in ECRITURES)
            for nom, details in OPERATIONS.items()
        }
        capacites["batir_plan"] = Capacite(
            nom="batir_plan", action=ACTION_BATIR,
            description=("Construit un batiment entier a partir d'une phrase : "
                         "une seule confirmation pour tout le plan."),
            ecriture=True)
        return capacites

    # --- Santé ----------------------------------------------------------------

    def sonder(self) -> Sante:
        """Le moteur peut-il vraiment tourner ? On le lui demande.

        Ne PAS se contenter de l'existence d'un dossier : c'est le défaut
        corrigé sur le connecteur de navigation (DEC-0066), où deux imports
        Python réussis faisaient annoncer `OPERATIONNEL` un navigateur absent.
        """
        pret, manque = self.capacite.sonder()
        if not pret:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="Aucun moteur d'architecture disponible.",
                         ce_qui_manque=manque, mesure_le=_maintenant())
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=(f"Moteur « {self.capacite.backend.nom} » pret : "
                     f"{len(OPERATIONS)} operations."),
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : le moteur tourne en local, sans identifiant."""
        return True

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        """Ce que la confirmation doit montrer : la scène touchée, pas un jargon.

        Pour `batir_plan`, elle montre **le plan entier** — c'est la
        contrepartie d'une confirmation unique. Onze confirmations pour une
        phrase seraient inutilisables ; une confirmation qui cache ce qu'elle
        autorise serait pire. Le plan est donc affiche en toutes lettres,
        avec ce qu'ARENA n'a PAS compris.
        """
        if capacite.nom == "batir_plan":
            from core.architecture.plan import planifier, resumer
            plan = planifier(str(parametres.get("phrase") or ""),
                             nom_projet=str(parametres.get("titre") or ""))
            return (f"Sur la scene « {parametres.get('session') or 'defaut'} » :\n"
                    + resumer(plan))
        if capacite.ecriture:
            session = parametres.get("session") or "defaut"
            return (f"{OPERATIONS[capacite.nom]['quoi']} "
                    f"(scene « {session} », moteur {self.capacite.backend.nom}).")
        return super().resultat_attendu(capacite, **parametres)

    # --- Le coeur -------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        session = str(parametres.pop("session", "") or "defaut")
        if capacite.nom == "batir_plan":
            return self._batir_plan(session, **parametres)
        try:
            mesure = self.capacite.executer(capacite.nom, session=session,
                                            **parametres)
        except OperationInconnue as erreur:
            # Ne peut arriver que si `capacites()` et `OPERATIONS` divergent.
            return echec(action=capacite.nom, cible=self.nom, message=str(erreur))

        if not mesure.ok:
            # Un moteur absent n'est pas une panne : c'est une configuration
            # manquante, et le message dit quoi installer.
            if "n'est pas installe" in mesure.raison or "n'existe pas" in mesure.raison:
                return non_configure(action=capacite.nom, cible=self.nom,
                                     ce_qui_manque=mesure.raison)
            return echec(action=capacite.nom, cible=self.nom,
                         message=mesure.raison, journal=mesure.journal())

        # `journal=` et non `**mesure.journal()` : ce dictionnaire porte une
        # cle `action` (l'observabilite exigee par la mission : model,
        # capability, backend, action, duree...), et l'etaler ecrasait
        # l'argument `action` de `succes()`. Mesure du 07/09/2026 : toutes
        # les LECTURES levaient `got multiple values for keyword argument
        # 'action'` — sur le premier appel reel, pas en relisant le code.
        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"{OPERATIONS[capacite.nom]['quoi']} ({mesure.duree_ms} ms).",
            preuve=f"{mesure.backend}/{capacite.nom} sur « {session} »",
            scene=mesure.detail, journal=mesure.journal())

    def fermer_session(self, session: str = "defaut") -> None:
        """Libère le moteur de cette scène. Un appelant qui oublie le garde vivant."""
        self.capacite.fermer(session)

    def _batir_plan(self, session: str, phrase: str = "",
                    titre: str = "", **_: Any) -> ResultatAction:
        """Le plan entier, sous UNE confirmation deja donnee.

        La permission a ete accordee sur `batir_plan` (action `batir`), et le
        message de confirmation montrait le plan complet : executer ses
        operations ici ne contourne rien, c'est ce qui a ete autorise. Les
        repasser une a une par le registre demanderait onze confirmations
        pour une decision deja prise.

        Une operation qui echoue **arrete la suite**. Continuer sur une scene
        a moitie batie produirait un batiment que personne n'a demande, et
        que rien ne signalerait comme incomplet.
        """
        from core.architecture.plan import planifier, resumer, sequence

        plan = planifier(phrase, nom_projet=titre)
        if not plan.operations:
            return echec(action="batir_plan", cible=self.nom,
                         message="Rien a construire.\n" + resumer(plan))

        faites, niveau = [], ""
        for operation, parametres in sequence(plan):
            if niveau and operation in ("creer_coque", "creer_piece", "creer_mur"):
                parametres.setdefault("niveau", niveau)
            mesure = self.capacite.executer(operation, session=session, **parametres)
            faites.append({"operation": operation, "ok": mesure.ok,
                           "duree_ms": mesure.duree_ms, "raison": mesure.raison})
            if not mesure.ok:
                return echec(
                    action="batir_plan", cible=self.nom,
                    message=(f"Arrete a « {operation} » : {mesure.raison}\n\n"
                             + resumer(plan)),
                    operations=faites, session=session)
            if operation == "lister_niveaux":
                niveaux = (mesure.detail or {}).get("levels") or []
                if niveaux:
                    niveau = niveaux[0].get("id", "")

        total = sum(o["duree_ms"] for o in faites)
        return succes(
            action="batir_plan", cible=self.nom,
            message=f"Batiment construit sur « {session} ».\n\n" + resumer(plan),
            preuve=f"{len(faites)} operations en {total} ms",
            operations=faites, session=session, plan=resumer(plan),
            capability=self.capacite.nom, backend=self.capacite.backend.nom)
