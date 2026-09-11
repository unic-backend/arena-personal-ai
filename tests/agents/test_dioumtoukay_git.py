"""Dioumtoukay et l'état Git structuré (DEC-0093) — sur un vrai dépôt, via
la boucle complète, jamais un raccourci qui contournerait le parsing réel.
"""
import subprocess
from pathlib import Path

import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from tools.atelier.atelier import Atelier


def _git(racine: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=str(racine), capture_output=True,
                   text=True, check=True)


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


@pytest.fixture
def depot(tmp_path) -> Path:
    racine = tmp_path / "depot"
    racine.mkdir()
    _git(racine, "init", "-q")
    _git(racine, "config", "user.email", "test@test.local")
    _git(racine, "config", "user.name", "test")
    (racine / "a.txt").write_text("contenu initial\n", encoding="utf-8")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-q", "-m", "initial")
    return racine


def agent(depot: Path, *reponses: str) -> DioumtoukayAgent:
    return DioumtoukayAgent(provider=ModeleScripte(*reponses), atelier=Atelier(racine=depot))


@pytest.mark.asyncio
class TestGitStatutEtDiff:
    async def test_git_statut_voit_un_fichier_reellement_modifie(self, depot):
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        a = agent(depot, "ACTION: git_statut\nDOSSIER: .")

        resultat = await a.run("regarde l'etat du depot")

        action = resultat["actions"][0]
        assert action["ok"] is True
        assert "1 modifie" in action["message"]

    async def test_git_diff_montre_le_vrai_contenu_change(self, depot):
        (depot / "a.txt").write_text("contenu initial\najoute par le test\n", encoding="utf-8")
        a = agent(depot, "ACTION: git_diff\nCIBLE: travail")

        resultat = await a.run("montre le diff")

        assert "+ajoute par le test" in resultat["actions"][0]["sortie"]


@pytest.mark.asyncio
class TestCheckpointDansLaBoucle:
    async def test_checkpoint_via_la_boucle_rend_un_identifiant_lisible(self, depot):
        a = agent(depot, "ACTION: git_checkpoint\nDOSSIER: .")

        resultat = await a.run("prepare un checkpoint avant de corriger")

        action = resultat["actions"][0]
        assert action["ok"] is True
        assert "cree" in action["message"].lower()

    async def test_un_second_passage_restaure_avec_l_identifiant_du_premier(self, depot):
        # Premier passage : amorce le checkpoint via l'atelier directement pour
        # obtenir un identifiant fiable (le format exact de la sortie texte
        # n'est pas le contrat — celui de `Atelier.git_checkpoint` l'est deja,
        # couvert par test_atelier_git.py).
        atelier = Atelier(racine=depot)
        checkpoint = atelier.git_checkpoint()
        identifiant = checkpoint.donnees["identifiant"]

        (depot / "cree_par_agent.txt").write_text("x", encoding="utf-8")

        a = DioumtoukayAgent(
            provider=ModeleScripte(f"ACTION: git_restaurer\nIDENTIFIANT: {identifiant}"),
            atelier=atelier)
        resultat = await a.run("annule ce que tu viens de faire")

        action = resultat["actions"][0]
        assert action["ok"] is True
        assert not (depot / "cree_par_agent.txt").exists()

    async def test_identifiant_manquant_est_refuse_sans_toucher_au_depot(self, depot):
        a = agent(depot, "ACTION: git_restaurer")

        resultat = await a.run("restaure")

        action = resultat["actions"][0]
        assert action["ok"] is False
        assert "IDENTIFIANT" in action["message"]
