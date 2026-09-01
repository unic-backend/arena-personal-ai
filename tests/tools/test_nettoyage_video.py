"""`tools/video/nettoyage.py` — la purge des artefacts vidéo générés.

Trouvé à l'audit du 01/09/2026 (DEC-0037) : `data/montages/` et
`media/rendered/` accumulaient indéfiniment, sans le TTL que
`apps/backend/pieces_jointes.py` applique déjà aux pièces entrantes.
"""
import time

from tools.video.nettoyage import AGE_MAX_SECONDES, purger_artefacts_anciens


def _toucher(chemin, il_y_a_secondes):
    chemin.write_bytes(b"contenu")
    date = time.time() - il_y_a_secondes
    import os
    os.utime(chemin, (date, date))


def test_un_dossier_absent_ne_leve_pas(tmp_path):
    assert purger_artefacts_anciens(tmp_path / "n_existe_pas") == []


def test_un_fichier_recent_est_garde(tmp_path):
    recent = tmp_path / "recent.mp4"
    _toucher(recent, il_y_a_secondes=60)

    retires = purger_artefacts_anciens(tmp_path, age_max_secondes=AGE_MAX_SECONDES)

    assert retires == []
    assert recent.exists()


def test_un_fichier_ancien_est_retire(tmp_path):
    ancien = tmp_path / "ancien.mp4"
    _toucher(ancien, il_y_a_secondes=AGE_MAX_SECONDES + 3600)

    retires = purger_artefacts_anciens(tmp_path, age_max_secondes=AGE_MAX_SECONDES)

    assert retires == [str(ancien)]
    assert not ancien.exists()


def test_seuls_les_fichiers_vraiment_trop_vieux_partent(tmp_path):
    recent = tmp_path / "recent.mp4"
    ancien = tmp_path / "ancien.mp4"
    _toucher(recent, il_y_a_secondes=3600)
    _toucher(ancien, il_y_a_secondes=AGE_MAX_SECONDES * 2)

    retires = purger_artefacts_anciens(tmp_path, age_max_secondes=AGE_MAX_SECONDES)

    assert retires == [str(ancien)]
    assert recent.exists()
    assert not ancien.exists()


def test_un_sous_dossier_n_est_jamais_touche(tmp_path):
    sous_dossier = tmp_path / "vieux_dossier"
    sous_dossier.mkdir()
    date_ancienne = time.time() - AGE_MAX_SECONDES * 2
    import os
    os.utime(sous_dossier, (date_ancienne, date_ancienne))

    retires = purger_artefacts_anciens(tmp_path, age_max_secondes=AGE_MAX_SECONDES)

    assert retires == []
    assert sous_dossier.is_dir()


def test_une_erreur_sur_un_fichier_n_arrete_pas_les_autres(tmp_path, monkeypatch):
    ancien1 = tmp_path / "ancien1.mp4"
    ancien2 = tmp_path / "ancien2.mp4"
    _toucher(ancien1, il_y_a_secondes=AGE_MAX_SECONDES * 2)
    _toucher(ancien2, il_y_a_secondes=AGE_MAX_SECONDES * 2)

    reel_unlink = type(ancien1).unlink

    def unlink_instable(self, *args, **kwargs):
        if self.name == "ancien1.mp4":
            raise OSError("verrouillé")
        return reel_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(ancien1), "unlink", unlink_instable)

    retires = purger_artefacts_anciens(tmp_path, age_max_secondes=AGE_MAX_SECONDES)

    assert retires == [str(ancien2)]
    assert ancien1.exists()
    assert not ancien2.exists()
