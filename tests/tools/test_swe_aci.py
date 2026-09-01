"""L'outil ACI : une recherche qui n'a rien pu lire ne dit pas « aucun résultat ».

Défaut trouvé le 01/09/2026 : `search_dir` avalait toute exception de lecture
puis répondait « 🔍 Aucun résultat », indistinguable d'une vraie absence.
L'agent qui lisait cette réponse en concluait que le terme n'existe pas dans
le projet — et cherchait ailleurs.
"""
import pytest

from tools.coder.swe_aci_tool import SWEACITool


@pytest.fixture
def projet(tmp_path):
    (tmp_path / "trouvable.py").write_text("def poser_cloison():\n    pass\n",
                                           encoding="utf-8")
    return tmp_path


class TestUneRechercheIncompleteLeDit:
    def test_un_fichier_illisible_est_signale_et_compte(self, projet, monkeypatch):
        secret = projet / "secret.py"
        secret.write_text("def poser_cloison(): pass\n", encoding="utf-8")

        vrai_lire = type(secret).read_text

        def refuse(self, *a, **k):
            if self.name == "secret.py":
                raise PermissionError(13, "Permission denied")
            return vrai_lire(self, *a, **k)

        monkeypatch.setattr(type(secret), "read_text", refuse)

        sortie = SWEACITool(root_dir=str(projet)).search_dir("poser_cloison")
        assert "n'ont pas pu être lus" in sortie
        assert "secret.py" in sortie

    def test_aucun_resultat_et_aucune_lecture_ne_se_confondent_pas(
        self, projet, monkeypatch
    ):
        """Le cas qui rendait la réponse trompeuse."""
        monkeypatch.setattr(
            type(projet / "x"), "read_text",
            lambda self, *a, **k: (_ for _ in ()).throw(OSError(5, "I/O error")))

        sortie = SWEACITool(root_dir=str(projet)).search_dir("poser_cloison")
        assert "Aucun résultat" in sortie
        assert "incomplète" in sortie, (
            "une recherche qui n'a rien lu s'est fait passer pour une absence"
        )

    def test_une_recherche_qui_lit_tout_ne_met_aucune_reserve(self, projet):
        sortie = SWEACITool(root_dir=str(projet)).search_dir("poser_cloison")
        assert "trouvable.py" in sortie
        assert "n'ont pas pu être lus" not in sortie

    def test_un_terme_vraiment_absent_reste_une_absence_nette(self, projet):
        sortie = SWEACITool(root_dir=str(projet)).search_dir("zzz_inexistant")
        assert "Aucun résultat" in sortie
        assert "incomplète" not in sortie
