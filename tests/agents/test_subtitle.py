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


class TestLaCorrectionAnnonceeEstAppliquee:
    """Mesure du 28/09/2026 : en mode segments, la correction du modele etait
    jetee ; en mode mots, elle l'etait des que « de vie » devenait « devis ».
    « corriges » etait annonce dans les deux cas."""

    @pytest.mark.asyncio
    async def test_un_segment_recoit_vraiment_la_correction(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = SubtitleAgent(provider=ModeleDouble("devis du chantier"))

        resultat = await agent.run("subs", context={
            "video_name": "chantier",
            "segments": [{"start": 0.0, "end": 2.0, "text": "de vie du chantier"}]})

        from pathlib import Path
        contenu = Path(resultat["ass_path"]).read_text(encoding="utf-8")
        assert "devis" in contenu and "de vie" not in contenu

    @pytest.mark.asyncio
    async def test_chaque_segment_numerote_recoit_sa_ligne(self):
        agent = SubtitleAgent(provider=ModeleDouble(
            "[1] on signe le devis\n[2] la plaque est posée"))
        segments = [{"start": 0.0, "end": 2.0, "text": "on signe le de vie"},
                    {"start": 2.0, "end": 4.0, "text": "la plaqué est posée"}]

        donnees, corrigee, _ = await agent.correct_words_contextually(segments)

        assert corrigee is True
        assert [s["text"] for s in donnees] == ["on signe le devis", "la plaque est posée"]

    @pytest.mark.asyncio
    async def test_une_reecriture_n_est_pas_appliquee_ni_annoncee(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = SubtitleAgent(provider=ModeleDouble(
            "Abonnez-vous pour plus de vidéos de rénovation !"))

        resultat = await agent.run("subs", context={
            "video_name": "chantier",
            "segments": [{"start": 0.0, "end": 2.0, "text": "de vie du chantier"}]})

        from pathlib import Path
        contenu = Path(resultat["ass_path"]).read_text(encoding="utf-8")
        assert resultat["corrigee"] is False
        assert "SANS relecture" in resultat["response"] and "écartait" in resultat["response"]
        assert "Abonnez" not in contenu

    @pytest.mark.asyncio
    async def test_en_mode_mots_de_vie_devient_devis_sur_la_duree_des_deux(self):
        agent = SubtitleAgent(provider=ModeleDouble("devis du chantier"))
        mots = [{"word": "de", "start": 0.0, "end": 0.5}, {"word": "vie", "start": 0.5, "end": 1.0},
                {"word": "du", "start": 1.0, "end": 1.5}, {"word": "chantier", "start": 1.5, "end": 2.0}]

        donnees, corrigee, _ = await agent.correct_words_contextually(mots)

        assert corrigee is True
        assert [(m["word"], m["start"], m["end"]) for m in donnees] == [
            ("devis", 0.0, 1.0), ("du", 1.0, 1.5), ("chantier", 1.5, 2.0)]

    @pytest.mark.asyncio
    async def test_en_mode_mots_un_mot_ajoute_n_entre_pas(self):
        agent = SubtitleAgent(provider=ModeleDouble("de vie du beau chantier"))
        mots = [{"word": "de", "start": 0.0, "end": 0.5}, {"word": "vie", "start": 0.5, "end": 1.0},
                {"word": "du", "start": 1.0, "end": 1.5}, {"word": "chantier", "start": 1.5, "end": 2.0}]

        donnees, _, _ = await agent.correct_words_contextually(mots)

        assert [m["word"] for m in donnees] == ["de", "vie", "du", "chantier"]
