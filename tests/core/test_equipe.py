"""Plusieurs agents sur UNE demande qui en nomme plusieurs (DEC-0143).

Mesure du 26/09/2026 : « fais un devis … et envoie-le par mail » partait au
seul Plaquiste, « cherche la derniere version de FastAPI puis ecris un
script » au seul agent d'actualite — chacun ne faisait que sa part.
"""
from __future__ import annotations

import pytest

from core.agent import equipe
from core.agent.equipe import Etape, decouper, executer, planifier


@pytest.fixture(autouse=True)
def plans_vierges():
    equipe.oublier_les_plans()
    yield
    equipe.oublier_les_plans()


@pytest.mark.parametrize("phrase, morceaux", [
    ("fais un devis de 30 m2 et envoie-le par mail à khady@exemple.com",
     ["fais un devis de 30 m2", "envoie-le par mail à khady@exemple.com"]),
    ("cherche la dernière version de FastAPI puis écris-moi un script",
     ["cherche la dernière version de FastAPI", "écris-moi un script"]),
    ("analyse cette photo du chantier et fais-moi le devis",
     ["analyse cette photo du chantier", "fais-moi le devis"]),
    ("traduis ce texte, ensuite résume-le",
     ["traduis ce texte", "résume-le"]),
])
def test_un_enchainement_explicite_se_decoupe(phrase, morceaux):
    assert decouper(phrase) == morceaux


@pytest.mark.parametrize("phrase", [
    "devis pour une cloison et un plafond de 20 m2",
    "compare Python et Rust",
    "bonjour, ça va ?",
    "quelle est la dernière version de Python",
])
def test_une_demande_simple_reste_entiere(phrase):
    assert decouper(phrase) == [phrase.strip(" ,;.")]


# --- Enchainements anglais : connecteurs, jamais de liste de verbes ----------------

@pytest.mark.parametrize("phrase, morceaux", [
    ("analyze this plan and then make the quote",
     ["analyze this plan", "make the quote"]),
    ("measure this plan, then email it to khady@exemple.com",
     ["measure this plan", "email it to khady@exemple.com"]),
    ("summarize this PDF afterwards send it",
     ["summarize this PDF", "send it"]),
    ("translate the quote, after that, print it",
     ["translate the quote", "print it"]),
    ("check the stock, and after that update the site",
     ["check the stock", "update the site"]),
    ("read the plan, next, file it",
     ["read the plan", "file it"]),
])
def test_un_enchainement_anglais_explicite_se_decoupe(phrase, morceaux):
    """Mesure du 30/09/2026 : chacune de ces demandes arrivait au classifieur
    EN UNE SEULE PIECE — un seul agent, et la seconde partie perdue. Ce sont
    des connecteurs (« then », « afterwards »…), jamais des verbes : la
    coupure « and » + verbe exige une liste de verbes que ce module n'a pas."""
    assert decouper(phrase) == morceaux


@pytest.mark.parametrize("phrase", [
    "measure the doors and windows of the ground floor",   # « and » seul ne coupe jamais
    "after that wall comes the corridor",                  # connector SANS ponctuation = du plan
    "open the next door schedule",                         # « the next door » : une piece, pas une etape
    "strengthen the beam on the south elevation",          # « then » colle dans un mot
    "compare the steel and the timber options",            # une comparaison est UNE demande
])
def test_une_demande_anglaise_simple_reste_entiere(phrase):
    assert decouper(phrase) == [phrase.strip(" ,;.")]


def test_une_demande_anglaise_sans_connecteur_reste_entiere():
    """La limite choisie, figee pour ne pas etre oubliee : « and » suivi d'un
    verbe anglais ne coupe PAS. Le jour ou ce cas doit decouper, il faudra une
    detection grammaticale reelle, pas une liste de verbes ecrite a la main."""
    phrase = "analyze this plan and send it by email"
    assert decouper(phrase) == [phrase]


async def test_une_equipe_anglaise_est_planifiee():
    classer = _classeur({"analyze": "VISION", "make": "PLAQUISTE"})

    plan = await planifier("analyze this photo of the site and then make the quote", classer)

    assert [e.intention for e in plan] == ["VISION", "PLAQUISTE"]
    assert classer.appels == ["analyze this photo of the site", "make the quote"]


def _classeur(table):
    appels = []

    async def classer(morceau):
        appels.append(morceau)
        for debut, intention in table.items():
            if morceau.startswith(debut):
                return intention
        return "CHAT"
    classer.appels = appels
    return classer


async def test_deux_metiers_font_une_equipe():
    classer = _classeur({"fais un devis": "PLAQUISTE", "envoie-le": "EMAIL"})

    plan = await planifier("fais un devis de 30 m2 et envoie-le par mail à k@x.sn", classer)

    assert [e.intention for e in plan] == ["PLAQUISTE", "EMAIL"]


async def test_une_demande_simple_ne_coute_aucun_appel_au_classeur():
    classer = _classeur({})

    assert await planifier("fais un devis de 30 m2 de cloison", classer) == []
    assert classer.appels == []


async def test_un_morceau_en_conversation_annule_l_equipe():
    classer = _classeur({"fais un devis": "PLAQUISTE"})

    assert await planifier("fais un devis puis dis-moi merci", classer) == []


async def test_deux_morceaux_pour_le_meme_agent_ne_font_pas_une_equipe():
    classer = _classeur({"écris": "CODE_EXECUTION", "corrige": "CODE_EXECUTION"})

    assert await planifier("écris une fonction puis corrige-la", classer) == []


async def test_le_plan_n_est_calcule_qu_une_fois_par_phrase():
    classer = _classeur({"fais un devis": "PLAQUISTE", "envoie-le": "EMAIL"})
    phrase = "fais un devis et envoie-le par mail à k@x.sn"

    await planifier(phrase, classer)
    await planifier(phrase, classer)

    assert len(classer.appels) == 2, "chaque morceau classe une seule fois"


async def test_le_resultat_passe_a_l_etape_suivante_comme_donnee():
    vus = []

    async def aiguiller(texte, intention):
        vus.append((intention, texte))
        return {"status": "success", "agent": intention,
                "response": "DEVIS-42 : 30 m2 a 12 000 F" if intention == "PLAQUISTE" else "Mail pret."}

    rendu = await executer([Etape("fais le devis", "PLAQUISTE"),
                            Etape("envoie-le par mail", "EMAIL")], aiguiller)

    assert vus[0] == ("PLAQUISTE", "fais le devis")
    assert vus[1][0] == "EMAIL"
    assert "DEVIS-42" in vus[1][1], "l'agent courrier doit recevoir le devis"
    assert "envoie-le par mail" in vus[1][1]
    assert "DEVIS-42" in rendu["response"] and "Mail pret." in rendu["response"]
    assert [e["intention"] for e in rendu["equipe"]] == ["PLAQUISTE", "EMAIL"]
    assert rendu["intention"] == "EMAIL"


async def test_une_etape_ratee_arrete_l_equipe_et_le_dit():
    vus = []

    async def aiguiller(texte, intention):
        vus.append(intention)
        return {"status": "error", "agent": intention, "response": "Recherche en panne."}

    rendu = await executer([Etape("cherche", "FRESH_INFO"),
                            Etape("écris le script", "CODE_EXECUTION")], aiguiller)

    assert vus == ["FRESH_INFO"], "le code ne doit pas etre ecrit sur rien"
    assert "CODE_EXECUTION n'a pas ete lance" in rendu["response"]


async def test_le_document_d_une_etape_remonte():
    async def aiguiller(texte, intention):
        if intention == "PLAQUISTE":
            return {"response": "Devis pret.", "document": {"chemin": "/media/devis.pdf"}}
        return {"response": "Mail pret."}

    rendu = await executer([Etape("devis", "PLAQUISTE"), Etape("envoie", "EMAIL")], aiguiller)

    assert rendu["document"] == {"chemin": "/media/devis.pdf"}


# --- Au-dela de la chaine courte : un projet, jamais un abandon (DEC-0197) --------

@pytest.mark.parametrize("phrase, morceaux", [
    ("Lis ce PDF puis résume-le puis fais un tableur puis envoie-le par mail", 4),
    ("cherche le prix puis fais le devis puis imprime-le puis envoie-le puis range-le", 5),
    ("read the plan, then measure it, then make the quote, then email it", 4),
])
def test_un_enchainement_plus_long_que_la_chaine_courte_est_nomme(phrase, morceaux):
    """**Le defaut mesure le 30/09/2026.** `decouper` voyait les quatre etapes,
    `planifier` jetait le plan, et un seul agent repondait sans que rien ne le
    signale. Le cas doit d'abord etre NOMMABLE pour cesser d'etre silencieux."""
    assert len(decouper(phrase)) == morceaux
    assert equipe.depasse_la_chaine_courte(phrase) is True


@pytest.mark.parametrize("phrase", [
    "fais un devis de 30 m2 de cloison",
    "fais un devis et envoie-le par mail à k@x.sn",
    "cherche le prix puis fais le devis puis envoie-le par mail",
    "",
])
def test_une_demande_dans_les_clous_ne_depasse_pas(phrase):
    """Une, deux ou trois etapes restent la chaine courte : rien n'escalade."""
    assert equipe.depasse_la_chaine_courte(phrase) is False


async def test_au_dela_de_la_chaine_courte_aucun_morceau_n_est_classe():
    """L'escalade est deterministe : elle ne coute AUCUN appel au modele.

    Classer cinq morceaux pour decider d'un projet paierait cinq fois le prix
    d'une decision que le decoupage rend deja.
    """
    classer = _classeur({"cherche": "FRESH_INFO", "fais": "PLAQUISTE"})
    phrase = "cherche le prix puis fais le devis puis imprime-le puis envoie-le"

    assert await planifier(phrase, classer) == []
    assert classer.appels == []
