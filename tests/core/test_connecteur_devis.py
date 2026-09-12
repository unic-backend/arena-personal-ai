"""Le devis UniC Plaquiste : chiffrer librement, et ecrire le PDF tout de suite.

**Le 04/09/2026, le proprietaire a retire la confirmation sur ce seul point** :
« si tu demandes un pdf il le fait simplement [...] je veux ca a tout prix ».
Ce qui rend le choix tenable, et que ces tests tiennent :

`test_produire_ecrit_le_pdf_tout_de_suite` : plus d'accord prealable — le
fichier est ecrit, et le succes est ce fichier.
`test_le_pdf_produit_porte_l_adresse_par_laquelle_l_ouvrir` : sans elle, le
PDF existe et reste inatteignable depuis un telephone.
`test_le_coupe_circuit_write_files_bloque_encore_le_pdf` : la protection n'a
pas disparu avec la confirmation.

Le PDF reste chez lui : il le relit, et c'est LUI qui l'envoie. Ce qui quitte
la machine — un e-mail, une publication — garde sa confirmation.

Le troisieme qui compte est `test_sans_destinataire_rien_n_est_produit` : un
devis adresse a la mauvaise personne est pire qu'un devis absent.
"""
import pytest

from agents.plaquiste.plaquiste_agent import charger_metier
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.devis import DevisConnector, lignes_depuis, lignes_depuis_parametres

#: La demande de son devis de reference UC-2026-0804-FG2.
DEMANDE = "18 parois de 5,40 x 2,50 m"

DESTINATAIRE = {"client": "Fast Group", "lieu": "Medina", "objet": "cloisons BA13"}


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "devis"


@pytest.fixture
def connecteur(dossier):
    return DevisConnector(dossier=dossier)


def fichiers(dossier):
    """Ce que le dossier de sortie contient reellement."""
    return sorted(p.name for p in dossier.glob("*")) if dossier.exists() else []


# --- Les deux tests que l'integration doit passer -------------------------------

def test_produire_ecrit_le_pdf_tout_de_suite(connecteur, dossier):
    """Le PDF ne demande plus d'accord prealable — decision du proprietaire du
    04/09/2026 (« si tu demandes un pdf il le fait simplement »).

    Ce qui rend ce choix tenable est teste juste en dessous : le fichier reste
    chez lui, et le coupe-circuit WRITE_FILES le bloque toujours.
    """
    resultat = connecteur.executer("produire", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES, resultat.message
    assert fichiers(dossier), "aucun fichier ecrit alors que le PDF etait demande"
    assert resultat.preuve, "un succes sans preuve ne se construit pas"


def test_le_pdf_produit_porte_l_adresse_par_laquelle_l_ouvrir(dossier, monkeypatch):
    """Sans cette adresse, le fichier existe et reste inatteignable depuis un
    telephone : le chemin sur le disque du serveur n'y veut rien dire. C'est
    le seul chemin par lequel le lien lui parvient depuis que la confirmation
    — qui le portait — ne s'affiche plus pour un devis.

    Le dossier de sortie EST celui que `GET /media/rendered/{nom:path}` sert : c'est
    cette egalite, et elle seule, qui autorise a annoncer une adresse.
    """
    monkeypatch.setattr("core.connectors.devis.RENDERED_DIR", dossier)

    resultat = DevisConnector(dossier=dossier).executer(
        "produire", demande=DEMANDE, **DESTINATAIRE)

    adresse = resultat.detail.get("url")
    assert adresse, "aucune adresse d'ouverture dans le resultat"
    assert adresse.startswith("/media/rendered/"), adresse
    assert adresse.endswith(".pdf"), adresse


def test_un_pdf_ecrit_hors_du_dossier_servi_n_annonce_aucune_adresse(connecteur):
    """L'inverse, et il compte autant : un fichier que le serveur ne sert pas
    n'a pas d'adresse — on ne fabrique pas un lien qui ferait 404."""
    resultat = connecteur.executer("produire", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES, resultat.message
    assert resultat.detail.get("url") is None


def test_le_coupe_circuit_write_files_bloque_encore_le_pdf(dossier, tmp_path):
    """Retirer la confirmation n'a PAS retire la protection.

    `WRITE_FILES` reste declare sur `plaquiste.document` : l'eteindre coupe
    encore toute production de PDF. C'est ce qui distingue « il n'a plus a
    donner son accord a chaque fois » de « plus rien ne le protege ».
    """
    import yaml

    from core.permissions.controle import ControleAcces
    from core.permissions.permission_manager import PermissionManager
    from core.permissions.politique import PolitiqueDePermissions

    politique = tmp_path / "politique.yaml"
    politique.write_text(yaml.safe_dump({"services": {"plaquiste": {"document": {
        "decision": "ALLOWED", "risque": "MEDIUM", "interrupteur": "WRITE_FILES"}}}}),
        encoding="utf-8")
    permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
    permissions.permissions.update({"WRITE_FILES": False})

    connecteur = DevisConnector(
        dossier=dossier,
        acces=ControleAcces(permissions=permissions,
                            politique=PolitiqueDePermissions(chemin=politique)))

    resultat = connecteur.executer("produire", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.REFUSE, resultat.message
    assert fichiers(dossier) == [], "un PDF a ete ecrit malgre WRITE_FILES eteint"


def test_un_devis_produit_laisse_un_fichier_qui_est_sa_preuve(connecteur, dossier):
    resultat = connecteur.executer_confirmee("produire", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve, "un succes sans preuve ne se construit pas"
    ecrit = dossier / resultat.preuve.rsplit("/", 1)[-1]
    assert ecrit.exists(), "la preuve designe un fichier qui n'existe pas"
    assert ecrit.stat().st_size > 0, "le devis produit est vide"
    assert resultat.detail["octets"] == ecrit.stat().st_size


# --- FACTURE : le renderer savait deja, seule l'orchestration manquait ----------

def test_sans_type_document_le_pdf_reste_un_devis(connecteur, dossier):
    """Retro-compatible : aucun appelant existant n'est affecte."""
    pytest.importorskip("pypdf", reason="pypdf n'est pas installe.")
    from pypdf import PdfReader

    resultat = connecteur.executer_confirmee("produire", demande=DEMANDE, **DESTINATAIRE)

    ecrit = dossier / resultat.preuve.rsplit("/", 1)[-1]
    texte = PdfReader(str(ecrit)).pages[0].extract_text()
    assert "DEVIS" in texte
    assert "Devis" in resultat.message


def test_type_document_facture_est_ecrit_dans_le_vrai_pdf(connecteur, dossier):
    """Verifie le fichier reellement produit, pas seulement le parametre transmis."""
    pytest.importorskip("pypdf", reason="pypdf n'est pas installe.")
    from pypdf import PdfReader

    resultat = connecteur.executer_confirmee(
        "produire", demande=DEMANDE, type_document="FACTURE", **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES
    ecrit = dossier / resultat.preuve.rsplit("/", 1)[-1]
    texte = PdfReader(str(ecrit)).pages[0].extract_text()
    assert "FACTURE" in texte
    assert "Facture" in resultat.message, "le message de succes doit nommer ce qui a ete ecrit"


# --- Le destinataire n'est jamais devine -----------------------------------------

def test_sans_destinataire_rien_n_est_produit(connecteur, dossier):
    resultat = connecteur.executer_confirmee("produire", demande=DEMANDE, lieu="Medina")

    assert resultat.statut is Statut.ECHEC
    assert "client" in resultat.message and "objet" in resultat.message, (
        "le refus ne nomme pas ce qui manque")
    assert fichiers(dossier) == [], "un devis sans destinataire a ete ecrit"


# --- Chiffrer ne coute rien -------------------------------------------------------

def test_chiffrer_n_ecrit_aucun_fichier(connecteur, dossier):
    resultat = connecteur.executer("chiffrer", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES, "voir un total demande une confirmation"
    assert fichiers(dossier) == [], "le chiffrage a ecrit sur le disque"


def test_le_total_vient_de_la_grille_de_prix_pas_de_l_appelant(connecteur):
    resultat = connecteur.executer("chiffrer", demande=DEMANDE, prix=1, total=1, **DESTINATAIRE)

    assert resultat.detail["chiffrage"]["total"] == 3298000, (
        "un prix passe par l'appelant a change le total")


def test_un_article_hors_grille_est_nomme_jamais_chiffre_au_juge():
    # Ses ratios reels, mais une grille de prix amputee a un seul article.
    metier = dict(charger_metier())
    metier["prix_materiaux"] = {"Plaque standard BA13": 4500}
    connecteur = DevisConnector(metier=metier)

    chiffrage = connecteur.executer("chiffrer", demande=DEMANDE, **DESTINATAIRE).detail["chiffrage"]

    assert chiffrage["articles_sans_prix"], "des articles absents de la grille ont recu un prix"


# --- Sans dimensions lues, rien ---------------------------------------------------

def test_sans_dimension_lue_rien_n_est_chiffre(connecteur):
    resultat = connecteur.executer("chiffrer", demande="fais-moi un devis", **DESTINATAIRE)

    assert resultat.statut is Statut.ECHEC
    assert "dimension" in resultat.message.lower()


def test_sans_dimension_lue_aucun_document_n_est_produit(connecteur, dossier):
    resultat = connecteur.executer_confirmee("produire", demande="un devis stp", **DESTINATAIRE)

    assert resultat.statut is Statut.ECHEC
    assert fichiers(dossier) == []


def test_lignes_depuis_rend_une_liste_vide_quand_rien_n_est_lu():
    assert lignes_depuis("bonjour", {"prix_materiaux": {}}) == []


# --- Des lignes deja calculees (metre d'un plan mesure) --------------------------
# Mesure du 30/08/2026 : sans ce chemin, un devis demande apres la mesure d'un
# PLAN (pas de chiffres tapes) echouait a la confirmation avec « aucune
# dimension lue » — le calcul affiche dans la reponse ne rejoignait jamais le
# PDF reellement ecrit. Voir tests/test_plaquiste_bout_en_bout.py pour la
# chaine complete plan -> metre -> devis -> PDF.

def test_lignes_depuis_parametres_construit_les_lignes_fournies():
    lignes = lignes_depuis_parametres(
        [{"designation": "Plaque standard BA13", "quantite": 23}])

    assert lignes[0].designation == "Plaque standard BA13"
    assert lignes[0].quantite == 23


def test_des_lignes_fournies_evitent_de_relire_la_phrase(connecteur, dossier):
    """Une phrase sans dimension reconnue produit quand meme un devis si les
    lignes sont deja fournies — le cas d'un plan mesure, jamais dicte en texte."""
    resultat = connecteur.executer_confirmee(
        "produire", demande="fais le pdf du devis pour le plafond mesure",
        lignes=[{"designation": "Plaque standard BA13", "quantite": 23}],
        **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES
    assert fichiers(dossier), "aucun fichier ecrit alors que des lignes etaient fournies"


def test_des_lignes_fournies_priment_sur_une_phrase_qui_en_dicterait_d_autres(connecteur, dossier):
    """Le connecteur ne redevine rien depuis le texte quand l'appelant a deja
    fait le calcul : ses lignes gagnent, meme si la phrase en dirait d'autres."""
    resultat = connecteur.executer_confirmee(
        "produire", demande=DEMANDE,  # "18 parois de 5,40 x 2,50 m"
        lignes=[{"designation": "Plaque standard BA13", "quantite": 5}],
        **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["chiffrage"]["total"] == 5 * 4500


# --- La sonde mesure, elle ne suppose pas ------------------------------------------

def test_sans_grille_de_prix_la_sonde_dit_ce_qui_manque():
    sante = DevisConnector(metier={}).sonder()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "metier.yaml" in sante.ce_qui_manque
    assert sante.mesure_le, "une sante sans date n'est pas une mesure"


def test_avec_sa_grille_la_sonde_compte_les_articles(connecteur):
    sante = connecteur.sonder()

    assert sante.etat is EtatSante.OPERATIONNEL
    assert "28" in sante.message, "la sonde n'annonce pas la grille reellement chargee"


# --- Ce que les capacites declarent -------------------------------------------------

def test_seule_la_production_est_declaree_comme_ecriture(connecteur):
    ecritures = {nom for nom, cap in connecteur.capacites().items() if cap.ecriture}

    assert ecritures == {"produire"}


class TestLeDevisSOuvreDepuisSonTelephone:
    """Un PDF que son téléphone ne peut pas ouvrir n'a servi à personne.

    Défaut mesuré le 02/09/2026. Les devis étaient écrits dans `data/devis/` :
    **personne ne lit ce dossier, et aucune route ne le sert.** Le fichier
    existait sur le disque du PC et nulle part ailleurs, alors que le
    propriétaire travaille depuis son téléphone. Il demandait « avec mon
    téléphone il peut afficher le pdf ? » — la réponse était non.

    Ils sortent maintenant dans `media/rendered/`, servi par
    `GET /media/rendered/{nom:path}` derrière `verify_media_access`. Réutiliser
    cette route plutôt qu'en ouvrir une seconde compte : elle a remplacé un
    `StaticFiles` qui servait n'importe quel fichier à qui devinait son nom.
    """

    def test_le_dossier_par_defaut_est_celui_qui_est_servi(self):
        from apps.backend.config import RENDERED_DIR
        from core.connectors.devis import DOSSIER_DEVIS

        assert DOSSIER_DEVIS == RENDERED_DIR

    def test_un_devis_produit_porte_son_adresse(self):
        """L'URL est ce qui rend le fichier atteignable ; sans elle, rien."""
        connecteur = DevisConnector(metier=charger_metier())

        resultat = connecteur.executer_confirmee(
            "produire", demande=DEMANDE, **DESTINATAIRE)

        assert resultat.statut is Statut.SUCCES
        url = (resultat.detail or {}).get("url")
        assert url, "le devis produit ne dit pas où l'ouvrir"
        assert url.startswith("/media/rendered/")
        assert url.endswith(".pdf")
        assert url == f"/media/rendered/{__import__('pathlib').Path(resultat.preuve).name}"

    def test_un_dossier_choisi_par_l_appelant_ne_promet_aucune_adresse(self, dossier):
        """Écrit ailleurs, le fichier n'est servi par aucune route : le dire
        plutôt que rendre un lien qui répondrait 404."""
        connecteur = DevisConnector(metier=charger_metier(), dossier=dossier)

        resultat = connecteur.executer_confirmee(
            "produire", demande=DEMANDE, **DESTINATAIRE)

        assert resultat.statut is Statut.SUCCES
        assert (resultat.detail or {}).get("url") is None


def test_la_vraie_politique_livree_ecrit_le_pdf_sans_accord_mais_sous_coupe_circuit():
    """Ce que le fichier LIVRE dit, pas ce qu'un test se fabrique.

    Trouve par sabotage le 04/09/2026 : `test_le_coupe_circuit_write_files_...`
    ecrit sa propre politique, donc il prouve que le mecanisme marche et rien
    de plus. Retirer `interrupteur: WRITE_FILES` de
    `config/permissions_services.yaml` ne faisait echouer aucun test — la
    protection pouvait disparaitre en silence. Celui-ci lit le vrai fichier.
    """
    from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

    regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("plaquiste", "document")

    assert regle is not None, "plaquiste.document a disparu de la politique livree"
    assert regle.get("decision") == "ALLOWED", (
        "le PDF redemande un accord : decision du 04/09/2026 annulee sans decision")
    assert regle.get("interrupteur") == "WRITE_FILES", (
        "le coupe-circuit a disparu : plus rien ne peut arreter l'ecriture de fichiers")
