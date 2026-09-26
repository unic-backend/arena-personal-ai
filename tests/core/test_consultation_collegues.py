"""Chaque agent peut consulter un collegue pendant son propre travail (DEC-0144).

Mesure du 26/09/2026 : sur vingt-cinq agents enregistres comme
collaborateurs, un seul — la production video — appelait jamais un collegue,
et les documents du proprietaire n'etaient consultables par aucun agent.
"""
from __future__ import annotations

import inspect
import json
from uuid import uuid4

import pytest

from core.agent.base_agent import CONSULTATIONS_MAX, BaseAgent
from core.agent.capacites import RegistreCapacites

DEMANDE = "[[COLLEGUE:documents|Quel est le prix du BA13 dans mes devis ?]]"
PRIX = "Le BA13 est facture 4 500 F la plaque (devis DV-7)."


class _Modele:
    """Rend les reponses prevues, dans l'ordre, et garde ce qu'on lui a dit."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []

    async def generate(self, prompt, system_prompt=None, **options):
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt, **options})
        return self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]

    async def generate_stream(self, prompt, system_prompt=None):
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt})
        texte = self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]
        for i in range(0, len(texte), 4):
            yield texte[i:i + 4]


class _Agent(BaseAgent):
    def __init__(self, nom, modele):
        super().__init__(nom, f"agent {nom}", modele)

    async def run(self, user_input, context=None):
        return {"status": "success", "agent": self.name,
                "response": await self.rediger(prompt=user_input)}


class _Documents:
    description = "documents du proprietaire"

    def __init__(self):
        self.questions = []

    async def run(self, user_input, context=None):
        self.questions.append(user_input)
        return {"status": "success", "agent": "LightRAG", "response": PRIX}


def _equipe(agent):
    registre = RegistreCapacites()
    documents = _Documents()
    registre.enregistrer("code", agent)
    registre.enregistrer("documents", documents)
    agent.collaborateurs = registre
    return documents


async def test_un_agent_consulte_un_collegue_puis_termine_son_travail():
    modele = _Modele(DEMANDE, "Devis : 10 plaques a 4 500 F = 45 000 F.")
    agent = _Agent("CoderAgent", modele)
    documents = _equipe(agent)

    reponse = await agent.rediger(prompt="calcule le prix de 10 plaques BA13")

    assert documents.questions == ["Quel est le prix du BA13 dans mes devis ?"]
    assert reponse == "Devis : 10 plaques a 4 500 F = 45 000 F."
    assert PRIX in modele.appels[1]["prompt"], "la reponse du collegue doit revenir au modele"
    assert "- documents" in modele.appels[0]["system_prompt"]
    assert "- code" not in modele.appels[0]["system_prompt"], "un agent ne se liste pas"


async def test_sans_equipe_rien_ne_change():
    modele = _Modele("reponse")
    agent = _Agent("CoderAgent", modele)

    assert await agent.rediger(prompt="bonjour") == "reponse"
    assert modele.appels == [{"prompt": "bonjour", "system_prompt": None}]


async def test_une_demande_repetee_s_arrete_et_n_est_jamais_montree():
    modele = _Modele(DEMANDE)
    agent = _Agent("CoderAgent", modele)
    documents = _equipe(agent)

    reponse = await agent.rediger(prompt="calcule")

    assert len(documents.questions) == CONSULTATIONS_MAX
    assert "[[COLLEGUE" not in reponse


async def test_une_boucle_entre_agents_s_arrete_sans_contexte_transmis():
    """B ne transmet AUCUN contexte a A : la chaine suit quand meme la requete."""
    registre = RegistreCapacites()
    a = _Agent("AgentA", _Modele("[[COLLEGUE:b|aide-moi]]", "fin A"))
    b = _Agent("AgentB", _Modele("[[COLLEGUE:a|aide-moi aussi]]", "fin B"))
    registre.enregistrer("a", a)
    registre.enregistrer("b", b)
    a.collaborateurs = b.collaborateurs = registre

    reponse = await a.rediger(prompt="tache")

    assert reponse == "fin A"
    assert len(a.provider.appels) == 2, "A ne doit jamais etre rappele par B"


async def test_le_flux_diffuse_une_reponse_ordinaire_telle_quelle():
    modele = _Modele("Bonjour Ousmane, voici la reponse.")
    agent = _Agent("OrchestratorAgent", modele)
    _equipe(agent)

    morceaux = [m async for m in agent.rediger_en_flux("bonjour")]

    assert "".join(morceaux) == "Bonjour Ousmane, voici la reponse."
    assert len(morceaux) > 1, "le flux ne doit pas etre retenu en entier"


async def test_le_flux_consulte_sans_montrer_la_demande():
    modele = _Modele(DEMANDE, "Le BA13 est a 4 500 F la plaque.")
    agent = _Agent("OrchestratorAgent", modele)
    documents = _equipe(agent)

    texte = "".join([m async for m in agent.rediger_en_flux("prix du BA13 ?")])

    assert texte == "Le BA13 est a 4 500 F la plaque."
    assert documents.questions


#: Les agents dont l'appel de travail principal doit passer par `rediger`.
AGENTS_BRANCHES = {
    "agents.coder.coder_agent": "CoderAgent",
    "agents.researcher.researcher_agent": "DeepResearcherAgent",
    "agents.fresh_info.fresh_info_agent": "FreshInfoAgent",
    "agents.dioumtoukay.dioumtoukay_agent": "DioumtoukayAgent",
    "agents.plaquiste.plaquiste_agent": "PlaquisteAgent",
    "agents.email.email_agent": "EmailAgent",
    "agents.social.social_agent": "SocialAgent",
    "agents.vision.vision_agent": "VisionAgent",
    "agents.orchestrator.orchestrator_agent": "OrchestratorAgent",
    "agents.video_analyzer.video_analyzer_agent": "VideoAnalyzerAgent",
    "agents.trend_analyzer.trend_analyzer_agent": "TrendAnalyzerAgent",
    "agents.finance.finance_agent": "FinanceAgent",
    "agents.repo_engineer.repo_engineer_agent": "RepoEngineerAgent",
    "agents.swe_agent.swe_agent": "SWEAgent",
    "agents.ui.ui_agent": "UiGenerationAgent",
    "agents.publisher.publisher_agent": "PublisherAgent",
}


@pytest.mark.parametrize("module, classe", sorted(AGENTS_BRANCHES.items()))
def test_chaque_agent_passe_par_la_consultation(module, classe):
    import importlib

    source = inspect.getsource(getattr(importlib.import_module(module), classe))
    assert "self.rediger(" in source, f"{classe} ne peut consulter aucun collegue"


def test_le_runtime_branche_toute_l_equipe_et_ses_outils():
    from apps.backend import runtime

    for cle in ("documents", "graphe", "raisonnement", "code", "recherche",
                "actualite", "atelier", "video_analyse", "plaquiste", "vision"):
        assert runtime.collaborateurs.connait(cle), cle
    for cle in runtime.collaborateurs.espaces():
        collegue = runtime.collaborateurs.obtenir(cle)
        if isinstance(collegue, BaseAgent):
            assert collegue.collaborateurs is runtime.collaborateurs, cle


def test_le_telephone_consulte_un_collegue(monkeypatch):
    """La conversation du telephone, par la vraie route `/agent/stream`."""
    from fastapi.testclient import TestClient

    from apps.backend import main
    from apps.backend import security as securite
    from apps.backend.routers import pwa_gateway

    async def _chat(*_a, **_k):
        return "CHAT"

    documents = _Documents()
    modele = _Modele(DEMANDE, "Le BA13 est a 4 500 F la plaque.")
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _chat)
    monkeypatch.setattr(pwa_gateway, "fast_provider", modele)
    monkeypatch.setitem(pwa_gateway.orchestrator.collaborateurs._capacites,
                        "documents", documents)
    monkeypatch.setattr(securite, "USMAN_API_KEY", "cle-consultation")
    securite.limiteur._passages.clear()
    client = TestClient(main.app, raise_server_exceptions=False)

    reponse = client.post("/agent/stream", headers={"Authorization": "Bearer cle-consultation"},
                          json={"text": "quel est le prix du BA13 ?",
                                "conversation_id": f"c-{uuid4()}", "run_id": f"r-{uuid4()}"})

    jetons = [json.loads(ligne[5:]) for ligne in reponse.text.splitlines()
              if ligne.startswith("data:")]
    texte = "".join(j.get("text", "") for j in jetons if j.get("type") == "token")
    assert documents.questions == ["Quel est le prix du BA13 dans mes devis ?"]
    assert "4 500 F" in texte
    assert "[[COLLEGUE" not in texte
