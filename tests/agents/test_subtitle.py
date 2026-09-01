"""SubtitleAgent : génération du fichier SRT. Exige Whisper et Ollama."""
import pytest

from agents.subtitle.subtitle_agent import SubtitleAgent


@pytest.mark.integration
async def test_les_sous_titres_sont_generes(ollama_en_ligne, memoire):
    agent = SubtitleAgent(provider=ollama_en_ligne, memory=memoire)

    res = await agent.run("Génère les sous-titres", context={"video_name": "test_video"})

    assert res["status"] in {"success", "error"}
    assert res["response"].strip() != ""


class ModeleDouble:
    """Rend un texte, ou tombe — pour distinguer relu de non relu."""

    def __init__(self, reponse=None, tombe=False):
        self.reponse, self.tombe = reponse, tombe

    async def is_available(self):
        return not self.tombe

    async def generate(self, prompt: str, **_):
        if self.tombe:
            raise RuntimeError("Ollama ne repond pas")
        return self.reponse


class TestIlN_InventePasDeSousTitres:
    """Deux phrases étaient posées ici en dur — « Bienvenue sur Usman » —
    et produisaient un vrai `.ass` annoncé comme un succès. De la réclame
    pouvait finir incrustée sur une vidéo de chantier. Mesuré le 01/09/2026.
    """

    @pytest.mark.asyncio
    async def test_sans_transcription_rien_n_est_produit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = SubtitleAgent(provider=ModeleDouble("x"))

        resultat = await agent.run("génère les sous-titres")

        assert resultat["status"] == "error"
        assert "invente" in resultat["response"]
        assert "ass_path" not in resultat
        assert list(tmp_path.rglob("*.ass")) == [], "un fichier a été écrit sans matière"

    @pytest.mark.asyncio
    async def test_avec_une_transcription_le_fichier_existe(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = SubtitleAgent(provider=ModeleDouble("on pose la cloison"))

        resultat = await agent.run("subs", context={
            "video_name": "chantier",
            "segments": [{"start": 0.0, "end": 2.0, "text": "on pose la cloison"}]})

        assert resultat["status"] == "success"
        from pathlib import Path
        assert Path(resultat["ass_path"]).exists()


class TestIlN_AnnoncePasUneRelectureQuiN_aPasEuLieu:
    """« corrigés » était écrit même quand le modèle était injoignable :
    l'exception partait dans un `logger.warning` que personne ne lit."""

    @pytest.mark.asyncio
    async def test_modele_absent_le_message_le_dit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = SubtitleAgent(provider=ModeleDouble(tombe=True))

        resultat = await agent.run("subs", context={
            "video_name": "chantier",
            "segments": [{"start": 0.0, "end": 2.0, "text": "de vie du chantier"}]})

        assert resultat["corrigee"] is False
        assert "SANS relecture" in resultat["response"]
        assert "corrigés" not in resultat["response"]

    @pytest.mark.asyncio
    async def test_modele_present_la_relecture_est_annoncee(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = SubtitleAgent(provider=ModeleDouble("devis du chantier"))

        resultat = await agent.run("subs", context={
            "video_name": "chantier",
            "segments": [{"start": 0.0, "end": 2.0, "text": "de vie du chantier"}]})

        assert resultat["corrigee"] is True
        assert "corrigés" in resultat["response"]
