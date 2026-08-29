"""`Gardien.executer_cycle()` : découvrir, enregistrer, dire ce qui a disparu.

Un scénario contrôlé — le §27 de la mission du 29/08/2026 : un défaut
inséré, détecté, puis retiré, avec la résolution constatée au cycle
suivant. Les diagnostics eux-mêmes sont injectés (voir
`test_guardian_diagnostics.py` sur pourquoi) ; ce fichier teste
l'orchestration — dédoublonnage, disparition, rapport — pas les outils.
"""
import pytest

from core.guardian.diagnostics import Constat
from core.guardian.file_maintenance import FileDeMaintenance
from core.guardian.gardien import Gardien

UN_BUG = Constat(categorie="BUG", gravite="P2", description="test en echec : x",
                 fichier="tests/test_x.py", preuve="AssertionError")


@pytest.fixture
def file(tmp_path):
    return FileDeMaintenance(db_path=str(tmp_path / "maintenance.db"))


def _gardien_qui_rend(*serie):
    """Un gardien dont chaque appel a `executer_cycle` consomme la liste de
    constats suivante — imite un defaut qui apparait, puis disparait."""
    it = iter(serie)

    def diagnostiquer(executer):
        return next(it)
    return diagnostiquer


class TestScenarioControle:
    """Le scénario complet de la mission §27, en un seul test."""

    def test_decouverte_puis_resolution(self, file, monkeypatch):
        import core.guardian.gardien as module_gardien
        monkeypatch.setattr(module_gardien, "diagnostiquer_tout",
                            _gardien_qui_rend([UN_BUG], []))
        gardien = Gardien(file_maintenance=file)

        # 1. DECOUVRIR : le defaut est vu pour la premiere fois.
        rapport_1 = gardien.executer_cycle()
        assert rapport_1.nouvelles == 1
        assert rapport_1.total_ouvertes == 1
        assert rapport_1.taches_ouvertes[0].description == UN_BUG.description

        # 2. Le defaut est corrige ailleurs (hors de ce module — un humain,
        #    une PR) : le prochain diagnostic ne le voit plus.
        rapport_2 = gardien.executer_cycle()

        # 3. VERIFIER : la tache est comptee resolue, plus dans les ouvertes.
        assert rapport_2.resolues == 1
        assert rapport_2.total_ouvertes == 0


class TestDedoublonnage:
    def test_un_meme_defaut_vu_deux_cycles_de_suite_reste_une_seule_tache(self, file, monkeypatch):
        import core.guardian.gardien as module_gardien
        monkeypatch.setattr(module_gardien, "diagnostiquer_tout",
                            _gardien_qui_rend([UN_BUG], [UN_BUG]))
        gardien = Gardien(file_maintenance=file)

        gardien.executer_cycle()
        rapport = gardien.executer_cycle()

        assert rapport.nouvelles == 0
        assert rapport.revues == 1
        assert rapport.total_ouvertes == 1


class TestRapportSante:
    def test_le_compte_par_categorie_est_correct(self, file, monkeypatch):
        import core.guardian.gardien as module_gardien
        autre = Constat(categorie="QUALITE_CODE", gravite="P5", description="F401", fichier="a.py")
        monkeypatch.setattr(module_gardien, "diagnostiquer_tout",
                            _gardien_qui_rend([UN_BUG, autre]))
        gardien = Gardien(file_maintenance=file)

        rapport = gardien.executer_cycle()

        assert rapport.ouvertes_par_categorie == {"BUG": 1, "QUALITE_CODE": 1}

    def test_un_etat_propre_le_dit_explicitement(self, file, monkeypatch):
        import core.guardian.gardien as module_gardien
        monkeypatch.setattr(module_gardien, "diagnostiquer_tout", _gardien_qui_rend([]))
        gardien = Gardien(file_maintenance=file)

        rapport = gardien.executer_cycle()

        assert "Aucune tache ouverte" in rapport.rendre()

    def test_to_dict_est_serialisable(self, file, monkeypatch):
        import core.guardian.gardien as module_gardien
        monkeypatch.setattr(module_gardien, "diagnostiquer_tout", _gardien_qui_rend([UN_BUG]))
        gardien = Gardien(file_maintenance=file)

        rapport = gardien.executer_cycle()
        corps = rapport.to_dict()

        assert corps["total_ouvertes"] == 1
        assert corps["taches_ouvertes"][0]["categorie"] == "BUG"
