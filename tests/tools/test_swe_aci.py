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


class TestLaLectureSeuleEstTenue:
    """`SWEAgent` se déclare en lecture seule — et le dit au propriétaire.

    Sa docstring : « Il LIT le depot et propose une correction. **Il ne modifie
    aucun fichier.** » Sa réponse le répète : « Cet agent analyse et propose. Il
    ne modifie aucun fichier : c'est toi qui décides d'appliquer la correction
    ou non. »

    Mesuré le 01/09/2026 : `SWEACITool.edit` **écrit** des fichiers, n'est
    appelé nulle part dans le dépôt, et n'était couvert par aucun test. La
    garantie ne tenait donc à rien d'autre qu'au fait que personne ne l'avait
    branché. Ces tests en font une frontière.
    """

    @staticmethod
    def _source_de(objet) -> str:
        import inspect
        return inspect.getsource(objet)

    def test_l_agent_n_appelle_aucune_ecriture(self):
        from agents.swe_agent.swe_agent import SWEAgent

        source = self._source_de(SWEAgent)

        assert ".edit(" not in source, (
            "SWEAgent se declare en lecture seule et promet de ne modifier "
            "aucun fichier : il ne peut pas appeler `edit`"
        )

    def test_personne_dans_le_depot_n_appelle_l_ecriture(self):
        """Pas seulement l'agent : rien ne doit brancher `edit` sans le décider.

        Le balayage se limite aux paquets sources, jamais à toute la racine du
        dépôt. Mesuré le 01/09/2026 sur la machine du propriétaire : un
        `rglob` depuis la racine descend dans `data/`, ignoré par
        `.gitignore` mais bien présent sur le disque — un cache d'embeddings
        y écrit des chemins que Windows refuse de lire
        (`OSError: [Errno 22] Invalid argument`).
        """
        from pathlib import Path

        racine = Path(__file__).resolve().parent.parent.parent
        paquets_source = ("apps", "core", "agents", "tools", "social")
        coupables = []
        for paquet in paquets_source:
            for chemin in (racine / paquet).rglob("*.py"):
                relatif = chemin.relative_to(racine).as_posix()
                if "__pycache__" in relatif or relatif == "tools/coder/swe_aci_tool.py":
                    continue
                if ".edit(" in chemin.read_text(encoding="utf-8", errors="ignore"):
                    coupables.append(relatif)

        assert coupables == [], (
            f"`SWEACITool.edit` ecrit des fichiers et est branche ici : {coupables}. "
            "Si c'est voulu, la garantie de lecture seule de SWEAgent doit changer "
            "d'abord — elle est ecrite dans sa reponse au proprietaire."
        )

    def test_la_reponse_de_l_agent_annonce_la_lecture_seule(self):
        """Si la promesse disparaît du texte, ce test doit tomber avec elle."""
        from agents.swe_agent.swe_agent import SWEAgent

        source = self._source_de(SWEAgent)

        assert "ne modifie aucun fichier" in source
