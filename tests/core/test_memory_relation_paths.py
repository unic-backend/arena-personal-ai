from core.memory.personnelle import MemoirePersonnelle


def test_chemin_relations_multi_saut_garde_les_sources(tmp_path):
    memoire = MemoirePersonnelle(str(tmp_path / "memoire.db"))
    memoire.relier("Ousmane", "dirige", "UniC", "registre", projet="unic")
    memoire.relier("UniC", "travaille_sur", "Arena", "conversation", projet="unic")
    memoire.relier("Arena", "utilise", "SQLite", "code", projet="unic")

    chemin = memoire.chemin_relations("Ousmane", "SQLite", projet="unic")

    assert [(r.depuis, r.lien, r.vers) for r in chemin] == [
        ("Ousmane", "dirige", "UniC"),
        ("UniC", "travaille_sur", "Arena"),
        ("Arena", "utilise", "SQLite"),
    ]
    assert [r.source for r in chemin] == ["registre", "conversation", "code"]


def test_chemin_relations_respecte_projet_et_profondeur(tmp_path):
    memoire = MemoirePersonnelle(str(tmp_path / "memoire.db"))
    memoire.relier("A", "vers", "B", "s1", projet="p1")
    memoire.relier("B", "vers", "C", "s2", projet="p1")
    memoire.relier("A", "raccourci", "C", "s3", projet="p2")

    assert memoire.chemin_relations("A", "C", projet="p1", profondeur_max=1) == []
    chemin = memoire.chemin_relations("A", "C", projet="p1", profondeur_max=2)
    assert [r.source for r in chemin] == ["s1", "s2"]


def test_chemin_relations_ne_fabrique_aucun_lien(tmp_path):
    memoire = MemoirePersonnelle(str(tmp_path / "memoire.db"))
    memoire.relier("A", "vers", "B", "source", projet="p")

    assert memoire.chemin_relations("A", "inconnu", projet="p") == []
