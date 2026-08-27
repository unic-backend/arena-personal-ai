"""PublisherAgent : il prepare, le connecteur dit ce qui est parti.

Ce fichier affirmait autrefois `res["status"] == "success"` pour une publication
simulee — l'assertion figeait la fabrication. Depuis, l'agent a change deux fois
de forme : d'abord pour dire la verite (phase 1.1), puis pour deleguer les
controles au connecteur au lieu d'en garder une copie (phase 4.2). Les
assertions suivent l'architecture ; aucune n'a ete retiree.

Aucun test ici n'emet de requete : le connecteur TikTok n'en emet pas non plus.
"""
import inspect

import pytest
import yaml

from agents.publisher.publisher_agent import PublisherAgent
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.registre import RegistreConnecteurs
from core.permissions.controle import ControleAcces
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions
from social.tiktok.tiktok_connector import TikTokConnector


@pytest.fixture
def video_factice(tmp_path):
    """Un fichier qui existe, sans quoi l'agent s'arrete avant tout le reste."""
    chemin = tmp_path / "video.mp4"
    chemin.write_bytes(b"pas une vraie video, mais le fichier existe")
    return chemin


@pytest.fixture
def registre(tmp_path):
    """Fabrique un registre contenant TikTok, sous une politique donnee."""
    compteur = {"n": 0}

    def _fabriquer(decision: str = "CONFIRMATION", publish: bool = False,
                   journal=None) -> RegistreConnecteurs:
        compteur["n"] += 1
        chemin = tmp_path / f"politique-{compteur['n']}.yaml"
        chemin.write_text(yaml.safe_dump({
            "services": {"social": {"publish": {"decision": decision, "risque": "HIGH"}}}
        }), encoding="utf-8")
        permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
        permissions.permissions["PUBLISH"] = publish
        acces = ControleAcces(permissions=permissions,
                              politique=PolitiqueDePermissions(chemin=chemin))
        registre = RegistreConnecteurs()
        registre.declarer("tiktok", lambda: TikTokConnector(acces=acces, journal=journal))
        return registre
    return _fabriquer


# --- Sans video : echec, et le modele n'est pas derange -----------------------

async def test_sans_video_l_agent_echoue_avant_toute_publication(fake_provider, registre):
    agent = PublisherAgent(provider=fake_provider, registre=registre())

    res = await agent.run("Les tendances tech", context={"video_path": "/inexistant.mp4"})

    assert res["status"] == Statut.ECHEC.value
    assert res["a_eu_lieu"] is False
    assert fake_provider.appels == []


async def test_sans_contexte_l_agent_echoue(fake_provider, registre):
    res = await PublisherAgent(provider=fake_provider, registre=registre()).run("Sujet")

    assert res["status"] == Statut.ECHEC.value
    assert res["a_eu_lieu"] is False


# --- Coupe-circuit eteint : refus annonce, brouillon quand meme ---------------

async def test_le_coupe_circuit_eteint_donne_un_refus_pas_un_succes(
    provider_factory, video_factice, registre
):
    agent = PublisherAgent(
        provider=provider_factory("Titre accrocheur\n#tech"),
        registre=registre(decision="ALLOWED", publish=False),
    )

    res = await agent.run("Les tendances tech", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.REFUSE.value
    assert res["a_eu_lieu"] is False
    assert "coupe-circuit:PUBLISH" in res["response"]


async def test_un_refus_rend_quand_meme_le_brouillon(provider_factory, video_factice, registre):
    """Preparer sans envoyer est le travail utile : il n'est pas perdu."""
    agent = PublisherAgent(provider=provider_factory("Titre accrocheur\n#tech"),
                           registre=registre())

    res = await agent.run("Les tendances tech", context={"video_path": str(video_factice)})

    assert "Titre accrocheur" in res["brouillon"]
    assert "Titre accrocheur" in res["response"]


# --- Les deux couches, chacune suffisante a bloquer ---------------------------

async def test_le_coupe_circuit_seul_leve_ne_suffit_pas(
    provider_factory, video_factice, registre
):
    """`PUBLISH: true` rouvre le circuit ; la politique demande encore un accord."""
    agent = PublisherAgent(provider=provider_factory("Titre\n#tech"),
                           registre=registre(decision="CONFIRMATION", publish=True))

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.A_CONFIRMER.value
    assert res["a_eu_lieu"] is False
    assert "Rien n'est parti" in res["response"]
    assert "HIGH" in res["response"]


async def test_la_politique_seule_ouverte_ne_suffit_pas(
    provider_factory, video_factice, registre
):
    """La regle dit ALLOWED, mais le coupe-circuit general est eteint."""
    agent = PublisherAgent(provider=provider_factory(),
                           registre=registre(decision="ALLOWED", publish=False))

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.REFUSE.value
    assert "PUBLISH" in res["response"]


async def test_les_deux_couches_levees_atteignent_le_connecteur(
    provider_factory, video_factice, registre
):
    """Et la, c'est la sante qui arrete : aucun jeton TikTok n'existe."""
    agent = PublisherAgent(provider=provider_factory(),
                           registre=registre(decision="ALLOWED", publish=True))

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.NON_CONFIGURE.value
    assert res["a_eu_lieu"] is False
    assert "video.publish" in res["response"]


async def test_aucun_chemin_de_l_agent_ne_declare_une_publication(
    provider_factory, video_factice, registre
):
    """Le test qui compte : quel que soit le chemin, rien n'a eu lieu."""
    for decision, publish in (("CONFIRMATION", False), ("ALLOWED", False),
                              ("CONFIRMATION", True), ("ALLOWED", True)):
        agent = PublisherAgent(provider=provider_factory(),
                               registre=registre(decision=decision, publish=publish))
        for contexte in ({"video_path": "/inexistant.mp4"}, {"video_path": str(video_factice)}):
            assert (await agent.run("Sujet", context=contexte))["a_eu_lieu"] is False


async def test_un_connecteur_absent_du_registre_est_une_reponse(provider_factory, video_factice):
    """Pas une trace de pile : l'agent rend NOT_IMPLEMENTED et continue."""
    agent = PublisherAgent(provider=provider_factory(), registre=RegistreConnecteurs())

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == Statut.NON_IMPLEMENTE.value
    assert "non declare" in res["response"]


# --- Le connecteur lui-meme ---------------------------------------------------

def test_le_connecteur_ne_s_authentifie_pas_faute_d_identifiants():
    assert TikTokConnector().authentifier() is False


def test_le_connecteur_se_declare_non_configure(monkeypatch):
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)

    sante = TikTokConnector().sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert sante.utilisable is False


def test_un_jeton_present_ne_vaut_pas_operationnel(monkeypatch):
    """Avoir un jeton ne prouve pas qu'il marche : INCONNU, donc rien ne part."""
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "un-jeton-quelconque")

    sante = TikTokConnector().sante()

    assert sante.etat is EtatSante.INCONNU
    assert sante.utilisable is False


def test_le_connecteur_dit_ce_qu_il_faut_pour_le_brancher():
    message = TikTokConnector().sante().ce_qui_manque

    assert "video.publish" in message
    assert "OAuth" in message


def test_le_connecteur_ne_declare_qu_une_capacite():
    capacites = TikTokConnector().capacites()

    assert set(capacites) == {"publish_video"}
    assert capacites["publish_video"].ecriture is True
    assert capacites["publish_video"].action == "publish"


def test_le_connecteur_declare_son_quota():
    """Un quota decouvert le jour ou le compte est suspendu coute plus cher."""
    assert TikTokConnector().capacites()["publish_video"].quota_par_minute == 2


def test_l_inventaire_du_connecteur_ne_montre_aucun_secret(monkeypatch):
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "ya29.SECRET-ABSOLU")

    assert "ya29.SECRET-ABSOLU" not in str(TikTokConnector().to_dict())


def test_le_mot_simulation_ne_revient_pas_dans_le_connecteur():
    """Garde-fou de non-regression : c'est la formulation qui avait menti.

    « simulee comme publiee avec succes » etait le message rendu au proprietaire.
    Le mot peut revenir dans un commentaire expliquant l'histoire ; il ne doit
    plus revenir dans ce que le connecteur execute ou renvoie.
    """
    assert "simul" not in inspect.getsource(TikTokConnector).lower()
