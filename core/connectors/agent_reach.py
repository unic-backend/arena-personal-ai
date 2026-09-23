"""Agent Reach capability layer for ARENA.

Agent Reach is deliberately used as a selector/doctor, not copied as another
search agent. Once a platform is healthy, ARENA calls Agent Reach's upstream
backend through its CLI contract. Read/search only here: posting remains owned
by Arena's explicit social connectors and confirmation policy.

Upstream: Panniantong/Agent-Reach (MIT), v1.5 capability-layer design.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

PLATEFORMES = (
    "twitter", "reddit", "youtube", "github", "bilibili", "xiaohongshu",
    "linkedin", "facebook", "instagram", "rss", "web",
)


class ConnecteurAgentReach(Connecteur):
    service = "web"
    nom = "agent_reach"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "doctor": Capacite("doctor", "read", "Mesure les backends Agent Reach disponibles."),
            "search": Capacite("search", "read", "Recherche une plateforme via son backend sain."),
            "read": Capacite("read", "read", "Lit une URL via le backend sain de sa plateforme."),
        }

    def authentifier(self) -> bool:
        return shutil.which("agent-reach") is not None

    @staticmethod
    def _run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout, check=False,
        )

    def _doctor(self) -> tuple[Sante, Dict[str, Any]]:
        exe = shutil.which("agent-reach")
        if not exe:
            return Sante(
                EtatSante.NON_CONFIGURE,
                message="Agent Reach n'est pas installe.",
                ce_qui_manque="agent-reach CLI",
                mesure_le=_maintenant(),
            ), {}
        try:
            proc = self._run(exe, "doctor", "--json", timeout=45)
        except (OSError, subprocess.TimeoutExpired) as err:
            return Sante(
                EtatSante.EN_PANNE, message=f"Agent Reach doctor: {type(err).__name__}",
                mesure_le=_maintenant(),
            ), {}
        if proc.returncode != 0:
            return Sante(
                EtatSante.EN_PANNE,
                message=(proc.stderr or proc.stdout or "doctor en echec").strip()[-600:],
                mesure_le=_maintenant(),
            ), {}
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return Sante(
                EtatSante.EN_PANNE, message="Agent Reach doctor n'a pas rendu du JSON valide.",
                mesure_le=_maintenant(),
            ), {}
        return Sante(
            EtatSante.OPERATIONNEL, message="Agent Reach doctor repond.",
            mesure_le=_maintenant(),
        ), data

    def sonder(self) -> Sante:
        return self._doctor()[0]

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        health, diagnostic = self._doctor()
        if not health.utilisable:
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque=health.ce_qui_manque or health.message,
            )
        if capacite.nom == "doctor":
            return succes(
                action="doctor", cible=self.nom,
                message=json.dumps(diagnostic, ensure_ascii=False)[:12000],
            )

        plateforme = str(parametres.get("plateforme") or "web").strip().lower()
        if plateforme not in PLATEFORMES:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"Plateforme non autorisee: {plateforme}.",
            )
        valeur = str(
            parametres.get("query") if capacite.nom == "search"
            else parametres.get("url") or ""
        ).strip()
        if not valeur:
            return echec(action=capacite.nom, cible=self.nom, message="Requete ou URL absente.")

        exe = shutil.which("agent-reach")
        # Agent Reach v1.5 routes to an ordered backend per capability. We ask
        # its CLI for the selected route; no shell=True and no arbitrary args.
        args = [exe, capacite.nom, plateforme, valeur, "--json"]
        try:
            proc = self._run(*args, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as err:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"Agent Reach {capacite.nom}: {type(err).__name__}",
            )
        if proc.returncode != 0:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=(proc.stderr or proc.stdout or "appel en echec").strip()[-1200:],
            )
        return succes(
            action=capacite.nom, cible=self.nom,
            message=(proc.stdout or "").strip()[:30000],
        )
