"""Fournisseur Ollama : exige le service local, donc marqué `integration`.

Deux tests en bas (`TestImages`) restent hors ligne : ils verifient que le
parametre `images` (DEC-0019) construit bien la requete attendue par
`/api/generate`, sans jamais toucher au reseau — le client HTTP est double.
"""
import json

import httpx
import pytest

from core.models.ollama_provider import NUM_CTX_TEXTE, NUM_CTX_VISION, OllamaProvider


@pytest.mark.integration
async def test_le_service_repond(ollama_en_ligne):
    assert await ollama_en_ligne.is_available() is True


@pytest.mark.integration
async def test_une_generation_renvoie_du_texte(ollama_en_ligne):
    reponse = await ollama_en_ligne.generate(
        prompt="Dis 'Usman est operationnel' en une phrase courte.",
        system_prompt="Tu es l'assistant de test Usman.",
    )

    assert reponse.strip() != ""
    assert "<think>" not in reponse


@pytest.mark.integration
async def test_le_streaming_produit_des_jetons(ollama_en_ligne):
    jetons = [j async for j in ollama_en_ligne.generate_stream(prompt="Compte jusqu'a trois.")]

    assert len(jetons) > 0
    assert "".join(jetons).strip() != ""


class TestImages:
    """`OllamaProvider.generate(images=...)` — la requete, jamais le reseau."""

    @pytest.fixture
    def provider_et_requetes(self, monkeypatch):
        requetes = []

        def repondre(requete: httpx.Request) -> httpx.Response:
            requetes.append(json.loads(requete.content))
            return httpx.Response(200, json={"response": "une scene de chantier"})

        vrai_client = httpx.AsyncClient

        def fabrique(*args, **kw):
            kw["transport"] = httpx.MockTransport(repondre)
            return vrai_client(*args, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", fabrique)
        return OllamaProvider(model_name="qwen3-vl:4b"), requetes

    async def test_les_images_partent_dans_la_requete(self, provider_et_requetes):
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Que vois-tu ?", images=["YmFzZTY0"])

        assert requetes[0]["images"] == ["YmFzZTY0"]

    async def test_sans_image_le_champ_est_absent(self, provider_et_requetes):
        """Un modele texte ne doit jamais recevoir un champ `images` vide."""
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Bonjour")

        assert "images" not in requetes[0]

    async def test_une_image_elargit_le_contexte(self, provider_et_requetes):
        """Le budget fixe pour la vitesse en conversation couperait la
        description d'une image avant qu'elle ne commence."""
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Que vois-tu ?", images=["YmFzZTY0"])

        assert requetes[0]["options"]["num_ctx"] == NUM_CTX_VISION

    async def test_sans_image_le_contexte_reste_celui_de_la_conversation(self, provider_et_requetes):
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Bonjour")

        assert requetes[0]["options"]["num_ctx"] == NUM_CTX_TEXTE

    async def test_la_reponse_est_rendue_normalement(self, provider_et_requetes):
        provider, _ = provider_et_requetes

        reponse = await provider.generate(prompt="Que vois-tu ?", images=["YmFzZTY0"])

        assert reponse == "une scene de chantier"


class TestFluxAvecLigneIllisible:
    """Une ligne de flux illisible ne doit ni casser le flux, ni disparaitre
    sans laisser de trace — un jeton du modele mal decode reste diagnosticable."""

    @pytest.fixture
    def provider(self, monkeypatch):
        lignes = [
            '{"response": "bonjour"}',
            "ceci n'est pas du JSON",
            '{"response": " Usman"}',
        ]

        def repondre(requete: httpx.Request) -> httpx.Response:
            corps = "\n".join(lignes) + "\n"
            return httpx.Response(200, content=corps)

        vrai_client = httpx.AsyncClient

        def fabrique(*args, **kw):
            kw["transport"] = httpx.MockTransport(repondre)
            return vrai_client(*args, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", fabrique)
        return OllamaProvider()

    async def test_les_jetons_valides_arrivent_malgre_la_ligne_cassee(self, provider):
        jetons = [j async for j in provider.generate_stream(prompt="Bonjour")]

        assert jetons == ["bonjour", " Usman"]

    async def test_la_ligne_illisible_est_journalisee(self, provider, caplog):
        with caplog.at_level("DEBUG", logger="usman.ollama"):
            [j async for j in provider.generate_stream(prompt="Bonjour")]

        assert any("ignoree" in enregistrement.message for enregistrement in caplog.records), (
            "une ligne de flux illisible doit laisser une trace, pas disparaitre sans bruit"
        )


class TestFenetreDuTexte:
    """La fenetre de contexte du texte (DEC-0210) : large, reglable, et la meme
    pour tous les appels au meme modele — la requete, jamais le reseau."""

    @pytest.fixture
    def requetes_du_flux(self, monkeypatch):
        requetes = []

        def repondre(requete: httpx.Request) -> httpx.Response:
            requetes.append(json.loads(requete.content))
            return httpx.Response(200, content=b'{"response": "ok"}\n')

        vrai_client = httpx.AsyncClient

        def fabrique(*args, **kw):
            kw["transport"] = httpx.MockTransport(repondre)
            return vrai_client(*args, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", fabrique)
        return requetes

    async def test_le_flux_et_la_generation_partagent_la_meme_fenetre(self, requetes_du_flux):
        """Si elles differaient, Ollama rechargerait le modele a chaque alternance."""
        provider = OllamaProvider()

        await provider.generate(prompt="Bonjour")
        _ = [j async for j in provider.generate_stream(prompt="Bonjour")]

        assert [r["options"]["num_ctx"] for r in requetes_du_flux] == [NUM_CTX_TEXTE, NUM_CTX_TEXTE]

    def test_le_defaut_depasse_l_ancienne_fenetre_qui_coupait_les_reponses(self):
        assert NUM_CTX_TEXTE > 4096

    def test_le_defaut_tient_la_consigne_de_jarvis_et_une_longue_reponse(self):
        """Le defaut du 02/10/2026 : la consigne (~3700 jetons) remplissait a
        elle seule les 4096 de l'ancienne fenetre. Estimation grossiere
        (3,5 caracteres par jeton en francais) ; si la consigne grossit au
        point de faire echouer ceci, c'est la fenetre qu'il faut revoir."""
        from apps.backend.prompts import prompt_avec_methode

        consigne = prompt_avec_methode("Redige un guide detaille de 1500 mots", None)
        jetons_consigne = len(consigne) / 3.5
        reponse_longue = 4000

        assert jetons_consigne + reponse_longue < NUM_CTX_TEXTE

    @pytest.mark.parametrize("valeur, attendu", [
        ("", 16384), ("  ", 16384), ("32768", 32768), ("8192", 8192),
        ("abc", 16384), ("4096.5", 16384), ("1024", 16384), ("0", 16384), ("-5", 16384),
    ])
    def test_le_reglage_de_l_environnement(self, monkeypatch, valeur, attendu):
        from core.models.ollama_provider import lire_num_ctx_texte

        monkeypatch.setenv("OLLAMA_NUM_CTX", valeur)

        assert lire_num_ctx_texte() == attendu

    def test_sans_reglage_c_est_le_defaut(self, monkeypatch):
        from core.models.ollama_provider import NUM_CTX_TEXTE_PAR_DEFAUT, lire_num_ctx_texte

        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        assert lire_num_ctx_texte() == NUM_CTX_TEXTE_PAR_DEFAUT

    def test_un_reglage_faux_est_dit_dans_le_journal(self, monkeypatch, caplog):
        from core.models.ollama_provider import lire_num_ctx_texte

        monkeypatch.setenv("OLLAMA_NUM_CTX", "abc")
        with caplog.at_level("WARNING", logger="usman.ollama"):
            lire_num_ctx_texte()

        assert "OLLAMA_NUM_CTX" in caplog.text
