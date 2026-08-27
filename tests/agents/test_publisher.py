"""PublisherAgent : trois situations, trois statuts differents.

Ce fichier affirmait auparavant `res["status"] == "success"` pour une
publication simulee. L'assertion etait exacte sur le code d'alors, et c'est
justement le probleme : elle **figeait la fabrication**. Elle est remplacee par
ce que le proprietaire a demande (section 27), pas affaiblie — le fichier
compte plus d'assertions qu'avant, et aucune n'a disparu.

Aucun test ici n'emet de requete : le connecteur TikTok n'en emet pas non plus.
"""
import inspect

import pytest

from agents.publisher.publisher_agent import PublisherAgent
from core.actions.resultat import ResultatAction, Statut
from social.tiktok.tiktok_connector import TikTokConnector


@pytest.fixture
def video_factice(tmp_path):
    """Un fichier qui existe, sans quoi l'agent s'arrete avant la verification."""
    chemin = tmp_path / "video.mp4"
    chemin.write_bytes(b"pas une vraie video, mais le fichier existe")
    return chemin


# --- Sans video : echec, et le modele n'est pas derange -----------------------

async def test_sans_video_l_agent_echoue_avant_toute_publication(fake_provider):
    agent = PublisherAgent(provider=fake_provider)

    res = await agent.run("Les tendances tech", context={"video_path": "/chemin/inexistant.mp4"})

    assert res["status"] == Statut.ECHEC.value
    assert res["a_eu_lieu"] is False
    assert fake_provider.appels == []


async def test_sans_contexte_l_agent_echoue(fake_provider):
    res = await PublisherAgent(provider=fake_provider).run("Les tendances tech")

    assert res["status"] == Statut.ECHEC.value
    assert res["a_eu_lieu"] is False


# --- Permission bloquee : refus annonce, brouillon quand meme -----------------

async def test_la_permission_bloquee_donne_un_refus_pas_un_succes(provider_factory, video_factice):
    provider = provider_factory("Titre accrocheur\nDescription\n#tech #senegal")
    agent = PublisherAgent(provider=provider)
    assert agent.permissions.is_allowed("PUBLISH") is False, "PUBLISH doit rester bloque"

    res = await agent.run("Les tendances tech", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.REFUSE.value
    assert res["a_eu_lieu"] is False
    assert "PUBLISH" in res["response"]
    assert "Rien n'a ete envoye" in res["response"]


async def test_un_refus_rend_quand_meme_le_brouillon(provider_factory, video_factice):
    """Preparer sans envoyer est le travail utile : il n'est pas perdu."""
    agent = PublisherAgent(provider=provider_factory("Titre accrocheur\n#tech"))

    res = await agent.run("Les tendances tech", context={"video_path": str(video_factice)})

    assert "Titre accrocheur" in res["brouillon"]
    assert "Titre accrocheur" in res["response"]


# --- Permission accordee : le connecteur n'est pas branche, et il le dit ------

async def test_permission_accordee_le_connecteur_se_declare_non_configure(
    provider_factory, video_factice, monkeypatch
):
    agent = PublisherAgent(provider=provider_factory())
    monkeypatch.setattr(agent.permissions, "is_allowed", lambda nom: True)

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.NON_CONFIGURE.value
    assert res["a_eu_lieu"] is False
    assert "video.publish" in res["response"]


async def test_aucun_chemin_de_l_agent_ne_declare_une_publication(
    provider_factory, video_factice, monkeypatch
):
    """Le test qui compte : quel que soit le chemin, rien n'a eu lieu."""
    agent = PublisherAgent(provider=provider_factory())
    chemins = [
        {"video_path": "/inexistant.mp4"},
        {"video_path": str(video_factice)},
    ]
    for contexte in chemins:
        assert (await agent.run("Sujet", context=contexte))["a_eu_lieu"] is False

    monkeypatch.setattr(agent.permissions, "is_allowed", lambda nom: True)
    assert (await agent.run("Sujet", context={"video_path": str(video_factice)}))["a_eu_lieu"] is False


# --- Le connecteur lui-meme ---------------------------------------------------

def test_le_connecteur_ne_s_authentifie_pas_faute_d_identifiants():
    connecteur = TikTokConnector()

    assert connecteur.authenticate() is False
    assert connecteur.is_authenticated is False


def test_le_connecteur_rend_un_resultat_typé_pas_un_dictionnaire_libre():
    resultat = TikTokConnector().publish_video("/x.mp4", "T", "D", ["#a"])

    assert isinstance(resultat, ResultatAction)
    assert resultat.statut is Statut.NON_CONFIGURE
    assert resultat.a_eu_lieu is False


def test_le_connecteur_dit_ce_qu_il_faut_pour_le_brancher():
    message = TikTokConnector().publish_video("/x.mp4", "T", "D", []).message

    assert "video.publish" in message
    assert "OAuth" in message


def test_le_mot_simulation_ne_revient_pas_dans_le_connecteur():
    """Garde-fou de non-regression : c'est la formulation qui avait menti.

    « simulee comme publiee avec succes » etait le message rendu au proprietaire.
    Le mot peut revenir dans un commentaire expliquant l'histoire ; il ne doit
    plus revenir dans ce que le connecteur execute ou renvoie.
    """
    code = inspect.getsource(TikTokConnector)

    assert "simul" not in code.lower()
