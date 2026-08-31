"""`stockage_jetons.py` : ce qui fait qu'un jeton OAuth survit a un
redemarrage sur un hebergement sans fichier `.env` (Railway, trouve le
31/08/2026 en testant Gmail juste apres l'avoir connecte pour de vrai)."""
from core.connectors.stockage_jetons import charger_tout, enregistrer


class TestEnregistrerEtCharger:
    def test_un_disque_neuf_ne_leve_pas(self, tmp_path):
        assert charger_tout(str(tmp_path / "neuf.db")) == {}

    def test_une_valeur_ecrite_se_retrouve(self, tmp_path):
        base = str(tmp_path / "jetons.db")
        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "abc123")

        assert charger_tout(base) == {"GOOGLE_REFRESH_TOKEN": "abc123"}

    def test_reecrire_remplace_sans_dupliquer(self, tmp_path):
        base = str(tmp_path / "jetons.db")
        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "ancien")
        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "nouveau")

        assert charger_tout(base) == {"GOOGLE_REFRESH_TOKEN": "nouveau"}

    def test_une_valeur_vide_efface(self, tmp_path):
        base = str(tmp_path / "jetons.db")
        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "abc123")

        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "")

        assert charger_tout(base) == {}

    def test_deux_variables_coexistent(self, tmp_path):
        base = str(tmp_path / "jetons.db")
        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "a")
        enregistrer(base, "AUTRE_JETON", "b")

        assert charger_tout(base) == {"GOOGLE_REFRESH_TOKEN": "a", "AUTRE_JETON": "b"}

    def test_survit_a_une_nouvelle_connexion_a_la_meme_base(self, tmp_path):
        """C'est exactement ce que doit garantir ce module : un nouveau
        processus (donc une nouvelle connexion SQLite) retrouve ce qu'un
        processus precedent y a ecrit."""
        base = str(tmp_path / "jetons.db")
        enregistrer(base, "GOOGLE_REFRESH_TOKEN", "abc123")

        relu = charger_tout(base)  # simule un processus neuf : nouvelle connexion

        assert relu["GOOGLE_REFRESH_TOKEN"] == "abc123"
