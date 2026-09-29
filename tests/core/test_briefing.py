"""Le briefing du matin de JARVIS (DEC-0166).

Deux regles, et ce fichier tient les deux : chaque rubrique dit son etat
(jamais un agenda non branche lu « journee libre »), et une rubrique lente ou
en panne ne retient pas les autres.
"""
import asyncio
from datetime import date, datetime, time

import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from core.actions.resultat import echec, non_configure, succes
from core.briefing.briefing import (
    INCONNU,
    INDISPONIBLE,
    NON_CONFIGURE,
    OK,
    Rubrique,
    composer_briefing,
    jour_en_toutes_lettres,
    rubrique_agenda,
    rubrique_d_agent,
)

MAINTENANT = datetime(2026, 9, 29, 7, 0)


# --- Les rubriques ----------------------------------------------------------------

def test_un_agenda_non_branche_n_est_jamais_une_journee_libre():
    rubrique = rubrique_agenda(non_configure("lire", "calendrier", "les identifiants Google"))

    assert rubrique.etat == NON_CONFIGURE
    assert "Aucun rendez-vous" not in rubrique.texte


def test_un_agenda_lu_et_vide_est_une_journee_libre():
    rubrique = rubrique_agenda(succes("lire", "calendrier", "0 rendez-vous", "GET", donnees=[]))

    assert rubrique.etat == OK
    assert rubrique.texte == "Aucun rendez-vous aujourd'hui."


def test_les_rendez_vous_sont_listes_avec_leurs_heures():
    rubrique = rubrique_agenda(succes(
        "lire", "calendrier", "1 rendez-vous", "GET",
        donnees=[{"debut": "2026-09-29T09:00+00:00", "fin": "2026-09-29T10:30+00:00",
                  "titre": "Chantier Almadies"}],
        illisibles=1))

    assert "09:00–10:30 Chantier Almadies" in rubrique.texte
    assert "1 rendez-vous illisible" in rubrique.texte


def test_un_agenda_en_echec_le_dit():
    rubrique = rubrique_agenda(echec("lire", "calendrier", "Google a repondu 500."))

    assert (rubrique.etat, rubrique.texte) == (INDISPONIBLE, "Google a repondu 500.")


def test_la_reponse_d_un_agent_est_gardee_telle_quelle():
    reponse = {"status": "success", "response": "Soleil, 31 °C [1].\n\n---\n**Verification automatique** : ..."}

    rubrique = rubrique_d_agent("Meteo", reponse)

    assert rubrique.etat == OK
    assert "Verification automatique" in rubrique.texte, "l'avertissement de l'agent n'est jamais retire"


def test_un_agent_qui_ne_trouve_rien_rend_une_rubrique_indisponible():
    rubrique = rubrique_d_agent("Actualites", {"status": "warning", "response": "Aucune source."})

    assert (rubrique.etat, rubrique.texte) == (INDISPONIBLE, "Aucune source.")


# --- L'assemblage -----------------------------------------------------------------

async def test_une_rubrique_lente_ne_retient_pas_les_autres():
    async def rapide():
        return Rubrique("Agenda", OK, "Aucun rendez-vous aujourd'hui.")

    async def muette():
        await asyncio.sleep(10)
        return Rubrique("Meteo", OK, "jamais")

    briefing = await composer_briefing({"Agenda": rapide, "Meteo": muette}, MAINTENANT, delai=0.05)

    assert [r.etat for r in briefing.rubriques] == [OK, INDISPONIBLE]
    assert "Pas de reponse" in briefing.rubriques[1].texte


async def test_une_rubrique_en_panne_n_emporte_pas_le_briefing():
    async def panne():
        raise RuntimeError("Ollama ne repond pas")

    async def courrier():
        return Rubrique("Courrier", OK, "2 messages.")

    briefing = await composer_briefing({"Actualites": panne, "Courrier": courrier}, MAINTENANT)

    assert briefing.rubriques[0].etat == INDISPONIBLE
    assert "Ollama ne repond pas" in briefing.rubriques[0].texte
    assert briefing.rubriques[1].texte == "2 messages."


async def test_le_texte_montre_l_etat_de_chaque_rubrique():
    async def agenda():
        return Rubrique("Agenda", NON_CONFIGURE, "Non configure : calendrier n'est pas connecte.")

    async def meteo():
        return Rubrique("Meteo", INCONNU, "Ville inconnue.")

    texte = (await composer_briefing({"Agenda": agenda, "Meteo": meteo}, MAINTENANT)).en_texte()

    assert texte.startswith("**Briefing du mardi 29 septembre**")
    assert "**Agenda** _(non configure)_" in texte
    assert "**Meteo** _(information manquante)_" in texte


def test_la_date_s_ecrit_sans_dependre_de_la_locale_du_pc():
    assert jour_en_toutes_lettres(date(2026, 9, 28)) == "lundi 28 septembre"


# --- Le routage -------------------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "Jarvis, mon briefing", "briefing", "Briefing !", "le briefing du jour",
    "donne-moi mon point du matin", "Résumé du matin",
])
def test_ces_phrases_demandent_le_briefing(phrase):
    assert OrchestratorAgent.demande_de_briefing(phrase) is True


@pytest.mark.parametrize("phrase", [
    "prépare un briefing pour mon équipe de chantier",
    "quelles sont les actualités du jour",
    "c'est quoi un brief créatif",
])
def test_ces_phrases_ne_le_demandent_pas(phrase):
    assert OrchestratorAgent.demande_de_briefing(phrase) is False


async def test_le_briefing_passe_avant_le_controle_date(provider_factory):
    """« mon briefing du jour » contient « du jour » : sans ce controle en
    premier, il partait en recherche web d'actualite."""
    orchestrateur = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    assert await orchestrateur.analyze_intent("mon briefing du jour") == "BRIEFING"


# --- La route et la planification --------------------------------------------------

async def test_la_route_compose_avec_les_capacites_branchees(monkeypatch):
    from apps.backend.routers import briefing as route

    class Registre:
        def executer(self, connecteur, capacite, **parametres):
            assert (connecteur, capacite) == ("calendrier", "lire")
            return non_configure("lire", "calendrier", "les identifiants Google")

    class Agent:
        def __init__(self, texte):
            self.texte, self.questions = texte, []

        async def run(self, question, context=None):
            self.questions.append(question)
            return {"status": "success", "response": self.texte}

    web = Agent("Soleil [1].")
    monkeypatch.setattr(route, "registre", Registre())
    monkeypatch.setattr(route, "email_agent", Agent("Aucun message urgent."))
    monkeypatch.setattr(route, "fresh_agent", web)
    monkeypatch.setattr(route.memory, "get_fact", lambda cle: {"ville": "Dakar"}.get(cle))
    monkeypatch.setattr(route, "_dernier", None)

    reponse = await route.lire_briefing(forcer=True)

    etats = {r["titre"]: r["etat"] for r in reponse["rubriques"]}
    assert etats == {"Agenda": NON_CONFIGURE, "Courrier": OK, "Meteo": OK, "Actualites": OK}
    assert "Quel temps fait-il à Dakar aujourd'hui ?" in web.questions


async def test_sans_ville_la_meteo_dit_ce_qui_manque(monkeypatch):
    from apps.backend.routers import briefing as route

    monkeypatch.setattr(route.memory, "get_fact", lambda cle: None)

    rubrique = await route._sources()["Meteo"]()

    assert rubrique.etat == INCONNU
    assert "ville" in rubrique.texte.lower()


async def test_un_briefing_recent_est_rendu_sans_recomposer(monkeypatch):
    from apps.backend.routers import briefing as route

    appels = []

    async def composer(sources, maintenant, delai=0):
        appels.append(maintenant)
        return route.Briefing(jour=maintenant.date(), compose_a=maintenant)

    monkeypatch.setattr(route, "composer_briefing", composer)
    monkeypatch.setattr(route, "_dernier", None)

    await route.briefing_du_jour()
    await route.briefing_du_jour()

    assert len(appels) == 1


@pytest.mark.parametrize("valeur, attendu", [
    ("07:00", time(7, 0)), ("6:30", time(6, 30)), ("off", None), ("", None), ("sept heures", None),
])
def test_l_heure_du_briefing_se_lit_ou_se_coupe(monkeypatch, valeur, attendu):
    from apps.backend.routers import briefing as route

    monkeypatch.setenv("BRIEFING_HEURE", valeur)

    assert route.heure_du_briefing() == attendu


def test_le_prochain_briefing_est_demain_si_l_heure_est_passee():
    from apps.backend.routers.briefing import secondes_avant

    assert secondes_avant(time(7, 0), datetime(2026, 9, 29, 6, 0)) == 3600
    assert secondes_avant(time(7, 0), datetime(2026, 9, 29, 8, 0)) == 23 * 3600
