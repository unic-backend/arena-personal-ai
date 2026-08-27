"""La passerelle vers l'interface PWA : son protocole, respecte a la lettre.

Le test qui compte le plus est `test_le_flux_se_termine_toujours` : son client
relance la requete jusqu'a trois fois si le flux se ferme sans `done` ni
`error`. Un flux qui s'arrete en silence transforme une reponse en trois.

Aucun test ici n'appelle Ollama : le fournisseur est un double.
"""
import json

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import pwa_gateway
from apps.backend.routers.pwa_gateway import (
    PERSONA_MAX_CARACTERES,
    instructions_persona,
    prompt_systeme,
)

CLE_DE_TEST = "cle-de-test"


class FauxFournisseur:
    """Un modele scripte : il rend les morceaux qu'on lui donne, sans reseau."""

    model_name = "qwen-test"

    def __init__(self, morceaux=None, disponible=True, leve=False):
        self._morceaux = morceaux if morceaux is not None else ["Bon", "jour", " Saer"]
        self._disponible = disponible
        self._leve = leve
        self.prompts = []
        self.systemes = []

    async def is_available(self):
        return self._disponible

    async def generate_stream(self, prompt, system_prompt=None):
        self.prompts.append(prompt)
        self.systemes.append(system_prompt)
        if self._leve:
            raise ConnectionError("le modele a coupe")
        for morceau in self._morceaux:
            yield morceau

    async def generate(self, prompt, system_prompt=None):
        return "".join(self._morceaux)


@pytest.fixture
def fournisseur(monkeypatch):
    def _installer(**kwargs):
        faux = FauxFournisseur(**kwargs)
        monkeypatch.setattr(pwa_gateway, "fast_provider", faux)
        return faux
    return _installer


@pytest.fixture
def chat_direct(monkeypatch):
    """Force l'intention CHAT : le classement par modele n'est pas le sujet ici."""
    async def _chat(_demande):
        return "CHAT"
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _chat)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def trames(texte: str) -> list:
    """Decoupe une reponse SSE comme le fait son client : sur la ligne vide."""
    charges = []
    for bloc in texte.replace("\r\n", "\n").split("\n\n"):
        for ligne in bloc.split("\n"):
            if ligne.startswith("data:"):
                charges.append(json.loads(ligne[5:].strip()))
    return charges


def demander(client, entetes, **corps):
    corps.setdefault("text", "Bonjour")
    return client.post("/agent/stream", headers=entetes, json=corps)


# --- La fermeture du flux -----------------------------------------------------

@pytest.mark.parametrize("etat", [
    {"morceaux": ["Bonjour"]},
    {"morceaux": []},
    {"disponible": False},
    {"leve": True},
])
def test_le_flux_se_termine_toujours(client, entetes, fournisseur, chat_direct, etat):
    """Sans `done` ni `error`, son client relance jusqu'a trois fois."""
    fournisseur(**etat)

    charges = trames(demander(client, entetes).text)

    assert charges, "aucune trame recue"
    assert charges[-1]["type"] in {"done", "error"}


def test_une_reponse_normale_finit_par_done(client, entetes, fournisseur, chat_direct):
    fournisseur(morceaux=["Bon", "jour"])

    assert trames(demander(client, entetes).text)[-1]["type"] == "done"


def test_ollama_hors_ligne_finit_par_une_erreur_expliquee(client, entetes, fournisseur, chat_direct):
    fournisseur(disponible=False)

    derniere = trames(demander(client, entetes).text)[-1]

    assert derniere["type"] == "error"
    assert "ollama serve" in derniere["message"]


def test_une_panne_en_cours_de_flux_devient_une_erreur(client, entetes, fournisseur, chat_direct):
    """Elle ne devient jamais une reponse tronquee presentee comme complete."""
    fournisseur(leve=True)

    charges = trames(demander(client, entetes).text)

    assert charges[-1]["type"] == "error"
    assert "coupe" in charges[-1]["message"]


# --- Le protocole des trames --------------------------------------------------

def test_chaque_morceau_devient_un_jeton(client, entetes, fournisseur, chat_direct):
    fournisseur(morceaux=["Bon", "jour", " Saer"])

    jetons = [c for c in trames(demander(client, entetes).text) if c["type"] == "token"]

    assert [j["text"] for j in jetons] == ["Bon", "jour", " Saer"]


def test_les_types_de_trame_sont_ceux_de_son_client(client, entetes, fournisseur, chat_direct):
    fournisseur()

    types = {c["type"] for c in trames(demander(client, entetes).text)}

    assert types <= {"token", "activity", "done", "error"}


def test_la_reponse_est_bien_un_flux_sse(client, entetes, fournisseur, chat_direct):
    fournisseur()

    res = demander(client, entetes)

    assert res.headers["content-type"].startswith("text/event-stream")


def test_le_meta_final_nomme_le_moteur(client, entetes, fournisseur, chat_direct):
    fournisseur()

    meta = trames(demander(client, entetes).text)[-1]["meta"]

    assert meta["provider"] == "arena"
    assert meta["model"] == "qwen-test"


# --- L'historique du navigateur fait foi --------------------------------------

def test_l_historique_envoye_est_utilise(client, entetes, fournisseur, chat_direct):
    faux = fournisseur()

    demander(client, entetes, text="Et ensuite ?", history=[
        {"role": "user", "content": "Combien de m2 pour 18 parois ?"},
        {"role": "assistant", "content": "486 m2 developpes."},
    ])

    prompt = faux.prompts[0]
    assert "486 m2 developpes." in prompt
    assert "Et ensuite ?" in prompt


def test_sans_historique_le_message_seul_suffit(client, entetes, fournisseur, chat_direct):
    faux = fournisseur()

    demander(client, entetes, text="Bonjour")

    assert "Bonjour" in faux.prompts[0]


# --- Fermeture ----------------------------------------------------------------

def test_sans_cle_le_flux_refuse(client, fournisseur, chat_direct):
    fournisseur()

    assert client.post("/agent/stream", json={"text": "Bonjour"}).status_code == 401


def test_sans_cle_aucun_appel_au_modele(client, fournisseur, chat_direct):
    faux = fournisseur()

    client.post("/agent/stream", json={"text": "Bonjour"})

    assert faux.prompts == []


def test_un_corps_sans_texte_est_refuse(client, entetes, fournisseur, chat_direct):
    fournisseur()

    assert client.post("/agent/stream", headers=entetes, json={}).status_code == 422


# --- Les pieces jointes le declarent au lieu de faire semblant ----------------

def test_les_pieces_jointes_declarent_qu_elles_ne_sont_pas_traitees(client, entetes):
    """Rendre un identifiant donnerait une piece jointe que rien ne lira."""
    res = client.post("/files", headers=entetes)

    assert res.status_code == 501
    assert "Rien n'a ete enregistre" in res.json()["detail"]


def test_les_pieces_jointes_restent_derriere_la_cle(client):
    assert client.post("/files").status_code == 401


# --- Ce qui n'est pas applique n'est pas ignore en silence --------------------

def test_les_champs_non_appliques_sont_journalises(client, entetes, fournisseur,
                                                   chat_direct, caplog):
    """Une interface qui offre un reglage sans effet est pire qu'une interface
    qui ne l'offre pas."""
    fournisseur()

    with caplog.at_level("INFO", logger="usman.backend.pwa"):
        demander(client, entetes, memories=["m1"], connectors=["gmail"])

    assert any("non appliques" in ligne.message for ligne in caplog.records)
    journal = " ".join(ligne.message for ligne in caplog.records)
    assert "memories" in journal and "connectors" in journal


def test_le_persona_ne_figure_plus_parmi_les_champs_ignores():
    """Il est applique depuis le 2026-08-27 : le dire encore serait faux."""
    assert "persona" not in pwa_gateway.CHAMPS_NON_APPLIQUES


# --- Le persona est applique --------------------------------------------------

def test_le_persona_atteint_le_prompt_systeme(client, entetes, fournisseur, chat_direct):
    faux = fournisseur()

    demander(client, entetes, persona={
        "instructions": "User Name: Ousmane\nTone: Be extremely concise.",
    })

    assert "Ousmane" in faux.systemes[0]
    assert "concise" in faux.systemes[0]


def test_le_persona_complete_les_regles_d_arena_sans_les_remplacer(
    client, entetes, fournisseur, chat_direct
):
    """Un reglage de ton ne doit pas pouvoir effacer ce que la plateforme
    s'interdit."""
    faux = fournisseur()

    demander(client, entetes, persona={"instructions": "Tone: concise."})

    assert prompt_systeme(None) in faux.systemes[0]


def test_sans_persona_le_prompt_systeme_est_inchange(client, entetes, fournisseur, chat_direct):
    faux = fournisseur()

    demander(client, entetes)

    assert faux.systemes[0] == prompt_systeme(None)


@pytest.mark.parametrize("persona", [None, {}, {"instructions": ""}, {"instructions": "   "}])
def test_un_persona_vide_n_encombre_pas_le_prompt(persona):
    """Un titre suivi du vide alourdirait chaque requete pour rien."""
    assert prompt_systeme(persona) == prompt_systeme(None)


def test_un_persona_trop_long_est_tronque():
    """Il vient du navigateur : sans plafond, un texte colle par megarde
    pousserait la conversation hors de la fenetre du modele."""
    enorme = "a" * (PERSONA_MAX_CARACTERES * 3)

    retenu = instructions_persona({"instructions": enorme})

    assert len(retenu) == PERSONA_MAX_CARACTERES


def test_les_preferences_sont_annoncees_comme_des_preferences():
    """Le modele doit savoir que ce bloc est un gout, pas une regle."""
    complet = prompt_systeme({"instructions": "Tone: concise."})

    assert pwa_gateway.TITRE_PERSONA in complet


def test_le_persona_n_est_pas_applique_a_un_agent_specialise(
    client, entetes, fournisseur, monkeypatch, caplog
):
    """Un ton « concis » ne doit pas raccourcir un devis ni une recherche sourcee."""
    fournisseur()

    async def _plaquiste(_demande):
        return "PLAQUISTE"
    monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _plaquiste)

    async def _resultat(_requete, intent=None):
        return {"response": "Devis chiffre.", "sources": []}
    monkeypatch.setattr(pwa_gateway, "dispatch_request", _resultat)

    with caplog.at_level("INFO", logger="usman.backend.pwa"):
        demander(client, entetes, persona={"instructions": "Tone: concise."})

    assert any("Persona non applique" in ligne.message for ligne in caplog.records)


def test_une_requete_sans_ces_champs_ne_journalise_rien(client, entetes, fournisseur,
                                                        chat_direct, caplog):
    fournisseur()

    with caplog.at_level("INFO", logger="usman.backend.pwa"):
        demander(client, entetes)

    assert not any("non appliques" in ligne.message for ligne in caplog.records)


# --- /health parle a son interface sans mentir aux anciens appelants ----------

def test_health_porte_les_champs_que_l_interface_lit(client):
    corps = client.get("/health").json()

    for champ in ("ok", "name", "provider", "model"):
        assert champ in corps
    assert corps["name"] == "ARENA"
    assert corps["provider"] == "ollama"


def test_ok_suit_la_disponibilite_reelle_d_ollama(client):
    corps = client.get("/health").json()

    assert corps["ok"] is corps["ollama_available"]


def test_les_anciens_champs_de_health_sont_intacts(client):
    corps = client.get("/health").json()

    for champ in ("status", "ollama_available", "models", "agents_active", "interface"):
        assert champ in corps
