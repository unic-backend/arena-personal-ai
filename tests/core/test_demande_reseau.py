"""« Mon Internet est lent, vérifie » (DEC-0203) : la phrase atteint la santé
réseau de DEC-0202 — aucun agent, aucun modèle, et le test de débit coûteux
ne part JAMAIS sans confirmation.

Tout est hors ligne : le registre est factice, la santé est construite —
aucune mesure réelle n'est revendiquée ici (mocked, jamais « real
measurement »).
"""
import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend.routers import chat as module_chat
from core.actions.resultat import a_confirmer, non_configure, succes
from core.reseau.demande import capacite_reseau, rendre_sante
from core.reseau.sante_reseau import SanteReseau, StatutReseau

# --- La phrase ------------------------------------------------------------------


@pytest.mark.parametrize("phrase, capacite", [
    ("Mon Internet est lent, vérifie.", "etat"),
    ("diagnostique ma connexion", "etat"),
    ("le wifi coupe tout le temps", "etat"),
    ("est-ce que le réseau marche ?", "etat"),
    ("ma connexion est instable depuis ce matin", "etat"),
    ("quel est l'état de ma connexion ?", "etat"),
    ("lance un test de débit", "mesurer_debit"),
    ("fais un speedtest", "mesurer_debit"),
    ("mesure mon débit", "mesurer_debit"),
    ("ma connexion est rapide ?", "mesurer_debit"),
    ("teste la vitesse de ma connexion", "mesurer_debit"),
])
def test_la_phrase_donne_la_capacite(phrase, capacite):
    assert capacite_reseau(phrase) == capacite


@pytest.mark.parametrize("phrase", [
    "publie ma vidéo sur mes réseaux",              # ses réseaux SOCIAUX
    "vérifie ma connexion TikTok",                  # un compte, pas sa ligne
    "connecte-toi à mon compte Instagram",
    "c'est quoi Internet ?",                        # une conversation
    "le réseau électrique du chantier est en panne",
    "la page de connexion de mon site marche pas",  # son site, pas sa ligne
    "mon site est en ligne ?",
    "vérifie mes réseaux sociaux",
    "génère une interface de connexion",            # UI, pas un diagnostic
])
def test_ces_phrases_ne_sont_pas_pour_le_reseau(phrase):
    assert capacite_reseau(phrase) is None


# --- L'orchestrateur --------------------------------------------------------------


async def test_l_orchestrateur_l_envoie_au_reseau_avant_le_controle_date(provider_factory):
    orchestrateur = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    # « vérifie » partirait sinon en recherche web (exige_verification), et
    # « aujourd'hui » sur le contrôle date : le web ne sait rien de sa ligne.
    assert await orchestrateur.analyze_intent("mon internet est lent, vérifie") == "RESEAU"
    assert await orchestrateur.analyze_intent("lance un test de débit aujourd'hui") == "RESEAU"


async def test_ses_reseaux_sociaux_ne_partent_pas_au_diagnostic(provider_factory):
    orchestrateur = OrchestratorAgent(provider=provider_factory("SOCIAL"), memory=None)

    assert await orchestrateur.analyze_intent("publie ma vidéo sur mes réseaux TikTok") != "RESEAU"


# --- Le chat ----------------------------------------------------------------------


class Registre:
    def __init__(self, resultat):
        self.resultat = resultat
        self.appels = []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.resultat


MESURE_NETRONOME = succes(
    "etat", "netronome", "Sante reseau lue depuis Netronome.",
    preuve="GET http://127.0.0.1:7575/api/speedtest/history",
    donnees={"download": 82.4, "upload": 23.1, "latency": 14.2, "jitter": None,
             "packet_loss": 0.0, "provider": "speedtest", "server": "Dakar",
             "timestamp": "2026-09-30T10:00:00Z"},
    mesure_disponible=True)


async def test_le_diagnostic_lit_l_etat_et_ne_lance_jamais_de_test(monkeypatch):
    registre = Registre(MESURE_NETRONOME)
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = await module_chat._aiguiller(
        module_chat.ChatRequest(prompt="mon internet est lent, vérifie"), "RESEAU")

    # Une seule capacité appelée : la lecture. Jamais le test coûteux.
    assert registre.appels == [("netronome", "etat", {})]
    assert ("netronome", "mesurer_debit", {}) not in registre.appels
    assert reponse["status"] == "success"
    assert "82.4 Mbps" in reponse["response"]
    assert "14.2 ms" in reponse["response"]
    # La mesure vient de Netronome, et la réponse le dit.
    assert reponse["reseau"]["source"] == "netronome"
    # La gigue n'a pas été mesurée : elle est déclarée absente, pas à zéro.
    assert "gigue" in reponse["response"].lower()
    assert reponse["reseau"]["mesures"]["jitter"] is None


async def test_sans_netronome_le_chat_rend_la_sonde_native_sans_inventer(monkeypatch):
    registre = Registre(non_configure(action="etat", cible="netronome",
                                      ce_qui_manque="Netronome lance sur la machine"))
    monkeypatch.setattr(module_chat, "registre", registre)
    native = SanteReseau(
        statut=StatutReseau.OPERATIONNEL, source="natif",
        mesures={"network_status": "up", "latency": 22.5, "download": None,
                 "upload": None, "jitter": None, "packet_loss": None,
                 "dns_latency": 4.1, "dns_status": "ok", "route_information": None,
                 "provider": "native", "server": None, "timestamp": None},
        message="Reseau joignable (sonde native ARENA).")
    monkeypatch.setattr(module_chat, "evaluer_sante_reseau", lambda _registre: native)

    reponse = module_chat._mon_reseau("diagnostique ma connexion")

    assert reponse["status"] == "success"
    # Le débit n'est PAS mesurable nativement : déclaré non mesuré, jamais 0.
    assert "non mesuré" in reponse["response"].lower()
    assert "0 Mbps" not in reponse["response"]
    assert reponse["reseau"]["mesures"]["download"] is None
    # Et la réponse dit comment obtenir une vraie mesure.
    assert "test de débit" in reponse["response"]


async def test_le_test_de_debit_attend_la_confirmation_du_proprietaire(monkeypatch):
    registre = Registre(a_confirmer(
        action="mesurer_debit", cible="netronome",
        message="Pret. Rien n'est parti. Confirme avec l'identifiant b7."))
    monkeypatch.setattr(module_chat, "registre", registre)

    reponse = module_chat._mon_reseau("lance un test de débit")

    assert registre.appels == [("netronome", "mesurer_debit", {})]
    assert reponse["statut_connecteur"] == "NEEDS_CONFIRMATION"
    assert "Rien n'est parti" in reponse["response"]


async def test_le_test_de_debit_sans_netronome_le_dit_et_donne_le_natif(monkeypatch):
    registre = Registre(non_configure(action="mesurer_debit", cible="netronome",
                                      ce_qui_manque="Netronome lance sur la machine"))
    monkeypatch.setattr(module_chat, "registre", registre)
    native = SanteReseau(
        statut=StatutReseau.OPERATIONNEL, source="natif",
        mesures={"latency": 30.0, "download": None, "upload": None,
                 "dns_status": "ok", "dns_latency": 5.0},
        message="Reseau joignable (sonde native ARENA).")
    monkeypatch.setattr(module_chat, "evaluer_sante_reseau", lambda _registre: native)

    reponse = module_chat._mon_reseau("fais un speedtest")

    assert reponse["status"] == "error"                     # rien n'a été mesuré en débit
    assert "Netronome lance sur la machine" in reponse["response"]
    assert "30.0 ms" in reponse["response"]                 # ce qui est su reste dit
    assert "Mbps" not in reponse["response"].replace("non mesuré", "")


# --- Le rendu ---------------------------------------------------------------------


def test_le_rendu_separe_le_mesure_du_non_mesure():
    sante = SanteReseau(
        statut=StatutReseau.PARTIEL, source="natif",
        mesures={"latency": 18.7, "download": None, "upload": None,
                 "jitter": None, "packet_loss": None, "dns_latency": 3.2,
                 "dns_status": "ok"},
        message="Reseau partiellement joignable (sonde native ARENA).")

    texte = rendre_sante(sante)

    assert "Latence : 18.7 ms" in texte
    assert "Latence DNS : 3.2 ms" in texte
    assert "Non mesuré : débit descendant, débit montant, gigue, perte de paquets." in texte
    # Aucun jugement à la place d'une mesure : le texte rapporte, il ne conclut pas.
    for jugement in ("mauvais", "bonne connexion", "excellent"):
        assert jugement not in texte.lower()
    assert "0 Mbps" not in texte


def test_le_rendu_d_une_mesure_complete_nomme_sa_source_et_son_serveur():
    sante = SanteReseau(
        statut=StatutReseau.OPERATIONNEL, source="netronome",
        mesures={"download": 82.4, "upload": 23.1, "latency": 14.2,
                 "jitter": 1.3, "packet_loss": 0.0, "dns_latency": None,
                 "dns_status": None, "provider": "speedtest",
                 "server": "Dakar", "timestamp": "2026-09-30T10:00:00Z"},
        message="Sante reseau lue depuis Netronome.")

    texte = rendre_sante(sante)

    assert "Débit descendant : 82.4 Mbps" in texte
    assert "Débit montant : 23.1 Mbps" in texte
    assert "Perte de paquets : 0.0 %" in texte              # un vrai zéro mesuré s'affiche
    assert "Netronome" in texte
    assert "Serveur de test : Dakar" in texte
    assert "Fournisseur de la mesure : speedtest" in texte
    assert "Non mesuré : latence dns." in texte


def test_l_adaptateur_porte_le_serveur_de_test_jusqu_au_schema():
    from core.reseau.sante_reseau import _mesures_depuis_netronome, _schema_vide

    assert "server" in _schema_vide()
    mesures = _mesures_depuis_netronome({"download": 10.0, "server": "Dakar"})
    assert mesures["server"] == "Dakar"
