"""L'ecosysteme d'agents : decouverte, delegation, recursion, parallele (DEC-0145).

Aucun test ne suppose les noms des agents du projet : ceux qui portent sur le
vrai runtime lisent ce que la decouverte a trouve ; les autres construisent
leurs propres agents.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from core.agent import message as module_message
from core.agent.base_agent import BaseAgent
from core.agent.capacites import RegistreCapacites
from core.agent.decouverte import decouvrir, identifiant_de


class _Modele:
    def __init__(self, *reponses):
        self.reponses = list(reponses)

    async def generate(self, prompt, system_prompt=None, **options):
        return self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]


class _Agent(BaseAgent):
    """Un agent de test : repond par son nom, ou delegue a `suivant`."""

    def __init__(self, nom, description="", competences=(), suivant=None, delai=0.0):
        super().__init__(nom, description, _Modele("ok"))
        self.competences = competences
        self.suivant = suivant
        self.delai = delai
        self.recus = []

    async def run(self, user_input, context=None):
        self.recus.append((user_input, dict(context or {})))
        if self.delai:
            await asyncio.sleep(self.delai)
        if self.suivant:
            sous = await self.demander_specialiste(self.suivant, f"{user_input} > {self.name}")
            return {"status": sous.get("status", "success"), "agent": self.name,
                    "response": f"{self.name}[{sous.get('response')}]"}
        return {"status": "success", "agent": self.name, "response": self.name}


def _equipe(*agents):
    registre = RegistreCapacites()
    for agent in agents:
        registre.enregistrer_agent(agent)
    return registre


# --- Decouverte (tests G et J) -------------------------------------------------

def test_le_vrai_runtime_decouvre_tous_ses_agents_sans_liste():
    """Test J (partie structure) : tout agent construit par le runtime est
    inscrit et relie au registre — compte mesure, jamais ecrit ici."""
    from apps.backend import runtime

    construits = [v for v in vars(runtime).values() if isinstance(v, BaseAgent)]
    assert construits, "le runtime ne construit aucun agent ?"
    for agent in construits:
        cle = runtime.collaborateurs.cle_de(agent)
        assert cle is not None, f"{type(agent).__name__} n'est pas dans l'ecosysteme"
        assert agent.collaborateurs is runtime.collaborateurs
    assert sorted(runtime.agents_decouverts) == sorted(runtime.collaborateurs.espaces())
    assert "_equipe" not in vars(runtime), "la liste manuelle ne doit plus exister"


def test_un_nouvel_agent_est_decouvert_automatiquement():
    """Test G : un agent ajoute a l'espace de composition, sans rien declarer
    ni toucher au registre, est trouve, inscrit et joignable."""
    ancien = _Agent("AncienAgent", "fait autre chose")

    class TraducteurWolofAgent(BaseAgent):
        async def run(self, user_input, context=None):
            return {"status": "success", "agent": self.name, "response": "Nanga def"}

    nouveau = TraducteurWolofAgent("TraducteurWolofAgent",
                                   "traduit du francais vers le wolof", _Modele("ok"))
    registre = RegistreCapacites()

    inscrits = registre.peupler({"ancien": ancien, "demain": nouveau, "autre": 42})

    assert identifiant_de(nouveau) == "traducteur_wolof"
    assert "traducteur_wolof" in inscrits
    assert nouveau.collaborateurs is registre
    assert [f.id for f in registre.rechercher("traduire en wolof")] == ["traducteur_wolof"]


def test_un_objet_sans_run_ou_sans_identifiant_n_est_pas_un_agent():
    class Outil:
        async def run(self, user_input, context=None):
            return {}

    assert decouvrir({"a": Outil(), "b": "texte", "c": _Agent("VraiAgent")}) != []
    assert len(decouvrir({"a": Outil(), "b": "texte"})) == 0


def test_la_fiche_est_lue_sur_l_agent():
    agent = _Agent("PlanificateurAgent", "planifie des chantiers", competences=("planning",))
    registre = _equipe(agent)

    fiche = registre.fiche("planificateur")

    assert fiche.name == "PlanificateurAgent"
    assert fiche.capabilities == ("planning",)
    assert fiche.metadata["peut_consulter"] is True
    assert fiche.interface.startswith("run(")


# --- Test A : decouvrir un agent inconnu, par competence ----------------------

async def test_un_agent_trouve_un_collegue_dont_il_ignorait_l_existence():
    demandeur = _Agent("DemandeurAgent", "redige des textes")
    expert = _Agent("CadastreAgent", "consulte le cadastre et les titres fonciers",
                    competences=("cadastre", "titre foncier"))
    _equipe(demandeur, expert)

    resultat = await demandeur.demander_competence("verifier un titre foncier", "parcelle 12")

    assert resultat["specialiste"] == "cadastre"
    assert resultat["response"] == "CadastreAgent"


async def test_sans_agent_competent_la_demande_le_dit():
    demandeur = _Agent("DemandeurAgent", "redige des textes")
    _equipe(demandeur)

    resultat = await demandeur.demander_competence("pilotage de drone", "decolle")

    assert resultat["status"] == "error"
    assert "Aucun agent competent" in resultat["response"]


# --- Test B / C : delegation et recursion ---------------------------------------

async def test_une_delegation_porte_un_message_et_une_tache():
    a, b = _Agent("AAgent"), _Agent("BAgent")
    _equipe(a, b)

    resultat = await a.demander_specialiste("b", "fais ceci")

    assert resultat["response"] == "BAgent"
    _texte, ctx = b.recus[0]
    assert ctx["message"]["sender"] == "a" and ctx["message"]["recipient"] == "b"
    assert ctx["depth"] == 1 and ctx["parent_task_id"] is None
    assert ctx["root_task_id"] == ctx["task_id"]


async def test_un_delegue_peut_appeler_un_troisieme_puis_un_quatrieme():
    """Test C : A -> B -> C -> D, et le resultat remonte jusqu'a A."""
    a = _Agent("AAgent", suivant="b")
    b = _Agent("BAgent", suivant="c")
    c = _Agent("CAgent", suivant="d")
    d = _Agent("DAgent")
    _equipe(a, b, c, d)

    resultat = await a.run("tache")

    assert resultat["response"] == "AAgent[BAgent[CAgent[DAgent]]]"
    profondeurs = [agent.recus[0][1]["depth"] for agent in (b, c, d)]
    assert profondeurs == [1, 2, 3]
    racines = {agent.recus[0][1]["root_task_id"] for agent in (b, c, d)}
    assert len(racines) == 1, "toute la chaine appartient a une seule tache racine"


# --- Test H : boucles, profondeur, budget ---------------------------------------

async def test_une_boucle_a_b_a_est_arretee():
    a = _Agent("AAgent", suivant="b")
    b = _Agent("BAgent", suivant="a")
    _equipe(a, b)

    resultat = await a.run("tache")

    assert len(a.recus) == 1, "A ne doit jamais etre rappele"
    assert "boucle" in resultat["response"]


async def test_la_profondeur_maximale_est_configurable(monkeypatch):
    monkeypatch.setattr(module_message, "PROFONDEUR_MAX", 2)
    agents = [_Agent(f"N{i}Agent", suivant=f"n{i + 1}") for i in range(4)] + [_Agent("N4Agent")]
    _equipe(*agents)

    resultat = await agents[0].run("tache")

    assert agents[3].recus == [], "la profondeur 3 ne doit pas etre atteinte"
    assert "profondeur maximale" in resultat["response"]


async def test_le_budget_d_une_demande_empeche_l_explosion(monkeypatch):
    monkeypatch.setattr(module_message, "TACHES_MAX_PAR_RACINE", 3)
    lead = _Agent("LeadAgent")
    ouvriers = [_Agent(f"O{i}Agent") for i in range(5)]
    _equipe(lead, *ouvriers)

    resultats = await lead.deleguer_en_parallele(
        [{"destinataire": f"o{i}", "requete": "x"} for i in range(5)])

    acceptes = [r for r in resultats if r.get("status") != "error"]
    refuses = [r for r in resultats if "budget" in str(r.get("response"))]
    assert acceptes and refuses, "au-dela du budget, les sous-taches sont refusees"


# --- Test D : parallele --------------------------------------------------------

async def test_plusieurs_agents_travaillent_en_parallele():
    lead = _Agent("LeadAgent")
    domaines = ("cadastre", "hydraulique", "electricite")
    ouvriers = [_Agent(f"P{i}Agent", competences=(domaine,), delai=0.3)
                for i, domaine in enumerate(domaines)]
    _equipe(lead, *ouvriers)

    debut = time.perf_counter()
    resultats = await lead.deleguer_en_parallele(
        [{"besoin": domaine, "requete": f"partie {i}"} for i, domaine in enumerate(domaines)])
    duree = time.perf_counter() - debut

    assert [r["response"] for r in resultats] == ["P0Agent", "P1Agent", "P2Agent"]
    assert duree < 0.8, f"3 x 0.3 s en sequence donnerait 0.9 s ; mesure {duree:.2f} s"


# --- Le modele d'un agent peut demander une COMPETENCE ------------------------

async def test_le_modele_peut_demander_une_competence_sans_nommer_l_agent():
    class _Redacteur(BaseAgent):
        async def run(self, user_input, context=None):
            return {"response": await self.rediger(prompt=user_input)}

    redacteur = _Redacteur("RedacteurAgent", "redige",
                           _Modele("[[COMPETENCE:titre foncier|la parcelle 12 est-elle libre ?]]",
                                   "Oui, la parcelle est libre."))
    expert = _Agent("CadastreAgent", "consulte le cadastre", competences=("titre foncier",))
    _equipe(redacteur, expert)

    reponse = await redacteur.rediger(prompt="redige l'offre pour la parcelle 12")

    assert expert.recus and expert.recus[0][0].startswith("la parcelle 12")
    assert reponse == "Oui, la parcelle est libre."


@pytest.mark.parametrize("identifiant", ["code", "plaquiste", "atelier", "documents"])
def test_les_identifiants_historiques_restent_joignables(identifiant):
    """Test J : les cles que les plans et les modeles utilisent deja ne changent pas."""
    from apps.backend import runtime

    assert runtime.collaborateurs.connait(identifiant)
