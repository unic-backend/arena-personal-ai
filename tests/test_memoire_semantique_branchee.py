"""La mémoire du chat retrouve-t-elle vraiment sur le sens ?

`core/memory/semantique.py` a ses propres tests
(`tests/core/test_recuperation_semantique.py`). Ce fichier tient le
**branchement** : la question posée dans l'interface passe par la passerelle
PWA, et ce que la passerelle rend change réellement parce que le sens est
consulté.

Aucun test n'appelle Ollama : le fournisseur de vecteurs est injecté.
"""
import pytest

from apps.backend.routers import pwa_gateway
from apps.backend.routers.pwa_gateway import souvenirs_pertinents
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import recuperer
from core.memory.semantique import IndexSemantique

# La question ne partage aucun mot utile avec le souvenir : « panneaux » n'est
# pas « plaques ». C'est exactement ce que le lexical seul rate.
QUESTION = "Combien de panneaux ai-je pris pour ce chantier ?"
PROCHE = "234 plaques BA13 commandees pour Fast Group."
ETRANGER = "Rendez-vous chez le dentiste mardi."

VECTEURS = {
    QUESTION: [0.0, 0.90, 0.10, 0.0],
    PROCHE: [0.0, 0.95, 0.05, 0.0],
    ETRANGER: [0.0, 0.0, 0.0, 1.0],
}
AUTRE = [1.0, 0.0, 0.0, 0.0]


class FournisseurDeVecteurs:
    """Rend des vecteurs connus, et compte ce qu'on lui a réellement demandé."""

    def __init__(self, muet=False):
        self.muet = muet
        self.demandes = []

    async def __call__(self, textes):
        self.demandes.extend(textes)
        if self.muet:
            return []
        return [VECTEURS.get(texte, AUTRE) for texte in textes]


@pytest.fixture
def memoire_arena(tmp_path, monkeypatch):
    """La mémoire de la passerelle, isolée : la base du dépôt n'entre pas ici."""
    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    monkeypatch.setattr(pwa_gateway, "memoire_personnelle", memoire)
    return memoire


@pytest.fixture
def brancher_vecteurs(monkeypatch):
    def _brancher(muet=False):
        fournisseur = FournisseurDeVecteurs(muet=muet)
        monkeypatch.setattr(pwa_gateway, "index_semantique",
                            IndexSemantique(fournisseur=fournisseur))
        return fournisseur
    return _brancher


def retenir(memoire, contenu):
    return memoire.retenir(contenu, TypeSouvenir.EPISODIQUE, Nature.FAIT,
                           source="devis UC-2026-0804-FG2")


# --- Le test qui justifie ce branchement ------------------------------------------

async def test_la_question_reformulee_retrouve_le_souvenir(memoire_arena, brancher_vecteurs):
    """« panneaux » doit ramener « plaques BA13 » : c'est toute la phase."""
    brancher_vecteurs()
    retenir(memoire_arena, PROCHE)

    bloc = await souvenirs_pertinents(QUESTION)

    assert "234 plaques BA13" in bloc


async def test_le_lexical_seul_ratait_ce_souvenir(memoire_arena):
    """Ce que le branchement corrige, mesuré et non raconté."""
    retenir(memoire_arena, PROCHE)

    assert recuperer(memoire_arena, QUESTION, budget_caracteres=1200) == []


async def test_un_souvenir_sans_rapport_ne_remonte_pas(memoire_arena, brancher_vecteurs):
    brancher_vecteurs()
    retenir(memoire_arena, ETRANGER)

    bloc = await souvenirs_pertinents(QUESTION)

    assert "dentiste" not in bloc


# --- Sans embeddings : lexical, et rien d'autre -----------------------------------

async def test_sans_embeddings_la_memoire_reste_exactement_lexicale(
        memoire_arena, brancher_vecteurs):
    """Une capacité absente ne se simule pas : on retombe sur l'ancien chemin."""
    brancher_vecteurs(muet=True)
    retenir(memoire_arena, "Le tarif de pose est 5000 FCFA le m2 developpe.")

    bloc = await souvenirs_pertinents("quel est le tarif de pose ?")
    lexical = recuperer(memoire_arena, "quel est le tarif de pose ?", budget_caracteres=1200)

    assert lexical, "le lexical doit trouver ce souvenir : c'est le repli mesuré ici"
    for resultat in lexical:
        assert resultat.souvenir.contenu in bloc
    assert "5000 FCFA" in bloc


async def test_sans_embeddings_le_souvenir_reformule_ne_remonte_pas(
        memoire_arena, brancher_vecteurs):
    """Le sens absent est une perte annoncée, pas un classement approché."""
    brancher_vecteurs(muet=True)
    retenir(memoire_arena, PROCHE)

    assert await souvenirs_pertinents(QUESTION) == ""


# --- Ce que le branchement ne doit pas coûter --------------------------------------

async def test_l_index_est_partage_entre_deux_questions(memoire_arena, brancher_vecteurs):
    """Un index recréé à chaque question repaierait toute la mémoire à chaque tour."""
    fournisseur = brancher_vecteurs()
    retenir(memoire_arena, PROCHE)

    await souvenirs_pertinents(QUESTION)
    demandes_apres_la_premiere = list(fournisseur.demandes)
    await souvenirs_pertinents(QUESTION)

    assert fournisseur.demandes.count(PROCHE) == 1, (
        "le souvenir ne doit être vectorisé qu'une fois")
    assert len(fournisseur.demandes) > len(demandes_apres_la_premiere), (
        "la sonde de capacité, elle, est bien remesurée à chaque question")


async def test_une_memoire_illisible_ne_casse_pas_la_reponse(monkeypatch, brancher_vecteurs):
    """Répondre sans souvenir vaut mieux que ne pas répondre."""
    brancher_vecteurs()

    class MemoireCassee:
        def souvenirs(self, **kw):
            raise RuntimeError("base illisible")

    monkeypatch.setattr(pwa_gateway, "memoire_personnelle", MemoireCassee())

    assert await souvenirs_pertinents(QUESTION) == ""


# --- Le bloc arrive-t-il dans le prompt ? ------------------------------------------

async def test_le_souvenir_retrouve_par_le_sens_entre_dans_le_prompt(
        memoire_arena, brancher_vecteurs):
    brancher_vecteurs()
    retenir(memoire_arena, PROCHE)

    systeme = await pwa_gateway.prompt_systeme(None, QUESTION)

    assert pwa_gateway.TITRE_MEMOIRE_ARENA in systeme
    assert "234 plaques BA13" in systeme
