"""« Où en est ma vidéo ? » — la question atteint-elle vraiment le suivi ?

Ces tests tiennent le branchement, pas le module : `core/connectors/suivi_video.py`
a déjà les siens (`tests/core/test_suivi_generation_video.py`). Ce qui est mesuré
ici, c'est qu'une **phrase du propriétaire** le fait tourner, sur l'agent vidéo,
et que le chat ne l'attend pas.

Rien n'appelle WanGP ni Ollama : le connecteur, le registre et le fournisseur
sont doublés ; la file de travaux et le journal des actions sont réels.
"""
import asyncio

import pytest

from agents.video_analyzer.video_analyzer_agent import (
    PREFIXE_SUIVI,
    VideoAnalyzerAgent,
    demande_de_suivi,
)
from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request
from core.actions.journal import ActionEnregistree, JournalDesActions
from core.actions.resultat import succes
from core.connectors.base import EtatSante, Sante
from core.execution.travaux import EtatTravail, FileDeTravaux

EN_COURS = {"done": False, "result": {"total_tasks": 4, "successful_tasks": 1}}
SANS_COMPTE = {"done": False, "result": {}}
FINI = {"done": True, "result": {"success": True, "total_tasks": 4, "successful_tasks": 4,
                                 "generated_files": ["outputs/chantier.mp4"]}}

COMMANDE_WANGP = "python wgp.py --mcp-server"


class FauxConnecteur:
    """Rend les instantanés prévus, un par interrogation."""

    def __init__(self, instantanes):
        self.instantanes = list(instantanes)
        self.appels = 0

    def executer(self, capacite, **parametres):
        self.appels += 1
        instantane = (self.instantanes.pop(0) if len(self.instantanes) > 1
                      else self.instantanes[0] if self.instantanes else None)

        class _Resultat:
            detail = {"donnees": instantane}
        return _Resultat()


class FauxRegistre:
    """Le registre réduit à ce que l'agent lui demande : une santé, un connecteur."""

    def __init__(self, connecteur, sante):
        self.connecteur = connecteur
        self._sante = sante
        self.sondes = 0

    def sante(self, nom):
        self.sondes += 1
        return self._sante

    def obtenir(self, nom):
        return self.connecteur


def journal_avec_generation(tmp_path, job_id="job-7"):
    """Un journal réel où WanGP a déposé l'identifiant d'une génération acceptée."""
    journal = JournalDesActions(db_path=str(tmp_path / "journal.db"))
    if job_id:
        journal.enregistrer(ActionEnregistree.depuis_resultat(
            succes(action="generer", cible="wan2gp",
                   message="Generation lancee.", preuve=job_id),
            outil="wan2gp"))
    return journal


def agent_video(fake_provider, journal, instantanes=(EN_COURS,), sante=None):
    connecteur = FauxConnecteur(list(instantanes))
    registre = FauxRegistre(connecteur, sante or Sante(EtatSante.OPERATIONNEL,
                                                       message="WanGP repond."))
    agent = VideoAnalyzerAgent(provider=fake_provider, memory=None, registre=registre,
                               travaux=FileDeTravaux(), journal=journal)
    return agent, registre, connecteur


# --- La phrase atteint-elle le suivi ? -------------------------------------------

async def test_la_question_ouvre_un_suivi_sur_l_agent_video(fake_provider, tmp_path):
    agent, _, _ = agent_video(fake_provider, journal_avec_generation(tmp_path))

    reponse = await agent.run("Où en est ma vidéo ?")

    assert reponse["suivi"]["job_id"] == "job-7"
    noms = [travail.nom for travail in agent.travaux.inventaire()]
    assert noms == [f"{PREFIXE_SUIVI} job-7"], "le suivi doit être entré dans la file"
    agent.travaux.annuler(agent.travaux.inventaire()[0].identifiant)


async def test_la_question_ne_reclame_aucun_fichier(fake_provider, tmp_path):
    """L'ancien chemin exigeait une vidéo sur le disque pour toute demande vidéo."""
    agent, _, _ = agent_video(fake_provider, journal_avec_generation(tmp_path))

    reponse = await agent.run("Où en est ma vidéo ?")

    assert "Aucune vidéo valide" not in reponse["response"]
    assert reponse["status"] == "success"
    agent.travaux.annuler(agent.travaux.inventaire()[0].identifiant)


async def test_le_chat_n_attend_pas_la_generation(fake_provider, tmp_path):
    """Le tour de chat se termine ; la vidéo, elle, arrive après."""
    agent, _, _ = agent_video(fake_provider, journal_avec_generation(tmp_path), [FINI])

    reponse = await agent.run("Où en est ma vidéo ?")
    travail = agent.travaux.lire(reponse["suivi"]["travail"])

    assert not travail.fini, "le suivi ne doit pas être terminé au retour de la réponse"

    fini = await agent.travaux.attendre(travail.identifiant)
    assert fini.etat is EtatTravail.TERMINE
    assert fini.resultat.fichiers == ["outputs/chantier.mp4"]


async def test_une_seconde_question_ne_lance_pas_un_second_suivi(fake_provider, tmp_path):
    agent, _, _ = agent_video(fake_provider, journal_avec_generation(tmp_path))

    await agent.run("Où en est ma vidéo ?")
    seconde = await agent.run("Et maintenant, où en est ma vidéo ?")

    assert len(agent.travaux.inventaire()) == 1
    assert seconde["suivi"]["job_id"] == "job-7"
    agent.travaux.annuler(agent.travaux.inventaire()[0].identifiant)


# --- Ce qui n'est jamais inventé --------------------------------------------------

async def test_l_identifiant_vient_du_journal_pas_de_la_phrase(fake_provider, tmp_path):
    agent, _, _ = agent_video(fake_provider, journal_avec_generation(tmp_path, "job-42"))

    reponse = await agent.run("Où en est ma vidéo job-999 ?")

    assert reponse["suivi"]["job_id"] == "job-42"
    agent.travaux.annuler(agent.travaux.inventaire()[0].identifiant)


async def test_sans_generation_lancee_il_n_y_a_rien_a_suivre(fake_provider, tmp_path):
    agent, registre, _ = agent_video(fake_provider, journal_avec_generation(tmp_path, ""))

    reponse = await agent.run("Où en est ma vidéo ?")

    assert reponse["suivi"]["statut"] == "AUCUNE"
    assert agent.travaux.inventaire() == [], "rien à suivre : aucun travail ne doit naître"
    assert registre.sondes == 0, "sans tâche, on n'interroge même pas WanGP"


async def test_wangp_eteint_donne_not_configured_et_la_commande(fake_provider, tmp_path):
    """La capacité absente se rapporte ; elle ne se simule pas."""
    agent, _, connecteur = agent_video(
        fake_provider, journal_avec_generation(tmp_path),
        sante=Sante(EtatSante.NON_CONFIGURE, message="WanGP ne repond pas sur 127.0.0.1.",
                    ce_qui_manque=f"WanGP demarre avec son serveur MCP : {COMMANDE_WANGP}"))

    reponse = await agent.run("Où en est ma vidéo ?")

    assert reponse["suivi"]["statut"] == "NOT_CONFIGURED"
    assert COMMANDE_WANGP in reponse["response"], "la commande de lancement doit être donnée"
    assert agent.travaux.inventaire() == [], "rien ne se suit sans WanGP"
    assert connecteur.appels == 0


async def test_un_total_inconnu_ne_devient_pas_zero(fake_provider, tmp_path):
    agent, _, _ = agent_video(fake_provider, journal_avec_generation(tmp_path), [SANS_COMPTE])

    premiere = await agent.run("Où en est ma vidéo ?")
    await asyncio.sleep(0)  # le suivi interroge une fois
    seconde = await agent.run("Où en est ma vidéo ?")

    assert premiere["suivi"]["progression"] is None
    assert seconde["suivi"]["progression"] is None
    assert "inconnu" in seconde["response"]
    agent.travaux.annuler(agent.travaux.inventaire()[0].identifiant)


async def test_sans_connecteur_l_agent_le_dit_au_lieu_de_se_taire(fake_provider):
    agent = VideoAnalyzerAgent(provider=fake_provider, memory=None)

    reponse = await agent.run("Où en est ma vidéo ?")

    assert reponse["suivi"]["statut"] == "NOT_CONFIGURED"
    assert reponse["status"] == "warning"


# --- L'analyse d'un fichier reste ce qu'elle était ---------------------------------

async def test_une_demande_d_analyse_n_est_pas_un_suivi(fake_provider, tmp_path):
    agent, _, connecteur = agent_video(fake_provider, journal_avec_generation(tmp_path))

    reponse = await agent.run("Analyse cette vidéo", context={"video_path": "/absent.mp4"})

    assert reponse["status"] == "error"
    assert connecteur.appels == 0, "aucune interrogation de WanGP sur le chemin d'analyse"
    assert agent.travaux.inventaire() == []


@pytest.mark.parametrize("phrase", [
    "Où en est ma vidéo ?",
    "ou en est la video du chantier",
    "Ma génération est terminée ?",
    "avancement de la génération vidéo",
])
def test_les_phrases_de_suivi_sont_reconnues(phrase):
    assert demande_de_suivi(phrase)


@pytest.mark.parametrize("phrase", [
    "Analyse cette vidéo",
    "Découpe cette vidéo en shorts",
    "Écris-moi un devis pour 40 m2",
])
def test_une_demande_ordinaire_n_est_pas_un_suivi(phrase):
    assert not demande_de_suivi(phrase)


# --- L'aiguillage du chat ---------------------------------------------------------

class AgentDouble:
    def __init__(self):
        self.appels = []

    async def run(self, user_input, context=None):
        self.appels.append((user_input, context))
        return {"status": "success", "agent": "VideoAnalyzerAgent", "response": "ok"}


async def test_le_routeur_n_exige_pas_de_fichier_pour_une_question_de_suivi(monkeypatch):
    """Avant : la branche vidéo validait un chemin média avant même l'agent."""
    double = AgentDouble()
    monkeypatch.setattr(routeur_chat, "video_agent", double)

    await dispatch_request(ChatRequest(prompt="Où en est ma vidéo ?", session_id="test"),
                           intent="VIDEO_ANALYSIS")

    assert double.appels == [("Où en est ma vidéo ?", None)]


async def test_le_routeur_passe_toujours_le_fichier_pour_une_analyse(monkeypatch):
    double = AgentDouble()
    monkeypatch.setattr(routeur_chat, "video_agent", double)

    await dispatch_request(ChatRequest(prompt="Analyse cette vidéo", session_id="test"),
                           intent="VIDEO_ANALYSIS")

    _, contexte = double.appels[0]
    assert contexte is not None and "video_path" in contexte


@pytest.mark.parametrize("phrase", [
    "Où en est ma vidéo ?",
    "ou en est ma video",
    "où en est la vidéo du chantier",
])
def test_le_repli_hors_ligne_envoie_la_question_a_l_agent_video(phrase):
    """Sans Ollama pour classer, la phrase doit quand même trouver l'agent vidéo."""
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    assert OrchestratorAgent._classer_par_mots_cles(None, phrase) == "VIDEO_ANALYSIS"
