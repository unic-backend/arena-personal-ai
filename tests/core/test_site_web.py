"""« Mon site est en ligne ? » (DEC-0182) : la phrase devient une capacite du
connecteur Netlify — aucun agent, aucun modele."""
import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend.routers import chat as module_chat
from core.actions.resultat import a_confirmer, non_configure, succes
from core.site_web.demande import capacite_du_site, rendre

# --- La phrase ------------------------------------------------------------------

@pytest.mark.parametrize("phrase, capacite", [
    ("Mon site est en ligne ?", "site_infos"),
    ("quel est l'état de mon site", "site_infos"),
    ("Le dernier déploiement de mon site a marché ?", "deploiements"),
    ("pourquoi le build de mon site a échoué", "deploiements"),
    ("j'ai reçu des messages sur mon site ?", "soumissions"),
    ("les demandes de devis du formulaire de mon site", "soumissions"),
    ("liste mes sites", "sites"),
    ("quels sites j'ai sur Netlify", "sites"),
    ("republie mon site", "redeployer"),
    ("remets mon site en ligne", "redeployer"),            # « en ligne » ne gagne pas
])
def test_la_phrase_donne_la_capacite(phrase, capacite):
    assert capacite_du_site(phrase) == capacite


@pytest.mark.parametrize("phrase", [
    "crée-moi un site pour mon entreprise",
    "améliore le design de mon site",
    "modifie la page d'accueil de mon site",
    "crée un formulaire de contact sur mon site",          # « formulaire », mais a fabriquer
    "ajoute un message d'accueil et redeploie : code-le sur mon site",
    "le site de la mairie est en ligne ?",                 # pas le sien
    "mes messages de la journée",                          # son courrier
    "est-ce que ça marche ?",
])
def test_ces_phrases_ne_sont_pas_pour_le_connecteur(phrase):
    assert capacite_du_site(phrase) is None


async def test_l_orchestrateur_l_envoie_au_site_avant_le_controle_date(provider_factory):
    orchestrateur = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    assert await orchestrateur.analyze_intent("mon site est en ligne aujourd'hui ?") == "SITE_WEB"
    assert await orchestrateur.analyze_intent("les messages de mon site") == "SITE_WEB"


# --- Le chat ---------------------------------------------------------------------

class Registre:
    def __init__(self, resultat):
        self.resultat = resultat
        self.appels = []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.resultat


async def test_les_deploiements_sont_lus_et_listes(monkeypatch):
    lus = [{"state": "error", "created_at": "2026-09-29T08:00:00Z", "branch": "main",
            "error_message": "Build script returned non-zero exit code: 2"},
           {"state": "ready", "created_at": "2026-09-28T10:00:00Z", "branch": "main"}]
    registre = Registre(succes("deploiements", "netlify", "2 deploiement(s) lu(s), dont 1 en echec.",
                               preuve="netlify:GET:/sites/x/deploys", donnees=lus))
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = await module_chat._aiguiller(
        module_chat.ChatRequest(prompt="le dernier déploiement de mon site a marché ?"), "SITE_WEB")

    assert registre.appels == [("netlify", "deploiements", {})]
    assert reponse["status"] == "success"
    assert reponse["response"].startswith("2 deploiement(s) lu(s), dont 1 en echec.")
    assert "erreur : Build script returned non-zero exit code: 2" in reponse["response"]


async def test_republier_attend_la_confirmation_du_connecteur(monkeypatch):
    registre = Registre(a_confirmer(action="redeployer", cible="netlify",
                                    message="Pret. Rien n'est parti. Confirme avec l'identifiant a1."))
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = module_chat._mon_site("republie mon site")

    assert reponse["statut_connecteur"] == "NEEDS_CONFIRMATION"
    assert "Rien n'est parti" in reponse["response"]


async def test_sans_jeton_le_chat_dit_ce_qui_manque(monkeypatch):
    registre = Registre(non_configure(action="site_infos", cible="netlify",
                                      ce_qui_manque="un jeton Netlify"))
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = module_chat._mon_site("mon site est en ligne ?")

    assert reponse["status"] == "error"
    assert "un jeton Netlify" in reponse["response"]


# --- Le rendu --------------------------------------------------------------------

def test_un_message_de_visiteur_s_affiche_sans_son_adresse_ip():
    texte = rendre("soumissions", "1 message(s) de formulaire lu(s).", [
        {"form_name": "devis", "created_at": "2026-09-29",
         "data": {"name": "Fatou", "message": "Plafond 40 m2", "ip": "41.82.0.1"}}])

    assert "- devis, 2026-09-29 — name : Fatou; message : Plafond 40 m2" in texte
    assert "41.82.0.1" not in texte


def test_un_champ_absent_s_affiche_inconnu_jamais_invente():
    texte = rendre("site_infos", "Site lu.", {"name": "unic"})

    assert "Adresse : ?" in texte and "Derniere publication : ?" in texte
