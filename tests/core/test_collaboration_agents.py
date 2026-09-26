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


# --- Une synthese ne s'invente rien (DEC-0147) ----------------------------------

from core.agent.verification_synthese import verifier_synthese  # noqa: E402

#: Extraits VERBATIM de la synthese recue par le proprietaire le 26/09/2026
#: (table ronde « budget des cloisons », participants plaquiste et finance).
_SYNTHESE_REELLE = """
| **« Les packs tout-compris sont toujours moins chers »** (recherche) | Valable uniquement avec des materiaux premium. |
| ≤ 100 m² | **5 000** | Cout de base. |
| 100 m² < ≤ 400 m² | **4 500** | Gain de 10 % grace a la mutualisation. |
| > 400 m² | **4 000** | Economies d'echelle. |
- **+ 5 %** sur le total du cout matiere.
2. **Marge** = % selon la surface (15 % / 12 % / 10 %).
3. **Prix TTC** = (Cout HT + Marge) x **1,18** (TVA 18 %).
> - Quantite plaques = 250 ÷ 0,6 ≈ 417 plaques → 417 x 4 500 = 1 876 500 FCFA.
> - Majoration 5 % → 1 970 325 FCFA.
> - TTC = (3 095 325 + 371 439) x 1,18 ≈ **4 084 000 FCFA**.
| Mise a jour du **prix des matieres premieres** | **Recherche / Tendances** | Mensuelle |
| Audit de l'**outil de devis** | **Orchestrator / Atelier** | Semestrielle |
| Retour terrain | **Plaquiste** (chef de chantier) | Apres chaque chantier |
"""

_DEBAT_REEL = (
    "Probleme : fais une table ronde sur le budget des cloisons de 250 m2\n"
    "[Tour 1] plaquiste : BA13 standard a 4 500 FCFA, forfait pose 5 000 FCFA/m2.\n"
    "[Tour 1] finance : une marge de 15 % et la TVA a 18 %.")


def _ecosysteme_reel():
    """Les agents de la table reelle et ceux que la synthese a cites a tort."""
    agents = {}
    for cle, nom in [("orchestrator", "OrchestratorAgent"), ("plaquiste", "PlaquisteAgent"),
                     ("finance", "FinanceAgent"), ("recherche", "ResearcherAgent"),
                     ("tendances", "TrendAnalyzerAgent"), ("atelier", "AtelierAgent")]:
        agent = _Specialiste(nom, f"agent {cle}")
        agent.identifiant = cle
        agents[cle] = agent
    return agents, _equipe(*agents.values())


def test_la_synthese_reelle_du_proprietaire_est_signalee():
    _agents, registre = _ecosysteme_reel()

    verification = verifier_synthese(_SYNTHESE_REELLE, [_DEBAT_REEL], registre,
                                     presents={"orchestrator", "plaquiste", "finance"})

    assert verification.agents_absents == ["recherche", "tendances", "atelier"]
    signales = set(verification.chiffres_non_verifies)
    # Le calcul de tete et ce que personne n'avait propose.
    assert {"417", "1 876 500", "1 970 325", "4 084 000", "4 000", "100", "400"} <= signales
    assert {"5 %", "12 %", "10 %"} <= signales
    # Ce que les participants ont bien dit n'est jamais signale.
    assert not signales & {"4 500", "5 000", "15 %", "18 %", "250"}


def test_une_synthese_fidele_ne_declenche_rien():
    _agents, registre = _ecosysteme_reel()
    fidele = ("**Plaquiste** et **Finance** s'accordent : BA13 a 4500 FCFA, pose a "
              "5 000 FCFA/m2, marge de 15 %, TVA 18 %. **BA13 standard** retenu "
              "le 26/09/2026. Il manque le prix du transport pour conclure.")

    verification = verifier_synthese(fidele, [_DEBAT_REEL], registre,
                                     presents={"orchestrator", "plaquiste", "finance"})

    assert verification.propre, verification.en_dict()
    assert verification.avertissement() == ""


async def test_la_table_ronde_signale_sous_la_synthese_sans_la_corriger():
    agents, registre = _ecosysteme_reel()
    agents["plaquiste"].competences = ("cloison", "budget")
    agents["finance"].competences = ("budget", "marge")
    lead = agents["orchestrator"]
    lead.provider = _Modele(_SYNTHESE_REELLE)

    table = await tenir_table_ronde(registre, "budget des cloisons", lead=lead, tours=1)

    assert set(table.participants) == {"plaquiste", "finance"}
    assert table.synthese.startswith(_SYNTHESE_REELLE.strip()[:40]), "rien n'est reecrit"
    assert "Verification automatique" in table.synthese
    assert table.verification["agents_absents"] == ["recherche", "tendances", "atelier"]
    assert "417" in table.verification["chiffres_non_verifies"]
    assert table.en_dict()["verification"] == table.verification
    consigne = lead.provider.prompts[-1]
    assert "ne cite que ces agents : orchestrator" in consigne
    assert "dis qu'il manque au lieu de l'estimer" in consigne


async def test_un_agent_consulte_en_chemin_n_est_pas_un_absent():
    """Un participant qui consulte un collegue le fait travailler : la
    synthese peut le citer. L'espace de travail en garde la trace."""
    agents, registre = _ecosysteme_reel()

    class _Consultant(_Specialiste):
        async def run(self, user_input, context=None):
            avis = await self.demander_specialiste("recherche", "prix du BA13 ?")
            return {"status": "success", "response": f"cloisons ; recherche dit {avis['response']}"}

    consultant = _Consultant("CloisonAgent", "cloisons", competences=("cloison",))
    registre.enregistrer_agent(consultant)
    lead = agents["orchestrator"]
    lead.provider = _Modele("Accord general (cloison) ; prix a confirmer (recherche) "
                            "et (tendances).")

    table = await tenir_table_ronde(registre, "cloison", lead=lead, tours=1)

    assert table.participants == ["cloison"]
    assert table.verification["agents_absents"] == ["tendances"]


async def test_le_livrable_d_un_projet_est_verifie_aussi():
    agents = _projet()
    plan = json.dumps([
        {"objectif": "verifier la structure beton", "competence": "structure beton", "depend_de": []},
        {"objectif": "etablir le budget", "competence": "budget chiffrage", "depend_de": [0]},
    ])
    lead = _Specialiste("ChefAgent", "coordonne les projets", competences=("coordination",),
                        modele=_Modele(plan, "Livrable : budget total 12 500 000 FCFA."))
    registre = _equipe(lead, *agents.values())

    rendu = await conduire_projet(registre, "renover le garage", lead=lead)

    assert rendu["verification"]["chiffres_non_verifies"] == ["12 500 000"]
    assert "a verifier avant tout usage : 12 500 000" in rendu["synthese"]


# --- Ce que chaque tour demande, et ce qu'une panne dit (DEC-0148) -----------

from core.models.routeur import AucunFournisseur  # noqa: E402


async def test_le_premier_tour_ne_demande_de_repondre_a_personne():
    """Mesure du 26/09/2026 : invite a « repondre aux autres » au premier tour,
    le plaquiste a invente les positions de trois agents qui n'avaient pas parle."""
    agents = _projet()
    lead = _Specialiste("ChefAgent", "coordonne", competences=("coordination",))
    registre = _equipe(lead, *agents.values())

    await tenir_table_ronde(registre, "cloisons et plafond", lead=lead, tours=2)

    premier, second = agents["cloisons"].recus[:2]
    assert "personne n'a encore rien dit" in premier
    assert "N'attribue aucune position" in premier
    assert "Reponds" not in premier, "au premier tour, il n'y a rien a quoi repondre"
    assert "Reponds uniquement aux interventions reelles" in second
    assert "Autour de la table : chef, cloison" in premier


async def test_une_panne_de_modele_dit_sa_cause_et_rien_de_plus():
    agents = _projet()
    diagnostic = "Aucun fournisseur n'a pu repondre. Essayes : groq, local."

    async def en_panne(user_input, context=None):
        raise AucunFournisseur(diagnostic)

    async def fuite(user_input, context=None):
        raise RuntimeError("https://api.exemple/v1?key=SECRET-123")

    agents["cloisons"].run = en_panne
    agents["budget"].run = fuite

    class _ModeleEnPanne:
        async def generate(self, prompt, system_prompt=None, **options):
            raise AucunFournisseur(diagnostic)

    lead = _Specialiste("ChefAgent", "coordonne", competences=("coordination",),
                        modele=_ModeleEnPanne())
    registre = _equipe(lead, *agents.values())

    table = await tenir_table_ronde(registre, "cloisons plafond et budget", lead=lead, tours=1)

    paroles = {i["agent"]: i["texte"] for i in table.tours[0]}
    assert diagnostic in paroles["cloison"]
    assert paroles["budget"].endswith("indisponible : RuntimeError")
    assert "SECRET" not in table.synthese and "SECRET" not in paroles["budget"]
    assert table.synthese.startswith(f"(Synthese indisponible : {diagnostic})")
