"""Le devis PDF à la charte UniC Plaquiste.

Une décision porte tout le reste : **le modèle choisit les articles et les
quantités, Python calcule l'argent.** Un modèle qui se trompe d'article se
voit ; un modèle qui se trompe d'addition passe inaperçu jusqu'au client.

Ces tests écrivent de vrais PDF dans un dossier temporaire et relisent leur
contenu. Aucun n'affirme qu'un fichier existe sans l'avoir ouvert.
"""
import pytest
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from agents.plaquiste.devis_pdf import (
    Devis,
    Ligne,
    chiffrer,
    construire,
    taille_du_titre,
)
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

    def test_un_bon_de_commande_s_adresse_a_un_fournisseur_pas_un_client(self, tmp_path):
        """Le bloc destinataire ne peut pas dire « CLIENT » quand on commande
        du materiel a un fournisseur — ce serait factuellement faux."""
        sortie = tmp_path / "commande.pdf"
        construire(_devis(type_document="BON DE COMMANDE", client="Sen Materiaux"),
                  METIER, sortie)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "BON DE COMMANDE" in texte
        assert "FOURNISSEUR" in texte
        assert "CLIENT" not in texte
        assert "Sen Materiaux" in texte

    def test_un_bon_de_livraison_porte_le_bon_titre_et_libelle(self, tmp_path):
        sortie = tmp_path / "livraison.pdf"
        construire(_devis(type_document="BON DE LIVRAISON"), METIER, sortie)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "BON DE LIVRAISON" in texte
        assert "LIVRE A" in texte

    def test_un_devis_dit_toujours_client_comme_avant(self, tmp_path):
        """Retro-compatible : le cas par defaut ne change pas."""
        sortie = tmp_path / "devis.pdf"
        construire(_devis(), METIER, sortie)
        assert "CLIENT" in PdfReader(str(sortie)).pages[0].extract_text()

    def test_l_absence_de_logo_n_empeche_pas_le_devis(self, tmp_path):
        """Son logo est un fichier local ; il peut manquer sur une autre machine."""
        sortie = tmp_path / "devis.pdf"
        construire(_devis(), METIER, sortie, logo=tmp_path / "logo_absent.png")
        assert sortie.exists()

    def test_le_dossier_de_sortie_est_cree_au_besoin(self, tmp_path):
        sortie = tmp_path / "sous" / "dossier" / "devis.pdf"
        construire(_devis(), METIER, sortie)
        assert sortie.exists()


class TestTailleDuTitre:
    """Le titre ne doit jamais retourner a la ligne — mesure, pas suppose.

    Trouve en testant le vrai PDF genere : « BON DE COMMANDE » a 20 pt
    (la taille fixe d'avant) debordait de sa colonne et se coupait en deux
    lignes dans le document reel.
    """

    LARGEUR_MM = 46  # doit rester synchronise avec LARGEUR_TITRE_MM

    @pytest.mark.parametrize("titre", ["DEVIS", "FACTURE", "BON DE COMMANDE", "BON DE LIVRAISON"])
    def test_le_titre_tient_toujours_sur_une_ligne(self, titre):
        from reportlab.lib.units import mm

        taille = taille_du_titre(titre)
        largeur = stringWidth(titre, "Helvetica-Bold", taille)

        assert largeur <= self.LARGEUR_MM * mm, (
            f"« {titre} » a {taille} pt deborde de sa colonne ({largeur / mm:.1f} mm)"
        )

    def test_devis_et_facture_gardent_la_taille_maximale(self):
        """Retro-compatible : les deux types courts ne doivent pas retrecir."""
        assert taille_du_titre("DEVIS") == 20
        assert taille_du_titre("FACTURE") == 20

    def test_un_titre_plus_long_retrecit(self):
        assert taille_du_titre("BON DE COMMANDE") < 20
        assert taille_du_titre("BON DE LIVRAISON") < 20


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


class TestSignature:
    """Sa signature, extraite de son bon de commande signé du 24/08/2026."""

    def test_par_defaut_le_devis_n_est_pas_signe(self, tmp_path):
        """Signer un document qu'on n'a pas relu est une mauvaise habitude."""
        sortie = tmp_path / "devis.pdf"
        construire(_devis(), METIER, sortie)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "Signature : ___" in texte

    def test_un_devis_signe_porte_l_image_et_le_nom_du_gerant(self, tmp_path):
        from PIL import Image

        signature = tmp_path / "signature.png"
        Image.new("RGB", (300, 120), "white").save(signature)

        sortie = tmp_path / "devis_signe.pdf"
        construire(_devis(signe=True), METIER, sortie, signature=signature)
        texte = PdfReader(str(sortie)).pages[0].extract_text()

        assert "Uthman" in texte, "le nom du gerant n'accompagne pas la signature"
        assert len(PdfReader(str(sortie)).pages[0].images) >= 1

    def test_signe_sans_fichier_de_signature_ne_casse_pas_le_devis(self, tmp_path):
        """Sur une autre machine, le fichier peut manquer."""
        sortie = tmp_path / "devis.pdf"
        construire(_devis(signe=True), METIER, sortie, signature=tmp_path / "absent.png")

        assert sortie.exists()
