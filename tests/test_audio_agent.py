"""L'agent audio : sa phrase choisit la capacité, et rien ne se simule.

Le classement se fait par mots-clés parce que c'est la MACHINE qui parle et
qui écoute — aucun modèle n'est nécessaire pour distinguer « transcris ça »
de « lis-moi ça ». C'est aussi ce qui le rend testable sans Ollama.
"""
import pytest

from agents.audio.audio_agent import AudioAgent, genre_de_demande, texte_a_lire
from core.actions.resultat import a_confirmer, echec, non_configure, succes


class RegistreDouble:
    def __init__(self, resultat=None):
        self.resultat, self.appels = resultat, []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.resultat or succes(
            action=capacite, cible=connecteur, message="ok", preuve="p", texte="ok")


class ModeleDouble:
    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, **_) -> str:
        raise AssertionError("l'agent audio ne doit appeler aucun modèle de langue")


@pytest.fixture
def audio(tmp_path):
    def construire(resultat=None):
        return AudioAgent(provider=ModeleDouble(), registre=RegistreDouble(resultat))
    return construire


class TestLeClassement:
    @pytest.mark.parametrize("phrase", [
        "transcris cette vidéo du chantier",
        "écris ce qui est dit dans l'enregistrement",
        "qu'est-ce qui est dit dans cet enregistrement",
    ])
    def test_ce_qui_demande_d_ecouter(self, phrase):
        assert genre_de_demande(phrase) == "ecouter"

    @pytest.mark.parametrize("phrase", [
        "lis-moi ce texte",
        "fais une voix off pour mon chantier",
        "transforme ce texte en voix",
        "génère une voix pour la narration",
    ])
    def test_ce_qui_demande_de_parler(self, phrase):
        assert genre_de_demande(phrase) == "parler"

    def test_transcrire_gagne_sur_parler_quand_les_deux_sont_la(self):
        """« transcris ce qu'il dit » contient « dis » : l'écoute prime."""
        assert genre_de_demande("transcris ce qu'il dit à voix haute") == "ecouter"


class TestLeTexteALire:
    def test_ce_qui_est_entre_guillemets_gagne(self):
        assert texte_a_lire('lis-moi « Bonjour Dakar »') == "Bonjour Dakar"

    def test_sans_guillemets_l_amorce_est_retiree(self):
        """Sans ça, « lis-moi bonjour » ferait dire « lis-moi bonjour »."""
        assert texte_a_lire("lis-moi bonjour à tous") == "bonjour à tous"

    def test_une_phrase_sans_amorce_reste_entiere(self):
        assert texte_a_lire("Bonjour, ici UniC") == "Bonjour, ici UniC"


class TestCeQuIlRefuseDeSimuler:
    @pytest.mark.asyncio
    async def test_sans_registre_il_le_dit(self):
        agent = AudioAgent(provider=ModeleDouble(), registre=None)
        r = await agent.run("lis-moi ce texte")
        assert r["status"] == "error"

    @pytest.mark.asyncio
    async def test_sans_fichier_il_ne_transcrit_rien(self, audio, tmp_path):
        agent = audio()
        r = await agent.run("transcris cette vidéo",
                            context={"medias": [str(tmp_path / "absent.mp4")]})
        assert r["status"] == "error"
        assert agent.registre.appels == [], "il a appelé le connecteur sans fichier"

    @pytest.mark.asyncio
    async def test_un_moteur_manquant_est_un_avertissement_pas_une_reussite(self, audio):
        agent = audio(non_configure(action="parler", cible="audio",
                                    ce_qui_manque="aucun moteur de voix"))
        r = await agent.run("lis-moi « bonjour »")
        assert r["status"] == "warning"
        assert "moteur" in r["response"]

    @pytest.mark.asyncio
    async def test_un_echec_du_service_reste_un_echec(self, audio):
        agent = audio(echec(action="transcrire", cible="audio",
                            message="VoiceStudio n'a rien entendu"))
        r = await agent.run("transcris ça", context={"medias": []})
        assert r["status"] == "error"

    @pytest.mark.asyncio
    async def test_une_confirmation_en_attente_n_est_pas_une_erreur(self, audio):
        """Parler écrit un fichier : la file d'attente est un état normal."""
        agent = audio(a_confirmer(action="parler", cible="audio",
                                  message="Prêt.", risque="MEDIUM",
                                  identifiant="abc"))
        r = await agent.run("lis-moi « bonjour »")
        assert r["status"] == "warning"


class TestLaChaine:
    @pytest.mark.asyncio
    async def test_lire_passe_par_la_capacite_parler(self, audio):
        agent = audio()
        await agent.run('lis-moi « Bonjour, ici UniC Plaquiste »')
        connecteur, capacite, parametres = agent.registre.appels[0]
        assert (connecteur, capacite) == ("audio", "parler")
        assert parametres["texte"] == "Bonjour, ici UniC Plaquiste"

    @pytest.mark.asyncio
    async def test_transcrire_passe_le_chemin_reel(self, audio, tmp_path):
        media = tmp_path / "chantier.mp4"
        media.write_bytes(b"x")
        agent = audio()
        await agent.run("transcris cette vidéo", context={"medias": [str(media)]})
        _, capacite, parametres = agent.registre.appels[0]
        assert capacite == "transcrire"
        assert parametres["chemin"] == str(media)

    @pytest.mark.asyncio
    async def test_une_question_sur_les_moteurs_liste_sans_rien_ecrire(self, audio):
        agent = audio()
        r = await agent.run("quelles voix sont disponibles ?")
        assert r["status"] == "success"
        assert agent.registre.appels[0][1] == "moteurs"

    @pytest.mark.asyncio
    async def test_un_fichier_non_audio_n_est_pas_propose_a_la_transcription(
        self, audio, tmp_path
    ):
        texte = tmp_path / "notes.txt"
        texte.write_bytes(b"x")
        agent = audio()
        r = await agent.run("transcris ça", context={"medias": [str(texte)]})
        assert r["status"] == "error"


class TestPasDeDoublon:
    """ARENA fabrique déjà les sous-titres (studio). L'audio ne les reprend pas."""

    @pytest.mark.parametrize("phrase", [
        "fais les sous-titres de cette vidéo",
        "sous-titre ma vidéo",
    ])
    def test_les_sous_titres_ne_sont_pas_une_demande_d_ecoute(self, phrase):
        assert genre_de_demande(phrase) != "ecouter", (
            "l'audio a repris une capacité que le studio fait déjà de bout en bout"
        )
