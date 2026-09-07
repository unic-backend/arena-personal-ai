"""RepoEngineerAgent : analyse d'architecture en lecture seule.

Le point qui compte : il lit le dépôt et propose, il n'écrit jamais.
"""
import pytest

from agents.repo_engineer.repo_engineer_agent import RepoEngineerAgent

ARBRE = ["apps/", "apps/backend/", "core/", "core/agent/", "tools/"]


@pytest.fixture
def agent(provider_factory, monkeypatch):
    agent = RepoEngineerAgent(provider=provider_factory("Plan : ajouter core/audit/."), memory=None)
    monkeypatch.setattr(agent.repo_tool, "get_tree", lambda max_depth=3: ARBRE)
    return agent


async def test_la_structure_lue_est_transmise_au_modele(agent):
    await agent.run("Ajoute un module de logs d'audit")

    prompt = agent.provider.appels[0]["prompt"]
    for entree in ARBRE:
        assert entree in prompt


async def test_le_plan_est_renvoye_et_la_reserve_de_lecture_seule_affichee(agent):
    res = await agent.run("Ajoute un module de logs d'audit")

    assert res["status"] == "success"
    assert res["architecture_plan"] == "Plan : ajouter core/audit/."
    assert "ne modifie aucun fichier" in res["response"]


async def test_la_methode_de_specialiste_atteint_le_modele(agent):
    """Le défaut de DEC-0061, sur un autre agent : `architecture`/`tests`
    (catalogue de spécialistes) étaient déclarés pour REPO_ENGINEERING mais
    n'atteignaient jamais cet agent — seul le repli conversationnel les
    composait, un chemin que REPO_ENGINEERING ne prend jamais."""
    await agent.run("quelle architecture pour ce module de logs")

    assert "MÉTHODE DE SPÉCIALISTE" in agent.provider.appels[0]["prompt"]


async def test_l_agent_n_ecrit_rien_sur_le_disque(agent, monkeypatch):
    """Lecture seule : toute écriture doit être absente, pas seulement annoncée."""
    def interdit(*args, **kwargs):
        raise AssertionError("RepoEngineerAgent a tenté d'écrire un fichier.")

    monkeypatch.setattr(agent.repo_tool, "apply_patch", interdit)
    monkeypatch.setattr("pathlib.Path.write_text", interdit)
    monkeypatch.setattr("pathlib.Path.write_bytes", interdit)

    assert (await agent.run("Modifie le fichier main.py"))["status"] == "success"


class TestLeRegardSurLeDepotVientDeGitingest:
    """**Défaut mesuré le 07/09/2026** (audit profond, DEC-0068).

    Cet agent analysait une architecture avec **30 lignes d'arborescence
    tronquée**, pendant que `gitingest` — enregistré dans le runtime, testé,
    diagnostiqué par `doctor.py` — n'était appelé par **aucun chemin
    d'exécution**. Un connecteur que rien n'atteint est mort, quelle que soit
    la qualité de son code : c'est DEC-0061 et DEC-0066, une troisième fois.

    Le repli compte autant que le branchement : `gitingest` est optionnel, et
    son absence ne doit jamais empêcher une analyse.
    """

    @staticmethod
    def _registre(resultat):
        class Reg:
            def __init__(self):
                self.appels = []

            def executer(self, connecteur, capacite, **parametres):
                self.appels.append((connecteur, capacite, parametres))
                return resultat
        return Reg()

    @pytest.mark.asyncio
    async def test_gitingest_est_reellement_appele_et_son_resume_utilise(
        self, fake_provider
    ):
        from core.actions.resultat import succes

        registre = self._registre(succes(
            action="ingerer", cible="gitingest", message="ok", preuve="p",
            resume="RESUME REEL DU DEPOT", arbre="core/\n  connectors/"))
        agent = RepoEngineerAgent(provider=fake_provider, registre=registre)

        await agent.run("analyse ce dépôt")

        assert [(c, cap) for c, cap, _ in registre.appels] == [("gitingest", "ingerer")], (
            "gitingest n'est pas appelé : le connecteur est de nouveau dormant")
        prompt = agent.provider.appels[0]["prompt"]
        assert "RESUME REEL DU DEPOT" in prompt, "le résumé obtenu n'atteint pas le modèle"
        assert "source : gitingest" in prompt

    @pytest.mark.asyncio
    async def test_gitingest_absent_ne_bloque_pas_l_analyse(self, fake_provider):
        """Et le prompt DIT qu'il regarde une arborescence, pas un résumé."""
        from core.actions.resultat import non_configure

        registre = self._registre(non_configure(
            action="ingerer", cible="gitingest", ce_qui_manque="pip install gitingest"))
        agent = RepoEngineerAgent(provider=fake_provider, registre=registre)

        resultat = await agent.run("analyse ce dépôt")

        assert resultat["status"] == "success"
        assert "source : arborescence" in agent.provider.appels[0]["prompt"]

    @pytest.mark.asyncio
    async def test_sans_registre_le_comportement_d_avant_est_intact(self, fake_provider):
        """Aucune régression : l'agent reste utilisable seul."""
        agent = RepoEngineerAgent(provider=fake_provider)

        resultat = await agent.run("analyse ce dépôt")

        assert resultat["status"] == "success"
        assert "source : arborescence" in agent.provider.appels[0]["prompt"]
