"""Connecteur `file_organization` — inspecter un dossier, proposer un plan
de classement, le valider, l'appliquer sous confirmation, l'annuler.

Mission « AI File Sorter » (09/09/2026) — voir `docs/audits/
ai_file_sorter_audit.md`. Ce connecteur ne touche JAMAIS le filesystem
directement : chaque mutation passe par `tools/atelier/atelier.py`
(DEC-0038, la seule main d'ARENA), via `core/production/organisation/`.

**Cinq règles :**

1. **Un plan est toujours REVU avant d'être appliqué.** `planifier` ne
   mute rien — il valide et rend un identifiant. `appliquer` exige cet
   identifiant, jamais une liste d'opérations fournie directement : un
   modèle ne peut pas sauter l'étape de validation en rappelant
   `appliquer` avec de nouvelles opérations non vérifiées.

2. **Une suppression demande un accord SÉPARÉ**, en plus de la
   confirmation ordinaire du plan — mission §18, « écrasement d'un fichier
   existant => protection appropriée ». `appliquer(..., confirmer_
   suppression=True)` est le seul chemin qui laisse passer un plan
   contenant `SUPPRIMER` ; sans lui, le plan est refusé avant tout accès
   disque, même déjà confirmé par ailleurs.

3. **Le dossier confié borne tout le plan.** Aucune opération, source ou
   destination, ne peut sortir du dossier passé à `inspecter`/`planifier`
   — `core/production/organisation/securite.py` le vérifie avant que quoi
   que ce soit ne soit tenté.

4. **Un plan appliqué reste annulable**, tant que ses opérations le
   permettent — `SUPPRIMER` ne l'est jamais, et `annuler` le dit
   explicitement plutôt que de prétendre avoir tout défait.

5. **Apprendre est un bonus, jamais une condition.** Un classement appliqué
   reste appliqué même si l'écriture en mémoire (`core/production/
   organisation/memoire.py`) échoue.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.organisation import application, inspection, memoire, securite
from core.production.organisation.plan import Operation, Plan, StatutPlan, TypeOperation

logger = logging.getLogger("usman.connecteurs.file_organization")

#: Formats de TypeOperation acceptes en entree, tels qu'un appelant les ecrit.
_TYPES_CONNUS = {t.value: t for t in TypeOperation}


class ConnecteurFileOrganization(Connecteur):
    """Classe des fichiers d'un dossier confié — inspecter, planifier,
    valider, appliquer, annuler. Jamais un deuxième moteur de fichiers :
    toute mutation passe par `Atelier`."""

    service = "file_organization"
    nom = "file_organization"

    def __init__(self, atelier: Optional[Any] = None,
                memoire_longue: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if atelier is None:
            from tools.atelier import Atelier
            atelier = Atelier()
        self.atelier = atelier
        self.memoire_longue = memoire_longue
        # En memoire, le temps du process — meme discipline que
        # `core/actions/attente.py` (FileDAttente) pour les confirmations :
        # un plan propose puis applique traverse plusieurs appels.
        self._plans: Dict[str, Plan] = {}

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "inspecter": Capacite(
                nom="inspecter", action="lecture",
                description="Liste un dossier confié, avec metadonnees et extrait de contenu.",
                ecriture=False),
            "planifier": Capacite(
                nom="planifier", action="lecture",
                description="Valide une liste d'operations proposees ; ne mute rien.",
                ecriture=False),
            "appliquer": Capacite(
                nom="appliquer", action="document",
                description="Applique un plan deja valide.",
                ecriture=True),
            "annuler": Capacite(
                nom="annuler", action="document",
                description="Annule un plan deja applique, la ou c'est reversible.",
                ecriture=True),
            "etat": Capacite(
                nom="etat", action="lecture",
                description="Etat d'un plan (propose/valide/applique/annule/echec).",
                ecriture=False),
        }

    def authentifier(self) -> bool:
        return True  # aucun service distant

    def sonder(self) -> Sante:
        return Sante(etat=EtatSante.OPERATIONNEL,
                    message="Atelier disponible, aucune dependance externe.",
                    mesure_le=_maintenant())

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        if capacite.nom == "appliquer":
            plan = self._plans.get(str(parametres.get("plan_id") or ""))
            n = len(plan.operations) if plan else 0
            return f"Applique {n} operation(s) de classement de fichiers reelles sur le disque."
        if capacite.nom == "annuler":
            return "Defait un plan de classement deja applique, la ou c'est reversible."
        return capacite.description

    # --- inspecter --------------------------------------------------------------

    def _inspecter(self, dossier: Any, avec_contenu: Any) -> ResultatAction:
        dossier = str(dossier or ".")
        inventaire = inspection.inspecter_dossier(self.atelier, dossier, bool(avec_contenu))
        if not inventaire.entrees:
            resultat_brut = self.atelier.lister(dossier)
            if not resultat_brut.ok:
                return echec("inspecter", self.nom, f"Dossier illisible : {resultat_brut.message}")
        return succes(
            "inspecter", self.nom,
            message=f"« {dossier} » : {len(inventaire.entrees)} entree(s).",
            preuve=dossier, inventaire=inventaire.to_dict())

    # --- planifier ---------------------------------------------------------------

    def _planifier(self, dossier: Any, operations_brutes: Any,
                   ecrasements_autorises: Any) -> ResultatAction:
        dossier = str(dossier or ".")
        if not isinstance(operations_brutes, list) or not operations_brutes:
            return echec("planifier", self.nom, "`operations` doit etre une liste non vide.")

        operations: List[Operation] = []
        for i, brut in enumerate(operations_brutes):
            if not isinstance(brut, dict):
                return echec("planifier", self.nom, f"operation {i} : doit etre un objet.")
            type_brut = str(brut.get("type") or "")
            type_op = _TYPES_CONNUS.get(type_brut)
            if type_op is None:
                return echec("planifier", self.nom,
                            f"operation {i} : type inconnu « {type_brut} » — "
                            f"attendu l'un de {sorted(_TYPES_CONNUS)}.")
            operations.append(Operation(
                type=type_op, source=str(brut.get("source") or ""),
                destination=str(brut.get("destination") or ""),
                raison=str(brut.get("raison") or "")))

        racine = self.atelier.racine / dossier if not Path(dossier).is_absolute() else Path(dossier)
        indices_ecrasement = set(ecrasements_autorises or [])
        valide, raisons = securite.valider_plan(racine, operations, indices_ecrasement)

        plan = Plan(operations=operations)
        if valide:
            plan.statut = StatutPlan.VALIDE
        else:
            plan.statut = StatutPlan.REFUSE
            plan.raisons_refus = raisons
        self._plans[plan.identifiant] = plan

        if not valide:
            return echec(
                "planifier", self.nom,
                f"Plan refuse ({len(raisons)} probleme(s)) : {'; '.join(raisons)}",
                plan_id=plan.identifiant, plan=plan.to_dict())

        contient_suppression = any(o.type is TypeOperation.SUPPRIMER for o in operations)
        return succes(
            "planifier", self.nom,
            message=f"Plan {plan.identifiant} valide : {len(operations)} operation(s). "
                    + ("Contient des SUPPRESSIONS, irreversibles — confirmer_suppression=True "
                       "sera exige a l'application. " if contient_suppression else "")
                    + "Appelle `appliquer` avec cet identifiant pour l'executer.",
            preuve=plan.identifiant, plan_id=plan.identifiant, plan=plan.to_dict())

    # --- appliquer -----------------------------------------------------------------

    def _appliquer(self, plan_id: Any, confirmer_suppression: Any) -> ResultatAction:
        plan = self._plans.get(str(plan_id or ""))
        if plan is None:
            return echec("appliquer", self.nom, f"Aucun plan connu avec l'identifiant « {plan_id} ».")
        if plan.statut is not StatutPlan.VALIDE:
            return echec("appliquer", self.nom,
                         f"Le plan {plan.identifiant} est {plan.statut.value}, "
                         f"pas VALIDATED — il ne peut pas etre applique.")

        contient_suppression = any(o.type is TypeOperation.SUPPRIMER for o in plan.operations)
        if contient_suppression and not confirmer_suppression:
            return echec(
                "appliquer", self.nom,
                f"Le plan {plan.identifiant} contient des SUPPRESSIONS, irreversibles. "
                f"Rappelle avec confirmer_suppression=true pour les autoriser explicitement. "
                f"Rien n'a ete touche.")

        application.appliquer_plan(self.atelier, plan)
        ecrits = memoire.apprendre_du_plan(self.memoire_longue, plan)

        statut_ok = plan.statut is StatutPlan.APPLIQUE
        message = (f"Plan {plan.identifiant} : {plan.deplaces} deplace(s), {plan.copies} copie(s), "
                  f"{plan.dossiers_crees} dossier(s) cree(s), {plan.supprimes} supprime(s), "
                  f"{plan.echecs} echec(s).")
        if statut_ok:
            return succes("appliquer", self.nom, message=message, preuve=plan.identifiant,
                          plan_id=plan.identifiant, plan=plan.to_dict(),
                          souvenirs_appris=ecrits)
        return echec("appliquer", self.nom, message=message,
                     plan_id=plan.identifiant, plan=plan.to_dict())

    # --- annuler ---------------------------------------------------------------------

    def _annuler(self, plan_id: Any) -> ResultatAction:
        plan = self._plans.get(str(plan_id or ""))
        if plan is None:
            return echec("annuler", self.nom, f"Aucun plan connu avec l'identifiant « {plan_id} ».")
        if plan.statut not in (StatutPlan.APPLIQUE, StatutPlan.ECHEC):
            return echec("annuler", self.nom,
                         f"Le plan {plan.identifiant} est {plan.statut.value} — "
                         f"seul un plan APPLIED (ou FAILED, partiellement applique) s'annule.")

        application.annuler_plan(self.atelier, plan)
        # Le type de l'operation d'ORIGINE decide, jamais un texte de message
        # (fragile — mesure ici meme : un premier essai cherchait "reversible"
        # sans l'accent dans un message qui l'a, et ne comptait donc jamais
        # rien).
        irreversibles = sum(1 for r in plan.rapports_application
                            if not r.ok and r.operation.type is TypeOperation.SUPPRIMER)
        return succes(
            "annuler", self.nom,
            message=f"Plan {plan.identifiant} annule. "
                    + (f"{irreversibles} operation(s) irreversible(s) (suppressions) "
                       f"n'ont pas pu etre defaites. " if irreversibles else "")
                    + f"{sum(1 for r in plan.rapports_application if r.ok)} operation(s) defaite(s).",
            preuve=plan.identifiant, plan_id=plan.identifiant, plan=plan.to_dict())

    # --- etat --------------------------------------------------------------------

    def _etat(self, plan_id: Any) -> ResultatAction:
        plan = self._plans.get(str(plan_id or ""))
        if plan is None:
            return echec("etat", self.nom, f"Aucun plan connu avec l'identifiant « {plan_id} ».")
        return succes("etat", self.nom, message=f"Plan {plan.identifiant} : {plan.statut.value}.",
                     preuve=plan.identifiant, plan=plan.to_dict())

    # --- Dispatch --------------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "inspecter":
            return self._inspecter(parametres.get("dossier"), parametres.get("avec_contenu"))
        if capacite.nom == "planifier":
            return self._planifier(parametres.get("dossier"), parametres.get("operations"),
                                   parametres.get("ecrasements_autorises"))
        if capacite.nom == "appliquer":
            return self._appliquer(parametres.get("plan_id"), parametres.get("confirmer_suppression"))
        if capacite.nom == "annuler":
            return self._annuler(parametres.get("plan_id"))
        if capacite.nom == "etat":
            return self._etat(parametres.get("plan_id"))
        return echec(capacite.nom, self.nom, "Capacite non cablee.")
