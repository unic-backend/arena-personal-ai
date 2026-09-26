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
