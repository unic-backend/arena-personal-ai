"""`core/skills/selection.py` — mission ARENA x AUTOSKILLS.

Mission §5, contre-exemple exact de la mission : un projet React avec 50
compétences possibles et une tâche Playwright ne doit récupérer QUE ce qui
concerne Playwright/le test, jamais SEO/Tailwind/Three.js.
"""
from core.skills.registry import Competence
from core.skills.selection import MAXIMUM, choisir_competences


def _competence(identifiant, technologies, mots_taches):
    return Competence(
        identifiant=identifiant, titre=identifiant, description="",
        technologies=tuple(technologies), mots_taches=tuple(mots_taches),
        source="ARENA", licence="ARENA (original)", version="1.0.0",
        commit_amont=None, chemin=None,
    )


CATALOGUE_DE_TEST = [
    _competence("playwright", ["playwright"], ["playwright", "test e2e", "locator"]),
    _competence("react", ["react"], ["react", "composant", "hook"]),
    _competence("seo", ["seo"], ["seo", "referencement", "meta tags"]),
    _competence("tailwind", ["tailwindcss"], ["tailwind", "css", "responsive"]),
    _competence("threejs", ["threejs"], ["three.js", "webgl", "3d"]),
]


class TestFiltreProjet:
    def test_une_technologie_absente_du_projet_n_apparait_jamais(self):
        """Le coeur de la mission §5 : SEO/Tailwind/Three.js présents dans
        le catalogue mais ABSENTS du projet détecté ne sortent jamais,
        quels que soient les mots de la demande."""
        technologies_detectees = ["playwright", "react"]
        retenues = choisir_competences(
            CATALOGUE_DE_TEST, technologies_detectees,
            "corrige ce test playwright, améliore aussi le SEO et le style tailwind")

        identifiants = {c.identifiant for c in retenues}
        assert "seo" not in identifiants
        assert "tailwind" not in identifiants
        assert "threejs" not in identifiants


class TestSelectionParTache:
    def test_tache_playwright_dans_un_projet_qui_a_tout(self):
        """Un projet React qui a AUSSI seo/tailwind/threejs présents —
        seule la tâche décide, la présence technologique ne suffit pas à
        elle seule."""
        technologies_detectees = ["playwright", "react", "seo", "tailwindcss", "threejs"]
        retenues = choisir_competences(
            CATALOGUE_DE_TEST, technologies_detectees,
            "Fix this Playwright test")

        identifiants = [c.identifiant for c in retenues]
        assert "playwright" in identifiants
        assert "seo" not in identifiants
        assert "tailwind" not in identifiants
        assert "threejs" not in identifiants

    def test_tache_mixte_retient_les_deux_technologies_nommees(self):
        technologies_detectees = ["react", "playwright"]
        retenues = choisir_competences(
            CATALOGUE_DE_TEST, technologies_detectees,
            "Crée un composant React avec des tests Playwright")

        identifiants = {c.identifiant for c in retenues}
        assert identifiants == {"react", "playwright"}

    def test_tache_sans_mot_reconnu_ne_retient_rien(self):
        technologies_detectees = ["react", "playwright"]
        retenues = choisir_competences(
            CATALOGUE_DE_TEST, technologies_detectees, "bonjour, comment vas-tu ?")
        assert retenues == []

    def test_demande_vide_ne_retient_rien(self):
        retenues = choisir_competences(CATALOGUE_DE_TEST, ["react"], "")
        assert retenues == []

    def test_aucune_technologie_detectee_ne_retient_rien(self):
        retenues = choisir_competences(CATALOGUE_DE_TEST, [], "corrige ce test playwright")
        assert retenues == []


class TestPlafond:
    def test_jamais_plus_que_le_maximum(self):
        beaucoup = [_competence(f"c{i}", ["python"], ["python"]) for i in range(10)]
        retenues = choisir_competences(beaucoup, ["python"], "python python python", maximum=2)
        assert len(retenues) <= 2

    def test_le_plafond_par_defaut_est_trois(self):
        assert MAXIMUM == 3
