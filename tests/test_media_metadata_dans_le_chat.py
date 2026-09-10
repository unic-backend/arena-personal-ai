"""EXIF & Media Metadata (DEC-0081) : la chaîne RÉELLE, pas seulement les
fonctions isolées.

Même discipline que `tests/test_contexte_openviking_dans_le_chat.py`, qui a
trouvé la leçon la plus chère de ce dépôt : « une capacité qui existe dans un
fichier mais que rien n'atteint depuis une conversation réelle n'est pas
intégrée » (`docs/CURRENT_TASK.md`).

Ce fichier mesure : `POST /api/chat` → `dispatch_request` (intent VISION,
forcé ici comme le fait le test-jumeau OpenViking — le classement par
mots-clés lui-même est déjà vérifié dans `tests/agents/test_orchestrator.py`)
→ `vision_agent.run` → `media_metadata` (connecteur RÉEL, pas un double) →
réponse. La piece jointe est une VRAIE image JPEG avec un VRAI EXIF, écrite
par Pillow — jamais des octets qui font semblant.
"""
import io

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as chat_module

CLE_DE_TEST = "cle-de-test-metadata"


def _jpeg_avec_exif() -> bytes:
    from PIL import Image
    from PIL.ExifTags import Base as Tag

    img = Image.new("RGB", (640, 480), color=(90, 100, 110))
    exif = img.getexif()
    exif[Tag.Make.value] = "ARENA-Chat-Cam"
    exif[Tag.Model.value] = "ChatTest-9"
    tampon = io.BytesIO()
    img.save(tampon, format="JPEG", exif=exif)
    return tampon.getvalue()


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


class TestLaChaineReelleJusquAMediaMetadata:
    """`analyze_intent` est force a "VISION" — meme discipline que le
    test-jumeau OpenViking : le classement par mots-cles a sa propre suite
    (`tests/agents/test_orchestrator.py::test_les_demandes_de_metadonnees_
    atteignent_vision`). Ce qui est verifie ICI, c'est tout ce qui vient
    APRES : le routeur atteint reellement `vision_agent`, qui atteint
    reellement `media_metadata` — jamais un module appele isolement."""

    @pytest.fixture(autouse=True)
    def _forcer_l_intention_vision(self, monkeypatch):
        async def vision(*_a, **_k):
            return "VISION"
        monkeypatch.setattr(chat_module.orchestrator, "analyze_intent", vision)

    @pytest.fixture(autouse=True)
    def _fast_provider_en_ligne(self, monkeypatch):
        # Porte d'entree de `/api/chat` : verifiee avant tout dispatch.
        async def disponible():
            return True
        monkeypatch.setattr(chat_module.fast_provider, "is_available", disponible)

    def test_ollama_reellement_absent_ici_les_vraies_metadonnees_partent_quand_meme(
        self, client, entetes,
    ):
        """Ce bac a sable n'a pas d'Ollama joignable (mesure, pas suppose) :
        ce test prend donc reellement le chemin de repli — la preuve la plus
        forte possible que `_reponse_metadonnees_seules` fonctionne, puisque
        rien ici ne le simule."""
        piece = chat_module.vision_agent.pieces_jointes.deposer(
            "photo-chat.jpg", _jpeg_avec_exif())

        reponse = client.post("/api/chat", headers=entetes, json={
            "prompt": "Donne-moi toutes les informations techniques disponibles sur cette photo.",
            "attachments": [piece.identifiant],
        })

        assert reponse.status_code == 200
        corps = reponse.json()
        assert corps["intent"] == "VISION"
        assert corps["agent"] == "VisionAgent"
        # Le VRAI connecteur media_metadata a lu le VRAI EXIF — rien de tout
        # cela n'est simule dans ce test.
        assert "ChatTest-9" in corps["response"]
        assert "Ollama ne repond pas" in corps["response"]

    def test_vision_et_metadonnees_combinees_sans_etre_fondues(self, client, entetes, monkeypatch):
        """Avec un modele de vision qui repond (simule ici, la seule piece
        qui doit l'etre : cette machine n'a pas d'Ollama) : la description
        libre ET les informations techniques arrivent toutes les deux, dans
        des sections distinctes — mission §4."""
        from tests.conftest import FakeProvider
        monkeypatch.setattr(
            chat_module.vision_agent, "provider",
            FakeProvider(reponses=["Une photo de test, fond uni."]))

        piece = chat_module.vision_agent.pieces_jointes.deposer(
            "photo-chat.jpg", _jpeg_avec_exif())

        reponse = client.post("/api/chat", headers=entetes, json={
            "prompt": "Analyse complètement cette photo",
            "attachments": [piece.identifiant],
        })

        corps = reponse.json()
        assert "Une photo de test, fond uni." in corps["response"]
        assert "INFORMATIONS TECHNIQUES" in corps["response"]
        assert "ChatTest-9" in corps["response"]
        assert corps["response"].index("Une photo de test") < corps["response"].index(
            "INFORMATIONS TECHNIQUES")

    def test_une_description_ordinaire_n_affiche_pas_les_metadonnees(
        self, client, entetes,
    ):
        piece = chat_module.vision_agent.pieces_jointes.deposer(
            "photo-chat2.jpg", _jpeg_avec_exif())

        reponse = client.post("/api/chat", headers=entetes, json={
            "prompt": "Que vois-tu sur cette image ?",
            "attachments": [piece.identifiant],
        })

        assert reponse.status_code == 200
        corps = reponse.json()
        assert "INFORMATIONS TECHNIQUES" not in corps["response"]

    def test_gps_absent_n_est_jamais_invente_dans_la_reponse_http(
        self, client, entetes,
    ):
        """La photo de ce test n'a AUCUN GPS EXIF : la reponse doit le dire
        tel quel, jamais laisser croire a une localisation."""
        piece = chat_module.vision_agent.pieces_jointes.deposer(
            "photo-chat3.jpg", _jpeg_avec_exif())

        reponse = client.post("/api/chat", headers=entetes, json={
            "prompt": "métadonnées de cette photo",
            "attachments": [piece.identifiant],
        })

        corps = reponse.json()
        assert "GPS : absent du fichier" in corps["response"]
