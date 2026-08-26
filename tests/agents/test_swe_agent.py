"""SWEAgent : choix du terme à chercher dans le dépôt, puis analyse en lecture seule.

Le choix du terme est de la logique pure : il se teste sans modèle ni dépôt.
"""
import pytest

from agents.swe_agent.swe_agent import SWEAgent


@pytest.fixture
def agent(provider_factory, monkeypatch):
    agent = SWEAgent(provider=provider_factory("Correction proposée."), memory=None)
    monkeypatch.setattr(agent.aci, "search_dir", lambda terme: f"occurrences pour {terme}")
    return agent


@pytest.mark.parametrize(
    "demande, terme_attendu",
    [
        ("Corrige l'erreur dans main.py", "main.py"),
        ("Le fichier permissions.yaml est mal lu", "permissions.yaml"),
        # Sans nom de fichier : le mot le plus long qui ne soit pas une instruction.
        ("Corrige le probleme d encodage", "encodage"),
        ("Corrige ça", "def"),
    ],
)
def test_le_terme_recherche_est_le_plus_informatif(agent, demande, terme_attendu):
    assert agent._extraire_terme(demande) == terme_attendu


def test_un_texte_vide_retombe_sur_un_terme_neutre(agent):
    assert agent._extraire_terme("") == "def"


async def test_les_occurrences_trouvees_sont_transmises_au_modele(agent):
    res = await agent.run("Corrige l'erreur dans main.py")

    assert res["search_term"] == "main.py"
    assert "occurrences pour main.py" in agent.provider.appels[0]["prompt"]


async def test_la_reserve_de_lecture_seule_est_affichee(agent):
    res = await agent.run("Corrige l'erreur dans main.py")

    assert res["status"] == "success"
    assert "ne modifie aucun fichier" in res["response"]


async def test_l_agent_n_ecrit_rien_sur_le_disque(agent, monkeypatch):
    def interdit(*args, **kwargs):
        raise AssertionError("SWEAgent a tenté d'écrire un fichier.")

    monkeypatch.setattr("pathlib.Path.write_text", interdit)
    monkeypatch.setattr("pathlib.Path.write_bytes", interdit)

    assert (await agent.run("Corrige main.py"))["status"] == "success"
