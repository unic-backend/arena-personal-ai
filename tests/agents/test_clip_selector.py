"""ClipSelectorAgent : choix du meilleur extrait et découpe.

Le premier test exige ffmpeg et Ollama. Les suivants n'exigent rien : ils
portent sur ce que l'agent **annonce**, et ils existent à cause d'un défaut
mesuré le 01/09/2026 — sans segments, donc sans aucune analyse, il répondait
« 🔥 Extrait le plus viral détecté (0.0s -> 15.0s) » sur une vidéo de 6,7 s.
"""
import pytest

from agents.clip_selector.clip_selector_agent import ClipSelectorAgent

SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "Bonjour à tous, bienvenue dans cette vidéo."},
    {"start": 4.0, "end": 12.0, "text": "Aujourd'hui, le plus grand secret de l'innovation au Sénégal !"},
    {"start": 12.0, "end": 18.0, "text": "Merci d'avoir regardé, abonnez-vous."},
]


@pytest.mark.integration
async def test_un_extrait_est_selectionne_et_decoupe(ollama_en_ligne, video_de_test, memoire):
    agent = ClipSelectorAgent(provider=ollama_en_ligne, memory=memoire)

    res = await agent.run(
        "Trouve le meilleur moment viral",
        context={"video_path": str(video_de_test), "segments": SEGMENTS},
    )

    assert res["status"] == "success"

class ModeleDouble:
    def __init__(self, reponse="{}"):
        self.reponse = reponse

    async def is_available(self):
        return True

    async def generate(self, prompt: str, **_):
        return self.reponse


@pytest.fixture
def agent(monkeypatch, tmp_path):
    def construire(reponse="{}"):
        a = ClipSelectorAgent(provider=ModeleDouble(reponse))
        # Les deux outils vidéo sont doublés : ce test porte sur ce qui est
        # ANNONCÉ, pas sur ffmpeg — déjà couvert ailleurs.
        a.ffmpeg.cut_video = lambda *a_, **k: True
        a.crop_tool.convert_to_vertical_9_16 = lambda src, dst: (
            __import__("pathlib").Path(dst).parent.mkdir(parents=True, exist_ok=True)
            or __import__("pathlib").Path(dst).write_bytes(b"x") or True)
        return a
    return construire


@pytest.fixture
def source(tmp_path):
    fichier = tmp_path / "chantier.mp4"
    fichier.write_bytes(b"x")
    return fichier


class TestSansAnalyseIlNeParlePasDeDetection:
    @pytest.mark.asyncio
    async def test_sans_segments_ce_n_est_pas_une_detection(self, agent, source, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        resultat = await agent().run("meilleur extrait", context={"video_path": str(source)})

        assert resultat["detecte"] is False
        assert "détecté" not in resultat["response"], (
            "une détection qui n'a pas eu lieu est annoncée comme telle"
        )
        assert "Aucune analyse" in resultat["response"]

    @pytest.mark.asyncio
    async def test_avec_une_analyse_reelle_la_detection_est_annoncee(
        self, agent, source, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        a = agent('{"start": 3.0, "end": 12.0, "reason": "le moment fort"}')
        resultat = await a.run("meilleur extrait", context={
            "video_path": str(source),
            "segments": [{"start": 0.0, "end": 20.0, "text": "on pose la cloison"}]})

        assert resultat["detecte"] is True
        assert "détecté" in resultat["response"]
        assert resultat["start_sec"] == 3.0

    @pytest.mark.asyncio
    async def test_un_json_illisible_ne_devient_pas_une_detection(
        self, agent, source, monkeypatch, tmp_path
    ):
        """Le modèle qui répond n'importe quoi ne vaut pas une analyse."""
        monkeypatch.chdir(tmp_path)
        a = agent("je ne sais pas trop")
        resultat = await a.run("meilleur extrait", context={
            "video_path": str(source),
            "segments": [{"start": 0.0, "end": 20.0, "text": "x"}]})

        assert resultat["detecte"] is False
        assert "détecté" not in resultat["response"]


class TestLeFichierManquantResteUneErreur:
    @pytest.mark.asyncio
    async def test_video_introuvable(self, agent, tmp_path):
        resultat = await agent().run("x", context={"video_path": str(tmp_path / "rien.mp4")})
        assert resultat["status"] == "error"
