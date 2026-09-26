import httpx

from core.actions.resultat import Statut
from core.connectors.huggingface import ConnecteurHuggingFace


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_recherche_modeles_hf_est_reelle_et_bornee():
    def handler(request):
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[{
                "id": "org/model",
                "pipeline_tag": "text-generation",
                "downloads": 42,
                "likes": 7,
                "trendingScore": 3.5,
                "gated": False,
                "tags": ["gguf"],
            }])
        return httpx.Response(404)

    connecteur = ConnecteurHuggingFace(client=_client(handler))
    resultat = connecteur.executer("chercher_modeles", recherche="qwen", limite=5)

    assert resultat.statut == Statut.SUCCES
    assert resultat.detail["modeles"][0]["id"] == "org/model"
    assert resultat.detail["modeles"][0]["trending_score"] == 3.5


def test_metadata_modele_conserve_parametres_licence_et_gated():
    def handler(request):
        if request.url.path == "/api/models/org/model":
            return httpx.Response(200, json={
                "id": "org/model",
                "sha": "abc123",
                "pipeline_tag": "text-generation",
                "safetensors": {"total": 7_000_000_000},
                "cardData": {"license": "apache-2.0"},
                "gated": "auto",
                "downloads": 99,
                "likes": 11,
                "tags": ["transformers"],
            })
        return httpx.Response(404)

    connecteur = ConnecteurHuggingFace(client=_client(handler))
    resultat = connecteur.executer("modele", modele="org/model")

    assert resultat.statut == Statut.SUCCES
    assert resultat.detail["parametres"] == 7_000_000_000
    assert resultat.detail["license"] == "apache-2.0"
    assert resultat.detail["gated"] == "auto"


def test_modele_exige_namespace():
    connecteur = ConnecteurHuggingFace(client=_client(lambda request: httpx.Response(500)))
    resultat = connecteur._faire_modele(modele="sans-namespace")
    assert resultat.statut == Statut.ECHEC
