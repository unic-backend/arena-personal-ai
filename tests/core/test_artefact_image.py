"""`core/production/artefact_image.py` — mission ARENA x HIDREAM-I1 (DEC-0085).

Mission §14 : « generation terminee » ou un nom de fichier ne sont jamais
une preuve. Chaque test ouvre un VRAI fichier (via Pillow) — jamais un
chemin suppose valide.
"""
from PIL import Image

from core.production.artefact_image import (
    ProvenanceImage,
    ecrire_provenance,
    lire_provenance,
    valider_image,
)


class TestValiderImage:
    def test_une_image_reelle_et_valide_passe(self, tmp_path):
        chemin = tmp_path / "ok.png"
        Image.new("RGB", (512, 512), color="red").save(chemin)

        resultat = valider_image(chemin)

        assert resultat.valide is True
        assert resultat.largeur == 512
        assert resultat.hauteur == 512
        assert resultat.format == "PNG"

    def test_fichier_absent_est_refuse(self, tmp_path):
        resultat = valider_image(tmp_path / "n-existe-pas.png")
        assert resultat.valide is False
        assert "absent" in resultat.raison

    def test_fichier_minuscule_est_refuse_avant_meme_l_ouverture(self, tmp_path):
        chemin = tmp_path / "vide.png"
        chemin.write_bytes(b"\x89PNG\r\n")

        resultat = valider_image(chemin)

        assert resultat.valide is False
        assert "petit" in resultat.raison

    def test_fichier_tronque_au_milieu_est_detecte(self, tmp_path):
        """Le controle qui compte : un fichier assez gros pour passer le
        filtre de taille, mais coupe en plein milieu d'une vraie image."""
        chemin_ok = tmp_path / "source.png"
        Image.new("RGB", (512, 512), color="blue").save(chemin_ok)
        donnees = chemin_ok.read_bytes()

        tronque = tmp_path / "tronque.png"
        tronque.write_bytes(donnees[:len(donnees) // 2])

        resultat = valider_image(tronque)

        assert resultat.valide is False
        assert "corrompu" in resultat.raison or "illisible" in resultat.raison

    def test_dimension_differente_de_celle_demandee_est_refusee(self, tmp_path):
        chemin = tmp_path / "mauvaise_taille.png"
        Image.new("RGB", (512, 512), color="green").save(chemin)

        resultat = valider_image(chemin, largeur_attendue=1024, hauteur_attendue=1024)

        assert resultat.valide is False
        assert "512" in resultat.raison
        assert "1024" in resultat.raison

    def test_dimension_conforme_est_acceptee(self, tmp_path):
        chemin = tmp_path / "bonne_taille.png"
        Image.new("RGB", (768, 1360), color="yellow").save(chemin)

        resultat = valider_image(chemin, largeur_attendue=768, hauteur_attendue=1360)

        assert resultat.valide is True

    def test_un_fichier_texte_n_est_pas_confondu_avec_une_image(self, tmp_path):
        chemin = tmp_path / "pas_une_image.png"
        chemin.write_text("x" * 1000, encoding="utf-8")

        resultat = valider_image(chemin)

        assert resultat.valide is False


class TestProvenance:
    def test_ecrite_puis_relue_a_l_identique(self, tmp_path):
        chemin = tmp_path / "img.png"
        Image.new("RGB", (512, 512)).save(chemin)
        provenance = ProvenanceImage(
            modele="HiDream-I1", modele_version="fast", fournisseur="hidream-local",
            seed=123, largeur=512, hauteur=512, duree_generation_s=8.4, prompt="un chat")

        ecrire_provenance(chemin, provenance)
        relue = lire_provenance(chemin)

        assert relue["modele"] == "HiDream-I1"
        assert relue["seed"] == 123
        assert relue["duree_generation_s"] == 8.4
        assert relue["prompt"] == "un chat"

    def test_provenance_absente_rend_none_jamais_une_exception(self, tmp_path):
        assert lire_provenance(tmp_path / "jamais_ecrite.png") is None

    def test_le_sidecar_ne_modifie_jamais_l_image_elle_meme(self, tmp_path):
        chemin = tmp_path / "img.png"
        Image.new("RGB", (256, 256)).save(chemin)
        taille_avant = chemin.stat().st_size

        ecrire_provenance(chemin, ProvenanceImage(
            modele="HiDream-I1", modele_version="full", fournisseur="hidream-local"))

        assert chemin.stat().st_size == taille_avant
