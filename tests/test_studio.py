"""Le Studio Vidéo 1-clic, traversé de bout en bout sans ffmpeg ni modèle.

La chaîne réelle enchaîne analyse, transcription, recadrage et incrustation.
Aucune de ces quatre étapes n'est exécutable ici — ni GPU, ni ffmpeg complet,
ni modèle. Ce qui est vérifié est donc ce qui doit rester vrai quoi qu'il
arrive : **le Studio ne prétend jamais avoir produit un fichier qui n'existe
pas**, et il dit à quelle étape il s'est arrêté.
"""
from pathlib import Path

import pytest

from apps.backend.studio import AUCUNE_VIDEO, derniere_video, lancer_studio


class AgentVideoDouble:
    """Rend des segments, et une transcription si on lui en donne une."""

    def __init__(self, segments=None, mots=None):
        self.segments = segments if segments is not None else [{"start": 0, "end": 5}]
        self.transcriber = self
        self._mots = mots or []
        self.appels = []

    async def run(self, prompt, context=None):
        self.appels.append(context)
        return {"segments": self.segments, "ai_analysis": "analyse factice"}

    def transcribe(self, chemin):
        return {"words": self._mots}


class OutilDeRecadrage:
    """Écrit réellement le fichier vertical, ou pas, selon ce qu'on demande."""

    def __init__(self, reussit=True):
        self.reussit = reussit

    def convert_to_vertical_9_16(self, source, destination):
        if self.reussit:
            Path(destination).write_bytes(b"video verticale factice")


class OutilFfmpeg:
    def __init__(self, reussit=True):
        self.reussit = reussit
        self.appels = []

    def burn_subtitles(self, video, sous_titres, destination):
        self.appels.append((video, sous_titres, destination))
        if self.reussit:
            Path(destination).write_bytes(b"video sous-titree factice")
        return self.reussit


class AgentMontageDouble:
    def __init__(self, recadrage_reussit=True, incrustation_reussit=True):
        self.crop_tool = OutilDeRecadrage(recadrage_reussit)
        self.ffmpeg = OutilFfmpeg(incrustation_reussit)


class AgentSousTitresDouble:
    def __init__(self, chemin_ass=None):
        self.chemin_ass = chemin_ass

    async def run(self, prompt, context=None):
        return {"ass_path": self.chemin_ass or ""}


@pytest.fixture
def media(tmp_path) -> Path:
    (tmp_path / "incoming").mkdir()
    (tmp_path / "source").mkdir()
    return tmp_path


def _video(dossier: Path, nom: str = "clip.mp4") -> Path:
    chemin = dossier / nom
    chemin.write_bytes(b"contenu video factice")
    return chemin


class TestChoixDeLaVideo:
    def test_sans_video_rien_n_est_choisi(self, media):
        assert derniere_video(media) is None

    def test_incoming_passe_avant_source(self, media):
        _video(media / "source", "ancienne.mp4")
        attendue = _video(media / "incoming", "nouvelle.mp4")
        assert derniere_video(media) == attendue

    def test_la_plus_recente_gagne(self, media):
        premiere = _video(media / "incoming", "a.mp4")
        seconde = _video(media / "incoming", "b.mp4")
        import os
        os.utime(premiere, (1, 1))
        assert derniere_video(media) == seconde

    def test_un_fichier_qui_n_est_pas_une_video_est_ignore(self, media):
        (media / "incoming" / "notes.txt").write_text("pas une video")
        assert derniere_video(media) is None

    def test_un_dossier_absent_est_un_dossier_vide(self, tmp_path):
        assert derniere_video(tmp_path) is None


class TestChaineComplete:
    @pytest.mark.asyncio
    async def test_sans_video_le_studio_dit_quoi_faire(self, media, tmp_path):
        resultat = await lancer_studio(
            AgentVideoDouble(), AgentMontageDouble(), AgentSousTitresDouble(),
            racine_media=media, dossier_rendu=tmp_path / "rendu",
        )
        assert resultat["status"] == "NO_VIDEO"
        assert resultat["response"] == AUCUNE_VIDEO

    @pytest.mark.asyncio
    async def test_la_chaine_complete_rend_un_fichier_qui_existe(self, media, tmp_path):
        _video(media / "incoming")
        ass = tmp_path / "clip.ass"
        ass.write_text("sous-titres factices")
        rendu = tmp_path / "rendu"

        resultat = await lancer_studio(
            AgentVideoDouble(mots=[{"word": "bonjour"}]),
            AgentMontageDouble(),
            AgentSousTitresDouble(chemin_ass=str(ass)),
            racine_media=media, dossier_rendu=rendu,
        )

        assert resultat["status"] == "OK"
        assert resultat["etapes"]["incrustation"] == "OK"
        assert Path(resultat["rendu"]).exists(), "le Studio annonce un fichier qui n'existe pas"
        assert resultat["rendu"].endswith("_capcut_9_16.mp4")

    @pytest.mark.asyncio
    async def test_sans_sous_titres_le_rendu_est_la_version_verticale(self, media, tmp_path):
        _video(media / "incoming")
        resultat = await lancer_studio(
            AgentVideoDouble(), AgentMontageDouble(), AgentSousTitresDouble(chemin_ass=None),
            racine_media=media, dossier_rendu=tmp_path / "rendu",
        )
        assert resultat["status"] == "OK"
        assert resultat["etapes"]["incrustation"] == "PAS_DE_SOUS_TITRES"
        assert resultat["rendu"].endswith("_vertical_9_16.mp4")
        assert Path(resultat["rendu"]).exists()

    @pytest.mark.asyncio
    async def test_une_incrustation_ratee_ne_devient_pas_un_succes(self, media, tmp_path):
        _video(media / "incoming")
        ass = tmp_path / "clip.ass"
        ass.write_text("sous-titres factices")
        resultat = await lancer_studio(
            AgentVideoDouble(),
            AgentMontageDouble(incrustation_reussit=False),
            AgentSousTitresDouble(chemin_ass=str(ass)),
            racine_media=media, dossier_rendu=tmp_path / "rendu",
        )
        assert resultat["etapes"]["incrustation"] == "ECHEC"
        assert resultat["rendu"].endswith("_vertical_9_16.mp4")

    @pytest.mark.asyncio
    async def test_quand_rien_n_est_produit_le_studio_le_dit(self, media, tmp_path):
        """Le cas le plus important : ffmpeg absent, aucun fichier écrit."""
        _video(media / "incoming")
        resultat = await lancer_studio(
            AgentVideoDouble(),
            AgentMontageDouble(recadrage_reussit=False),
            AgentSousTitresDouble(),
            racine_media=media, dossier_rendu=tmp_path / "rendu",
        )
        assert resultat["status"] == "FAILED"
        assert "n'a produit aucun fichier" in resultat["response"]
        assert "rendu" not in resultat

    @pytest.mark.asyncio
    async def test_une_transcription_qui_echoue_ne_bloque_pas_la_chaine(self, media, tmp_path):
        video = _video(media / "incoming")
        (video.parent / f"{video.stem}_extracted.wav").write_bytes(b"audio factice")

        class TranscriptionCassee(AgentVideoDouble):
            def transcribe(self, chemin):
                raise RuntimeError("faster-whisper absent")

        resultat = await lancer_studio(
            TranscriptionCassee(), AgentMontageDouble(), AgentSousTitresDouble(),
            racine_media=media, dossier_rendu=tmp_path / "rendu",
        )
        assert resultat["etapes"]["transcription"] == "ECHEC"
        assert resultat["status"] == "OK"


class TestAiguillage:
    """Le Studio doit être atteignable comme Usman l'utilise : en le demandant."""

    @pytest.mark.parametrize("demande", [
        "studio",
        "transforme la vidéo en short tiktok",
        "sous-titre ma vidéo",
        "reformatte en 9:16",
    ])
    def test_ces_demandes_vont_au_studio(self, demande):
        from agents.orchestrator.orchestrator_agent import OrchestratorAgent
        assert OrchestratorAgent._classer_par_mots_cles(None, demande) == "STUDIO"

    def test_le_studio_est_un_agent_specialise(self):
        """Sans cela, l'intention serait détectée puis ignorée par la passerelle."""
        from apps.backend.config import AGENTS_SPECIALISES
        assert "STUDIO" in AGENTS_SPECIALISES

    def test_le_studio_est_propose_dans_le_menu(self):
        import asyncio

        from apps.backend.routers import openai_gateway
        modeles = asyncio.run(openai_gateway.list_openai_models())
        assert "usman-studio" in [m["id"] for m in modeles["data"]]

    def test_l_intention_studio_est_une_etiquette_connue(self):
        """Une étiquette absente de la liste fermée serait rejetée en silence."""
        from agents.orchestrator.orchestrator_agent import INTENTIONS
        assert "STUDIO" in INTENTIONS


# ==============================================================================
# La chaîne HTTP complète : LibreChat -> passerelle -> studio
# ==============================================================================
from fastapi.testclient import TestClient  # noqa: E402

from apps.backend import main  # noqa: E402
from apps.backend import security as securite  # noqa: E402
from apps.backend.routers import chat as routeur_chat  # noqa: E402
from apps.backend.routers import openai_gateway as passerelle  # noqa: E402

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    monkeypatch.setattr(securite, "REQUETES_MAX", 100)
    monkeypatch.setattr(securite.limiteur, "requetes_max", 100)

    async def toujours_disponible():
        return True

    monkeypatch.setattr(main.fast_provider, "is_available", toujours_disponible)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def studio_double(monkeypatch):
    """Remplace la chaîne réelle et retient si elle a été appelée."""
    appels = []

    async def _studio(video_agent, editor_agent, subtitle_agent, **kw):
        appels.append(True)
        return {"status": "OK", "agent": "Studio", "response": "rendu factice", "etapes": {}}

    monkeypatch.setattr(routeur_chat, "lancer_studio", _studio)
    monkeypatch.setattr(passerelle, "lancer_studio", _studio)
    return appels


class TestChaineHTTP:
    def test_le_modele_arena_studio_atteint_le_studio(self, client, studio_double):
        reponse = client.post(
            "/v1/chat/completions",
            headers=ENTETES,
            json={"model": "usman-studio",
                  "messages": [{"role": "user", "content": "vas-y"}],
                  "stream": False},
        )
        assert reponse.status_code == 200
        assert studio_double == [True], "le studio n'a pas été appelé"
        assert "rendu factice" in reponse.json()["choices"][0]["message"]["content"]

    def test_une_demande_ordinaire_de_studio_y_arrive_aussi(self, client, studio_double, monkeypatch):
        """C'est ainsi que Usman l'utilise : il écrit sa demande, sans choisir de modèle."""
        async def _classer(user_input):
            return "STUDIO"

        monkeypatch.setattr(routeur_chat.orchestrator, "analyze_intent", _classer)

        reponse = client.post(
            "/v1/chat/completions",
            headers=ENTETES,
            json={"model": "usman-chat",
                  "messages": [{"role": "user", "content": "sous-titre ma vidéo"}],
                  "stream": False},
        )
        assert reponse.status_code == 200
        assert studio_double == [True]

    def test_le_studio_exige_la_cle_api(self, client, studio_double):
        reponse = client.post(
            "/v1/chat/completions",
            json={"model": "usman-studio",
                  "messages": [{"role": "user", "content": "vas-y"}]},
        )
        assert reponse.status_code in (401, 403)
        assert studio_double == [], "le studio a tourné sans authentification"


class TestJamaisDeReponseVide:
    """Une bulle vide dans LibreChat est pire qu'un message d'erreur.

    Observé le 2026-08-26 sur `usman-research` : après trois minutes,
    une bulle entièrement vide, sans texte ni erreur. Chaque branche de la
    passerelle lit `.get("response", "")`, et `"" is not None` est vrai.
    """

    def test_un_texte_normal_passe_intact(self):
        from apps.backend.routers.openai_gateway import garantir_un_texte
        assert garantir_un_texte("la réponse", "usman-chat") == "la réponse"

    @pytest.mark.parametrize("vide", ["", "   ", "\n\n", None])
    def test_rien_ne_devient_un_message_explicite(self, vide):
        from apps.backend.routers.openai_gateway import garantir_un_texte
        texte = garantir_un_texte(vide, "usman-research")
        assert texte.strip(), "une réponse vide est repartie telle quelle"
        assert "usman-research" in texte
        assert "aucune réponse" in texte

    def test_un_agent_muet_ne_produit_pas_une_bulle_vide(self, client, monkeypatch):
        """Le cas réel, par la chaîne HTTP : l'agent renvoie un dict sans texte."""
        async def _agent_muet(*args, **kw):
            return {"status": "error"}

        monkeypatch.setattr(passerelle.researcher_agent, "run", _agent_muet)

        reponse = client.post(
            "/v1/chat/completions",
            headers=ENTETES,
            json={"model": "usman-research",
                  "messages": [{"role": "user", "content": "une question"}],
                  "stream": False},
        )
        contenu = reponse.json()["choices"][0]["message"]["content"]
        assert contenu.strip(), "LibreChat aurait affiché une bulle vide"
        assert "usman-research" in contenu


class TestNomVideo:
    """`usman-video` est le nom que voit l'utilisateur ; il doit lancer le Studio."""

    @pytest.mark.parametrize("nom", ["usman-video", "usman-studio"])
    def test_les_deux_noms_lancent_le_studio(self, nom, client, studio_double):
        reponse = client.post(
            "/v1/chat/completions",
            headers=ENTETES,
            json={"model": nom,
                  "messages": [{"role": "user", "content": "vas-y"}],
                  "stream": False},
        )
        assert reponse.status_code == 200
        assert studio_double == [True], f"{nom} n'a pas atteint le Studio"

    def test_arena_video_est_servi_par_l_api(self):
        import asyncio
        modeles = asyncio.run(passerelle.list_openai_models())
        assert "usman-video" in [m["id"] for m in modeles["data"]]
