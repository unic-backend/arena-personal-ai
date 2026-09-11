"""`MemoryManager.list_facts` — ajoute pour l'Executive Intelligence (mission
ARENA x OPENEXECUTIVE, DEC-0086, §15), reutilisable par toute categorie."""
from core.memory.memory_manager import MemoryManager


class TestListFacts:
    def test_rend_du_plus_recent_au_plus_ancien(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        memoire.set_fact("categorie_test", "k1", {"n": 1})
        memoire.set_fact("categorie_test", "k2", {"n": 2})
        memoire.set_fact("categorie_test", "k3", {"n": 3})
        resultats = memoire.list_facts("categorie_test", limit=10)
        assert [r["value"]["n"] for r in resultats] == [3, 2, 1]

    def test_respecte_la_limite(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        for i in range(5):
            memoire.set_fact("categorie_test", f"k{i}", {"n": i})
        assert len(memoire.list_facts("categorie_test", limit=2)) == 2

    def test_ne_melange_pas_les_categories(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        memoire.set_fact("a", "k1", {"n": 1})
        memoire.set_fact("b", "k2", {"n": 2})
        assert len(memoire.list_facts("a", limit=10)) == 1

    def test_categorie_absente_rend_liste_vide(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        assert memoire.list_facts("inexistante", limit=10) == []

    def test_metadonnees_preservees(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        memoire.set_fact("a", "k1", {"n": 1}, metadata={"source": "test"})
        resultats = memoire.list_facts("a", limit=1)
        assert resultats[0]["metadata"] == {"source": "test"}
