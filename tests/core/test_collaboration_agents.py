"""Table ronde, lead dynamique, projet decoupe, espace partage (DEC-0146).

Les agents sont construits ici : aucun test ne suppose les noms des agents du
projet. Ceux qui touchent le vrai runtime lisent ce que la decouverte a trouve.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from fastapi.testclient import TestClient

from core.agent.base_agent import BaseAgent
from core.agent.capacites import RegistreCapacites
from core.agent.collaboration import (
    choisir_lead,
    conduire_projet,
    decomposer,
    tenir_table_ronde,
)
from core.agent.espace_de_travail import ESPACES, EspacesDeTravail


class _Modele:
    """Un modele scripte : rend `reponses` dans l'ordre (la derniere se repete)."""

    def __init__(self, *reponses):
        self.reponses = list(reponses) or ["ok"]
        self.prompts = []

    async def generate(self, prompt, system_prompt=None, **options):
        self.prompts.append(prompt)
        return self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]


class _Specialiste(BaseAgent):
    """Repond par sa specialite ; peut demander une invitation une fois."""

    def __init__(self, nom, description, competences=(), invitation=None, delai=0.0,
                 modele=None):
        super().__init__(nom, description, modele or _Modele("synthese du lead"))
        self.competences = competences
        self.invitation = invitation
        self.delai = delai
        self.recus = []

    async def run(self, user_input, context=None):
        self.recus.append(user_input)
        if self.delai:
            await asyncio.sleep(self.delai)
        texte = f"analyse de {self.name}"
        if self.invitation and len(self.recus) == 1:
            texte += f"\n[[INVITER:{self.invitation}|il faut cet avis]]"
        return {"status": "success", "agent": self.name, "response": texte}


def _equipe(*agents):
    registre = RegistreCapacites()
    for agent in agents:
        registre.enregistrer_agent(agent)
    return registre


def _projet():
    return {
        "structure": _Specialiste("StructureAgent", "calcul de structure beton",
                                  competences=("structure", "beton", "calcul")),
        "cloisons": _Specialiste("CloisonAgent", "cloisons et plafonds en plaques",
                                 competences=("cloison", "plafond", "plaques")),
        "budget": _Specialiste("BudgetAgent", "chiffrage et budget de chantier",
                               competences=("budget", "chiffrage", "devis")),
        "jardin": _Specialiste("JardinAgent", "amenagement de jardins",
                               competences=("jardin", "plantes")),
        "juridique": _Specialiste("JuridiqueAgent", "droit de l urbanisme et permis",
                                  competences=("permis", "urbanisme", "juridique")),
    }


# --- Lead dynamique ---------------------------------------------------------

def test_le_lead_depend_de_la_tache():
    agents = _projet()
    registre = _equipe(*agents.values())

    assert choisir_lead(registre, "chiffrer le budget du chantier") is agents["budget"]
    assert choisir_lead(registre, "calcul de structure beton") is agents["structure"]


# --- Test E : participants choisis dynamiquement ----------------------------

async def test_la_table_ronde_choisit_ses_participants_selon_le_probleme():
    agents = _projet()
    registre = _equipe(*agents.values())

    table = await tenir_table_ronde(
        registre, "cloisons en plaques, plafond et budget du chantier", tours=1)

    invites_attendus = {"cloison", "budget"} - {table.lead}
    assert invites_attendus <= set(table.participants) | {table.lead}
    assert "jardin" not in table.participants, "un agent sans rapport n'est pas invite"
    assert agents["jardin"].recus == []
    assert table.synthese == "synthese du lead"


async def test_les_participants_parlent_en_parallele_et_voient_le_tour_precedent():
    agents = {n: _Specialiste(f"{n.title()}Agent", f"expert {n}", competences=(n, "maison"),
                              delai=0.3)
              for n in ("toiture", "fondation", "facade")}
    lead = _Specialiste("ChefAgent", "coordonne la maison", competences=("coordination",))
    registre = _equipe(lead, *agents.values())

    debut = time.perf_counter()
    table = await tenir_table_ronde(registre, "renover la maison", lead=lead, tours=2)
    assert set(table.participants) == {"toiture", "fondation", "facade"}
    duree = time.perf_counter() - debut

    assert duree < 1.2, f"2 tours de 3 x 0.3 s en sequence donneraient 1.8 s ; mesure {duree:.2f}"
    deuxieme = agents["toiture"].recus[1]
    assert "analyse de FacadeAgent" in deuxieme, "au 2e tour chacun voit ce que les autres ont dit"


# --- Test F : un participant fait inviter un agent supplementaire ------------

async def test_un_participant_fait_entrer_un_agent_qui_manquait():
    agents = _projet()
    agents["cloisons"].invitation = "permis de construire et urbanisme"
    registre = _equipe(*agents.values())

    table = await tenir_table_ronde(registre, "cloisons et plafond du garage", tours=2)

    assert any(i["agent"] == "juridique" and i["par"] == "cloison" for i in table.invites)
    assert "juridique" in table.participants
    assert agents["juridique"].recus, "l'invite doit prendre la parole au tour suivant"
    assert all("[[INVITER" not in i["texte"] for tour in table.tours for i in tour)


# --- Test I : un projet complexe decoupe et reparti --------------------------

async def test_un_projet_est_decoupe_et_confie_aux_agents_competents():
    agents = _projet()
    plan = json.dumps([
        {"objectif": "verifier la structure beton", "competence": "structure beton", "depend_de": []},
        {"objectif": "poser cloisons et plafond", "competence": "cloison plafond", "depend_de": [0]},
        {"objectif": "etablir le budget", "competence": "budget chiffrage", "depend_de": [0, 1]},
    ])
    lead = _Specialiste("ChefAgent", "coordonne les projets", competences=("coordination",),
                        modele=_Modele(plan, "livrable assemble"))
    registre = _equipe(lead, *agents.values())

    rendu = await conduire_projet(registre, "renover le garage", lead=lead)

    assert [t["agent"] for t in rendu["sous_taches"]] == ["structure", "cloison", "budget"]
    assert all(t["etat"] == "DONE" for t in rendu["sous_taches"])
    budget_recu = agents["budget"].recus[0]
    assert "analyse de StructureAgent" in budget_recu and "analyse de CloisonAgent" in budget_recu
    assert rendu["synthese"] == "livrable assemble"
    etat = ESPACES.pour(rendu["project_id"]).etat()
    assert {t["recipient"] for t in etat["taches"]} >= {"structure", "cloison", "budget"}
    assert etat["decisions"] and etat["decisions"][-1]["texte"] == "livrable assemble"


async def test_sans_json_valide_le_projet_est_decoupe_sur_ses_enchainements():
    lead = _Specialiste("ChefAgent", "coordonne", modele=_Modele("je ne sais pas faire du JSON"))

    taches = await decomposer(lead, "verifie la structure puis chiffre le budget")

    assert [t.objectif for t in taches] == ["verifie la structure", "chiffre le budget"]
    assert taches[1].depend_de == [0]


# --- Espace de travail partage ----------------------------------------------

async def test_un_agent_qui_rejoint_recoit_le_contexte_pertinent_seulement():
    a = _Specialiste("AAgent", "redige", competences=("redaction",))
    b = _Specialiste("BAgent", "calcule le beton", competences=("beton",))
    _equipe(a, b)
    espace = ESPACES.pour("projet-test-contexte")
    espace.verser("a", "Le beton choisi est un C25/30 dose a 350 kg.")
    espace.verser("a", "Le client prefere les couleurs claires.")

    await a.demander_specialiste("b", "quantite de beton pour la dalle",
                                 {"project_id": "projet-test-contexte"})

    recu = b.recus[0]
    assert "C25/30" in recu
    assert "couleurs claires" not in recu


def test_l_espace_survit_a_un_redemarrage(tmp_path):
    avant = EspacesDeTravail(dossier=tmp_path)
    espace = avant.pour("chantier-ouakam")
    espace.decider("chef", "Dalle en C25/30.")
    avant.sauver("chantier-ouakam")

    apres = EspacesDeTravail(dossier=tmp_path)

    assert apres.pour("chantier-ouakam").decisions[0]["texte"] == "Dalle en C25/30."


# --- API ------------------------------------------------------------------

def _client(monkeypatch):
    from apps.backend import main
    from apps.backend import security as securite

    monkeypatch.setattr(securite, "USMAN_API_KEY", "cle-ecosysteme")
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False), {
        "Authorization": "Bearer cle-ecosysteme"}


def test_l_api_liste_tous_les_agents_decouverts(monkeypatch):
    from apps.backend import runtime

    client, entetes = _client(monkeypatch)

    corps = client.get("/api/agents", headers=entetes).json()

    assert corps["total"] == len(runtime.collaborateurs.espaces())
    assert {a["id"] for a in corps["agents"]} == set(runtime.agents_decouverts)
    assert all(a["description"] or a["capabilities"] for a in corps["agents"])


def test_l_api_tient_une_table_ronde_avec_les_agents_du_registre(monkeypatch):
    from apps.backend.routers import ecosysteme

    agents = _projet()
    monkeypatch.setattr(ecosysteme, "collaborateurs", _equipe(*agents.values()))
    client, entetes = _client(monkeypatch)

    corps = client.post("/api/agents/table-ronde", headers=entetes,
                        json={"probleme": "budget des cloisons", "tours": 1}).json()

    assert corps["lead"] and corps["participants"]
    assert re.fullmatch(r"[0-9a-f]{12}", corps["project_id"])
    espace = client.get(f"/api/agents/espaces/{corps['project_id']}", headers=entetes).json()
    assert espace["discussions"][0]["interventions"]


def test_le_telephone_lance_une_table_ronde(monkeypatch):
    """La phrase du proprietaire, par la vraie route `/agent/stream` : le
    classement deterministe mene a EQUIPE, puis a la table ronde, avec les
    agents du registre."""
    from uuid import uuid4

    from apps.backend.routers import chat as module_chat

    agents = _projet()
    monkeypatch.setattr(module_chat, "collaborateurs", _equipe(*agents.values()))
    client, entetes = _client(monkeypatch)

    reponse = client.post("/agent/stream", headers=entetes, json={
        "text": "fais une table ronde de tes agents sur le budget des cloisons",
        "conversation_id": f"c-{uuid4()}", "run_id": f"r-{uuid4()}"})

    texte = "".join(json.loads(ligne[5:]).get("text", "")
                    for ligne in reponse.text.splitlines()
                    if ligne.startswith("data:") and '"token"' in ligne)
    assert "Table ronde" in texte
    assert agents["budget"].recus or agents["cloisons"].recus
