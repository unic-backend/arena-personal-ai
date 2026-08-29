"""`FileDeMaintenance` : la mémoire qui évite de redécouvrir le même constat,
et qui ne dit « résolu » que pour une empreinte réellement disparue.
"""
import pytest

from core.guardian.diagnostics import Constat
from core.guardian.file_maintenance import EtatTache, FileDeMaintenance

UN_CONSTAT = Constat(categorie="BUG", gravite="P2", description="test en echec : x",
                     fichier="tests/test_x.py", preuve="AssertionError")


@pytest.fixture
def file(tmp_path):
    return FileDeMaintenance(db_path=str(tmp_path / "maintenance.db"))


class TestEnregistrerConstats:
    def test_un_nouveau_constat_devient_une_tache_decouverte(self, file):
        triage = file.enregistrer_constats([UN_CONSTAT])

        assert triage.nouvelles == 1
        assert triage.revues == 0
        taches = file.ouvertes()
        assert len(taches) == 1
        assert taches[0].etat == EtatTache.DECOUVERTE
        assert taches[0].occurrences == 1

    def test_le_meme_constat_deux_fois_ne_cree_pas_deux_taches(self, file):
        file.enregistrer_constats([UN_CONSTAT])
        triage = file.enregistrer_constats([UN_CONSTAT])

        assert triage.nouvelles == 0
        assert triage.revues == 1
        assert len(file.ouvertes()) == 1
        assert file.ouvertes()[0].occurrences == 2

    def test_la_preuve_est_rafraichie_a_chaque_reapparition(self, file):
        file.enregistrer_constats([UN_CONSTAT])
        autre = Constat(categorie="BUG", gravite="P2", description="test en echec : x",
                        fichier="tests/test_x.py", preuve="ligne differente")

        file.enregistrer_constats([autre])

        assert file.ouvertes()[0].preuve == "ligne differente"


class TestMarquerResolue:
    def test_une_tache_disparue_du_diagnostic_peut_etre_marquee_resolue(self, file):
        file.enregistrer_constats([UN_CONSTAT])

        resolue = file.marquer_resolue(UN_CONSTAT.empreinte)

        assert resolue is True
        assert file.ouvertes() == []

    def test_marquer_resolue_deux_fois_ne_leve_pas(self, file):
        file.enregistrer_constats([UN_CONSTAT])
        file.marquer_resolue(UN_CONSTAT.empreinte)

        assert file.marquer_resolue(UN_CONSTAT.empreinte) is False

    def test_une_empreinte_inconnue_ne_leve_pas(self, file):
        assert file.marquer_resolue("empreinte-qui-n-existe-pas") is False


class TestOuvertes:
    def test_une_tache_terminee_n_apparait_plus(self, file):
        file.enregistrer_constats([UN_CONSTAT])
        file.marquer_resolue(UN_CONSTAT.empreinte)

        assert file.ouvertes() == []
        assert len(file.toutes()) == 1, "l'historique reste, seule la liste ouverte se vide"

    def test_le_filtre_par_categorie_fonctionne(self, file):
        autre = Constat(categorie="QUALITE_CODE", gravite="P5", description="F401",
                        fichier="core/x.py")
        file.enregistrer_constats([UN_CONSTAT, autre])

        assert len(file.ouvertes(categorie="BUG")) == 1
        assert len(file.ouvertes(categorie="QUALITE_CODE")) == 1
        assert len(file.ouvertes()) == 2

    def test_le_tri_met_la_plus_grave_en_premier(self, file):
        grave = Constat(categorie="BUG", gravite="P2", description="grave", fichier="a.py")
        mineure = Constat(categorie="CODE_MORT", gravite="P6", description="mineure", fichier="b.py")
        file.enregistrer_constats([mineure, grave])

        ouvertes = file.ouvertes()

        assert ouvertes[0].description == "grave"
        assert ouvertes[1].description == "mineure"


class TestPersistance:
    def test_une_nouvelle_instance_relit_l_etat_deja_enregistre(self, tmp_path):
        chemin = str(tmp_path / "maintenance.db")
        FileDeMaintenance(db_path=chemin).enregistrer_constats([UN_CONSTAT])

        relue = FileDeMaintenance(db_path=chemin)

        assert len(relue.ouvertes()) == 1
