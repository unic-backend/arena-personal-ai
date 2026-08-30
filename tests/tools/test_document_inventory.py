"""Inventaire des documents : ne pas refaire ce qui est déjà fait.

Indexer un document occupe la carte graphique. Le vrai sujet de ces tests est
donc ce que l'inventaire **refuse** de refaire.
"""
import json

import pytest

from tools.documents.inventory import Inventaire, Plan, empreinte


@pytest.fixture
def dossier(tmp_path):
    d = tmp_path / "documents"
    d.mkdir()
    return d


@pytest.fixture
def inventaire(tmp_path):
    return Inventaire(tmp_path / "inventaire.json")


def deposer(dossier, nom, contenu="Devis 2026-041, cloison BA13."):
    chemin = dossier / nom
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# --- Empreinte -----------------------------------------------------------------

def test_deux_contenus_identiques_ont_la_meme_empreinte(dossier):
    a = deposer(dossier, "a.txt", "meme contenu")
    b = deposer(dossier, "b.txt", "meme contenu")

    assert empreinte(a) == empreinte(b)


def test_un_contenu_different_change_l_empreinte(dossier):
    a = deposer(dossier, "a.txt", "version un")
    avant = empreinte(a)
    a.write_text("version deux", encoding="utf-8")

    assert empreinte(a) != avant


def test_recopier_un_fichier_ne_le_rend_pas_modifie(dossier, inventaire):
    """La date de modification change, le contenu non : c'est le contenu qui compte."""
    chemin = deposer(dossier, "devis.txt")
    inventaire.noter_indexation(chemin, passages=1, caracteres=30)

    chemin.touch()   # nouvelle date, meme contenu

    assert inventaire.a_change(chemin) is False


# --- Analyse d'un dossier ------------------------------------------------------

def test_un_dossier_vide_ne_donne_rien_a_faire(dossier, inventaire):
    plan = inventaire.analyser(dossier)

    assert plan.rien_a_faire
    assert plan.resume() == {"nouveaux": 0, "modifies": 0, "inchanges": 0,
                             "disparus": 0, "ignores": 0}


def test_un_document_jamais_vu_est_nouveau(dossier, inventaire):
    deposer(dossier, "devis.pdf")

    plan = inventaire.analyser(dossier)

    assert [c.name for c in plan.nouveaux] == ["devis.pdf"]
    assert plan.a_indexer


def test_un_document_deja_indexe_et_inchange_n_est_pas_refait(dossier, inventaire):
    """Le point central : ne pas occuper le GPU pour rien."""
    chemin = deposer(dossier, "devis.txt")
    inventaire.noter_indexation(chemin, passages=1, caracteres=30)

    plan = inventaire.analyser(dossier)

    assert plan.a_indexer == []
    assert [c.name for c in plan.inchanges] == ["devis.txt"]
    assert plan.rien_a_faire


def test_un_document_modifie_est_a_reindexer(dossier, inventaire):
    chemin = deposer(dossier, "devis.txt", "version un")
    inventaire.noter_indexation(chemin, passages=1, caracteres=11)

    chemin.write_text("version deux, prix revise", encoding="utf-8")
    plan = inventaire.analyser(dossier)

    assert [c.name for c in plan.modifies] == ["devis.txt"]
    assert plan.inchanges == []


def test_un_document_supprime_est_signale_pas_oublie(dossier, inventaire):
    """L'index continuerait sinon à répondre à partir d'un fichier disparu."""
    chemin = deposer(dossier, "ancien.txt")
    inventaire.noter_indexation(chemin, passages=1, caracteres=10)
    chemin.unlink()

    plan = inventaire.analyser(dossier)

    assert plan.disparus == ["ancien.txt"]


def test_un_format_non_lisible_est_compte_a_part(dossier, inventaire):
    deposer(dossier, "devis.txt")
    (dossier / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    (dossier / "tableur.ods").write_bytes(b"PK\x03\x04")

    plan = inventaire.analyser(dossier)

    assert sorted(c.name for c in plan.ignores) == ["photo.jpg", "tableur.ods"]
    assert [c.name for c in plan.nouveaux] == ["devis.txt"]


def test_les_sous_dossiers_sont_parcourus(dossier, inventaire):
    (dossier / "2026" / "chantier_almadies").mkdir(parents=True)
    deposer(dossier / "2026" / "chantier_almadies", "devis.txt")

    plan = inventaire.analyser(dossier)

    assert [c.name for c in plan.nouveaux] == ["devis.txt"]


def test_les_fichiers_caches_sont_laisses_de_cote(dossier, inventaire):
    deposer(dossier, ".brouillon.txt")

    assert inventaire.analyser(dossier).resume()["nouveaux"] == 0


def test_un_dossier_absent_signale_tout_comme_disparu(tmp_path, inventaire):
    chemin = tmp_path / "devis.txt"
    chemin.write_text("x", encoding="utf-8")
    inventaire.noter_indexation(chemin, passages=1, caracteres=1)

    plan = inventaire.analyser(tmp_path / "dossier_qui_n_existe_pas")

    assert plan.disparus == ["devis.txt"]
    assert plan.a_indexer == []


# --- Persistance ---------------------------------------------------------------

def test_l_inventaire_survit_a_un_redemarrage(dossier, tmp_path):
    fichier = tmp_path / "inventaire.json"
    chemin = deposer(dossier, "devis.txt")
    premier = Inventaire(fichier)
    premier.noter_indexation(chemin, passages=3, caracteres=120)
    premier.enregistrer_sur_disque()

    second = Inventaire(fichier)

    assert second.connait("devis.txt")
    assert second.entrees["devis.txt"]["passages"] == 3
    assert second.analyser(dossier).a_indexer == []


def test_un_inventaire_illisible_est_reconstruit_sans_bloquer(dossier, tmp_path):
    """Le pire cas doit être « tout réindexer une fois », pas « ne plus rien faire »."""
    fichier = tmp_path / "inventaire.json"
    fichier.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    deposer(dossier, "devis.txt")

    plan = Inventaire(fichier).analyser(dossier)

    assert [c.name for c in plan.nouveaux] == ["devis.txt"]


def test_un_inventaire_d_une_autre_version_est_reconstruit(dossier, tmp_path):
    fichier = tmp_path / "inventaire.json"
    fichier.write_text(json.dumps({"version": 99, "documents": {"devis.txt": {}}}),
                       encoding="utf-8")
    deposer(dossier, "devis.txt")

    plan = Inventaire(fichier).analyser(dossier)

    assert [c.name for c in plan.nouveaux] == ["devis.txt"]


def test_l_ecriture_ne_laisse_pas_de_fichier_temporaire(dossier, tmp_path):
    fichier = tmp_path / "inventaire.json"
    inventaire = Inventaire(fichier)
    inventaire.noter_indexation(deposer(dossier, "devis.txt"), passages=1, caracteres=10)

    inventaire.enregistrer_sur_disque()

    assert fichier.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_l_inventaire_ne_contient_pas_le_contenu_des_documents(dossier, tmp_path):
    """Il est écrit sur le disque : y recopier une facture serait une fuite."""
    fichier = tmp_path / "inventaire.json"
    chemin = deposer(dossier, "facture.txt", "Client X, 450000 FCFA, RIB SN012345")
    inventaire = Inventaire(fichier)
    inventaire.noter_indexation(chemin, passages=1, caracteres=36)
    inventaire.enregistrer_sur_disque()

    ecrit = fichier.read_text(encoding="utf-8")

    assert "450000" not in ecrit
    assert "RIB" not in ecrit
    assert "facture.txt" in ecrit


def test_oublier_retire_un_document_de_l_inventaire(dossier, tmp_path):
    inventaire = Inventaire(tmp_path / "inventaire.json")
    inventaire.noter_indexation(deposer(dossier, "devis.txt"), passages=1, caracteres=10)

    inventaire.oublier("devis.txt")

    assert not inventaire.connait("devis.txt")


# --- Lisibilité du plan --------------------------------------------------------

def test_le_plan_se_resume_en_une_phrase():
    plan = Plan(nouveaux=["a"], modifies=["b", "c"], inchanges=["d"], disparus=["e"])

    assert str(plan) == "1 nouveau(x), 2 modifie(s), 1 inchange(s), 1 disparu(s), 0 ignore(s)"
