"""Indexation des documents : ce qui est fait, et surtout ce qui est refusé.

Aucun test n'appelle Ollama. Le moteur documentaire est un double qui respecte
le contrat de `LightRAGTool` : `insert_text(texte) -> bool`.
"""
import httpx
import pytest

from tools.documents.indexer import (
    Rapport,
    indexer_documents,
    texte_avec_provenance,
    verifier_moteur,
)
from tools.documents.inventory import Inventaire
from tools.documents.reader import lire_document


class MoteurDouble:
    """Respecte le contrat de LightRAGTool, sans Ollama."""

    def __init__(self, accepte=True, leve=False):
        self.accepte = accepte
        self.leve = leve
        self.textes = []

    def insert_text(self, texte: str) -> bool:
        if self.leve:
            raise RuntimeError("moteur indisponible")
        self.textes.append(texte)
        return self.accepte


@pytest.fixture
def classeur(tmp_path):
    dossier = tmp_path / "documents"
    dossier.mkdir()
    (dossier / "devis.txt").write_text("Devis 2026-041, cloison BA13.", encoding="utf-8")
    (dossier / "notes.md").write_text("Chantier Almadies, 12 m2.", encoding="utf-8")
    (dossier / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    return dossier


@pytest.fixture
def inventaire_chemin(tmp_path):
    return tmp_path / "inventaire.json"


def indexer(moteur, classeur, inventaire_chemin, **kw):
    return indexer_documents(moteur, classeur, inventaire_chemin, verifier=False, **kw)


# --- Vérification du moteur ----------------------------------------------------

def test_ollama_injoignable_donne_une_raison_actionnable(monkeypatch):
    def refuse(*a, **k):
        raise httpx.ConnectError("connexion refusee")

    monkeypatch.setattr(httpx, "get", refuse)

    raison = verifier_moteur("http://127.0.0.1:11434")

    assert "ne repond pas" in raison
    assert "ollama serve" in raison


def test_le_modele_d_embeddings_absent_est_signale(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"models": [{"name": "qwen2.5-coder:14b"}]}, request=httpx.Request("GET", "x")))

    raison = verifier_moteur()

    assert "nomic-embed-text" in raison
    assert "ollama pull" in raison


def test_un_moteur_pret_ne_donne_aucune_raison(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"models": [{"name": "nomic-embed-text:latest"}]},
        request=httpx.Request("GET", "x")))

    assert verifier_moteur() is None


def test_sans_moteur_rien_n_est_indexe_et_rien_n_est_note(
    monkeypatch, classeur, inventaire_chemin
):
    """Un refus franc vaut mieux qu'une indexation à moitié faite."""
    def refuse(*a, **k):
        raise httpx.ConnectError("hors ligne")

    monkeypatch.setattr(httpx, "get", refuse)
    moteur = MoteurDouble()

    rapport = indexer_documents(moteur, classeur, inventaire_chemin, verifier=True)

    assert rapport.statut == "REFUSE"
    assert moteur.textes == []
    assert not inventaire_chemin.exists(), "l'inventaire ne doit pas etre touche"


# --- Chemin nominal ------------------------------------------------------------

def test_les_documents_lisibles_sont_indexes(classeur, inventaire_chemin):
    moteur = MoteurDouble()

    rapport = indexer(moteur, classeur, inventaire_chemin)

    assert rapport.statut == "INDEXE"
    assert sorted(rapport.indexes) == ["devis.txt", "notes.md"]
    assert len(moteur.textes) == 2


def test_la_provenance_part_avec_le_texte(classeur, inventaire_chemin):
    """Sans elle, la lecture page par page ne servirait à rien."""
    moteur = MoteurDouble()

    indexer(moteur, classeur, inventaire_chemin)

    envoye = "\n".join(moteur.textes)
    assert "[Source : devis.txt]" in envoye
    assert "Devis 2026-041" in envoye


def test_le_numero_de_page_est_transmis(tmp_path):
    """Le préfixe doit porter la page pour un PDF, pas seulement le fichier."""
    from tools.documents.reader import Document, Passage

    document = Document(chemin=tmp_path / "d.pdf", statut="LU", passages=[
        Passage(texte="page une", fichier="d.pdf", page=1),
        Passage(texte="page deux", fichier="d.pdf", page=2),
    ])

    texte = texte_avec_provenance(document)

    assert "[Source : d.pdf, page 1]" in texte
    assert "[Source : d.pdf, page 2]" in texte


def test_un_format_non_lu_est_compte_a_part(classeur, inventaire_chemin):
    rapport = indexer(MoteurDouble(), classeur, inventaire_chemin)

    assert rapport.ignores == ["photo.jpg"]


def test_relancer_la_commande_ne_reindexe_rien(classeur, inventaire_chemin):
    """Le point de tout l'inventaire : ne pas occuper le GPU deux fois."""
    indexer(MoteurDouble(), classeur, inventaire_chemin)
    moteur = MoteurDouble()

    rapport = indexer(moteur, classeur, inventaire_chemin)

    assert rapport.statut == "RIEN_A_FAIRE"
    assert moteur.textes == []
    assert sorted(rapport.inchanges) == ["devis.txt", "notes.md"]


def test_un_document_modifie_est_repris(classeur, inventaire_chemin):
    indexer(MoteurDouble(), classeur, inventaire_chemin)
    (classeur / "devis.txt").write_text("Devis 2026-041 REVISE, 470000.", encoding="utf-8")
    moteur = MoteurDouble()

    rapport = indexer(moteur, classeur, inventaire_chemin)

    assert rapport.indexes == ["devis.txt"]
    assert "REVISE" in moteur.textes[0]


# --- Échecs --------------------------------------------------------------------

def test_un_document_refuse_par_le_moteur_n_est_pas_note_comme_indexe(
    classeur, inventaire_chemin
):
    """Sinon il ne serait jamais repris, et l'index se croirait complet."""
    rapport = indexer(MoteurDouble(accepte=False), classeur, inventaire_chemin)

    assert rapport.statut == "ECHEC"
    assert rapport.indexes == []
    assert len(rapport.echecs) == 2
    assert not Inventaire(inventaire_chemin).connait("devis.txt")


def test_un_moteur_qui_leve_ne_fait_pas_tomber_la_commande(classeur, inventaire_chemin):
    rapport = indexer(MoteurDouble(leve=True), classeur, inventaire_chemin)

    assert rapport.statut == "ECHEC"
    assert rapport.indexes == []


def test_un_document_illisible_est_signale_les_autres_passent(classeur, inventaire_chemin):
    (classeur / "scan_vide.txt").write_text("", encoding="utf-8")
    moteur = MoteurDouble()

    rapport = indexer(moteur, classeur, inventaire_chemin)

    assert rapport.statut == "PARTIEL"
    assert sorted(rapport.indexes) == ["devis.txt", "notes.md"]
    assert rapport.echecs[0]["fichier"] == "scan_vide.txt"


def test_un_echec_est_repris_au_passage_suivant(classeur, inventaire_chemin):
    indexer(MoteurDouble(accepte=False), classeur, inventaire_chemin)
    moteur = MoteurDouble(accepte=True)

    rapport = indexer(moteur, classeur, inventaire_chemin)

    assert sorted(rapport.indexes) == ["devis.txt", "notes.md"]


# --- Rapport -------------------------------------------------------------------

def test_le_rapport_se_lit_en_une_phrase():
    assert str(Rapport(statut="REFUSE", raison="Ollama absent")) == "REFUSE : Ollama absent"
    assert str(Rapport(statut="RIEN_A_FAIRE", inchanges=["a", "b"])) == (
        "Rien a faire : 2 document(s) deja indexe(s)."
    )
    assert str(Rapport(statut="INDEXE", indexes=["a"], ignores=["b"])) == (
        "1 indexe(s), 1 ignore(s)."
    )


def test_le_rapport_ne_contient_pas_le_contenu_des_documents(classeur, inventaire_chemin):
    rapport = indexer(MoteurDouble(), classeur, inventaire_chemin)

    assert "Almadies" not in str(rapport.resume())
    assert "2026-041" not in str(rapport.resume())


def test_un_document_disparu_est_remonte(classeur, inventaire_chemin):
    indexer(MoteurDouble(), classeur, inventaire_chemin)
    (classeur / "notes.md").unlink()

    rapport = indexer(MoteurDouble(), classeur, inventaire_chemin)

    assert rapport.disparus == ["notes.md"]


def test_la_lecture_reelle_est_utilisee(classeur, inventaire_chemin):
    """Garde-fou : le texte inséré doit venir du lecteur, pas d'une reconstruction."""
    attendu = lire_document(classeur / "devis.txt").texte
    moteur = MoteurDouble()

    indexer(moteur, classeur, inventaire_chemin)

    assert any(attendu in t for t in moteur.textes)
