"""Connecteur Hermes Agent Self-Evolution — jamais sur ce dépôt.

Demande directe du propriétaire (05/09/2026), après une question posée sur
DEC-0014 : le Gardien de maintenance a tranché — DÉCOUVRE et RAPPORTE,
jamais MODIFIE, aucune PR autonome sur ce dépôt, même relue avant fusion.
Hermes Agent Self-Evolution (NousResearch/hermes-agent-self-evolution,
MIT) fait exactement ça — proposer des PR qui font évoluer des
compétences/prompts — mais **sa cible n'est jamais ARENA** : sa réponse a
été explicite, « construis-le, mais pointe-le sur autre chose que ce
dépôt ARENA ». Ce connecteur porte donc une garde structurelle, jamais
seulement une promesse : `depot_cible` est REFUSÉ s'il tombe dans le dépôt
d'ARENA lui-même.

**Un programme séparé, jamais importé.** Ce dépôt d'évolution est cloné et
installé à côté, comme OpenTakeoff, WanGP, VoiceStudio, KrillinAI et
SiteGuard — jamais dans `requirements.txt` d'ARENA. Il est invoqué par
sous-processus (`python -m evolution.skills.evolve_skill`), la seule forme
d'appel qu'il expose (pas de serveur HTTP, contrairement à SiteGuard).

**`EXECUTE_COMMANDS` est le bon coupe-circuit, vérifié dans le code réel**
(`core/permissions/controle.py::ControleAcces.verifier`) : il est à `false`
par défaut dans `config/permissions.yaml`, et `interrupteur_de()` le lit
pour TOUTE capacité qui le déclare dans `config/permissions_services.yaml`
— exactement le chemin qu'emprunte ce connecteur. Une note d'audit
antérieure (`documents/USMAN_ENGINEERING_WORKLOG.md`, P-05) dit qu'un appel
direct et plus ancien à `PermissionManager.is_allowed()` ne le consultait
nulle part ; ce connecteur, lui, passe par `Connecteur._conduire()` comme
tous les autres — le chemin réellement gardé.

**Une exécution reste une exécution : `CONFIRMATION`, risque `HIGH`.** Le
config par défaut de l'outil ouvre une PR (`create_pr: True`, vérifié dans
son code source) — un effet visible sur un dépôt réel, jamais lancé
d'autorité.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import BASE_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.hermes_evolution")

CE_QUI_MANQUE = (
    "L'outil n'est pas installé : cloner "
    "https://github.com/NousResearch/hermes-agent-self-evolution à côté "
    "(jamais dans ce dépôt), `pip install -r requirements.txt` dans SON "
    "propre environnement, puis HERMES_EVOLUTION_DIR=/chemin/vers/le/clone "
    "dans .env."
)

SOURCES_EVALUATION = ("synthetic", "sessiondb")

#: Bornes de sécurité — une évolution qui tourne sans fin transforme un
#: outil utile en boucle incontrôlée (même principe que
#: `core/execution/coordination.py` : la reprise est bornée).
ITERATIONS_MAX = 50
TIMEOUT_SECONDES_DEFAUT = 1800.0
TIMEOUT_SECONDES_MAX = 7200.0

DUREE_SONDE_SECONDES = 60.0


def _racine_outil() -> str:
    return os.getenv("HERMES_EVOLUTION_DIR", "").strip()


def _cible_hors_du_depot(chemin: str) -> bool:
    """Faux si `chemin` tombe dans le dépôt d'ARENA — à refuser.

    Même garde que `chemin_hors_du_depot` (`agents/plaquiste/
    plaquiste_agent.py`) : ARENA ne peut jamais être la cible d'une
    évolution automatique, quelle que soit la demande.
    """
    try:
        resolu = Path(chemin).resolve()
        resolu.relative_to(BASE_DIR.resolve())
    except (ValueError, OSError):
        return True
    return False


class ConnecteurHermesEvolution(Connecteur):
    """Fait évoluer les compétences d'un agent Hermes CIBLE — jamais ARENA."""

    service = "hermes_evolution"
    nom = "hermes_evolution"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "evoluer": Capacite(
                nom="evoluer", action="execute",
                description=(
                    "Lance une évolution GEPA d'une compétence sur un dépôt "
                    "hermes-agent CIBLE (jamais ARENA) — peut ouvrir une PR."),
                ecriture=True),
        }

    def authentifier(self) -> bool:
        """Vrai : un sous-processus local, aucun identifiant à présenter ici
        (l'outil lui-même lit les siens dans SON propre environnement)."""
        return True

    def sonder(self) -> Sante:
        import time
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        racine = _racine_outil()
        if not racine:
            sante = Sante(etat=EtatSante.NON_CONFIGURE, message="HERMES_EVOLUTION_DIR absent.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            try:
                resultat = subprocess.run(
                    [sys.executable, "-m", "evolution.skills.evolve_skill", "--help"],
                    cwd=racine, capture_output=True, text=True, timeout=15.0)
            except (OSError, subprocess.TimeoutExpired) as erreur:
                sante = Sante(etat=EtatSante.NON_CONFIGURE, message=f"Outil injoignable : {erreur}",
                             ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
            else:
                if resultat.returncode == 0:
                    sante = Sante(etat=EtatSante.OPERATIONNEL,
                                 message="L'outil d'évolution répond (--help).",
                                 mesure_le=_maintenant())
                else:
                    sante = Sante(etat=EtatSante.EN_PANNE,
                                 message=f"L'outil répond en erreur (code {resultat.returncode}).",
                                 mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        depot_cible = str(parametres.get("depot_cible") or "").strip()
        competence = str(parametres.get("competence") or "").strip()
        source_evaluation = str(parametres.get("source_evaluation") or "synthetic").strip()
        try:
            iterations = int(parametres.get("iterations") or 3)
        except (TypeError, ValueError):
            return echec(action=capacite.nom, cible=self.nom,
                         message="`iterations` doit être un entier.")
        try:
            timeout_secondes = float(parametres.get("timeout_secondes") or TIMEOUT_SECONDES_DEFAUT)
        except (TypeError, ValueError):
            return echec(action=capacite.nom, cible=self.nom,
                         message="`timeout_secondes` doit être un nombre.")

        if not depot_cible:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun dépôt cible fourni : rien à faire évoluer.")
        if not _cible_hors_du_depot(depot_cible):
            logger.warning("Cible d'évolution refusée (dans le dépôt d'ARENA) : %s", depot_cible)
            return echec(
                action=capacite.nom, cible=self.nom,
                message=("Refusé : ARENA ne peut jamais être la cible de sa propre "
                         "évolution automatique (DEC-0014, DEC-0055)."))
        if not Path(depot_cible).is_dir():
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Aucun dépôt à ce chemin : {depot_cible}")
        if not competence:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucune compétence (`--skill`) fournie.")
        if source_evaluation not in SOURCES_EVALUATION:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=(f"Source d'évaluation inconnue : {source_evaluation!r}. "
                         f"Connues : {', '.join(SOURCES_EVALUATION)}."))
        if not 1 <= iterations <= ITERATIONS_MAX:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"`iterations` doit rester entre 1 et {ITERATIONS_MAX}.")
        if not 1.0 <= timeout_secondes <= TIMEOUT_SECONDES_MAX:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"`timeout_secondes` doit rester sous {TIMEOUT_SECONDES_MAX:g}.")

        racine = _racine_outil()
        if not racine:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)

        environnement = dict(os.environ)
        environnement["HERMES_AGENT_REPO"] = str(Path(depot_cible).resolve())

        commande = [
            sys.executable, "-m", "evolution.skills.evolve_skill",
            "--skill", competence, "--iterations", str(iterations),
            "--eval-source", source_evaluation,
        ]
        try:
            resultat = subprocess.run(
                commande, cwd=racine, env=environnement,
                capture_output=True, text=True, timeout=timeout_secondes)
        except subprocess.TimeoutExpired:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"Évolution interrompue après {timeout_secondes:g} s sans conclure.")
        except OSError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Impossible de lancer l'outil : {erreur}")

        if resultat.returncode != 0:
            derniere_ligne = (resultat.stderr or resultat.stdout or "").strip().splitlines()[-1:] \
                or ["aucune sortie"]
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"Évolution en échec (code {resultat.returncode}) : {derniere_ligne[0]}")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Évolution de « {competence} » terminée sur {depot_cible} "
                     f"({iterations} itération(s))."),
            preuve=f"{competence}@{depot_cible}",
            sortie=resultat.stdout[-4000:],
        )
