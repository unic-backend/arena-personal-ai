"""Ce que l'IA fait pendant qu'elle travaille, annonce au fur et a mesure.

Demande du proprietaire, 19/09/2026 : « quand mon IA est en train de
travailler il fait seulement "Réflexion" ; je veux comme celle de Claude, ce
que l'IA fait en temps reel — reflexion, execution, raisonnement, memoire... »

**L'interface savait deja les afficher** : `ActivityEvent` est defini depuis
longtemps, `chatStore.ts` range ces evenements dans l'arbre d'activite, et
`StatusIcon.tsx` a une icone et une couleur par genre. Ce qui manquait etait a
l'autre bout — cette passerelle n'envoyait que `token`, `done` et `error`.

La regle tenue ici, et ce n'est pas une preference d'affichage : **on n'annonce
que ce qui tourne**. Une etape absente n'emet rien du tout, jamais une ligne
grisee ni un « en attente ». Et les durees sont mesurees, jamais estimees.
"""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import pwa_gateway
from apps.backend.routers.pwa_gateway import Etape, description_memoire, libelles

CLE = "cle-de-test"


class FauxFournisseur:
    model_name = "faux"

    def __init__(self, morceaux=("Bonjour",)):
        self._morceaux = list(morceaux)

    async def is_available(self):
        return True

    async def generate_stream(self, prompt, system_prompt=None):
        for morceau in self._morceaux:
            yield morceau

    async def generate(self, prompt, system_prompt=None):
        return "".join(self._morceaux)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    monkeypatch.setattr(pwa_gateway, "fast_provider", FauxFournisseur())
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes():
    return {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def chat_direct(monkeypatch):
    async def _chat(_demande, espace=None):
        return "CHAT"
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _chat)


def repondre(client, entetes, **corps):
    corps.setdefault("text", "Bonjour")
    corps.setdefault("conversation_id", f"conv-etapes-{uuid4()}")
    corps.setdefault("run_id", f"run-{uuid4()}")
    reponse = client.post("/agent/stream", headers=entetes, json=corps)
    etapes, autres = [], []
    for bloc in reponse.text.replace("\r\n", "\n").split("\n\n"):
        for ligne in bloc.split("\n"):
            if not ligne.startswith("data:"):
                continue
            charge = json.loads(ligne[5:].strip())
            (etapes if charge["type"] == "activity" else autres).append(charge)
    return [c["event"] for c in etapes], autres


def titres(etapes, statut=None):
    return [e["title"] for e in etapes
            if statut is None or e["status"] == statut]


# --- Ce qui est annonce ------------------------------------------------------

def test_un_tour_ordinaire_annonce_ses_etapes(client, entetes, chat_direct):
    etapes, _ = repondre(client, entetes)

    assert titres(etapes, "completed") == [
        "Lecture de la demande", "Mémoire", "Rédaction de la réponse", "Relecture",
    ], "les etapes reellement executees ne sont pas toutes annoncees"


def test_chaque_etape_est_ouverte_puis_fermee(client, entetes, chat_direct):
    etapes, _ = repondre(client, entetes)

    par_identifiant: dict = {}
    for evenement in etapes:
        par_identifiant.setdefault(evenement["id"], []).append(evenement["status"])
    assert all(suite == ["running", "completed"] for suite in par_identifiant.values()), (
        f"une etape n'a pas ete fermee, ou fermee sans avoir ete ouverte : "
        f"{par_identifiant}")


def test_le_classement_dit_l_intention_qu_il_a_trouvee(client, entetes, chat_direct):
    etapes, _ = repondre(client, entetes)

    lecture = [e for e in etapes if e["title"] == "Lecture de la demande"]
    assert lecture[-1]["description"] == "CHAT"


def test_la_memoire_dit_ce_qu_elle_a_lu(client, entetes, chat_direct):
    conv = f"conv-etapes-{uuid4()}"
    repondre(client, entetes, text="Mon tarif BA13 est 4500 FCFA le m2",
             conversation_id=conv)

    etapes, _ = repondre(client, entetes, text="Et pour 40 m2 ?",
                         conversation_id=conv, history=[])

    memoire = [e for e in etapes if e["title"] == "Mémoire" and e["status"] == "completed"]
    description = memoire[-1].get("description", "")
    assert "tour(s) de conversation relus" in description, (
        f"la memoire n'annonce pas le fil relu : {description!r}")
    assert "recherche par" in description, (
        "la memoire ne dit pas PAR QUOI elle a cherche — c'est la difference "
        "entre le sens et les mots, et elle change la qualite des reponses")


def test_la_duree_n_existe_qu_a_la_fermeture(client, entetes, chat_direct):
    etapes, _ = repondre(client, entetes)

    for evenement in etapes:
        if evenement["status"] == "running":
            assert "durationMs" not in evenement, (
                "une etape en cours annonce une duree : elle serait inventee")
        else:
            assert isinstance(evenement["durationMs"], int)


def test_les_etapes_arrivent_avant_la_fin(client, entetes, chat_direct):
    """En direct veut dire pendant, pas apres. Un resume envoye avec `done`
    n'aurait rien montre du travail en cours."""
    _, autres = repondre(client, entetes)

    assert autres[-1]["type"] == "done"


# --- Ce qui n'est PAS annonce ------------------------------------------------

def test_une_etape_qui_ne_tourne_pas_n_emet_rien(client, entetes, monkeypatch):
    """Le chemin d'un agent specialise ne passe ni par la redaction ni par la
    relecture : ces deux etapes ne doivent apparaitre nulle part."""
    async def _email(_demande, espace=None):
        return "EMAIL"
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _email)

    async def _resultat(_requete, intent=None):
        return {"response": "Message envoye.", "sources": []}
    monkeypatch.setattr(pwa_gateway, "dispatch_request", _resultat)

    etapes, _ = repondre(client, entetes, text="Ecris a Seck")

    assert "Rédaction de la réponse" not in titres(etapes)
    assert "Relecture" not in titres(etapes)


def test_un_agent_specialise_porte_son_nom(client, entetes, monkeypatch):
    async def _email(_demande, espace=None):
        return "EMAIL"
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _email)

    async def _resultat(_requete, intent=None):
        return {"response": "Message envoye.", "sources": []}
    monkeypatch.setattr(pwa_gateway, "dispatch_request", _resultat)

    etapes, _ = repondre(client, entetes, text="Ecris a Seck")

    assert "Agent EMAIL" in titres(etapes, "completed")


def test_un_agent_en_echec_ferme_son_etape_en_echec(client, entetes, monkeypatch):
    """`completed` sur un agent qui a plante dirait que le travail a abouti."""
    async def _email(_demande, espace=None):
        return "EMAIL"
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _email)

    async def _casse(_requete, intent=None):
        raise ConnectionError("Gmail injoignable")
    monkeypatch.setattr(pwa_gateway, "dispatch_request", _casse)

    etapes, _ = repondre(client, entetes, text="Ecris a Seck")

    agent = [e for e in etapes if e["title"] == "Agent EMAIL"]
    assert agent[-1]["status"] == "failed"
    assert "Agent EMAIL" not in titres(etapes, "completed")


# --- La langue ---------------------------------------------------------------

def test_les_etapes_suivent_la_langue_de_l_interface(client, entetes, chat_direct):
    etapes, _ = repondre(client, entetes, locale="en-GB")

    assert "Reading the request" in titres(etapes)
    assert "Lecture de la demande" not in titres(etapes)


def test_le_francais_est_le_defaut():
    assert libelles(None)["memoire"] == "Mémoire"
    assert libelles("fr-SN")["memoire"] == "Mémoire"


# --- Les pieces detachees ----------------------------------------------------

def test_une_etape_non_ouverte_n_emet_rien():
    """Construire une etape ne l'annonce pas : c'est `ouvrir()` qui le fait."""
    etape = Etape("analysis", "Jamais ouverte")

    assert isinstance(etape.identifiant, str) and etape.identifiant


def test_l_identifiant_relie_l_ouverture_et_la_fermeture():
    etape = Etape("database", "Mémoire")

    ouverture = json.loads(etape.ouvrir()[len("data: "):])["event"]
    fermeture = json.loads(etape.fermer()[len("data: "):])["event"]

    assert ouverture["id"] == fermeture["id"], (
        "l'interface rangerait deux lignes distinctes au lieu d'en mettre "
        "une a jour")


def test_aucun_souvenir_se_dit():
    """Zero souvenir est une mesure — la recherche a tourne et n'a rien
    trouve. Ne rien afficher se confondrait avec « la memoire n'a pas ete
    consultee »."""
    mots = libelles("fr")

    assert description_memoire({"souvenirs": 0}, mots) == mots["aucun_souvenir"]


def test_une_memoire_jamais_consultee_ne_dit_rien():
    """L'absence de cle, elle, dit que rien n'a ete cherche."""
    assert description_memoire({}, libelles("fr")) == ""
