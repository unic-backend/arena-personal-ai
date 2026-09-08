"""Dioumtoukay consulte RepoEngineerAgent et SWEAgent en cours de tâche (DEC-0073).

Avant : deux portes séparées (`REPO_ENGINEERING`, `SWE_FIX`) que le
propriétaire devait choisir à la place de Dioumtoukay, et dont l'analyse ne
lui servait jamais — `agents/orchestrator/orchestrator_agent.py` les route
encore, ce fichier ne teste que le nouveau chemin.

**Ce qui doit rester vrai, et c'est tout ce que ces tests gardent :**

- `analyser`/`diagnostiquer` rendent la réponse du spécialiste, telle quelle.
- Ni l'un ni l'autre ne peut modifier un fichier — ce sont des actions en
  lecture seule, exactement comme leurs agents le sont déjà seuls
  (`agents/repo_engineer/`, `agents/swe_agent/`).
- Un spécialiste absent, ou qui lève, ne casse jamais la tâche de Dioumtoukay.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import ACTIONS_QUI_MODIFIENT, DioumtoukayAgent
from tools.atelier import Atelier


class ModeleScripte:
    """Même double que test_dioumtoukay.py : des réponses écrites d'avance."""

    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


class SpecialisteScripte:
    """Un `RepoEngineerAgent`/`SWEAgent` factice : une réponse, une trace des
    questions reçues — jamais le vrai agent, jamais de vrai modèle."""

    def __init__(self, reponse: str = "voici l'analyse", statut: str = "success"):
        self.reponse = reponse
        self.statut = statut
        self.questions = []

    async def run(self, question, context=None):
        self.questions.append(question)
        return {"status": self.statut, "response": self.reponse}


class SpecialisteQuiLeve:
    async def run(self, question, context=None):
        raise RuntimeError("le fournisseur n'a pas repondu")


def agent(bac, reponses, analyste=None, chercheur_de_bug=None):
    return DioumtoukayAgent(
        provider=ModeleScripte(*reponses), atelier=Atelier(racine=bac),
        analyste=analyste, chercheur_de_bug=chercheur_de_bug)


@pytest.fixture
def bac(tmp_path):
    return tmp_path


# --- analyser -----------------------------------------------------------------------

class TestAnalyser:
    @pytest.mark.asyncio
    async def test_la_reponse_de_lanalyste_arrive_dans_le_rapport(self, bac):
        analyste = SpecialisteScripte("le depot separe agents/ et core/")
        a = agent(bac, [
            "ACTION: analyser\nTEXTE: comment est organise ce depot ?",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], analyste=analyste)

        resultat = await a.run("explique l'architecture")

        assert analyste.questions == ["comment est organise ce depot ?"]
        assert "le depot separe agents/ et core/" in resultat["response"]

    @pytest.mark.asyncio
    async def test_sans_analyste_branche_lechec_est_rapporte(self, bac):
        a = agent(bac, [
            "ACTION: analyser\nTEXTE: comment est organise ce depot ?",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], analyste=None)

        resultat = await a.run("explique l'architecture")

        assert "n'est pas branche" in resultat["response"]

    @pytest.mark.asyncio
    async def test_un_analyste_qui_leve_ne_casse_pas_la_tache(self, bac):
        """Un outil consulte en chemin echoue ; la tache de Dioumtoukay continue
        et se termine normalement — elle ne remonte pas une exception."""
        a = agent(bac, [
            "ACTION: analyser\nTEXTE: la structure",
            "ACTION: terminer\nCONTENU:\nfini apres l'echec\nFIN",
        ], analyste=SpecialisteQuiLeve())

        resultat = await a.run("explique")

        assert resultat["status"] == "success"
        assert "n'a pas repondu" in resultat["response"]


# --- diagnostiquer --------------------------------------------------------------------

class TestDiagnostiquer:
    @pytest.mark.asyncio
    async def test_la_reponse_du_chercheur_de_bug_arrive_dans_le_rapport(self, bac):
        chercheur = SpecialisteScripte("le bug est dans pwa_gateway.py ligne 42")
        a = agent(bac, [
            "ACTION: diagnostiquer\nTEXTE: /machine/adresse rend 500",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], chercheur_de_bug=chercheur)

        resultat = await a.run("trouve le bug")

        assert chercheur.questions == ["/machine/adresse rend 500"]
        assert "pwa_gateway.py ligne 42" in resultat["response"]

    @pytest.mark.asyncio
    async def test_un_echec_declare_par_le_specialiste_est_rapporte(self, bac):
        """Le specialiste peut rendre `status: error` sans lever — le rapporter
        est different de l'ignorer."""
        chercheur = SpecialisteScripte("aucune piste trouvee", statut="error")
        a = agent(bac, [
            "ACTION: diagnostiquer\nTEXTE: bug introuvable",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], chercheur_de_bug=chercheur)

        resultat = await a.run("trouve le bug")

        rendu = resultat["actions"][0]
        assert rendu["ok"] is False
        assert "aucune piste trouvee" in rendu["message"]


# --- La garde qui compte : ni l'un ni l'autre ne modifie quoi que ce soit ---------

def test_analyser_et_diagnostiquer_ne_sont_pas_des_actions_qui_modifient():
    """S'ils entraient dans `ACTIONS_QUI_MODIFIENT`, `fichiers_touches()` les
    compterait comme une ecriture reelle — un mensonge dans le rapport, pour
    deux actions qui ne touchent jamais un fichier."""
    assert "analyser" not in ACTIONS_QUI_MODIFIENT
    assert "diagnostiquer" not in ACTIONS_QUI_MODIFIENT


@pytest.mark.asyncio
async def test_analyser_napparait_jamais_dans_les_fichiers_modifies(bac):
    analyste = SpecialisteScripte("analyse complete")
    a = agent(bac, [
        "ACTION: analyser\nTEXTE: la structure",
        "ACTION: terminer\nCONTENU:\nfini\nFIN",
    ], analyste=analyste)

    resultat = await a.run("explique")

    assert resultat["fichiers_modifies"] == []
