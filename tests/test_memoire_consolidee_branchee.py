"""Le prompt dit-il vraiment chaque chose une seule fois ?

`core/memory/consolidation.py` a ses propres tests
(`tests/core/test_consolidation_memoire.py`). Ce fichier tient le
**branchement** : ce qui part dans le prompt de la passerelle PWA est
regroupé, et ce que le regroupement promet — ne rien effacer, ne pas
mélanger les natures, ne pas gonfler l'importance — tient sur ce chemin-là.
"""
import pytest

from apps.backend.routers import pwa_gateway
from apps.backend.routers.pwa_gateway import souvenirs_pertinents
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.semantique import IndexSemantique

QUESTION = "Quel est le tarif de pose ?"
TARIF = "Le tarif de pose est 5000 FCFA le m2 developpe."


class FournisseurMuet:
    """Pas d'embeddings : la récupération reste lexicale, comme sur le cloud."""

    async def __call__(self, textes):
        return []


@pytest.fixture
def memoire_arena(tmp_path, monkeypatch):
    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    monkeypatch.setattr(pwa_gateway, "memoire_personnelle", memoire)
    monkeypatch.setattr(pwa_gateway, "index_semantique",
                        IndexSemantique(fournisseur=FournisseurMuet()))
    return memoire


def retenir(memoire, contenu, **kw):
    valeurs = {"type": TypeSouvenir.SEMANTIQUE, "nature": Nature.FAIT,
               "source": "devis UC-2026-0804-FG2"}
    valeurs.update(kw)
    return memoire.retenir(contenu, **valeurs)


# --- Le test qui justifie ce branchement ------------------------------------------

async def test_un_souvenir_retenu_deux_fois_ne_prend_qu_une_ligne(memoire_arena):
    """Sans regroupement, le prompt portait la même phrase deux fois."""
    retenir(memoire_arena, TARIF)
    retenir(memoire_arena, TARIF)

    bloc = await souvenirs_pertinents(QUESTION)

    assert bloc.count("5000 FCFA") == 1
    assert "vu 2 fois" in bloc


async def test_la_meme_phrase_ecrite_autrement_est_le_meme_souvenir(memoire_arena):
    """« Plafond BA13 de 40 m2. » et « plafond ba13 de 40 m2 » sont une chose."""
    retenir(memoire_arena, "Plafond BA13 de 40 m2.")
    retenir(memoire_arena, "plafond ba13 de 40 m2")

    bloc = await souvenirs_pertinents("Que sais-tu du plafond BA13 ?")

    assert bloc.lower().count("plafond ba13 de 40 m2") == 1
    assert "vu 2 fois" in bloc


async def test_sans_repetition_aucun_compte_n_est_affiche(memoire_arena):
    """Un « vu 1 fois » sur chaque ligne alourdirait chaque conversation."""
    retenir(memoire_arena, TARIF)

    bloc = await souvenirs_pertinents(QUESTION)

    assert "vu 1 fois" not in bloc
    assert "5000 FCFA" in bloc


# --- Ce que le regroupement n'a pas le droit de faire ------------------------------

async def test_une_supposition_ne_rejoint_jamais_un_fait(memoire_arena):
    """Regrouper les deux ferait d'une supposition un fait par ressemblance."""
    retenir(memoire_arena, TARIF, nature=Nature.FAIT)
    retenir(memoire_arena, TARIF, nature=Nature.INFERENCE)

    bloc = await souvenirs_pertinents(QUESTION)

    assert bloc.count("5000 FCFA") == 2, "deux natures, deux lignes"
    assert "vu 2 fois" not in bloc


async def test_deux_sources_restent_deux_preuves(memoire_arena):
    retenir(memoire_arena, TARIF, source="devis UC-2026-0804-FG2")
    retenir(memoire_arena, TARIF, source="conversation du 27/08")

    bloc = await souvenirs_pertinents(QUESTION)

    assert bloc.count("5000 FCFA") == 2
    assert "UC-2026-0804-FG2" in bloc and "conversation du 27/08" in bloc


async def test_le_regroupement_n_efface_rien_en_memoire(memoire_arena):
    """Le prompt montre une ligne ; la mémoire garde les deux dates et sources."""
    retenir(memoire_arena, TARIF)
    retenir(memoire_arena, TARIF)

    await souvenirs_pertinents(QUESTION)

    assert len(memoire_arena.souvenirs(limite=50)) == 2


async def test_l_ordre_du_classement_est_conserve(memoire_arena):
    """Le plus pertinent reste en tête : regrouper ne re-classe pas."""
    retenir(memoire_arena, "Le tarif de pose est 5000 FCFA le m2 developpe.")
    retenir(memoire_arena, "La pose du plafond a ete faite en juillet.")

    bloc = await souvenirs_pertinents(QUESTION)

    assert bloc.index("5000 FCFA") < bloc.index("juillet")


async def test_le_souvenir_regroupe_entre_dans_le_prompt(memoire_arena):
    retenir(memoire_arena, TARIF)
    retenir(memoire_arena, TARIF)

    systeme = await pwa_gateway.prompt_systeme(None, QUESTION)

    assert pwa_gateway.TITRE_MEMOIRE_ARENA in systeme
    assert systeme.count("5000 FCFA") == 1
