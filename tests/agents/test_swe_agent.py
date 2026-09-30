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


async def test_la_methode_de_specialiste_atteint_le_modele(agent):
    """Le défaut de DEC-0061, sur un autre agent : `debugging`/`tests`
    (catalogue de spécialistes) étaient déclarés pour SWE_FIX mais
    n'atteignaient jamais SWEAgent — seul le repli conversationnel les
    composait, un chemin que SWE_FIX ne prend jamais."""
    await agent.run("le script plante avec une erreur dans main.py")

    assert "MÉTHODE DE SPÉCIALISTE" in agent.provider.appels[0]["prompt"]


async def test_l_agent_n_ecrit_rien_sur_le_disque(agent, monkeypatch):
    def interdit(*args, **kwargs):
        raise AssertionError("SWEAgent a tenté d'écrire un fichier.")

    monkeypatch.setattr("pathlib.Path.write_text", interdit)
    monkeypatch.setattr("pathlib.Path.write_bytes", interdit)

    assert (await agent.run("Corrige main.py"))["status"] == "success"


class TestSWEAgentAvecCodebaseMemory:
    """Mission Codebase Memory MCP (DEC-0201).

    Si codebase_memory est déclaré et disponible, SWEAgent utilise tracer_chemin
    ou rechercher_graphe pour obtenir des chaînes d'appels AST précises.
    """

    @pytest.mark.asyncio
    async def test_codebase_memory_trace_utilise_si_disponible(self, fake_provider):
        from core.actions.resultat import succes

        class RegistreAvecCBM:
            def __init__(self):
                self.appels = []

            def est_declare(self, nom):
                return nom == "codebase_memory"

            def executer(self, connecteur, capacite, **parametres):
                self.appels.append((connecteur, capacite, parametres))
                if connecteur == "codebase_memory" and capacite == "tracer_chemin":
                    return succes(
                        action="tracer_chemin", cible="codebase_memory",
                        message="[donnée external]\nCALL CHAIN: main -> process -> error_node",
                        preuve="test_func",
                    )
                return succes(action="search", cible="aci", message="none", preuve="p")

        registre = RegistreAvecCBM()
        agent = SWEAgent(provider=fake_provider, registre=registre)

        resultat = await agent.run("Corrige le bug dans ProcessOrder")

        assert resultat["status"] == "success"
        assert ("codebase_memory", "tracer_chemin") in [(c, cap) for c, cap, _ in registre.appels]
        assert "CALL CHAIN: main -> process -> error_node" in agent.provider.appels[0]["prompt"]
        assert resultat["source"] == "codebase_memory (trace_path)"

    @pytest.mark.asyncio
    async def test_repli_sur_aci_si_codebase_memory_echoue(self, fake_provider):
        from core.actions.resultat import non_configure

        class RegistreEchec:
            def __init__(self):
                self.appels = []

            def est_declare(self, nom):
                return nom == "codebase_memory"

            def executer(self, connecteur, capacite, **parametres):
                self.appels.append((connecteur, capacite, parametres))
                return non_configure(action=capacite, cible=connecteur, ce_qui_manque="bin")

        registre = RegistreEchec()
        agent = SWEAgent(provider=fake_provider, registre=registre)

        resultat = await agent.run("Corrige le bug dans ProcessOrder")

        assert resultat["status"] == "success"
        assert resultat["source"] == "recherche_aci"
