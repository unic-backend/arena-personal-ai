"""`core/guardian/diagnostics.py` : trois constats réels, une sortie injectée
pour rester rapide et hors ligne — le vrai `ruff`/`pytest` a tourné à la
main pendant l'écriture de ce module (voir docs/DECISIONS.md, DEC-0014).
"""
import json

from core.guardian.diagnostics import (
    CATEGORIE_BUG,
    CATEGORIE_QUALITE,
    Constat,
    SortieCommande,
    diagnostiquer_bugs,
    diagnostiquer_qualite,
)


def _fixe(sortie: SortieCommande):
    """Un exécuteur de test qui rend toujours la même sortie, sans vrai processus."""
    def _executer(commande):
        return sortie
    return _executer


class TestConstat:
    def test_l_empreinte_est_stable_pour_le_meme_constat(self):
        a = Constat(categorie="BUG", gravite="P2", description="x", fichier="f.py")
        b = Constat(categorie="BUG", gravite="P2", description="x", fichier="f.py")

        assert a.empreinte == b.empreinte

    def test_l_empreinte_change_si_la_description_change(self):
        a = Constat(categorie="BUG", gravite="P2", description="x", fichier="f.py")
        b = Constat(categorie="BUG", gravite="P2", description="y", fichier="f.py")

        assert a.empreinte != b.empreinte

    def test_l_empreinte_ignore_la_preuve(self):
        """La preuve peut varier legerement d'un cycle a l'autre (un numero de
        ligne qui bouge) sans que ca cree une nouvelle tache a chaque fois."""
        a = Constat(categorie="BUG", gravite="P2", description="x", fichier="f.py", preuve="v1")
        b = Constat(categorie="BUG", gravite="P2", description="x", fichier="f.py", preuve="v2")

        assert a.empreinte == b.empreinte


class TestDiagnostiquerBugs:
    def test_aucun_echec_ne_rend_rien(self):
        executer = _fixe(SortieCommande(0, "5 passed in 0.1s\n", ""))

        assert diagnostiquer_bugs(executer) == []

    def test_un_echec_devient_un_constat(self):
        sortie = (
            "F                                                          [100%]\n"
            "=================== FAILURES ===================\n"
            "E   AssertionError: boum\n"
            "tests/test_x.py:12: AssertionError: boum\n"
            "=========== short test summary info ===========\n"
            "FAILED tests/test_x.py::test_qui_echoue\n"
            "1 failed in 0.02s\n"
        )
        executer = _fixe(SortieCommande(1, sortie, ""))

        constats = diagnostiquer_bugs(executer)

        assert len(constats) == 1
        assert constats[0].categorie == CATEGORIE_BUG
        assert "test_x.py::test_qui_echoue" in constats[0].description
        assert constats[0].fichier == "tests/test_x.py"

    def test_plusieurs_echecs_rendent_plusieurs_constats(self):
        sortie = (
            "FAILED tests/test_a.py::test_1\n"
            "FAILED tests/test_b.py::test_2\n"
            "2 failed in 0.1s\n"
        )
        executer = _fixe(SortieCommande(1, sortie, ""))

        constats = diagnostiquer_bugs(executer)

        assert {c.fichier for c in constats} == {"tests/test_a.py", "tests/test_b.py"}

    def test_la_commande_reelle_appelee_est_pytest(self):
        appels = []

        def executer(commande):
            appels.append(commande)
            return SortieCommande(0, "0 passed\n", "")

        diagnostiquer_bugs(executer)

        assert "pytest" in appels[0]
        assert "tests/" in appels[0]


class TestDiagnostiquerQualite:
    def test_une_sortie_vide_ne_rend_rien(self):
        executer = _fixe(SortieCommande(0, "[]", ""))

        assert diagnostiquer_qualite(executer) == []

    def test_une_violation_devient_un_constat(self):
        violations = [{"code": "F401", "message": "unused import",
                      "filename": "/x/module.py", "location": {"row": 3}}]
        executer = _fixe(SortieCommande(1, json.dumps(violations), ""))

        constats = diagnostiquer_qualite(executer)

        assert len(constats) == 1
        assert constats[0].categorie == CATEGORIE_QUALITE
        assert "F401" in constats[0].description

    def test_une_sortie_illisible_ne_leve_pas(self):
        executer = _fixe(SortieCommande(1, "pas du json", "erreur ruff"))

        assert diagnostiquer_qualite(executer) == []
