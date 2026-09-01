"""« Un projet vidéo complet » : l'intention VIDEO_PROJET atteint-elle
vraiment `VideoProductionAgent` ?

Ce fichier tient le BRANCHEMENT (DEC-0037) — `VideoProductionAgent` a ses
propres tests (`tests/agents/video/test_production_agent.py`), et la
classification de l'intention les siens
(`tests/agents/test_orchestrator.py::TestAiguillageDuProjetVideo`). Aucun
test n'appelle Ollama.
"""
from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request


class VideoProductionAgentDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse or {"status": "success", "agent": "VideoProductionAgent",
                                    "response": "ok", "projet": {}}

    async def run(self, objectif, context=None):
        self.appels.append((objectif, context))
        return self._reponse


async def test_video_projet_atteint_reellement_l_agent(monkeypatch):
    double = VideoProductionAgentDouble()
    monkeypatch.setattr(routeur_chat, "video_production_agent", double)
    monkeypatch.setattr(routeur_chat, "medias_montables", lambda video_path=None: ["/media/x.jpg"])

    resultat = await dispatch_request(
        ChatRequest(prompt="un projet vidéo complet pour ce chantier", session_id="test"),
        intent="VIDEO_PROJET")

    assert resultat["status"] == "success"
    assert double.appels == [
        ("un projet vidéo complet pour ce chantier", {"references": ["/media/x.jpg"]})]


async def test_video_projet_transmet_l_inventaire_reel_des_medias(monkeypatch):
    """Meme discipline que MONTAGE : les references viennent du serveur
    (`medias_montables`), jamais d'un chemin cite par la phrase."""
    double = VideoProductionAgentDouble()
    monkeypatch.setattr(routeur_chat, "video_production_agent", double)
    appels_inventaire = []

    def inventaire(video_path=None):
        appels_inventaire.append(video_path)
        return []

    monkeypatch.setattr(routeur_chat, "medias_montables", inventaire)

    await dispatch_request(
        ChatRequest(prompt="produis une vidéo complète", session_id="test",
                   video_path="/media/incoming/plan.pdf"),
        intent="VIDEO_PROJET")

    assert appels_inventaire == ["/media/incoming/plan.pdf"]


async def test_une_reponse_en_echec_de_l_agent_n_est_pas_maquillee(monkeypatch):
    double = VideoProductionAgentDouble(reponse={
        "status": "error", "agent": "VideoProductionAgent",
        "response": "Le plan de projet propose ne tient pas."})
    monkeypatch.setattr(routeur_chat, "video_production_agent", double)
    monkeypatch.setattr(routeur_chat, "medias_montables", lambda video_path=None: [])

    resultat = await dispatch_request(
        ChatRequest(prompt="un projet vidéo complet", session_id="test"),
        intent="VIDEO_PROJET")

    assert resultat["status"] == "error"
