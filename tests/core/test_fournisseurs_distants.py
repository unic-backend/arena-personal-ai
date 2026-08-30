"""Groq et DeepInfra : deux services, une seule mécanique.

Le test qui porte l'étape est `test_la_cle_ne_fuit_jamais` : une clé reprise
dans un message d'erreur finit dans un journal, et un journal se colle dans une
conversation.

Le second est `test_sans_cle_le_fournisseur_est_absent_et_ne_tente_rien` : sans
clé, interroger le service est une requête perdue et une seconde d'attente de
plus avant de basculer sur Ollama.

Aucun test n'appelle Groq ni DeepInfra : le client HTTP est injecté.
"""
import json

import pytest

from core.models.deepinfra_provider import DeepInfraProvider
from core.models.groq_provider import GroqProvider
from core.models.openai_compatible import Mesure, nettoyer_erreur

CLE = "gsk_cle-de-test-tres-secrete"

REPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "  Bonjour Saer.  "}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4},
}


def flux(*morceaux, fin=True):
    """Les lignes d'un flux, au format du protocole."""
    lignes = [f"data: {json.dumps({'choices': [{'delta': {'content': m}}]})}"
              for m in morceaux]
    if fin:
        lignes.append("data: [DONE]")
    return lignes


class FausseReponse:
    def __init__(self, charge=None, lignes=None, leve=None):
        self._charge = charge
        self._lignes = lignes or []
        self._leve = leve

    def raise_for_status(self):
        if self._leve is not None:
            raise self._leve

    def json(self):
        return self._charge

    async def aiter_lines(self):
        for ligne in self._lignes:
            yield ligne


class _Flux:
    def __init__(self, reponse):
        self._reponse = reponse

    async def __aenter__(self):
        return self._reponse

    async def __aexit__(self, *args):
        return False


class FauxClient:
    """Un client HTTP de test : il note ce qu'on lui demande, sans réseau."""

    def __init__(self, reponse=None, lignes=None, leve=None):
        self.appels = []
        self._reponse = reponse
        self._lignes = lignes
        self._leve = leve

    async def get(self, url, headers=None, **kw):
        self.appels.append(("GET", url, dict(headers or {}), None))
        return FausseReponse(charge={"data": []}, leve=self._leve)

    async def post(self, url, headers=None, json=None, **kw):
        self.appels.append(("POST", url, dict(headers or {}), json))
        return FausseReponse(charge=self._reponse, leve=self._leve)

    def stream(self, methode, url, headers=None, json=None, **kw):
        self.appels.append((methode, url, dict(headers or {}), json))
        return _Flux(FausseReponse(lignes=self._lignes, leve=self._leve))

    async def aclose(self):
        pass


def fournisseur(classe, client, cle=CLE):
    return classe(api_key=cle, model_name="modele-de-test", client=client)


CLASSES = [GroqProvider, DeepInfraProvider]


# --- Les deux tests qui portent l'étape ------------------------------------------

@pytest.mark.parametrize("classe", CLASSES)
def test_la_cle_ne_fuit_jamais(classe):
    """Un service qui refuse une authentification reprend parfois ce qu'il a reçu."""
    erreur = RuntimeError(f"401 invalid api key: {CLE}")

    nettoye = nettoyer_erreur(erreur, CLE)

    assert CLE not in nettoye
    assert "[cle retiree]" in nettoye


@pytest.mark.parametrize("classe", CLASSES)
async def test_sans_cle_le_fournisseur_est_absent_et_ne_tente_rien(classe, monkeypatch):
    """Sans clé, rien ne part — y compris sur une machine qui en a une.

    Mesuré le 30/08/2026 : ce test échouait chez le propriétaire dès qu'il a
    mis sa vraie clé Groq dans `.env`, et passait en CI qui n'en a aucune.
    La cause est dans le fournisseur : `api_key=api_key or GROQ_API_KEY` fait
    qu'une clé **vide** retombe sur celle de la configuration. Passer `""` ne
    voulait donc pas dire « sans clé » — cela voulait dire « celle du .env ».

    **Le test ne prouvait la garantie que sur une machine qui ne pouvait pas
    la violer.** C'est exactement la façon dont un test passe pour la mauvaise
    raison. La configuration est donc vidée ici, et l'absence devient réelle.
    """
    monkeypatch.setattr("apps.backend.config.GROQ_API_KEY", "", raising=False)
    monkeypatch.setattr("apps.backend.config.DEEPINFRA_API_KEY", "", raising=False)
    client = FauxClient()
    absent = classe(api_key="", model_name="modele-de-test", client=client)

    assert absent.configure is False
    assert await absent.is_available() is False
    assert client.appels == [], "aucune requete ne doit partir sans cle"


# --- Génération complète ------------------------------------------------------------

@pytest.mark.parametrize("classe", CLASSES)
async def test_la_reponse_est_lue_et_nettoyee(classe):
    fourn = fournisseur(classe, FauxClient(reponse=REPONSE))

    assert await fourn.generate("bonjour") == "Bonjour Saer."


@pytest.mark.parametrize("classe", CLASSES)
async def test_la_cle_part_dans_l_entete(classe):
    client = FauxClient(reponse=REPONSE)
    await fournisseur(classe, client).generate("bonjour")

    _, url, entetes, corps = client.appels[0]

    assert entetes["Authorization"] == f"Bearer {CLE}"
    assert url.endswith("/chat/completions")
    assert corps["model"] == "modele-de-test"
    assert corps["stream"] is False


@pytest.mark.parametrize("classe", CLASSES)
async def test_l_instruction_systeme_est_transmise(classe):
    client = FauxClient(reponse=REPONSE)
    await fournisseur(classe, client).generate("bonjour", system_prompt="Tu es Usman.")

    _, _, _, corps = client.appels[0]

    assert corps["messages"][0] == {"role": "system", "content": "Tu es Usman."}
    assert corps["messages"][1]["content"] == "bonjour"


@pytest.mark.parametrize("classe", CLASSES)
async def test_les_jetons_viennent_du_service(classe):
    fourn = fournisseur(classe, FauxClient(reponse=REPONSE))
    await fourn.generate("bonjour")

    assert fourn.derniere_mesure.jetons_entree == 12
    assert fourn.derniere_mesure.jetons_sortie == 4


@pytest.mark.parametrize("classe", CLASSES)
async def test_des_jetons_absents_restent_absents(classe):
    """Une estimation maison deviendrait une facture imaginaire."""
    sans_usage = {"choices": [{"message": {"content": "ok"}}]}
    fourn = fournisseur(classe, FauxClient(reponse=sans_usage))

    await fourn.generate("bonjour")

    assert fourn.derniere_mesure.jetons_entree is None
    assert fourn.derniere_mesure.jetons_sortie is None
    assert fourn.derniere_mesure.jetons_par_seconde is None


@pytest.mark.parametrize("classe", CLASSES)
async def test_une_charge_illisible_ne_fait_pas_tomber_l_appel(classe):
    fourn = fournisseur(classe, FauxClient(reponse={"rien": "d'exploitable"}))

    assert await fourn.generate("bonjour") == ""


# --- Streaming --------------------------------------------------------------------

@pytest.mark.parametrize("classe", CLASSES)
async def test_la_reponse_arrive_mot_a_mot(classe):
    fourn = fournisseur(classe, FauxClient(lignes=flux("Bon", "jour", " Saer")))

    morceaux = [m async for m in fourn.generate_stream("bonjour")]

    assert morceaux == ["Bon", "jour", " Saer"]


@pytest.mark.parametrize("classe", CLASSES)
async def test_une_ligne_illisible_n_interrompt_pas_le_flux(classe):
    lignes = ["data: pas du json", "", "bruit"] + flux("Bonjour")
    fourn = fournisseur(classe, FauxClient(lignes=lignes))

    assert [m async for m in fourn.generate_stream("bonjour")] == ["Bonjour"]


@pytest.mark.parametrize("classe", CLASSES)
async def test_le_temps_du_premier_mot_est_mesure(classe):
    fourn = fournisseur(classe, FauxClient(lignes=flux("Bonjour", " Saer")))

    [m async for m in fourn.generate_stream("bonjour")]
    mesure = fourn.derniere_mesure

    assert mesure.secondes_premier_jeton is not None
    assert mesure.secondes_total is not None
    assert mesure.secondes_premier_jeton <= mesure.secondes_total


@pytest.mark.parametrize("classe", CLASSES)
async def test_un_flux_qui_ne_rend_rien_n_annonce_aucun_premier_mot(classe):
    """`None` veut dire « aucun mot n'est arrivé », pas « instantané »."""
    fourn = fournisseur(classe, FauxClient(lignes=["data: [DONE]"]))

    assert [m async for m in fourn.generate_stream("bonjour")] == []
    assert fourn.derniere_mesure.secondes_premier_jeton is None


# --- Pannes ----------------------------------------------------------------------

@pytest.mark.parametrize("classe", CLASSES)
async def test_un_service_en_panne_est_indisponible_pas_bruyant(classe):
    fourn = fournisseur(classe, FauxClient(leve=ConnectionError("injoignable")))

    assert await fourn.is_available() is False


@pytest.mark.parametrize("classe", CLASSES)
async def test_une_panne_pendant_la_generation_laisse_une_mesure_nettoyee(classe):
    fourn = fournisseur(classe, FauxClient(leve=RuntimeError(f"boom {CLE}")))

    with pytest.raises(RuntimeError):
        await fourn.generate("bonjour")

    assert CLE not in fourn.derniere_mesure.erreur
    assert fourn.derniere_mesure.secondes_total is not None


@pytest.mark.parametrize("classe", CLASSES)
async def test_la_mesure_transportable_ne_contient_aucune_cle(classe):
    fourn = fournisseur(classe, FauxClient(reponse=REPONSE))
    await fourn.generate("bonjour")

    assert CLE not in str(fourn.derniere_mesure.to_dict())


# --- Ce qui distingue les deux ------------------------------------------------------

def test_les_deux_fournisseurs_ne_partagent_pas_leur_adresse():
    groq = GroqProvider(api_key=CLE, model_name="m", client=FauxClient())
    deepinfra = DeepInfraProvider(api_key=CLE, model_name="m", client=FauxClient())

    assert groq.nom != deepinfra.nom
    assert groq.base_url != deepinfra.base_url
    assert "groq" in groq.base_url
    assert "deepinfra" in deepinfra.base_url


def test_le_delai_de_connexion_est_court():
    """Sans réseau, ARENA doit basculer sur Ollama sans faire attendre."""
    groq = GroqProvider(api_key=CLE, model_name="m", client=FauxClient())

    assert groq._delai.connect is not None and groq._delai.connect <= 5.0


def test_une_mesure_sans_duree_ne_calcule_aucune_vitesse():
    mesure = Mesure(fournisseur="groq", modele="m")

    assert mesure.jetons_par_seconde is None
    assert mesure.secondes_total is None
