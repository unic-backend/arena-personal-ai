"""« Mes avis Google ? » (DEC-0184) : la phrase devient une capacite du
connecteur `fiche_google` — aucun agent, aucun modele."""
import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend.routers import chat as module_chat
from core.actions.resultat import a_confirmer, non_configure, succes
from core.fiche_google.demande import choisir_avis, lire_demande, rendre

AVIS = [
    {"id": "r1", "auteur": "Fatou Ndiaye", "etoiles": 5, "commentaire": "Top",
     "date": "2026-09-28T10:00:00Z", "reponse": None},
    {"id": "r2", "auteur": "Moussa", "etoiles": 4, "commentaire": "Bien",
     "date": "2026-09-29T09:00:00Z", "reponse": None},
    {"id": "r3", "auteur": "Fatou Sow", "etoiles": 3, "commentaire": "Correct",
     "date": "2026-09-29T10:00:00Z", "reponse": "Merci"},
]

# --- La phrase ------------------------------------------------------------------

@pytest.mark.parametrize("phrase, capacite", [
    ("Quels sont mes avis Google ?", "avis"),
    ("ma note sur Google Maps", "avis"),
    ("les derniers commentaires de ma fiche", "avis"),
    ("l'adresse sur ma fiche Google est bonne ?", "fiche"),
    ("réponds au dernier avis : Merci beaucoup !", "repondre"),
    ("Réponds à l'avis de Fatou Ndiaye : Merci Fatou, à bientôt !", "repondre"),
])
def test_la_phrase_donne_la_capacite(phrase, capacite):
    assert lire_demande(phrase).capacite == capacite


@pytest.mark.parametrize("phrase", [
    "donne-moi ton avis sur ce devis",       # son opinion, pas ses avis clients
    "quel est ton avis ?",
    "cherche sur google le prix du BA13",     # « google » sans avis ni fiche
    "réponds à Fatou : merci",               # un message, pas un avis
    "quelle est la note de Google en bourse ?",  # Google l'entreprise, pas sa fiche
])
def test_ces_phrases_ne_sont_pas_pour_la_fiche(phrase):
    assert lire_demande(phrase) is None


def test_le_texte_de_la_reponse_est_garde_tel_qu_il_a_ete_dit():
    demande = lire_demande("Réponds à l'avis de Fatou Ndiaye : Merci Fatou, à bientôt !")

    assert demande.auteur == "Fatou Ndiaye"
    assert demande.message == "Merci Fatou, à bientôt !", "accents et majuscules compris"


async def test_l_orchestrateur_l_envoie_a_la_fiche_avant_le_courrier(provider_factory):
    orchestrateur = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    assert await orchestrateur.analyze_intent("mes avis google aujourd'hui") == "FICHE_GOOGLE"
    assert await orchestrateur.analyze_intent(
        "réponds à l'avis de Fatou : merci !") == "FICHE_GOOGLE"


# --- Quel avis viser -------------------------------------------------------------

def test_le_nom_vise_sans_accents_ni_casse():
    assert [a["id"] for a in choisir_avis(AVIS, "fatou ndiaye")] == ["r1"]


def test_deux_auteurs_du_meme_prenom_ne_sont_jamais_departages_ici():
    assert [a["id"] for a in choisir_avis(AVIS, "Fatou")] == ["r1", "r3"]


def test_le_dernier_avis_est_le_plus_recent_sans_reponse():
    # r3 est plus recent, mais il a deja une reponse.
    assert [a["id"] for a in choisir_avis(AVIS, None)] == ["r2"]


# --- Le chat ---------------------------------------------------------------------

class Registre:
    def __init__(self, resultats):
        self.resultats = resultats
        self.appels = []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.resultats[capacite]


LUS = succes("avis", "fiche_google", "3 avis lu(s) ; note Google : 4.6/5 sur 18 avis.",
             preuve="google:GET:x", donnees=AVIS)


def test_reponde_a_un_avis_nomme_attend_la_confirmation(monkeypatch):
    registre = Registre({"avis": LUS, "repondre_avis": a_confirmer(
        action="repondre_avis", cible="fiche_google", message="Pret. Rien n'est parti.")})
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = module_chat._ma_fiche_google("Réponds à l'avis de Fatou Ndiaye : Merci Fatou !")

    assert registre.appels[-1] == ("fiche_google", "repondre_avis",
                                   {"avis_id": "r1", "message": "Merci Fatou !"})
    assert reponse["statut_connecteur"] == "NEEDS_CONFIRMATION"
    assert reponse["avis_vise"]["auteur"] == "Fatou Ndiaye"


def test_un_nom_ambigu_ne_repond_a_personne(monkeypatch):
    registre = Registre({"avis": LUS})
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = module_chat._ma_fiche_google("réponds à l'avis de Fatou : merci")

    assert reponse["status"] == "error" and "2 avis" in reponse["response"]
    assert [c for _, c, _ in registre.appels] == ["avis"], "aucune reponse soumise"


def test_un_nom_absent_le_dit(monkeypatch):
    monkeypatch.setattr(module_chat, "registre", Registre({"avis": LUS}))

    reponse = module_chat._ma_fiche_google("réponds à l'avis de Awa : merci")

    assert "Aucun avis de « Awa »" in reponse["response"]


async def test_les_avis_sont_lus_et_listes(monkeypatch):
    registre = Registre({"avis": LUS})
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = await module_chat._aiguiller(
        module_chat.ChatRequest(prompt="mes avis google"), "FICHE_GOOGLE")

    assert registre.appels == [("fiche_google", "avis", {"limite": 10})]
    assert reponse["response"].startswith("3 avis lu(s) ; note Google : 4.6/5 sur 18 avis.")
    assert "- Moussa · 4/5 · 2026-09-29T09:00:00Z : Bien [sans reponse]" in reponse["response"]
    assert "- Fatou Sow · 3/5 · 2026-09-29T10:00:00Z : Correct [repondu]" in reponse["response"]


def test_sans_connexion_le_chat_dit_ce_qui_manque(monkeypatch):
    pas_la = non_configure(action="avis", cible="fiche_google", ce_qui_manque="la connexion Google")
    monkeypatch.setattr(module_chat, "registre", Registre({"avis": pas_la}))

    reponse = module_chat._ma_fiche_google("réponds au dernier avis : merci")

    assert reponse["status"] == "error" and "la connexion Google" in reponse["response"]


def test_une_note_absente_s_affiche_inconnue():
    texte = rendre("avis", "1 avis lu(s).", [{"auteur": None, "etoiles": None, "commentaire": None}])

    assert "- anonyme · ?/5 · ? : (sans commentaire) [sans reponse]" in texte
