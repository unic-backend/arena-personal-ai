"""Memoire de decision executive — concise, jamais la deliberation entiere
(mission §15/§16)."""
from core.executive.contrat import AnalyseSpecialiste, DecisionExecutive, Position
from core.executive.memoire import bloc_decisions_recentes, decisions_recentes, enregistrer_decision
from core.memory.memory_manager import MemoryManager


def _decision(question="Devrions-nous accepter ?", recommandation="Accepter"):
    return DecisionExecutive(
        question=question, simple=False, reponse=recommandation,
        recommandation=recommandation, roles_consultes=["finance"],
        analyses=[AnalyseSpecialiste(role="finance", domaine="Finance", position=Position.FAVORABLE)],
        hypotheses=["h1"], informations_manquantes=["i1"],
    )


class TestEnregistrerDecision:
    def test_sans_memoire_rend_none(self):
        assert enregistrer_decision(None, _decision()) is None

    def test_ecrit_un_enregistrement_concis(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        cle = enregistrer_decision(memoire, _decision())
        assert cle is not None
        enregistrements = memoire.list_facts("executive_decision", limit=5)
        assert len(enregistrements) == 1
        valeur = enregistrements[0]["value"]
        assert valeur["question"] == "Devrions-nous accepter ?"
        assert valeur["specialists_consulted"] == ["finance"]

    def test_ne_stocke_pas_les_analyses_completes(self, tmp_path):
        """§15 : jamais la transcription entiere de la deliberation."""
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        enregistrer_decision(memoire, _decision())
        valeur = memoire.list_facts("executive_decision", limit=1)[0]["value"]
        assert "analyses" not in valeur
        assert "specialist_analyses" not in valeur


class TestDecisionsRecentes:
    def test_sans_memoire_rend_liste_vide(self):
        assert decisions_recentes(None) == []

    def test_limite_respectee(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        for i in range(5):
            enregistrer_decision(memoire, _decision(question=f"question {i}"))
        assert len(decisions_recentes(memoire, limite=2)) == 2


class TestBlocDecisionsRecentes:
    def test_vide_si_rien(self):
        assert bloc_decisions_recentes(None) == ""

    def test_liste_les_questions_et_resumes(self, tmp_path):
        memoire = MemoryManager(db_path=str(tmp_path / "m.db"))
        enregistrer_decision(memoire, _decision(question="Accepter le chantier ?"))
        bloc = bloc_decisions_recentes(memoire)
        assert "Accepter le chantier ?" in bloc
