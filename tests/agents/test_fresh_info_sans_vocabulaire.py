"""FRESH_INFO ne reconnait plus une question de suivi a du vocabulaire.

DEC-0191. `TERMES_SUIVI_GENERIQUES` listait « buteur », « score »,
« vainqueur », « match » : du football. Elle reparait le football et laissait
tomber la finance, l'edition, le chantier, la cuisine — il aurait fallu un
mot de plus par domaine, sans fin.

Ce qui la remplace n'appartient a aucun metier : le fil entier part au
modele, et le filet deterministe ne regarde plus que **l'orthographe** (ce
que la phrase NOMME) et le travail du modele.
"""
import ast
import inspect
import pathlib

import pytest

from agents.fresh_info import fresh_info_agent as module
from agents.fresh_info.fresh_info_agent import FreshInfoAgent

#: Les fonctions qui decident du contexte d'une question. Aucune ne doit
#: dependre d'un lexique metier.
CHEMIN_DU_CONTEXTE = (
    "_entites_nommees", "_question_du_tour", "_dernier_message_avec_ancre",
    "_requete_de_suivi", "_indices_evenement_assistant",
)


@pytest.mark.parametrize("liste", [
    "TERMES_SUIVI_GENERIQUES", "MOTS_HINT_ASSISTANT",
    "TERMES_DETAIL_EVENEMENT", "MOTS_LIAISON_EVENEMENT",
])
def test_les_listes_de_mots_de_domaine_ont_disparu(liste):
    assert not hasattr(module, liste), (
        f"{liste} est revenue : une liste de mots ne couvrira jamais tous "
        "les domaines (DEC-0191)")


def test_aucun_lexique_ne_sert_plus_a_decider_du_contexte():
    """Verifie par lecture du code, pas par intention : si une de ces
    fonctions se remet a lire un ensemble de mots du module, ce test tombe."""
    source = pathlib.Path(inspect.getfile(module)).read_text("utf-8")
    arbre = ast.parse(source)
    lexiques = {
        noeud.targets[0].id
        for noeud in arbre.body
        if isinstance(noeud, ast.Assign)
        and isinstance(noeud.targets[0], ast.Name)
        and isinstance(noeud.value, ast.Call)
        and getattr(noeud.value.func, "id", "") == "frozenset"
    }
    assert lexiques, "l'analyse du module n'a trouve aucun ensemble de mots"

    for classe in arbre.body:
        if not isinstance(classe, ast.ClassDef):
            continue
        for fonction in classe.body:
            if getattr(fonction, "name", "") not in CHEMIN_DU_CONTEXTE:
                continue
            noms = {n.id for n in ast.walk(fonction) if isinstance(n, ast.Name)}
            assert not (noms & lexiques), (
                f"{fonction.name} decide du contexte avec "
                f"{sorted(noms & lexiques)} : c'est la methode abandonnee")


# --- Ce que la phrase NOMME, domaine par domaine ---------------------------

@pytest.mark.parametrize("phrase", [
    "donne-moi un nom",                       # football
    "donne-moi un chiffre",                   # monnaie
    "un titre",                               # edition
    "combien",                                # chantier
    "et pour six personnes ?",                # cuisine
    "Celle de 2006 ?",                        # pronom + annee
    "quel est le prochain ?",
])
def test_une_demande_qui_ne_nomme_rien_est_reconnue_sans_lexique(phrase):
    assert FreshInfoAgent._entites_nommees(phrase) == []


@pytest.mark.parametrize("phrase, nomme", [
    ("Qui a gagné entre Angleterre et Espagne ?", ["angleterre", "espagne"]),
    ("Que vaut le Bitcoin aujourd'hui ?", ["bitcoin"]),
    ("Parle-moi de Mariama Bâ.", ["mariama", "bâ"]),
    ("Le chantier de Médina avance ?", ["médina"]),
    ("Qui sont les Beatles ?", ["beatles"]),
    ("Dernier match du FC Barcelone", ["fc", "barcelone"]),
])
def test_une_demande_qui_nomme_son_sujet_est_reconnue_aussi(phrase, nomme):
    assert FreshInfoAgent._entites_nommees(phrase) == nomme


def test_une_majuscule_de_debut_de_phrase_ne_nomme_personne():
    """« Maintenant, ... ? Vérifie sur le web. » ne nomme ni Maintenant ni
    Vérifie : c'est la ponctuation qui met ces majuscules."""
    phrase = ("Maintenant, quel a été le dernier match du FC Barcelone ? "
              "Vérifie sur le web.")

    assert FreshInfoAgent._entites_nommees(phrase) == ["fc", "barcelone"]


# --- Le filet deterministe, hors du football -------------------------------

class _ModeleQuiPerdLeSujet:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        return "donne-moi un chiffre"


async def test_le_filet_rattache_une_demande_monetaire_sans_connaitre_la_finance():
    """Le modele rend la question inchangee — il a perdu le sujet. Le filet
    la rattache a ce que le tour precedent NOMMAIT, sans savoir ce qu'est
    une monnaie."""
    agent = FreshInfoAgent(provider=_ModeleQuiPerdLeSujet())
    historique = [
        {"role": "user", "content": "Que vaut le Bitcoin en ce moment ?"},
        {"role": "assistant", "content": "Autour de 61 000 dollars."},
    ]

    question, ancres = await agent._question_du_tour("donne-moi un chiffre",
                                                     historique)

    assert "Bitcoin" in question
    assert question.endswith("donne-moi un chiffre")
    assert ancres == ["bitcoin"]


class _ModeleQuiNommeAutreChose:
    async def generate(self, prompt, **kw):
        return "Quel temps fait-il à Dakar aujourd'hui ?"


async def test_un_nouveau_sujet_nomme_par_le_modele_n_est_pas_rattache_au_fil():
    """Le modele a lu tout le fil et a nomme autre chose : c'est une nouvelle
    question, le fil ne doit pas la recouvrir."""
    agent = FreshInfoAgent(provider=_ModeleQuiNommeAutreChose())
    historique = [
        {"role": "user", "content": "Que vaut le Bitcoin en ce moment ?"},
        {"role": "assistant", "content": "Autour de 61 000 dollars."},
    ]

    question, ancres = await agent._question_du_tour("et dehors ?", historique)

    assert question == "Quel temps fait-il à Dakar aujourd'hui ?"
    assert ancres == []


async def test_le_fil_entier_part_au_modele_avant_tout_filet():
    agent = FreshInfoAgent(provider=_ModeleQuiPerdLeSujet())
    historique = [
        {"role": "user", "content": "Que vaut le Bitcoin en ce moment ?"},
        {"role": "assistant", "content": "Autour de 61 000 dollars."},
    ]

    await agent._question_du_tour("donne-moi un chiffre", historique)

    invite = agent.provider.prompts[0]
    assert "Bitcoin" in invite and "61 000 dollars" in invite
