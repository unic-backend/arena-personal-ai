"""Selection dynamique des roles executifs (mission §6/§39)."""
import pytest

from core.executive.selection import MAXIMUM, identifiants, par_identifiant, selectionner


class TestZeroEstUneReponse:
    def test_bonjour_ne_convoque_personne(self):
        assert selectionner("Bonjour, comment vas-tu ?") == []

    def test_texte_vide(self):
        assert selectionner("") == []
        assert selectionner("   ") == []


class TestSelectionParDomaine:
    def test_tache_a_marketing_strategie(self):
        """Mission §39, TACHE A : strategie marketing -> marketing/vente/recherche."""
        roles = [r.identifiant for r in selectionner(
            "Comment ameliorer notre strategie d'acquisition client et notre positionnement marche ?")]
        assert "strategie_marche" in roles

    def test_tache_b_tresorerie_finance_operations(self):
        """Mission §39, TACHE B : probleme de tresorerie -> finance/operations."""
        roles = [r.identifiant for r in selectionner(
            "Nous avons un probleme de tresorerie ce mois-ci, le budget est serre.")]
        assert "finance" in roles

    def test_tache_c_contrat_fournisseur(self):
        """Mission §39, TACHE C : contrat fournisseur -> approvisionnement/risque."""
        roles = [r.identifiant for r in selectionner(
            "Ce fournisseur nous propose un contrat, mais je crains une dependance trop forte.")]
        assert "approvisionnement" in roles
        assert "risque" in roles

    def test_tache_d_code_ne_convoque_aucun_role_affaires(self):
        """Mission §39, TACHE D : l'Executive ne doit JAMAIS detourner une
        question de code."""
        assert selectionner("Corrige ce bug dans le module d'authentification") == []

    def test_tache_e_video_ne_convoque_aucun_role_affaires(self):
        """Mission §39, TACHE E : idem pour la video."""
        assert selectionner("Genere-moi une video promotionnelle de mon chantier") == []


class TestPlafond:
    def test_jamais_plus_que_le_maximum(self):
        texte = ("marge tresorerie delai chantier fournisseur contrat risque retard "
                 "concurrent marche embauche recrutement equipe")
        roles = selectionner(texte)
        assert len(roles) <= MAXIMUM

    def test_maximum_reglable(self):
        texte = "marge delai risque fournisseur concurrent embauche"
        assert len(selectionner(texte, maximum=1)) == 1


class TestReconnaissanceDeMots:
    def test_sous_chaine_ne_declenche_pas(self):
        # "cout" ne doit pas matcher a l'interieur d'un autre mot.
        assert selectionner("le decoupage du bois") == []

    def test_accents_ignores(self):
        assert [r.identifiant for r in selectionner("quelle est notre rentabilité ?")] == ["finance"]


class TestCatalogue:
    def test_par_identifiant_connu(self):
        assert par_identifiant("finance").domaine == "Finance d'affaires"

    def test_par_identifiant_inconnu_leve(self):
        with pytest.raises(KeyError):
            par_identifiant("inexistant")

    def test_identifiants_couvre_tous_les_roles(self):
        assert set(identifiants()) == {
            "finance", "operations", "risque", "approvisionnement",
            "strategie_marche", "ressources_humaines",
        }
