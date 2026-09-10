"""`core/characters/registry.py` — mission ARENA x AGENT HEROES (DEC-0084).

Meme discipline que `tests/core/test_skills_registry.py` : chaque test
construit son propre petit registre dans `tmp_path`, jamais le vrai
`data/personnages/` (donnees d'execution, absentes d'un checkout propre).
"""
import pytest

from core.characters.registry import (
    DOSSIER_PERSONNAGES,
    charger_personnage,
    charger_registre,
    creer_personnage,
    enregistrer_generation,
)


class TestEmplacementReel:
    def test_le_dossier_par_defaut_vit_hors_de_l_arbre_source(self):
        """Les images/metadonnees d'un personnage sont des donnees
        d'execution (comme `data/database/memory.db`), jamais du contenu
        versionne comme `core/skills/store/`."""
        assert "core" not in DOSSIER_PERSONNAGES.parts
        assert "data" in DOSSIER_PERSONNAGES.parts

    def test_un_checkout_propre_n_a_aucun_personnage(self):
        """Vrai sur ce depot aujourd'hui : `data/personnages/` n'existe pas
        avant qu'un personnage n'y soit reellement cree."""
        if not DOSSIER_PERSONNAGES.is_dir():
            assert charger_registre() == []


class TestCreation:
    def test_un_personnage_cree_se_relit_a_l_identique(self, tmp_path):
        image = tmp_path / "media" / "visage.jpg"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"\xff\xd8\xff\xe0-visage")

        cree = creer_personnage(
            "Aissatou", "Presentatrice ARENA", [str(image)],
            "femme senegalaise, la trentaine, boubou bleu, cheveux courts",
            negatif="pas de lunettes", dossier=tmp_path / "personnages")

        relu = charger_personnage(cree.identifiant, dossier=tmp_path / "personnages")

        assert relu is not None
        assert relu.nom == "Aissatou"
        assert relu.images_reference == (str(image),)
        assert relu.profil_visuel.startswith("femme senegalaise")
        assert relu.negatif == "pas de lunettes"
        assert relu.moteur_generation == "wangp"
        assert relu.historique == ()

    def test_l_image_de_reference_n_est_jamais_copiee(self, tmp_path):
        """Mission §21-22 : jamais un second stockage de binaire. Le chemin
        est pris tel quel, rien n'est ecrit a cote de `personnage.json`."""
        image = tmp_path / "media" / "visage.jpg"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"donnees")
        dossier = tmp_path / "personnages"

        cree = creer_personnage("Test", "desc", [str(image)], "profil",
                                dossier=dossier)

        contenu_dossier_personnage = list((dossier / cree.identifiant).iterdir())
        assert contenu_dossier_personnage == [dossier / cree.identifiant / "personnage.json"]

    def test_nom_vide_est_refuse(self, tmp_path):
        with pytest.raises(ValueError):
            creer_personnage("  ", "desc", [], "profil", dossier=tmp_path / "personnages")

    def test_moteur_non_cable_est_refuse(self, tmp_path):
        """Un personnage ne doit jamais declarer un moteur qu'ARENA ne sait
        pas interroger (`core/production/disponibilite.py:PAR_CONNECTEUR`)."""
        with pytest.raises(ValueError, match="fal_ai"):
            creer_personnage("Test", "desc", [], "profil",
                             moteur_generation="fal_ai", dossier=tmp_path / "personnages")


class TestChargement:
    def test_identifiant_absent_rend_none(self, tmp_path):
        assert charger_personnage("n-existe-pas", dossier=tmp_path / "personnages") is None

    def test_dossier_absent_rend_un_registre_vide(self, tmp_path):
        assert charger_registre(tmp_path / "n-existe-pas") == []

    def test_personnage_json_illisible_est_ignore_pas_une_exception(self, tmp_path):
        dossier = tmp_path / "personnages"
        casse = dossier / "casse"
        casse.mkdir(parents=True)
        (casse / "personnage.json").write_text("{pas du json", encoding="utf-8")

        creer_personnage("Valide", "desc", [], "profil", dossier=dossier)

        registre = charger_registre(dossier)
        assert [p.nom for p in registre] == ["Valide"]

    def test_personnage_json_incomplet_est_ignore(self, tmp_path):
        dossier = tmp_path / "personnages"
        incomplet = dossier / "incomplet"
        incomplet.mkdir(parents=True)
        (incomplet / "personnage.json").write_text('{"nom": "x"}', encoding="utf-8")

        assert charger_registre(dossier) == []


class TestProvenance:
    """TEST du mission §29 : persistance + provenance apres plusieurs
    generations, sur un registre REEL (fichiers reels dans tmp_path)."""

    def test_creer_puis_generer_deux_fois_puis_relire_plus_tard(self, tmp_path):
        dossier = tmp_path / "personnages"
        image = tmp_path / "visage.jpg"
        image.write_bytes(b"visage")

        personnage = creer_personnage("Moussa", "desc", [str(image)], "profil",
                                      dossier=dossier)
        assert personnage.version == 1
        assert personnage.historique == ()

        apres_1 = enregistrer_generation(
            personnage, "image", "media/rendered/moussa-1.jpg", "wangp",
            note="premiere scene", dossier=dossier)
        apres_2 = enregistrer_generation(
            apres_1, "identite_video", "media/rendered/moussa-2.mp4", "xaar_kaname",
            dossier=dossier)

        # Retrouve plus tard, comme un nouveau processus le ferait : relu du
        # DISQUE, jamais de l'objet garde en memoire.
        relu = charger_personnage(personnage.identifiant, dossier=dossier)

        assert relu is not None
        assert len(relu.historique) == 2
        assert relu.historique[0]["type"] == "image"
        assert relu.historique[0]["fichier"] == "media/rendered/moussa-1.jpg"
        assert relu.historique[1]["type"] == "identite_video"
        assert relu.historique[1]["moteur"] == "xaar_kaname"
        # L'identite du personnage (images/profil) ne bouge pas : seule la
        # provenance s'accumule.
        assert relu.images_reference == (str(image),)
        assert apres_2.historique == relu.historique

    def test_l_historique_est_append_only_jamais_recrit(self, tmp_path):
        dossier = tmp_path / "personnages"
        personnage = creer_personnage("X", "d", [], "profil", dossier=dossier)
        avec_une_entree = enregistrer_generation(
            personnage, "image", "a.jpg", "wangp", dossier=dossier)

        avec_deux_entrees = enregistrer_generation(
            avec_une_entree, "image", "b.jpg", "wangp", dossier=dossier)

        assert avec_deux_entrees.historique[0]["fichier"] == "a.jpg"
        assert avec_deux_entrees.historique[1]["fichier"] == "b.jpg"
