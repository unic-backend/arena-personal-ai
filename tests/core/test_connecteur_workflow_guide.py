"""Le guide de procedure protege-t-il ce qu'il ne doit jamais laisser fuir ?

Ce connecteur existe en reponse a une demande d'integrer Mimik
(westpoint-io) — refusee dans sa partie capture en direct (surveillance de
navigateur, sans besoin reel exprime). Ce qui reste : recevoir un workflow
DEJA DECRIT et le transformer en document. Deux familles de tests :

1. **Le module pur** (`core/production/workflow_guide.py`) : redaction,
   garde de chemin, quatre rendus reels — PDF/DOCX relus avec pypdf/python-docx,
   jamais "la fonction a rendu succes" seul.
2. **Le connecteur** : permissions, contrat `Connecteur`, sabotage des gardes.
"""
from pathlib import Path

import pytest
import yaml

from core.actions.resultat import Statut
from core.connectors.base import ControleAcces, EtatSante
from core.connectors.workflow_guide import ConnecteurWorkflowGuide
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions
from core.production.workflow_guide import (
    Etape,
    Workflow,
    chemin_capture_est_sur,
    expurger,
    valider_captures,
    vers_docx,
    vers_html,
    vers_markdown,
    vers_pdf,
)


@pytest.fixture
def capture_reelle(tmp_path: Path) -> Path:
    """Une vraie image PNG, pas un fichier vide : les rendus l'ouvrent pour de vrai."""
    from PIL import Image as ImagePIL

    chemin = tmp_path / "capture.png"
    ImagePIL.new("RGB", (200, 100), color=(10, 20, 30)).save(chemin)
    return chemin


@pytest.fixture
def workflow_de_test(capture_reelle: Path) -> Workflow:
    return Workflow(
        titre="Comment remplir un devis dans ARENA",
        introduction="Petit guide.",
        prerequis=["Avoir le nom du client"],
        etapes=[
            Etape(action="Ouvrir l'espace", description="Choisis le chantier.",
                  capture_ecran=str(capture_reelle)),
            Etape(action="Contacter le client",
                  description="Ecris a contact.fake@exemple.sn si besoin.",
                  avertissement="Verifie l'adresse avant d'envoyer."),
            Etape(action="Enregistrer", description="Le PDF part tout de suite."),
        ],
        conclusion="C'est pret a partager.",
    )


class TestExpurger:
    def test_un_email_est_masque(self):
        assert "@" not in expurger("contact.fake@exemple.sn")

    def test_une_carte_est_masquee(self):
        assert expurger("4111 1111 1111 1111") == "[masque]"

    def test_un_telephone_avec_indicatif_est_masque(self):
        assert "[masque]" in expurger("Appelle le +221 77 123 45 67")

    def test_une_affectation_secrete_a_entropie_haute_est_masquee(self):
        resultat = expurger('api_key = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv"')
        assert "Zq7Z" not in resultat
        assert "[masque]" in resultat

    def test_un_mot_de_passe_factice_a_entropie_basse_reste_visible(self):
        """`changeme` n'a rien d'un secret : le masquer partout deviendrait du bruit."""
        assert expurger('password = "changeme"') == 'password = "changeme"'

    @pytest.mark.parametrize("texte", [
        "Cliquer sur Enregistrer",
        "La hauteur mesure 2,50 m",
        "Le total est de 312 400 FCFA",
    ])
    def test_un_texte_normal_n_est_pas_touche(self, texte):
        assert expurger(texte) == texte

    def test_texte_vide(self):
        assert expurger("") == ""


class TestGardeDeChemin:
    @pytest.mark.parametrize("chemin", ["~/.ssh/id_rsa", "~/.aws/credentials", "~/.gnupg"])
    def test_chemin_sensible_refuse(self, chemin):
        assert chemin_capture_est_sur(chemin) is not None

    @pytest.mark.parametrize("segment", [".ssh", ".aws", ".gnupg", ".git-credentials", ".netrc"])
    def test_segment_interdit_seul_suffit_a_refuser(self, tmp_path, segment):
        """Isole le garde de segment des deux autres filtres (existence,
        extension) : une vraie image PNG existante, dans un dossier au nom
        interdit, doit quand meme etre refusee — sinon le test ci-dessus
        passe pour la mauvaise raison (le fichier n'existe pas)."""
        from PIL import Image as ImagePIL

        dossier = tmp_path / segment
        dossier.mkdir()
        chemin = dossier / "capture.png"
        ImagePIL.new("RGB", (10, 10)).save(chemin)

        assert chemin_capture_est_sur(str(chemin)) is not None

    def test_fichier_env_refuse(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=1")
        assert chemin_capture_est_sur(str(tmp_path / ".env")) is not None

    def test_fichier_env_refuse_meme_existant_et_image(self, tmp_path):
        """Isole le garde de nom de fichier : meme un vrai fichier existant,
        renomme .env, doit etre refuse pour la bonne raison (le nom), pas
        parce qu'il serait absent ou d'une mauvaise extension."""
        from PIL import Image as ImagePIL

        chemin = tmp_path / ".env"
        ImagePIL.new("RGB", (10, 10)).save(chemin, format="PNG")
        assert chemin_capture_est_sur(str(chemin)) is not None

    def test_capture_introuvable_refusee(self, tmp_path):
        assert chemin_capture_est_sur(str(tmp_path / "absent.png")) is not None

    def test_extension_non_image_refusee(self, tmp_path):
        fichier = tmp_path / "capture.txt"
        fichier.write_text("x")
        assert chemin_capture_est_sur(str(fichier)) is not None

    def test_une_vraie_capture_png_est_acceptee(self, capture_reelle):
        assert chemin_capture_est_sur(str(capture_reelle)) is None

    def test_valider_captures_signale_sans_lever(self, tmp_path):
        wf = Workflow(titre="T", etapes=[
            Etape(action="a", capture_ecran=str(tmp_path / "absente.png"))])
        problemes = valider_captures(wf)
        assert len(problemes) == 1
        assert problemes[0].etape_index == 0


class TestRendusReels:
    """Chaque fichier est RELU, pas seulement "produit sans erreur"."""

    def test_pdf_reel_contient_le_titre_et_masque_l_email(self, workflow_de_test, tmp_path):
        from pypdf import PdfReader

        chemin = vers_pdf(workflow_de_test, tmp_path / "guide.pdf")
        assert chemin.is_file() and chemin.stat().st_size > 0

        texte = "".join(p.extract_text() or "" for p in PdfReader(str(chemin)).pages)
        assert "Comment remplir un devis" in texte
        assert "contact.fake@exemple.sn" not in texte
        assert "[masque]" in texte

    def test_docx_reel_contient_le_titre_masque_l_email_et_l_image(self, workflow_de_test, tmp_path):
        import docx

        chemin = vers_docx(workflow_de_test, tmp_path / "guide.docx")
        d = docx.Document(str(chemin))
        texte = "\n".join(p.text for p in d.paragraphs)

        assert "Comment remplir un devis" in texte
        assert "contact.fake@exemple.sn" not in texte
        assert "[masque]" in texte
        assert len(d.inline_shapes) == 1, "l'image fournie doit apparaitre exactement une fois"

    def test_html_est_autonome_et_masque_l_email(self, workflow_de_test):
        rendu = vers_html(workflow_de_test)
        assert "contact.fake@exemple.sn" not in rendu
        assert "[masque]" in rendu
        assert "data:image/png;base64," in rendu, "l'image doit etre embarquee, pas referencee"
        assert "<script" not in rendu.lower()

    def test_markdown_masque_l_email_et_reference_l_image(self, workflow_de_test):
        rendu = vers_markdown(workflow_de_test)
        assert "contact.fake@exemple.sn" not in rendu
        assert "[masque]" in rendu
        assert "![" in rendu

    def test_une_capture_refusee_n_empeche_pas_le_rendu(self, tmp_path):
        """Un chemin sensible en capture ne doit ni lever, ni etre inclus."""
        wf = Workflow(titre="T", etapes=[
            Etape(action="a", capture_ecran=str(Path.home() / ".ssh" / "id_rsa"))])

        rendu_html = vers_html(wf)
        assert "<img" not in rendu_html

        chemin_pdf = vers_pdf(wf, tmp_path / "t.pdf")
        assert chemin_pdf.is_file()


class TestCapacitesEtSante:
    def test_une_capacite_qui_ecrit(self):
        capacites = ConnecteurWorkflowGuide().capacites()
        assert set(capacites) == {"generer"}
        assert capacites["generer"].ecriture is True

    def test_authentifier_toujours_vrai(self):
        assert ConnecteurWorkflowGuide().authentifier() is True

    def test_sonde_operationnelle(self):
        assert ConnecteurWorkflowGuide().sonder().etat is EtatSante.OPERATIONNEL


PARAMETRES_MINIMAUX = {
    "titre": "Guide de test",
    "etapes": [{"action": "Faire quelque chose"}],
}


class TestExecutionReelle:
    def test_genere_un_vrai_fichier_pdf(self, tmp_path):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", format="pdf", **PARAMETRES_MINIMAUX)

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert Path(resultat.preuve).is_file()
        assert resultat.detail["format"] == "pdf"

    @pytest.mark.parametrize("fmt", ["pdf", "docx", "html", "markdown"])
    def test_genere_chaque_format(self, tmp_path, fmt):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", format=fmt, **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert Path(resultat.preuve).suffix == {"markdown": ".md"}.get(fmt, f".{fmt}")

    def test_format_inconnu_est_un_echec(self, tmp_path):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", format="rtf", **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.ECHEC

    def test_sans_titre_est_un_echec(self, tmp_path):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", format="pdf", etapes=[{"action": "a"}])
        assert resultat.statut is Statut.ECHEC

    def test_sans_etape_est_un_echec(self, tmp_path):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", format="pdf", titre="T")
        assert resultat.statut is Statut.ECHEC

    def test_une_capture_sensible_est_signalee_sans_faire_echouer(self, tmp_path):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path)
        parametres = {
            "titre": "Guide",
            "etapes": [{"action": "a", "capture_ecran": str(Path.home() / ".ssh" / "id_rsa")}],
        }
        resultat = connecteur.executer_confirmee("generer", format="pdf", **parametres)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert len(resultat.detail["captures_ignorees"]) == 1

    def test_url_seulement_si_ecrit_dans_rendered_dir(self, tmp_path, monkeypatch):
        import core.connectors.workflow_guide as module

        monkeypatch.setattr(module, "RENDERED_DIR", tmp_path)
        connecteur = ConnecteurWorkflowGuide()  # utilise RENDERED_DIR par defaut

        resultat = connecteur.executer_confirmee("generer", format="pdf", **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["url"].startswith("/media/rendered/")

    def test_pas_d_url_hors_rendered_dir(self, tmp_path):
        connecteur = ConnecteurWorkflowGuide(dossier=tmp_path / "ailleurs")
        resultat = connecteur.executer_confirmee("generer", format="pdf", **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert "url" not in resultat.detail


class TestLeCoupeCircuitWriteFilesBloqueLaGeneration:
    def test_generer_refuse_sous_write_files_eteint(self, tmp_path):
        politique = tmp_path / "politique.yaml"
        politique.write_text(yaml.safe_dump({"services": {"workflow_guide": {"document": {
            "decision": "ALLOWED", "risque": "LOW", "interrupteur": "WRITE_FILES"}}}}),
            encoding="utf-8")
        permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
        permissions.permissions.update({"WRITE_FILES": False})

        connecteur = ConnecteurWorkflowGuide(
            dossier=tmp_path / "sortie",
            acces=ControleAcces(permissions=permissions,
                                politique=PolitiqueDePermissions(chemin=politique)))

        resultat = connecteur.executer("generer", format="pdf", **PARAMETRES_MINIMAUX)

        assert resultat.statut is Statut.REFUSE, resultat.message
        assert not (tmp_path / "sortie").exists(), "un fichier a ete ecrit malgre WRITE_FILES eteint"


class TestLaVraiePolitiqueLivree:
    def test_generer_reste_sous_write_files_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("workflow_guide", "document")

        assert regle is not None, "workflow_guide.document a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"
        assert regle.get("interrupteur") == "WRITE_FILES"
