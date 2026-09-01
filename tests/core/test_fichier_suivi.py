"""Un fichier de configuration relu quand il change, jamais avant.

Ce module est né d'un constat : la **même** forme de défaut a été trouvée
quatre fois dans la nuit du 01/09/2026 — une valeur lue une fois, à la
construction d'un objet lui-même créé au démarrage du serveur, puis servie
comme si elle était actuelle.
"""
import pytest

from core.fichier_suivi import FichierSuivi, date_de


def lire(chemin):
    """Un lecteur qui rend toujours quelque chose, même sans fichier."""
    try:
        return chemin.read_text(encoding="utf-8")
    except OSError:
        return ""


@pytest.fixture
def fichier(tmp_path):
    chemin = tmp_path / "config.txt"
    chemin.write_text("premier", encoding="utf-8")
    return chemin


class TestDateDe:

    def test_un_fichier_absent_n_a_pas_la_date_zero(self, tmp_path):
        """`None` n'est pas `0` : `0` déclencherait une relecture puis plus jamais."""
        assert date_de(tmp_path / "absent.txt") is None

    def test_un_fichier_present_a_une_date(self, fichier):
        assert isinstance(date_de(fichier), float)


class TestFichierSuivi:

    def test_le_contenu_de_depart_est_lu(self, fichier):
        assert FichierSuivi(fichier, lire).actuel() == "premier"

    def test_un_changement_est_vu(self, fichier):
        suivi = FichierSuivi(fichier, lire)
        assert suivi.actuel() == "premier"

        fichier.write_text("second", encoding="utf-8")

        assert suivi.actuel() == "second"

    def test_un_fichier_inchange_n_est_pas_relu(self, fichier):
        lectures = []
        suivi = FichierSuivi(fichier, lambda c: lectures.append(1) or lire(c))
        lectures.clear()

        for _ in range(5):
            suivi.actuel()

        assert lectures == []

    def test_un_fichier_efface_rend_la_valeur_vide_du_lecteur(self, fichier):
        """Servir une configuration disparue est plus dangereux que servir du vide."""
        suivi = FichierSuivi(fichier, lire)
        assert suivi.actuel() == "premier"

        fichier.unlink()

        assert suivi.actuel() == ""

    def test_un_fichier_recree_est_relu(self, fichier):
        suivi = FichierSuivi(fichier, lire)
        fichier.unlink()
        assert suivi.actuel() == ""

        fichier.write_text("revenu", encoding="utf-8")

        assert suivi.actuel() == "revenu"
