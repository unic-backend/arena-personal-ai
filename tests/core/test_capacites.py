"""Le canal par lequel un espace en interroge un autre.

Ce que ce registre doit garantir :

- appeler un espace connu appelle REELLEMENT l'agent enregistre, avec sa
  requete et son contexte, et rend son resultat tel quel — rien n'est
  reformule au passage ;
- un espace inconnu leve une erreur qui NOMME les espaces reellement connus,
  jamais une KeyError muette ;
- un outil synchrone (`LightRAGTool.query`) peut etre expose avec le meme
  contrat que les agents, sans que l'appelant ait a le savoir.
"""
from typing import Any, Dict, Optional

import pytest

from core.agent.capacites import CapaciteInconnue, RegistreCapacites, adaptateur_synchrone


class AgentDouble:
    """Un espace scripte : rend une reponse fixe, garde ce qu'il a recu."""

    def __init__(self, reponse: Dict[str, Any]):
        self.reponse = reponse
        self.appels: list = []

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.appels.append({"user_input": user_input, "context": context})
        return self.reponse


class AgentQuiEchoue:
    """Un espace dont l'appel leve — pour verifier que rien ne l'avale."""

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise RuntimeError("l'agent de video a refuse")


@pytest.fixture
def registre() -> RegistreCapacites:
    return RegistreCapacites()


class TestDemande:
    async def test_un_espace_connu_est_reellement_appele(self, registre):
        agent = AgentDouble({"status": "success", "agent": "Coder", "response": "def f(): ..."})
        registre.enregistrer("code", agent)

        resultat = await registre.demander("code", "ecris une fonction", contexte={"depuis": "video"})

        assert resultat == {"status": "success", "agent": "Coder", "response": "def f(): ..."}
        assert agent.appels == [{"user_input": "ecris une fonction", "context": {"depuis": "video"}}]

    async def test_un_espace_inconnu_nomme_les_espaces_reellement_connus(self, registre):
        registre.enregistrer("code", AgentDouble({"status": "success"}))
        registre.enregistrer("video", AgentDouble({"status": "success"}))

        with pytest.raises(CapaciteInconnue) as exc:
            await registre.demander("plaquiste", "un devis")

        assert exc.value.espace == "plaquiste"
        assert sorted(exc.value.connus) == ["code", "video"]
        assert "code" in str(exc.value)
        assert "video" in str(exc.value)

    async def test_un_registre_vide_le_dit_dans_l_erreur(self, registre):
        with pytest.raises(CapaciteInconnue) as exc:
            await registre.demander("code", "peu importe")

        assert "(aucun)" in str(exc.value)

    async def test_une_erreur_de_l_agent_appele_n_est_pas_avalee(self, registre):
        registre.enregistrer("video", AgentQuiEchoue())

        with pytest.raises(RuntimeError, match="l'agent de video a refuse"):
            await registre.demander("video", "analyse cette video")

    async def test_reenregistrer_un_espace_remplace_l_ancien(self, registre):
        """Un module reimporte en test ne doit pas laisser une entree perimee."""
        ancien = AgentDouble({"status": "success", "response": "ancien"})
        neuf = AgentDouble({"status": "success", "response": "neuf"})
        registre.enregistrer("code", ancien)
        registre.enregistrer("code", neuf)

        resultat = await registre.demander("code", "peu importe")

        assert resultat["response"] == "neuf"
        assert ancien.appels == []


class TestConnait:
    def test_connait_un_espace_enregistre(self, registre):
        registre.enregistrer("web", AgentDouble({}))
        assert registre.connait("web") is True

    def test_ne_connait_pas_un_espace_absent(self, registre):
        assert registre.connait("web") is False

    def test_espaces_liste_ce_qui_est_enregistre(self, registre):
        registre.enregistrer("code", AgentDouble({}))
        registre.enregistrer("documents", AgentDouble({}))

        assert sorted(registre.espaces()) == ["code", "documents"]


class TestAdaptateurSynchrone:
    async def test_le_resultat_synchrone_devient_le_contrat_commun(self):
        capacite = adaptateur_synchrone(lambda texte: f"reponse a : {texte}", "LightRAG")

        resultat = await capacite.run("ou est le devis Fast Group ?")

        assert resultat == {
            "status": "success",
            "agent": "LightRAG",
            "response": "reponse a : ou est le devis Fast Group ?",
        }

    async def test_l_adaptateur_est_utilisable_depuis_le_registre(self, registre):
        appels = []
        registre.enregistrer("documents", adaptateur_synchrone(
            lambda texte: appels.append(texte) or "trouve", "LightRAG",
        ))

        resultat = await registre.demander("documents", "cherche le devis")

        assert resultat["response"] == "trouve"
        assert appels == ["cherche le devis"]
