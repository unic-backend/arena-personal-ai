"""Les compétences réseaux sociaux, devenues des capacités qui s'exécutent.

Le test qui porte l'intégration est
`test_une_phrase_naturelle_fait_executer_la_bonne_capacite` : le propriétaire ne
nomme jamais une compétence, et pourtant la bonne tourne.

Le second est `test_sa_voix_ne_s_invente_jamais` : sans voix connue, ARENA
demande au lieu d'écrire dans un ton supposé — le texte partirait sous son nom.

Aucun test n'appelle Ollama, Apify, Gemini ni un réseau social.
"""
import pytest

from agents.social.social_agent import CAPACITES, SocialAgent, choisir
from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request
from core.actions.resultat import a_confirmer, refuse
from core.memory.personnelle import MemoirePersonnelle
from tools.social import voix as memoire_voix

PUBLICATION = (
    "Trois chantiers, une erreur.\n\nCelle-la m'a coute cher.\n\n"
    + "\n\n".join(" ".join(["mot"] * 11) for _ in range(14))
    + "\n\nPartage si ca t'a servi ♻"
)


class ModeleDouble:
    def __init__(self, reponse=PUBLICATION):
        self.reponse = reponse
        self.systemes = []
        self.prompts = []

    async def generate(self, prompt, system_prompt=None, **kw):
        self.prompts.append(prompt)
        self.systemes.append(system_prompt)
        return self.reponse


class RegistreDouble:
    def __init__(self, resultat=None):
        self.appels = []
        self._resultat = resultat or a_confirmer(
            action="publish_video", cible="tiktok",
            message="Pret a publier. Rien n'est parti : confirme pour que ca parte.")

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, dict(parametres)))
        return self._resultat


@pytest.fixture
def memoire(tmp_path):
    return MemoirePersonnelle(db_path=str(tmp_path / "voix.db"))


@pytest.fixture
def avec_voix(memoire):
    """Sa voix, telle qu'il l'aurait dite une fois."""
    memoire_voix.apprendre(memoire, "qui", "Ousmane, plaquiste a Dakar")
    memoire_voix.apprendre(memoire, "audience", "des proprietaires et des architectes")
    memoire_voix.apprendre(memoire, "piliers", "cloisons BA13, faux plafonds, devis honnetes")
    memoire_voix.apprendre(memoire, "ton", "direct, concret, sans jargon")
    return memoire


def agent(memoire=None, modele=None, registre=None, recherche=None):
    return SocialAgent(provider=modele or ModeleDouble(), memoire_personnelle=memoire,
                       registre=registre, recherche=recherche)


# --- Les deux tests qui portent l'intégration -------------------------------------

@pytest.mark.parametrize("phrase,attendue", [
    ("Ecris une publication LinkedIn sur mon chantier", "social.post_writer"),
    ("Analyse ce qui marche actuellement dans mon secteur", "social.recherche_niche"),
    ("Optimise mon profil LinkedIn", "social.profil"),
    ("Donne-moi 10 idees de contenu", "social.idees"),
    ("Analyse cette publication avant que je la publie", "social.verifier"),
    ("Prepare un Reel", "social.reels"),
    ("Fais une image pour cette publication", "social.visuel"),
    ("Analyse mes publications recentes", "social.analytics"),
    ("Je n'ecris jamais comme ca", "social.voix"),
    ("Donne-moi des accroches pour ce sujet", "social.accroches"),
])
def test_une_phrase_naturelle_fait_executer_la_bonne_capacite(phrase, attendue):
    """Il ne nomme jamais une compétence. C'est ici que la bonne est choisie."""
    capacite = choisir(phrase)

    assert capacite is not None and capacite.nom == attendue


async def test_sa_voix_ne_s_invente_jamais(memoire):
    """Un texte écrit dans une voix supposée part sous son nom."""
    modele = ModeleDouble()
    resultat = await agent(memoire, modele).run("Ecris une publication sur mon chantier")

    assert resultat["execution"]["statut"] == "MANQUE_CONTEXTE"
    assert modele.prompts == [], "aucun texte ne doit avoir ete ecrit"
    assert "manque" in resultat["response"].lower()


# --- La voix, apprise et gardée -----------------------------------------------------

async def test_la_voix_connue_entre_dans_l_instruction(avec_voix):
    modele = ModeleDouble()

    await agent(avec_voix, modele).run("Ecris une publication sur mon chantier")

    instruction = modele.systemes[0]
    assert "plaquiste a Dakar" in instruction
    assert "cloisons BA13" in instruction
    assert "N'invente aucun trait de voix" in instruction


async def test_une_correction_est_retenue_et_pese_plus_lourd(avec_voix):
    resultat = await agent(avec_voix).run("Je n'ecris jamais comme ca, trop de jargon")

    souvenirs = avec_voix.souvenirs(projet=memoire_voix.PROJET, limite=50)
    corrections = [s for s in souvenirs if s.source == "correction"]

    assert resultat["execution"]["capacite"] == "social.voix"
    assert corrections, "la correction doit etre retenue"
    assert corrections[0].importance > memoire_voix.IMPORTANCE_INTERVIEW


async def test_la_voix_dit_ce_qui_lui_manque_encore(memoire):
    memoire_voix.apprendre(memoire, "qui", "Ousmane, plaquiste")

    resultat = await agent(memoire).run("mon style est direct")

    assert "Il me manque" in resultat["response"]


# --- Ce que le modèle rend est relu par une machine -----------------------------------

async def test_le_brouillon_est_relu_et_les_ecarts_sont_dits(avec_voix):
    """Une consigne n'est pas une garantie : le comptage décide."""
    trop_long = "\n\n".join(f"ligne {i} " + "mot " * 10 for i in range(30))
    resultat = await agent(avec_voix, ModeleDouble(trop_long)).run(
        "Ecris une publication sur mon chantier")

    controle = resultat["execution"]["controle"]
    assert controle["conforme"] is False
    assert any(i["regle"] == "lignes_max" for i in controle["infractions"])
    assert "a corriger" in resultat["response"]


async def test_une_publication_conforme_est_annoncee_conforme(avec_voix):
    resultat = await agent(avec_voix).run("Ecris une publication sur mon chantier")

    assert resultat["execution"]["controle"]["conforme"] is True


def test_relire_ne_demande_aucun_modele(avec_voix):
    """Relire est mécanique : aucun appel au modèle, aucun jeton dépensé."""
    modele = ModeleDouble()
    resultat = agent(avec_voix, modele).relire(PUBLICATION)

    assert modele.prompts == []
    assert resultat["execution"]["controle"]["conforme"] is True


# --- Publier est une confirmation ------------------------------------------------------

async def test_publier_passe_par_le_connecteur_et_rien_ne_part(avec_voix):
    registre = RegistreDouble()
    resultat = await agent(avec_voix, registre=registre).run(
        "Ecris une publication sur mon chantier et publie-la")

    assert registre.appels and registre.appels[0][1] == "publish_video"
    assert resultat["execution"]["statut"] == "EN_ATTENTE_APPROBATION"
    assert "Rien n'est parti" in resultat["response"]


async def test_sans_demande_d_envoi_rien_n_est_soumis(avec_voix):
    registre = RegistreDouble()
    await agent(avec_voix, registre=registre).run("Ecris une publication sur mon chantier")

    assert registre.appels == []


async def test_un_coupe_circuit_ferme_refuse_et_le_brouillon_reste(avec_voix):
    """Préparer sans envoyer est le travail utile : il n'est pas perdu."""
    registre = RegistreDouble(refuse(action="publish_video", cible="tiktok",
                                     permission="PUBLISH"))
    resultat = await agent(avec_voix, registre=registre).run(
        "Ecris une publication et publie-la")

    assert resultat["execution"]["brouillon"], "le brouillon doit rester"
    assert "Refuse" in resultat["response"] or "refus" in resultat["response"].lower()


async def test_sans_connecteur_l_agent_le_dit(avec_voix):
    resultat = await agent(avec_voix).run("Ecris une publication et publie-la")

    assert "aucun reseau n'est branche" in resultat["response"]


# --- Les dépendances absentes -----------------------------------------------------------

@pytest.mark.parametrize("phrase,manque", [
    ("Prepare un Reel", "Apify"),
    ("Fais une image pour cette publication", "generation d'images"),
    ("Analyse mes publications recentes", "compte connecte"),
])
async def test_une_capacite_sans_dependance_se_declare(avec_voix, phrase, manque):
    """Ce qui manque est nommé. Le reste continue de marcher."""
    resultat = await agent(avec_voix).run(phrase)

    assert resultat["execution"]["statut"] == "CONFIGURATION_REQUISE"
    assert manque in resultat["response"]
    assert manque in resultat["execution"]["manque"]


async def test_une_capacite_indisponible_n_empeche_pas_les_autres(avec_voix):
    agent_social = agent(avec_voix)

    await agent_social.run("Prepare un Reel")
    ecriture = await agent_social.run("Ecris une publication sur mon chantier")

    assert ecriture["execution"]["statut"] == "PRET"


async def test_la_recherche_de_niche_n_invente_pas_de_tendances(avec_voix):
    """Sans recherche branchée, on le dit — c'est le contraire d'inventer."""
    resultat = await agent(avec_voix).run("Qu'est-ce qui marche dans mon secteur ?")

    assert resultat["execution"]["statut"] == "INDISPONIBLE"
    assert "je n'invente pas de tendances" in resultat["response"].lower()


async def test_la_recherche_branchee_est_reellement_appelee(avec_voix):
    appels = []

    def chercher(demande):
        appels.append(demande)
        return [{"titre": "source", "url": "https://exemple.test"}]

    resultat = await agent(avec_voix, recherche=chercher).run(
        "Qu'est-ce qui marche dans mon secteur ?")

    assert appels, "la recherche doit avoir tourne"
    assert resultat["execution"]["sources"]


# --- Les idées sont calculées, pas générées ----------------------------------------------

async def test_les_idees_viennent_de_ses_piliers_sans_modele(avec_voix):
    modele = ModeleDouble()
    resultat = await agent(avec_voix, modele).run("Donne-moi 10 idees de contenu")

    assert modele.prompts == [], "une combinatoire ne s'appelle pas a un modele"
    assert resultat["execution"]["resume"]["total"] >= 24
    assert "cloisons BA13" in str(resultat["execution"]["idees"])


# --- Chaque exécution laisse ses étapes ---------------------------------------------------

async def test_les_etapes_correspondent_a_des_operations_reelles(avec_voix):
    resultat = await agent(avec_voix).run("Ecris une publication sur mon chantier")

    etapes = resultat["execution"]["etapes"]
    assert any("voix chargee" in e for e in etapes)
    assert any("brouillon ecrit" in e for e in etapes)
    assert any("relecture" in e for e in etapes)


def test_le_registre_declare_ses_dependances():
    """Ce que chaque capacité exige est lisible sans ouvrir son code."""
    par_nom = {c.nom: c for c in CAPACITES}

    assert par_nom["social.reels"].dependances == ("Apify", "Gemini")
    assert par_nom["social.post_writer"].permission == "approbation"
    assert par_nom["social.idees"].dependances == ()


# --- L'aiguillage depuis une vraie phrase ---------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "Ecris une publication LinkedIn sur mon chantier",
    "Donne-moi des idees de contenu",
    "Prepare un post pour mes reseaux sociaux",
])
def test_le_repli_hors_ligne_envoie_aux_reseaux(phrase):
    """« chantier » est son métier : la demande n'en est pas un devis pour autant."""
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    assert OrchestratorAgent._classer_par_mots_cles(None, phrase) == "SOCIAL"


def test_ecrire_un_devis_reste_au_metier():
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    assert OrchestratorAgent._classer_par_mots_cles(
        None, "fais-moi un devis pour 12 parois") == "PLAQUISTE"


async def test_le_routeur_mene_a_l_agent_social(monkeypatch):
    appels = []

    async def _double(user_input, context=None):
        appels.append(user_input)
        return {"status": "success", "agent": "SocialAgent", "response": "ok"}

    monkeypatch.setattr(routeur_chat.social_agent, "run", _double)

    resultat = await dispatch_request(
        ChatRequest(prompt="Ecris une publication sur mon chantier", session_id="t"),
        intent="SOCIAL")

    assert appels and resultat["agent"] == "SocialAgent"


def test_l_intention_a_une_voie():
    from core.execution.voies import voie_pour

    assert voie_pour("SOCIAL").value in ("DEEP", "LIGHT")
