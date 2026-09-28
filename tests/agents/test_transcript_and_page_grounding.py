"""Une analyse de transcription et une reponse sur une page sont relues
contre ce qu'elles ont recu (DEC-0160).

Audit du 28/09/2026 : l'analyse d'une video ordinaire pouvait consulter un
collegue (qui repond de memoire), et ni elle, ni le compte rendu de reunion,
ni la reponse « discuter avec une page » n'etaient relus.
"""
import pytest

from agents.browser.browser_agent import BrowserAgent
from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent

TRANSCRIPTION = "Pose de plaques BA13 dans le salon, trois heures de travail."


class _Modele:
    def __init__(self, reponse):
        self.reponse = reponse
        self.prompts = []

    async def is_available(self):
        return True

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        return self.reponse


def _analyseur(tmp_path, monkeypatch, reponse):
    media = tmp_path / "chantier.mp4"
    media.write_bytes(b"video-test")
    agent = VideoAnalyzerAgent(provider=_Modele(reponse))
    monkeypatch.setattr(agent.ffmpeg, "extract_audio", lambda source, cible: True)
    monkeypatch.setattr(agent.transcriber, "transcribe", lambda chemin: {
        "full_text": TRANSCRIPTION, "duration": 12.0,
        "segments": [{"start": 0.0, "end": 12.0, "text": TRANSCRIPTION}]})
    return agent, str(media)


@pytest.mark.asyncio
async def test_un_nom_absent_de_la_transcription_est_signale(tmp_path, monkeypatch):
    inventee = "Moussa Diop pose les plaques BA13 dans le salon."
    agent, chemin = _analyseur(tmp_path, monkeypatch, inventee)

    resultat = await agent.run("Analyse cette vidéo.", {"video_path": chemin})

    assert resultat["response"].startswith(inventee)
    assert "Verification automatique" in resultat["response"]
    assert "Moussa, Diop" in resultat["response"].split("Verification automatique")[1]


@pytest.mark.asyncio
async def test_une_analyse_fidele_reste_telle_quelle(tmp_path, monkeypatch):
    fidele = "Pose de plaques BA13 dans le salon. Potentiel : 6 sur 10."
    agent, chemin = _analyseur(tmp_path, monkeypatch, fidele)

    resultat = await agent.run("Analyse cette vidéo.", {"video_path": chemin})

    assert resultat["response"] == fidele


@pytest.mark.asyncio
async def test_l_analyse_d_une_video_ne_consulte_aucun_collegue(tmp_path, monkeypatch):
    """`consulter=False` est consomme par `rediger` : il ne fuit pas vers le
    fournisseur, et aucune consigne d'equipe n'est ajoutee."""
    agent, chemin = _analyseur(tmp_path, monkeypatch, "Pose de plaques BA13.")
    appels = []

    async def rediger_espion(prompt, system_prompt=None, consulter=True, **options):
        appels.append(consulter)
        return "Pose de plaques BA13."

    agent.rediger = rediger_espion
    await agent.run("Analyse cette vidéo.", {"video_path": chemin})

    assert appels == [False]


class _LecteurPage:
    async def lire(self, url):
        return {"status": "READY", "url": url, "titre": "Tarifs 2026",
                "texte": "Le forfait de base coute 15 000 FCFA par mois.",
                "tronque": False, "provenance": "test"}


@pytest.mark.asyncio
async def test_une_reponse_sur_une_page_est_relue():
    agent = BrowserAgent(provider=_Modele("Le forfait premium coute 25 000 FCFA."))
    agent.lecteur_page = _LecteurPage()

    resultat = await agent.discuter_page("https://exemple.test/tarifs", "Combien coute le forfait ?")

    assert resultat["response"].startswith("Le forfait premium coute 25 000 FCFA.")
    assert resultat["sans_source"] == ["25000"]


@pytest.mark.asyncio
async def test_une_reponse_fidele_sur_une_page_reste_telle_quelle():
    agent = BrowserAgent(provider=_Modele("Le forfait de base coute 15 000 FCFA par mois."))
    agent.lecteur_page = _LecteurPage()

    resultat = await agent.discuter_page("https://exemple.test/tarifs", "Combien coute le forfait ?")

    assert resultat["response"] == "Le forfait de base coute 15 000 FCFA par mois."
    assert resultat["sans_source"] == []
