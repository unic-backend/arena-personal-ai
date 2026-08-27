"""Le devis PDF à la charte UniC Plaquiste.

Une décision porte tout le reste : **le modèle choisit les articles et les
quantités, Python calcule l'argent.** Un modèle qui se trompe d'article se
voit ; un modèle qui se trompe d'addition passe inaperçu jusqu'au client.

Ces tests écrivent de vrais PDF dans un dossier temporaire et relisent leur
contenu. Aucun n'affirme qu'un fichier existe sans l'avoir ouvert.
"""
import pytest
from pypdf import PdfReader

from agents.plaquiste.devis_pdf import Devis, Ligne, chiffrer, construire
from agents.plaquiste.plaquiste_agent import charger_metier

METIER = charger_metier()


def _devis(**kw) -> Devis:
    defauts = dict(
        client="Client Test", lieu="Dakar", numero="UC-2026-0101-TST",
        date="1 janvier 2026", objet="Objet du devis de test",
        lignes=[Ligne("Plaque standard BA13", 10)],
    )
    defauts.update(kw)
    return Devis(**defauts)


class TestChiffrage:
    """C'est Python qui additionne. Vérifié à la main."""

    def test_une_ligne_est_le_produit_du_prix_par_la_quantite(self):
        calcul = chiffrer(_devis(lignes=[Ligne("Plaque standard BA13", 10)]), METIER)

        assert calcul["lignes"][0]["prix_unitaire"] == 4500
        assert calcul["lignes"][0]["total"] == 45000
        assert calcul["total"] == 45000

    def test_plusieurs_lignes_s_additionnent(self):
        calcul = chiffrer(_devis(lignes=[
            Ligne("Plaque standard BA13", 120),
            Ligne("Montant 48 mm", 150),
            Ligne("Sac enduit", 8),
        ]), METIER)

        attendu = 120 * 4500 + 150 * 1600 + 8 * 12000
        assert calcul["total"] == attendu == 876000

    def test_la_main_oeuvre_est_le_tarif_par_la_surface(self):
        calcul = chiffrer(_devis(lignes=[], main_oeuvre_m2=200), METIER)

        assert calcul["total_main_oeuvre"] == 200 * 5000 == 1000000

    def test_un_article_inconnu_n_est_pas_chiffre(self):
        """Ni prix, ni total, ni contribution au montant : il est nommé."""
        calcul = chiffrer(_devis(lignes=[
            Ligne("Plaque standard BA13", 10),
            Ligne("Spot LED encastre", 8),
        ]), METIER)

        assert calcul["articles_sans_prix"] == ["Spot LED encastre"]
        assert calcul["lignes"][1]["prix_unitaire"] is None
        assert calcul["lignes"][1]["total"] is None
        assert calcul["total"] == 45000, "un article sans prix a ete compte"

    def test_une_quantite_decimale_est_arrondie_au_franc(self):
        calcul = chiffrer(_devis(lignes=[Ligne("Plaque standard BA13", 2.5)], main_oeuvre_m2=None), METIER)
        assert calcul["total"] == 11250

    def test_un_devis_vide_vaut_zero_et_ne_leve_pas(self):
        assert chiffrer(_devis(lignes=[]), METIER)["total"] == 0


class TestRendu:
    def test_le_fichier_est_ecrit_et_lisible(self, tmp_path):
        sortie = tmp_path / "devis.pdf"
        resultat = construire(_devis(), METIER, sortie)

        assert sortie.exists()
        assert resultat["octets"] > 1000
        assert len(PdfReader(str(sortie)).pages) >= 1

    def test_les_informations_legales_figurent_sur_le_document(self, tmp_path):
        sortie = tmp_path / "devis.pdf"
        construire(_devis(), METIER, sortie)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "UniC Plaquiste" in texte
        assert "013141677" in texte          # NINEA
        assert "SN.DKR.2026.A.22010" in texte  # RCCM
        assert "+221 77 708 50 92" in texte

    def test_les_prix_du_document_sont_ceux_de_la_grille(self, tmp_path):
        sortie = tmp_path / "devis.pdf"
        construire(_devis(lignes=[Ligne("Plaque standard BA13", 120)]), METIER, sortie)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "4 500" in texte
        assert "540 000" in texte

    def test_un_article_sans_prix_porte_la_mention_a_confirmer(self, tmp_path):
        """Jamais un chiffre inventé dans un document qui part chez un client."""
        sortie = tmp_path / "devis.pdf"
        construire(_devis(lignes=[Ligne("Spot LED encastre", 8)]), METIER, sortie)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "a confirmer" in texte
        assert "Spot LED encastre" in texte

    def test_les_exclusions_habituelles_figurent(self, tmp_path):
        sortie = tmp_path / "devis.pdf"
        construire(_devis(), METIER, sortie)
        assert "electricite" in PdfReader(str(sortie)).pages[0].extract_text()

    def test_une_facture_porte_le_bon_titre(self, tmp_path):
        sortie = tmp_path / "facture.pdf"
        construire(_devis(type_document="FACTURE"), METIER, sortie)
        assert "FACTURE" in PdfReader(str(sortie)).pages[0].extract_text()

    def test_l_absence_de_logo_n_empeche_pas_le_devis(self, tmp_path):
        """Son logo est un fichier local ; il peut manquer sur une autre machine."""
        sortie = tmp_path / "devis.pdf"
        construire(_devis(), METIER, sortie, logo=tmp_path / "logo_absent.png")
        assert sortie.exists()

    def test_le_dossier_de_sortie_est_cree_au_besoin(self, tmp_path):
        sortie = tmp_path / "sous" / "dossier" / "devis.pdf"
        construire(_devis(), METIER, sortie)
        assert sortie.exists()


class TestCharte:
    def test_les_couleurs_viennent_du_fichier_metier(self):
        from agents.plaquiste.devis_pdf import _couleurs

        c = _couleurs(METIER)
        assert c["bleu"].hexval() == "0x1a3fa0"
        assert c["jaune"].hexval() == "0xf2c200"

    def test_changer_la_charte_change_le_document(self):
        from agents.plaquiste.devis_pdf import _couleurs

        modifie = {**METIER, "charte": {**METIER["charte"], "bleu": "#000000"}}
        assert _couleurs(modifie)["bleu"].hexval() == "0x000000"

    @pytest.mark.parametrize("cle", ["bleu", "jaune"])
    def test_une_charte_absente_retombe_sur_les_couleurs_du_proprietaire(self, cle):
        from agents.plaquiste.devis_pdf import _couleurs

        assert _couleurs({})[cle] == _couleurs(METIER)[cle]
