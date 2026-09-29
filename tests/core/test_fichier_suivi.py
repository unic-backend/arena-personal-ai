"""Un fichier de configuration relu quand il change, jamais avant.

Ce module est né d'un constat : la **même** forme de défaut a été trouvée
quatre fois dans la nuit du 01/09/2026 — une valeur lue une fois, à la
construction d'un objet lui-même créé au démarrage du serveur, puis servie
comme si elle était actuelle.
"""
import os

import pytest

from core.fichier_suivi import FichierSuivi, date_de, empreinte_de


def figer_la_date(chemin, reference):
    """Redonne à `chemin` exactement la date de `reference`.

    Sans ça, ces tests dépendent de la granularité du système de fichiers :
    ils passeraient sous ext4 (nanosecondes) et échoueraient sur un partage
    réseau, ce qui est **l'inverse** de ce qu'on veut d'un test de ce défaut.
    Figer la date reproduit à volonté, et partout, la seule condition qui
    compte : le fichier a changé, sa date non.
    """
    etat = os.stat(reference)
    os.utime(chemin, ns=(etat.st_atime_ns, etat.st_mtime_ns))


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


class TestEmpreinteDe:
    """Ce qui décide vraiment d'une relecture, depuis le 29/09/2026.

    La date seule ne suffisait pas : deux écritures dans le même tic
    d'horloge du système de fichiers la laissent identique, et une règle de
    permission durcie n'était alors jamais appliquée.
    """

    def test_un_fichier_absent_n_a_pas_d_empreinte(self, tmp_path):
        assert empreinte_de(tmp_path / "absent.txt") is None

    def test_un_fichier_inchange_garde_la_meme_empreinte(self, fichier):
        assert empreinte_de(fichier) == empreinte_de(fichier)

    def test_un_contenu_different_a_meme_date_et_meme_taille_change_l_empreinte(
            self, fichier):
        """Le cas réel : `4500` devient `5200`. Même date, même taille, même inode."""
        avant = empreinte_de(fichier)
        temoin = fichier.parent / "temoin"
        temoin.write_bytes(b"x")
        figer_la_date(temoin, fichier)

        fichier.write_text("PREMIER", encoding="utf-8")  # 7 octets, comme "premier"
        figer_la_date(fichier, temoin)

        apres = empreinte_de(fichier)
        assert os.stat(fichier).st_mtime_ns == avant[0], "la date devait rester figée"
        assert os.stat(fichier).st_size == avant[1], "la taille devait rester la même"
        assert apres != avant

    def test_au_dela_du_plafond_l_empreinte_du_contenu_n_est_pas_calculee(
            self, fichier, monkeypatch):
        """Un gros fichier n'est pas relu à chaque appel : métadonnées seules."""
        monkeypatch.setattr("core.fichier_suivi.PLAFOND_CONTENU", 0)

        assert empreinte_de(fichier)[3] is None

    def test_un_fichier_illisible_ne_leve_pas(self, fichier, monkeypatch):
        """Lever figerait l'ancienne valeur — le défaut que ce module empêche."""
        def refuser(_self):
            raise PermissionError("droits retirés entre le stat et la lecture")

        monkeypatch.setattr("pathlib.Path.read_bytes", refuser)

        empreinte = empreinte_de(fichier)
        assert empreinte is not None and empreinte[3] is None


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

    def test_un_changement_est_vu_meme_si_la_date_ne_bouge_pas(self, fichier):
        """Le défaut du 29/09/2026, reproduit à volonté plutôt qu'au hasard."""
        suivi = FichierSuivi(fichier, lire)
        assert suivi.actuel() == "premier"
        temoin = fichier.parent / "temoin"
        temoin.write_bytes(b"x")
        figer_la_date(temoin, fichier)

        fichier.write_text("PREMIER", encoding="utf-8")  # même longueur
        figer_la_date(fichier, temoin)

        assert suivi.actuel() == "PREMIER"

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
