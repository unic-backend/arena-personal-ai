"""Planifier une scene : auditer le prompt, et ne l'envoyer a WanGP que s'il est pret.

Methode extraite de Hell-Grind-AIGC-Skill (renmu2017, MIT) — voir DEC-0015 et
`tests/tools/test_prompt_audit.py` pour l'auditeur lui-meme. Ce fichier tient
le branchement : une phrase du proprietaire declenche-t-elle l'audit, et
bloque-t-il vraiment un envoi a WanGP quand le prompt est incomplet ?

Rien n'appelle WanGP ni Ollama : le registre est double.
"""
import pytest

from agents.video_analyzer.video_analyzer_agent import (
    VideoAnalyzerAgent,
    description_de_plan,
)
from core.connectors.base import EtatSante, Sante
from core.execution.travaux import FileDeTravaux

PROMPT_COMPLET = (
    "Une femme fatiguee sort de l'atelier sous la pluie, 6 secondes, camera "
    "fixe puis fin sur son visage, ambiance pluie."
)
PROMPT_INCOMPLET = "Une femme sort de l'atelier."


class RegistreDePlanification:
    """Un registre de test : il note ce qu'on lui demande, sans rien generer."""

    def __init__(self, resultat=None):
        self.appels = []
        self._resultat = resultat

    def executer(self, connecteur, capacite, **parametres):
        from core.actions.resultat import a_confirmer
        self.appels.append((connecteur, capacite, dict(parametres)))
        return self._resultat or a_confirmer(
            action="generer", cible=connecteur,
            message="Pret a generer. Rien n'est lance : confirme pour que ca parte.")

    def sante(self, nom):
        return Sante(EtatSante.OPERATIONNEL, message="pret")

    def obtenir(self, nom):
        return None


@pytest.mark.parametrize("phrase, reste", [
    ("Prépare le prompt de cette scène : une femme sort de l'atelier",
     "une femme sort de l'atelier"),
    ("écris le prompt pour ce plan : un homme traverse la rue",
     "un homme traverse la rue"),
    ("storyboard : un chantier au lever du jour", "un chantier au lever du jour"),
])
def test_les_phrases_de_planification_sont_reconnues(phrase, reste):
    assert description_de_plan(phrase) == reste


@pytest.mark.parametrize("phrase", [
    "fais-moi une vidéo sur les cloisons BA13",
    "où en est ma vidéo ?",
    "Analyse cette vidéo",
])
def test_une_demande_ordinaire_n_est_pas_une_planification(phrase):
    assert description_de_plan(phrase) is None


class TestPromptPret:
    async def test_un_prompt_complet_part_vers_wangp(self, fake_provider):
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run(f"Prépare le prompt de cette scène : {PROMPT_COMPLET}")

        assert registre.appels[0][0] == "wan2gp"
        assert registre.appels[0][1] == "generer"
        assert registre.appels[0][2]["source"] == PROMPT_COMPLET.rstrip(".")
        assert reponse["planification"]["audit"]["pret"] is True
        assert reponse["planification"]["statut"] == "NEEDS_CONFIRMATION"

    async def test_une_generation_ne_part_jamais_sans_confirmation(self, fake_provider):
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run(f"écris le prompt pour ce plan : {PROMPT_COMPLET}")

        assert "Rien n'est lance" in reponse["response"]


class TestPromptIncomplet:
    async def test_un_prompt_incomplet_ne_part_jamais(self, fake_provider):
        """Le defaut que l'audit existe pour prevenir : depenser la carte
        graphique sur un prompt sans duree ni etat final de camera."""
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run(f"storyboard : {PROMPT_INCOMPLET}")

        assert registre.appels == [], "aucun prompt incomplet ne doit atteindre WanGP"
        assert reponse["planification"]["statut"] == "A_COMPLETER"
        assert reponse["planification"]["audit"]["pret"] is False
        assert reponse["status"] == "warning"

    async def test_les_problemes_bloquants_sont_dans_la_reponse(self, fake_provider):
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run(f"storyboard : {PROMPT_INCOMPLET}")

        assert "duree" in reponse["response"].lower() or "durée" in reponse["response"].lower()


class TestSansDescription:
    async def test_une_description_vide_est_demandee_pas_devinee(self, fake_provider):
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run("storyboard")

        assert reponse["planification"]["statut"] == "INCOMPLET"
        assert registre.appels == []


class TestSansRegistre:
    async def test_sans_generateur_l_agent_le_dit(self, fake_provider):
        agent = VideoAnalyzerAgent(provider=fake_provider)

        reponse = await agent.run(f"storyboard : {PROMPT_COMPLET}")

        assert reponse["planification"]["statut"] == "NOT_CONFIGURED"
        assert reponse["status"] == "warning"


class TestNeSeConfondPasAvecLesAutresDemandes:
    async def test_une_demande_de_video_reste_une_fabrication(self, fake_provider):
        """« Prepare » declenche AUSSI FABRIQUER_VIDEO : la planification, plus
        specifique, doit gagner uniquement quand « prompt »/scene/plan y sont."""
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run("prépare-moi une vidéo sur les cloisons BA13")

        assert registre.appels[0][0] == "moneyprinter"
        assert reponse.get("planification") is None

    async def test_une_demande_d_analyse_n_est_pas_une_planification(self, fake_provider):
        registre = RegistreDePlanification()
        agent = VideoAnalyzerAgent(provider=fake_provider, registre=registre,
                                   travaux=FileDeTravaux())

        reponse = await agent.run("Analyse cette vidéo", context={"video_path": "/absent.mp4"})

        assert registre.appels == []
        assert reponse["status"] == "error"


def test_le_repli_hors_ligne_envoie_la_planification_a_l_agent_video():
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    phrase = "Prépare le prompt de cette scène : un homme traverse la rue"
    assert OrchestratorAgent._classer_par_mots_cles(None, phrase) == "VIDEO_ANALYSIS"
