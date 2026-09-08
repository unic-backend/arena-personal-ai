"""Le connecteur de conversion de fichiers (DEC-0074, mission
« File_Converter_Pro ») : chaque moteur est réellement invoqué — aucun mock
sur LibreOffice/Pillow/CairoSVG/WeasyPrint/pypdfium2/ffmpeg, tous
véritablement installés dans l'environnement de test — parce qu'un mock ici
prouverait seulement que le code appelle une fonction, jamais qu'un fichier
utilisable en sort.

Trois sabotages ont trouvé un vrai défaut pendant l'écriture de ce
connecteur, chacun tenu par une classe de ce fichier :

1. `soffice` rend 0 sur une conversion PDF -> DOCX SANS `--infilter`
   explicite, sans avoir rien écrit — `TestValidationDeLaSortie`.
2. Un `.docx` rempli d'octets arbitraires devient, via LibreOffice, un PDF
   de plusieurs Ko parfaitement valide — un « succès » qui ne prouve rien
   sur le fichier d'origine — `TestCoherenceFormatSource`.
3. Une archive ZIP peut viser `../../evil.txt` ou multiplier ses membres —
   `TestArchive`.
"""
import subprocess
import zipfile

import pytest
import yaml

from core.actions.resultat import Statut
from core.connectors.base import ControleAcces
from core.connectors.file_conversion import ConnecteurFileConversion
from core.connectors.registre import RegistreConnecteurs
from core.execution.travaux import FileDeTravaux
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions
from core.production.conversion import registre, securite, validation
from core.production.conversion.moteurs import MoteurEchec


def _fichier_docx(tmp_path, texte="Texte réel pour la conversion."):
    from docx import Document
    d = Document()
    d.add_paragraph(texte)
    chemin = tmp_path / "source.docx"
    d.save(chemin)
    return chemin


def _fichier_image(tmp_path, nom="source.png", taille=(30, 20), couleur=(200, 50, 50), mode="RGB"):
    from PIL import Image
    chemin = tmp_path / nom
    Image.new(mode, taille, couleur).save(chemin)
    return chemin


class TestCapacites:
    def test_quatre_capacites_qui_ecrivent_deux_qui_lisent(self):
        capacites = ConnecteurFileConversion().capacites()
        assert set(capacites) == {
            "convertir", "convertir_lot", "compresser", "extraire",
            "etat_lot", "formats_disponibles",
        }
        for nom in ("convertir", "convertir_lot", "compresser", "extraire"):
            assert capacites[nom].ecriture is True
            assert capacites[nom].action == "document"
        for nom in ("etat_lot", "formats_disponibles"):
            assert capacites[nom].ecriture is False
            assert capacites[nom].action == "lecture"


class TestSonde:
    def test_operationnel_quand_au_moins_un_moteur_repond(self):
        sante = ConnecteurFileConversion().sonder()
        assert sante.etat.value == "OPERATIONAL", sante.message

    def test_non_configure_quand_rien_n_est_disponible(self, monkeypatch):
        monkeypatch.setattr(registre, "matrice_disponibilite", lambda: [
            {"source": "docx", "cible": "pdf", "disponible": False, "moteurs": []},
        ])
        sante = ConnecteurFileConversion().sonder()
        assert sante.etat.value == "NOT_CONFIGURED"


class TestSecuriteChemin:
    def test_chemin_sensible_refuse(self):
        connecteur = ConnecteurFileConversion()
        resultat = connecteur.executer("convertir", entree="~/.ssh/id_rsa", format_cible="pdf")
        assert resultat.statut is Statut.ECHEC
        assert "sensible" in resultat.message

    def test_fichier_introuvable_est_un_echec(self, tmp_path):
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        resultat = connecteur.executer(
            "convertir", entree=str(tmp_path / "n-existe-pas.docx"), format_cible="pdf")
        assert resultat.statut is Statut.ECHEC
        assert "introuvable" in resultat.message

    def test_fichier_vide_est_un_echec(self, tmp_path):
        vide = tmp_path / "vide.docx"
        vide.write_bytes(b"")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        resultat = connecteur.executer("convertir", entree=str(vide), format_cible="pdf")
        assert resultat.statut is Statut.ECHEC
        assert "vide" in resultat.message

    def test_fichier_trop_volumineux_est_un_echec(self, tmp_path, monkeypatch):
        monkeypatch.setattr(securite, "TAILLE_MAX_DEFAUT_OCTETS", 10)
        gros = tmp_path / "gros.docx"
        gros.write_bytes(b"x" * 100)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        resultat = connecteur.executer("convertir", entree=str(gros), format_cible="pdf")
        assert resultat.statut is Statut.ECHEC
        assert "volumineux" in resultat.message

    def test_meme_format_source_et_cible_est_un_echec(self, tmp_path):
        html = tmp_path / "page.html"
        html.write_text("<p>x</p>")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        resultat = connecteur.executer("convertir", entree=str(html), format_cible="html")
        assert resultat.statut is Statut.ECHEC
        assert "déjà" in resultat.message


class TestCoherenceFormatSource:
    """Sabotage : un fichier qui PORTE l'extension sans en être un ne doit
    pas déclencher la « récupération » permissive de LibreOffice en silence."""

    def test_faux_docx_est_refuse_avant_tout_moteur(self, tmp_path):
        faux = tmp_path / "faux.docx"
        faux.write_bytes(b"ce n'est pas un conteneur zip")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(faux), format_cible="pdf")

        assert resultat.statut is Statut.ECHEC, resultat.message
        assert "ZIP" in resultat.message

    def test_faux_pdf_est_refuse_avant_tout_moteur(self, tmp_path):
        faux = tmp_path / "faux.pdf"
        faux.write_bytes(b"pas un pdf du tout")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(faux), format_cible="docx")

        assert resultat.statut is Statut.ECHEC, resultat.message
        assert "en-tête" in resultat.message

    def test_vrai_docx_passe_la_verification(self, tmp_path):
        vrai = _fichier_docx(tmp_path)
        assert securite.format_source_coherent(vrai, "docx") is None


class TestConversionsReelles:
    """Une vraie conversion, un vrai fichier relu — pas un mock. Le format
    couvert par chaque test suit la matrice mesurée dans
    `core/production/conversion/registre.py`."""

    def test_docx_vers_pdf(self, tmp_path):
        source = _fichier_docx(tmp_path, "Devis réel, converti pour de vrai.")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["moteur"] == "libreoffice"
        from pypdf import PdfReader
        assert len(PdfReader(resultat.preuve).pages) >= 1

    def test_pdf_vers_docx(self, tmp_path):
        docx_source = _fichier_docx(tmp_path, "Contenu à reconvertir en PDF puis en DOCX.")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        pdf = connecteur.executer("convertir", entree=str(docx_source), format_cible="pdf")
        assert pdf.statut is Statut.SUCCES, pdf.message

        resultat = connecteur.executer("convertir", entree=pdf.preuve, format_cible="docx")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert "limites_qualite" in resultat.detail  # mesuré : texte en cadres, pas en flux
        from docx import Document
        Document(resultat.preuve)  # ne lève pas : relecture réelle

    def test_xlsx_vers_pdf(self, tmp_path):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active["A1"] = "Colonne"
        source = tmp_path / "tableau.xlsx"
        wb.save(source)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_pptx_vers_pdf(self, tmp_path):
        from pptx import Presentation
        p = Presentation()
        p.slides.add_slide(p.slide_layouts[0]).shapes.title.text = "Titre"
        source = tmp_path / "presentation.pptx"
        p.save(source)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_png_vers_webp(self, tmp_path):
        source = _fichier_image(tmp_path)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="webp")

        assert resultat.statut is Statut.SUCCES, resultat.message
        from PIL import Image
        with Image.open(resultat.preuve) as img:
            assert img.format == "WEBP"

    def test_png_rgba_vers_jpg_ne_leve_pas(self, tmp_path):
        """JPEG n'a pas de canal alpha : sabotage — sans le fond blanc dans
        `moteurs.convertir_image`, cette conversion lève une OSError Pillow."""
        source = _fichier_image(tmp_path, mode="RGBA", couleur=(200, 50, 50, 120))
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="jpg")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_svg_vers_png(self, tmp_path):
        source = tmp_path / "forme.svg"
        source.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
            '<rect width="20" height="20" fill="blue"/></svg>')
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="png")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_html_vers_pdf(self, tmp_path):
        source = tmp_path / "page.html"
        source.write_text("<h1>Titre</h1><p>Un paragraphe.</p>")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_markdown_vers_pdf(self, tmp_path):
        source = tmp_path / "notes.md"
        source.write_text("# Titre\n\n- un\n- deux\n")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_txt_vers_pdf(self, tmp_path):
        source = tmp_path / "brut.txt"
        source.write_text("Une ligne.\nUne deuxième ligne avec <balise> non échappée.")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_pdf_vers_png(self, tmp_path):
        docx_source = _fichier_docx(tmp_path)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        pdf = connecteur.executer("convertir", entree=str(docx_source), format_cible="pdf")
        assert pdf.statut is Statut.SUCCES, pdf.message

        resultat = connecteur.executer("convertir", entree=pdf.preuve, format_cible="png")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_audio_wav_vers_mp3(self, tmp_path):
        source = tmp_path / "son.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             str(source)], capture_output=True, timeout=30, check=True)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="mp3")

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_video_mp4_vers_mp3_extrait_l_audio(self, tmp_path):
        source = tmp_path / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=5",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "libx264", "-c:a", "aac", str(source)],
            capture_output=True, timeout=60, check=True)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="mp3")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["limites_qualite"]


class TestFormatNonEnregistre:
    def test_couple_sans_aucun_moteur_est_non_implemente(self, tmp_path):
        source = tmp_path / "notes.txt"
        source.write_text("x")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="epub")

        assert resultat.statut is Statut.NON_IMPLEMENTE
        assert "epub" in resultat.message


class TestMoteurIndisponible:
    def test_couple_enregistre_mais_moteur_absent_est_non_configure(self, tmp_path):
        from dataclasses import replace

        source = tmp_path / "page.html"
        source.write_text("<p>x</p>")

        entrees_originales = registre.MATRICE[("html", "pdf")]
        registre.MATRICE[("html", "pdf")] = [
            replace(e, disponible=lambda: (False, "bibliothèques système manquantes"))
            for e in entrees_originales
        ]
        try:
            connecteur = ConnecteurFileConversion(dossier=tmp_path)
            resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")
        finally:
            registre.MATRICE[("html", "pdf")] = entrees_originales

        assert resultat.statut is Statut.NON_CONFIGURE
        assert "bibliothèques système" in resultat.message


class TestFallback:
    """Sabotage : le premier moteur déclaré échoue, un second réellement
    disponible doit prendre le relais — jamais un échec direct alors qu'une
    autre voie marche."""

    def test_deuxieme_moteur_pris_si_le_premier_echoue(self, tmp_path):
        from core.production.conversion.registre import EntreeMoteur

        def _echoue_toujours(entree, sortie):
            raise MoteurEchec("panne simulée du premier moteur")

        def _ecrit_un_fichier(entree, sortie):
            sortie.write_text("<html><body>ok</body></html>")
            import weasyprint
            weasyprint.HTML(string="<p>ok</p>").write_pdf(str(sortie))

        source = tmp_path / "page.html"
        source.write_text("<p>x</p>")

        entrees_originales = registre.MATRICE[("html", "pdf")]
        registre.MATRICE[("html", "pdf")] = [
            EntreeMoteur("premier-casse", _echoue_toujours, lambda: (True, "toujours dispo")),
            EntreeMoteur("second-ok", _ecrit_un_fichier, lambda: (True, "toujours dispo")),
        ]
        try:
            connecteur = ConnecteurFileConversion(dossier=tmp_path)
            resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")
        finally:
            registre.MATRICE[("html", "pdf")] = entrees_originales

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["moteur"] == "second-ok"
        assert resultat.detail["fallback_utilise"] is True

    def test_tous_les_moteurs_echouent_est_un_echec_explicite(self, tmp_path):
        from core.production.conversion.registre import EntreeMoteur

        def _echoue(entree, sortie):
            raise MoteurEchec("raison précise du refus")

        source = tmp_path / "page.html"
        source.write_text("<p>x</p>")

        entrees_originales = registre.MATRICE[("html", "pdf")]
        registre.MATRICE[("html", "pdf")] = [
            EntreeMoteur("x", _echoue, lambda: (True, "dispo"))]
        try:
            connecteur = ConnecteurFileConversion(dossier=tmp_path)
            resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")
        finally:
            registre.MATRICE[("html", "pdf")] = entrees_originales

        assert resultat.statut is Statut.ECHEC
        assert "raison précise du refus" in resultat.message


class TestValidationDeLaSortie:
    """Sabotage central : `soffice` peut rendre 0 sans avoir écrit de fichier
    (mesuré le 08/09/2026, PDF->DOCX sans `--infilter`) — la seule preuve
    acceptée est la relecture réelle, jamais le code de retour."""

    def test_sortie_invalide_apres_conversion_devient_un_echec(self, tmp_path, monkeypatch):
        monkeypatch.setattr(validation, "verifier", lambda sortie, fmt: "sabotage : jamais valide")
        source = _fichier_docx(tmp_path)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.ECHEC
        assert "sabotage" in resultat.message

    def test_ffmpeg_qui_rend_0_sans_ecrire_est_un_echec(self, tmp_path, monkeypatch):
        """Reproduit le defaut mesure : un sous-processus a code 0, aucun
        fichier reel. `FFmpegTool.convertir` doit le refuser lui-meme."""
        from tools.video.ffmpeg_tool import FFmpegTool

        class _CompletedFactice:
            returncode = 0
            stderr = b""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CompletedFactice())
        outil = FFmpegTool()

        ok, raison = outil.convertir(str(tmp_path / "in.wav"), str(tmp_path / "out.mp3"))

        assert ok is False
        assert "aucun fichier" in raison


class TestArchive:
    def test_compresser_puis_extraire(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("un")
        f2 = tmp_path / "b.txt"
        f2.write_text("deux")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        zippe = connecteur.executer("compresser", entrees=[str(f1), str(f2)])
        assert zippe.statut is Statut.SUCCES, zippe.message
        assert zipfile.is_zipfile(zippe.preuve)

        extrait = connecteur.executer("extraire", entree=zippe.preuve)
        assert extrait.statut is Statut.SUCCES, extrait.message
        assert len(extrait.detail["fichiers"]) == 2

    def test_evasion_de_chemin_est_refusee(self, tmp_path):
        """Sabotage : un membre `../../evil.txt` ne doit jamais être extrait
        hors du dossier cible."""
        malveillant = tmp_path / "evasion.zip"
        with zipfile.ZipFile(malveillant, "w") as zf:
            zf.writestr("../../evil.txt", "contenu")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("extraire", entree=str(malveillant))

        assert resultat.statut is Statut.ECHEC
        assert "sort du dossier cible" in resultat.message
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_trop_de_membres_est_refuse(self, tmp_path, monkeypatch):
        monkeypatch.setattr(securite, "ZIP_MEMBRES_MAX", 5)
        bombe = tmp_path / "bombe.zip"
        with zipfile.ZipFile(bombe, "w") as zf:
            for i in range(6):
                zf.writestr(f"f{i}.txt", "x")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("extraire", entree=str(bombe))

        assert resultat.statut is Statut.ECHEC
        assert "membres" in resultat.message

    def test_taille_decompressee_excessive_est_refusee(self, tmp_path, monkeypatch):
        monkeypatch.setattr(securite, "ZIP_TAILLE_DECOMPRESSEE_MAX_OCTETS", 10)
        gros = tmp_path / "gros.zip"
        with zipfile.ZipFile(gros, "w") as zf:
            zf.writestr("f.txt", "x" * 1000)
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("extraire", entree=str(gros))

        assert resultat.statut is Statut.ECHEC
        assert "décompressé" in resultat.message

    def test_archive_corrompue_est_un_echec_pas_un_crash(self, tmp_path):
        corrompu = tmp_path / "corrompu.zip"
        corrompu.write_bytes(b"PK\x03\x04pas vraiment un zip")
        connecteur = ConnecteurFileConversion(dossier=tmp_path)

        resultat = connecteur.executer("extraire", entree=str(corrompu))

        assert resultat.statut is Statut.ECHEC

    def test_compresser_fichier_absent_est_un_echec(self, tmp_path):
        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        resultat = connecteur.executer("compresser", entrees=[str(tmp_path / "absent.txt")])
        assert resultat.statut is Statut.ECHEC


class TestLot:
    @pytest.mark.asyncio
    async def test_lot_reel_converti_en_fond_avec_progression(self, tmp_path):
        travaux = FileDeTravaux()
        connecteur = ConnecteurFileConversion(dossier=tmp_path, travaux=travaux)
        chemins = [str(_fichier_image(tmp_path, nom=f"img{i}.png")) for i in range(3)]

        soumis = connecteur.executer("convertir_lot", entrees=chemins, format_cible="jpg")
        assert soumis.statut is Statut.SUCCES, soumis.message
        job_id = soumis.preuve

        travail = await travaux.attendre(job_id, delai=15.0)
        assert travail is not None and travail.etat.value == "DONE"
        assert travail.faits == 3 and travail.total == 3
        assert travail.resultat["reussites"] == 3

        etat = connecteur.executer("etat_lot", job_id=job_id)
        assert etat.statut is Statut.SUCCES
        assert etat.detail["resultat"]["reussites"] == 3

    def test_lot_vide_est_un_echec(self, tmp_path):
        connecteur = ConnecteurFileConversion(dossier=tmp_path, travaux=FileDeTravaux())
        resultat = connecteur.executer("convertir_lot", entrees=[], format_cible="pdf")
        assert resultat.statut is Statut.ECHEC

    def test_lot_trop_grand_est_refuse(self, tmp_path, monkeypatch):
        from core.production.conversion import lot as lot_module
        monkeypatch.setattr(lot_module, "LOT_MAX_FICHIERS", 2)
        connecteur = ConnecteurFileConversion(dossier=tmp_path, travaux=FileDeTravaux())

        resultat = connecteur.executer(
            "convertir_lot", entrees=["a.png", "b.png", "c.png"], format_cible="jpg")

        assert resultat.statut is Statut.ECHEC
        assert "plafond" in resultat.message

    def test_identifiant_de_lot_inconnu_est_un_echec(self, tmp_path):
        connecteur = ConnecteurFileConversion(dossier=tmp_path, travaux=FileDeTravaux())
        resultat = connecteur.executer("etat_lot", job_id="inexistant")
        assert resultat.statut is Statut.ECHEC

    def test_sans_file_de_fond_le_lot_reste_synchrone_mais_fonctionne(self, tmp_path):
        """Mission §6 : le lot doit marcher meme sans tache de fond injectee —
        seule la latence en paie le prix, jamais une conversion qui echoue."""
        connecteur = ConnecteurFileConversion(dossier=tmp_path, travaux=None)
        chemins = [str(_fichier_image(tmp_path, nom="seule.png"))]

        resultat = connecteur.executer("convertir_lot", entrees=chemins, format_cible="jpg")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["resultats"][0]["status"] == "SUCCESS"


class TestFormatsDisponibles:
    def test_rend_la_matrice_reelle(self):
        connecteur = ConnecteurFileConversion()
        resultat = connecteur.executer("formats_disponibles")
        assert resultat.statut is Statut.SUCCES
        assert len(resultat.detail["matrice"]) == len(registre.couples_connus())
        docx_pdf = next(ligne for ligne in resultat.detail["matrice"]
                        if ligne["source"] == "docx" and ligne["cible"] == "pdf")
        assert docx_pdf["disponible"] is True


class TestCoupeCircuitWriteFiles:
    """Retirer la confirmation n'a jamais retiré la protection — même
    principe que `test_connecteur_graphify.py::TestLeCoupeCircuit...`."""

    def test_convertir_refuse_sous_write_files_eteint(self, tmp_path):
        politique = tmp_path / "politique.yaml"
        politique.write_text(yaml.safe_dump({"services": {"file_conversion": {"document": {
            "decision": "ALLOWED", "risque": "LOW", "interrupteur": "WRITE_FILES"}}}}),
            encoding="utf-8")
        permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
        permissions.permissions.update({"WRITE_FILES": False})

        source = _fichier_docx(tmp_path)
        connecteur = ConnecteurFileConversion(
            dossier=tmp_path,
            acces=ControleAcces(permissions=permissions,
                                politique=PolitiqueDePermissions(chemin=politique)))

        resultat = connecteur.executer("convertir", entree=str(source), format_cible="pdf")

        assert resultat.statut is Statut.REFUSE
        assert not any(tmp_path.glob("*.pdf")), "un fichier a ete ecrit malgre le refus"


class TestAccessibleDepuisLeRegistre:
    """Model-agnostic : n'importe quel agent qui detient le registre atteint
    la capacite de la meme facon, sans savoir qu'un moteur en particulier
    existe derriere — meme test que la mission demande §21 (« USER -> MODEL
    -> ARENA ROUTER -> FILE_CONVERSION TOOL -> ENGINE -> ARTIFACT »), sans
    modele reel : le chemin registre est ce que tout modele emprunte."""

    def test_deux_appelants_independants_obtiennent_le_meme_resultat(self, tmp_path):
        registre_connecteurs = RegistreConnecteurs()
        registre_connecteurs.declarer(
            "file_conversion", lambda: ConnecteurFileConversion(dossier=tmp_path))

        source = _fichier_image(tmp_path)
        r1 = registre_connecteurs.executer(
            "file_conversion", "convertir", entree=str(source), format_cible="webp")
        r2 = registre_connecteurs.executer(
            "file_conversion", "convertir", entree=str(source), format_cible="jpg")

        assert r1.statut is Statut.SUCCES and r2.statut is Statut.SUCCES
        assert r1.preuve != r2.preuve  # deux appels, deux fichiers distincts
