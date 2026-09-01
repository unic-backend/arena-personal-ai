"""Le rendu : produire un fichier, et surtout PROUVER qu'il tient.

La règle que ces tests défendent vient de la mission comme du projet : un
`returncode == 0` de ffmpeg ne prouve rien. Un rendu n'est un succès que si
le fichier existe, se relit, et dure ce que le projet annonçait.
"""
import shutil
import subprocess

import pytest

from core.montage.operations import Montage
from core.montage.projet import Element, TypePiste, nouveau_projet
from core.montage.rendu import (
    TOLERANCE_DUREE_MS,
    CompilateurFiltres,
    _texte_pour_ffmpeg,
    rendre,
)


@pytest.fixture
def ffmpeg_reel() -> str:
    chemin = shutil.which("ffmpeg")
    if not chemin:
        pytest.skip("ffmpeg n'est pas installé sur cette machine.")
    return chemin


@pytest.fixture
def sources(ffmpeg_reel, tmp_path):
    """Une vraie vidéo, un vrai son, un vrai logo."""
    video = tmp_path / "chantier.mp4"
    son = tmp_path / "musique.wav"
    logo = tmp_path / "logo.png"
    subprocess.run([ffmpeg_reel, "-v", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30:duration=8",
                    "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    subprocess.run([ffmpeg_reel, "-v", "error", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=330:duration=8", str(son)],
                   check=True, capture_output=True)
    subprocess.run([ffmpeg_reel, "-v", "error", "-y", "-f", "lavfi",
                    "-i", "color=c=blue:s=400x160:d=1", "-frames:v", "1", str(logo)],
                   check=True, capture_output=True)
    return {"video": video, "son": son, "logo": logo}


class TestEchappement:
    """Une apostrophe dans « l'Almadies » ne doit pas casser tout le rendu."""

    @pytest.mark.parametrize("brut, interdit", [
        ("l'Almadies", "'"), ("18:30 chantier", ":"), ("100% fini", "%"),
        ("avant, apres", ","), ("[note]", "["),
    ])
    def test_les_caracteres_qui_cassent_un_filtre_sont_neutralises(self, brut, interdit):
        propre = _texte_pour_ffmpeg(brut)

        assert interdit not in propre.replace("\\" + interdit, ""), (
            f"« {interdit} » reste non échappé dans {propre!r}")


class TestCompilateur:
    """Le graphe de filtres se vérifie en le lisant, sans attendre un encodage."""

    def _projet_avec(self, *genres):
        p = nouveau_projet("essai", 1080, 1920)
        from core.montage.projet import Media
        for i, genre in enumerate(genres):
            if genre != "texte":
                p.ajouter_media(Media(f"m{i}", f"/x/f{i}.mp4", genre, duree_ms=10_000))
            piste = p.ajouter_piste(
                {"video": TypePiste.VIDEO, "image": TypePiste.IMAGE,
                 "audio": TypePiste.AUDIO, "texte": TypePiste.TEXTE}[genre])
            piste.ajouter(Element(
                f"e{i}", genre, 0, 3_000,
                media_id=None if genre == "texte" else f"m{i}",
                contenu="Titre" if genre == "texte" else ""))
        return p

    def test_une_video_est_mise_a_l_echelle_du_projet(self):
        commande = CompilateurFiltres(self._projet_avec("video")).commande(
            "/tmp/x.mp4", "ffmpeg")

        filtre = commande[commande.index("-filter_complex") + 1]
        assert "scale=1080:1920" in filtre
        assert "force_original_aspect_ratio=decrease" in filtre, (
            "la video serait deformee au lieu d'etre mise en boite")

    def test_le_point_d_entree_dans_la_source_part_dans_le_filtre(self):
        p = self._projet_avec("video")
        p.pistes[0].elements[0].coupe_debut_ms = 2_500

        filtre = CompilateurFiltres(p).commande("/tmp/x.mp4", "ffmpeg")[
            CompilateurFiltres(p).commande("/tmp/x.mp4", "ffmpeg").index("-filter_complex") + 1]

        assert "trim=start=2.500" in filtre

    def test_le_texte_devient_un_drawtext_limite_dans_le_temps(self):
        filtre = " ".join(CompilateurFiltres(self._projet_avec("texte")).commande(
            "/tmp/x.mp4", "ffmpeg"))

        assert "drawtext" in filtre
        assert "enable='between(t,0.000,3.000)'" in filtre

    def test_l_audio_est_mixe_et_mappe(self):
        commande = CompilateurFiltres(self._projet_avec("audio")).commande(
            "/tmp/x.mp4", "ffmpeg")

        assert "amix" in commande[commande.index("-filter_complex") + 1]
        assert "[aout]" in commande

    def test_une_piste_masquee_ne_part_pas_au_rendu(self):
        p = self._projet_avec("video", "texte")
        p.pistes[1].masquee = True

        filtre = " ".join(CompilateurFiltres(p).commande("/tmp/x.mp4", "ffmpeg"))

        assert "drawtext" not in filtre

    def test_une_piste_audio_muette_ne_part_pas_au_rendu(self):
        p = self._projet_avec("audio")
        p.pistes[0].muette = True

        assert "[aout]" not in CompilateurFiltres(p).commande("/tmp/x.mp4", "ffmpeg")


class TestRefus:
    def test_un_projet_vide_ne_rend_rien(self, tmp_path):
        r = rendre(nouveau_projet("vide"), tmp_path / "sortie.mp4")

        assert r.ok is False and "vide" in r.message
        assert not (tmp_path / "sortie.mp4").exists()

    def test_sans_ffmpeg_le_rendu_dit_ce_qui_manque(self, tmp_path, monkeypatch):
        from core.montage.projet import Media

        p = nouveau_projet("x")
        p.ajouter_media(Media("m", "/x/a.mp4", "video", duree_ms=5_000))
        p.ajouter_piste(TypePiste.VIDEO).ajouter(
            Element("e", "video", 0, 3_000, media_id="m"))
        monkeypatch.setattr("core.montage.rendu.shutil.which", lambda _: None)

        r = rendre(p, tmp_path / "s.mp4")

        assert r.ok is False and "ffmpeg" in r.message.lower()


@pytest.mark.integration
class TestRenduReel:
    """Un vrai fichier, produit puis re-sondé."""

    def _montage(self, sources, largeur=1080, hauteur=1920):
        m = Montage()
        m.creer_projet("Reel chantier", largeur, hauteur)
        return m

    def test_une_video_rendue_existe_et_dure_ce_qui_etait_annonce(self, sources, tmp_path):
        m = self._montage(sources)
        v = m.importer_media(str(sources["video"])).detail["media_id"]
        piste = m.ajouter_piste("video").detail["piste_id"]
        m.ajouter_clip(piste, v, debut_ms=0, duree_ms=4_000)

        r = rendre(m.projet, tmp_path / "sortie.mp4")

        assert r.ok, r.message
        assert (tmp_path / "sortie.mp4").exists()
        assert r.octets > 1_000
        assert abs(r.duree_ms - 4_000) <= TOLERANCE_DUREE_MS
        assert (r.largeur, r.hauteur) == (1080, 1920), "le format 9:16 n'a pas ete applique"

    def test_le_montage_complet_compose_video_logo_texte_et_son(self, sources, tmp_path):
        """Le cas de la mission : logo + sous-titre + 9:16 + son, en un rendu."""
        m = self._montage(sources)
        v = m.importer_media(str(sources["video"])).detail["media_id"]
        logo = m.importer_media(str(sources["logo"])).detail["media_id"]
        son = m.importer_media(str(sources["son"])).detail["media_id"]
        pv = m.ajouter_piste("video").detail["piste_id"]
        pi = m.ajouter_piste("image").detail["piste_id"]
        pt = m.ajouter_piste("texte").detail["piste_id"]
        pa = m.ajouter_piste("audio").detail["piste_id"]
        m.ajouter_clip(pv, v, 0, 5_000, coupe_debut_ms=1_000)
        m.ajouter_clip(pi, logo, 0, 5_000)
        m.ajouter_texte(pt, "Chantier de l'Almadies : avant / apres", 500, 3_500)
        m.ajouter_clip(pa, son, 0, 5_000)

        r = rendre(m.projet, tmp_path / "reel.mp4")

        assert r.ok, r.message
        assert abs(r.duree_ms - 5_000) <= TOLERANCE_DUREE_MS

        # Le conteneur porte-t-il bien une piste audio ET une piste video ?
        sonde = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", str(tmp_path / "reel.mp4")],
            capture_output=True, text=True)
        assert "video" in sonde.stdout and "audio" in sonde.stdout, (
            f"flux manquants dans le rendu : {sonde.stdout!r}")

    def test_une_source_absente_fait_echouer_le_rendu_sans_laisser_de_fichier(
        self, sources, tmp_path
    ):
        """Un échec ne doit jamais laisser un fichier à moitié écrit."""
        m = self._montage(sources)
        v = m.importer_media(str(sources["video"])).detail["media_id"]
        piste = m.ajouter_piste("video").detail["piste_id"]
        m.ajouter_clip(piste, v, 0, 3_000)
        m.projet.medias[v].chemin = "/nulle/part/disparu.mp4"

        r = rendre(m.projet, tmp_path / "casse.mp4")

        assert r.ok is False
        assert not (tmp_path / "casse.mp4").exists(), "un fichier casse a survecu"

    def test_un_texte_avec_apostrophe_ne_casse_pas_le_rendu(self, sources, tmp_path):
        m = self._montage(sources)
        v = m.importer_media(str(sources["video"])).detail["media_id"]
        pv = m.ajouter_piste("video").detail["piste_id"]
        pt = m.ajouter_piste("texte").detail["piste_id"]
        m.ajouter_clip(pv, v, 0, 3_000)
        m.ajouter_texte(pt, "l'Almadies : 100% fini, avant/apres", 0, 3_000)

        r = rendre(m.projet, tmp_path / "texte.mp4")

        assert r.ok, f"une apostrophe a casse le rendu : {r.message}"


class TestUneProprieteNOuvrePasUneOptionFfmpeg:
    """La faille la plus sérieuse de la nuit du 01/09/2026, et elle était à moi.

    `ajouter_texte(**proprietes)` accepte des propriétés libres — c'est voulu,
    pour la taille et la couleur. Elles étaient interpolées **telles quelles**
    dans `filter_complex`. Un `couleur` valant `white:fontfile=/etc/passwd`
    ouvrait donc une option ffmpeg supplémentaire.

    Ce n'est pas théorique : `drawtext` sait lire un fichier (`textfile=`), et
    le contenu d'un fichier de la machine pouvait finir **incrusté dans une
    vidéo que le propriétaire publie**. Le contenu du texte, lui, était déjà
    échappé — la barrière de `planificateur.py` couvrait `importer_media` et
    laissait passer les propriétés.
    """

    def _graphe(self, **proprietes):
        from core.montage.operations import Montage
        from core.montage.rendu import CompilateurFiltres

        montage = Montage()
        montage.creer_projet("x", 1080, 1920)
        montage.ajouter_piste("texte", "t")
        montage.ajouter_texte("t", "bonjour", 0, 2000, **proprietes)
        graphe, _, _ = CompilateurFiltres(montage.projet).graphe()
        return graphe

    @pytest.mark.parametrize("propriete,valeur", [
        ("couleur", "white:fontfile=/etc/passwd"),
        ("couleur", "white':textfile='/etc/passwd"),
        ("x", "0:textfile=/etc/passwd"),
        ("y", "0,movie=/etc/passwd"),
        ("taille", "48:fontfile=/etc/passwd"),
        ("couleur", "white:drawbox=0:0:100:100:red"),
    ])
    def test_aucune_option_ne_se_glisse_par_une_propriete(self, propriete, valeur):
        graphe = self._graphe(**{propriete: valeur})
        for interdit in ("passwd", "textfile=", "movie=", "fontfile=", "drawbox"):
            assert interdit not in graphe, (
                f"« {valeur} » a ouvert une option ffmpeg via {propriete}"
            )

    def test_les_valeurs_legitimes_traversent_intactes(self):
        """Fermer la porte ne doit pas fermer la fenêtre."""
        graphe = self._graphe(couleur="#ffcc00", taille=72, x="(w-text_w)/2", y="h-th-80")
        assert "fontcolor=#ffcc00" in graphe
        assert "fontsize=72" in graphe
        assert "x=(w-text_w)/2" in graphe

    @pytest.mark.parametrize("couleur", ["white", "black@0.5", "#ffcc00", "0xFFCC00"])
    def test_les_formes_de_couleur_admises(self, couleur):
        assert f"fontcolor={couleur}" in self._graphe(couleur=couleur)

    def test_une_taille_absurde_retombe_sur_le_defaut(self):
        assert "fontsize=48" in self._graphe(taille=999999)
        assert "fontsize=48" in self._graphe(taille="grande")

    def test_la_propriete_d_une_image_est_gardee_pareil(self, tmp_path):
        """Le même garde couvre l'overlay d'image, pas seulement le texte.

        Le projet est bâti directement : ce test porte sur le compilateur de
        filtres, et passer par `Montage` ferait dépendre le résultat de ce
        que ffprobe lit dans un fichier factice.
        """
        from core.montage.projet import Element, Media, TypePiste, nouveau_projet
        from core.montage.rendu import CompilateurFiltres

        logo = tmp_path / "logo.png"
        logo.write_bytes(b"x")

        projet = nouveau_projet("x", 1080, 1920)
        projet.ajouter_media(Media(identifiant="m1", chemin=str(logo),
                                   genre="image", nom="logo"))
        piste = projet.ajouter_piste(TypePiste.IMAGE, "marque")
        piste.ajouter(Element(
            identifiant="e1", genre="image", debut_ms=0, duree_ms=2000,
            media_id="m1",
            proprietes={"x": "0:textfile=/etc/passwd", "largeur": "1:movie=/x"}))

        graphe, _, _ = CompilateurFiltres(projet).graphe()
        assert "textfile=" not in graphe and "movie=" not in graphe
        assert "passwd" not in graphe
