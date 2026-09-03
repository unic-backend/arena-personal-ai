"""Les deux nouvelles capacités sont atteignables depuis une phrase.

**Une capacité qui existe dans un fichier mais que rien n'atteint depuis le
runtime n'est pas intégrée.** C'est la leçon la plus chère de ce dépôt : neuf
modules réels y ont dormi, écrits et testés, sans qu'aucune phrase du
propriétaire ne les fasse tourner (`docs/CURRENT_TASK.md`). Et le 03/09/2026,
`xaar_kaname` existait partout sauf dans la liste de l'écran qui le lance.

Ce fichier mesure la chaîne entière : phrase → routage → registre →
permission → connecteur. Les tests contre le moteur réel vivent dans
`test_connecteur_faceplugin.py` et `test_connecteur_ui_ux_pro_max.py`.
"""
import logging

import pytest

from agents.orchestrator.orchestrator_agent import INTENTIONS


@pytest.fixture(autouse=True)
def _silence():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def runtime():
    from apps.backend import runtime as r
    return r


class TestRegistre:
    def test_les_deux_connecteurs_sont_declares(self, runtime):
        noms = set(runtime.registre.noms())

        assert {"faceplugin", "ui_ux_pro_max"} <= noms

    def test_leurs_capacites_sont_exposees(self, runtime):
        visage = runtime.registre.obtenir("faceplugin").capacites()
        design = runtime.registre.obtenir("ui_ux_pro_max").capacites()

        assert set(visage) == {"detecter", "reperes", "caracteristiques", "comparer"}
        assert set(design) == {"chercher", "design_system"}

    def test_leur_sante_se_mesure_sans_lever(self, runtime):
        """Un connecteur qui lève à la sonde ferait tomber tout le diagnostic."""
        for nom in ("faceplugin", "ui_ux_pro_max"):
            assert runtime.registre.obtenir(nom).sonder() is not None


class TestRoutage:
    """Les phrases de la mission, une par une."""

    @pytest.mark.parametrize("phrase", [
        "analyse ces visages",
        "compare ces deux visages",
        "extrais les caractéristiques du visage",
        "détecte les visages sur cette photo",
    ])
    def test_les_demandes_de_visage_vont_a_faceplugin(self, runtime, phrase):
        assert runtime.orchestrator._classer_par_mots_cles(phrase) == "VISAGE"

    @pytest.mark.parametrize("phrase", [
        "conçois l'interface de cette application",
        "génère un design system",
        "quelle palette et quelle typographie pour cette application ?",
        "améliore l'UX de ce dashboard",
    ])
    def test_les_demandes_de_design_vont_a_ui_ux(self, runtime, phrase):
        assert runtime.orchestrator._classer_par_mots_cles(phrase) == "DESIGN_UI"

    def test_les_deux_etiquettes_sont_connues_du_classeur(self):
        """Une étiquette absente d'`INTENTIONS` est rejetée quand c'est
        le MODÈLE qui classe — le routage marcherait hors ligne et casserait
        dès qu'Ollama répond."""
        assert {"VISAGE", "DESIGN_UI"} <= INTENTIONS

    def test_generer_un_visage_ne_part_pas_a_lanalyse(self, runtime):
        """« mets ce visage sur cette photo » est une génération (Xaar Kaname),
        pas une mesure. Router les deux au même endroit ferait échouer l'une
        des deux sans jamais dire laquelle."""
        assert runtime.orchestrator._classer_par_mots_cles(
            "mets ce visage sur cette photo") != "VISAGE"


class TestDispatch:
    def test_les_deux_intentions_sont_traitees_par_le_routeur(self):
        """Une intention routée vers rien retomberait silencieusement dans le
        cas par défaut : la phrase partirait au chat, et le connecteur
        resterait dormant."""
        source = (__import__("pathlib").Path(__file__).resolve().parent.parent
                  / "apps" / "backend" / "routers" / "chat.py").read_text(encoding="utf-8")

        assert 'elif intent == "VISAGE":' in source
        assert 'elif intent == "DESIGN_UI":' in source

    def test_les_images_viennent_de_son_inventaire(self):
        """Le modèle ne nomme aucun chemin : même discipline que le montage et
        la vision. Sans cela il pourrait faire analyser un fichier inventé."""
        from apps.backend.routers.chat import EXTENSIONS_IMAGES, images_analysables

        assert ".mp4" not in EXTENSIONS_IMAGES, (
            "une video partirait au moteur de visages et echouerait dedans")
        assert isinstance(images_analysables(), list)

    def test_sans_image_rien_nest_invente(self):
        from apps.backend.routers.chat import _analyse_de_visages

        reponse = _analyse_de_visages("analyse ces visages", [])

        assert reponse["status"] == "error"
        assert "aucune image" in reponse["response"].lower()

    def test_comparer_avec_une_seule_image_est_refuse(self):
        """Comparer une image avec elle-même rendrait 100 et se lirait comme
        un résultat."""
        from apps.backend.routers.chat import _analyse_de_visages

        reponse = _analyse_de_visages("compare ces deux visages", ["/tmp/une.jpg"])

        assert reponse["status"] == "error"


class TestPermissionsBoutDeChaine:
    """La protection tient depuis le registre, pas seulement dans le YAML."""

    def test_lecture_de_visages_passe_sans_confirmation(self, runtime, tmp_path):
        image = tmp_path / "vide.jpg"
        image.write_bytes(b"x")
        resultat = runtime.registre.executer("faceplugin", "detecter", image=str(image))

        assert resultat.statut.value != "NEEDS_CONFIRMATION"

    @pytest.mark.parametrize("capacite,arguments", [
        ("caracteristiques", {"image": "a.jpg"}),
        ("comparer", {"image": "a.jpg", "image2": "b.jpg"}),
    ])
    def test_la_biometrie_exige_une_confirmation(self, runtime, capacite, arguments):
        resultat = runtime.registre.executer("faceplugin", capacite, **arguments)

        assert resultat.statut.value == "NEEDS_CONFIRMATION", (
            "un gabarit biometrique partirait sans son accord")
        assert "Rien n'est parti" in resultat.message

    def test_le_design_ne_demande_aucune_confirmation(self, runtime):
        """Lecture pure : demander un accord pour une recommandation de
        couleurs userait le mécanisme sans rien protéger."""
        resultat = runtime.registre.executer(
            "ui_ux_pro_max", "chercher", requete="dashboard", domaine="style")

        assert resultat.statut.value != "NEEDS_CONFIRMATION"


class TestDiagnostic:
    def test_les_deux_moteurs_ont_leur_ligne(self):
        """Sans ligne au diagnostic, le propriétaire n'apprend l'absence d'un
        moteur qu'en lançant une demande — après coup."""
        import inspect

        from scripts import doctor

        source = inspect.getsource(doctor)
        assert 'mesurer("Visages (Faceplugin)"' in source
        assert 'mesurer("Design (UI/UX Pro Max)"' in source
