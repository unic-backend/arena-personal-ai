"""Le projet de montage : ce qu'il accepte, et surtout ce qu'il refuse.

Ce qui compte ici n'est pas qu'un projet valide se construise — c'est qu'un
projet INVALIDE ne se construise pas. Un rendu qui part d'une timeline
incohérente produit une vidéo fausse qui a l'air juste, et personne ne la
regarde avant qu'elle parte chez un client.
"""
import json

import pytest

from core.montage.projet import (
    Element,
    ErreurProjet,
    Media,
    Projet,
    TypePiste,
    nouveau_projet,
)


@pytest.fixture
def projet() -> Projet:
    p = nouveau_projet("chantier Almadies", largeur=1080, hauteur=1920)
    p.ajouter_media(Media("m1", "/chantiers/plan.mp4", "video", duree_ms=12_000))
    return p


class TestConstruction:
    def test_un_projet_vide_dure_zero(self, projet):
        """Zéro est ici une vraie mesure : rien n'est posé, donc rien ne dure."""
        assert projet.duree_ms == 0

    def test_le_format_est_celui_demande(self, projet):
        assert projet.format == "1080x1920"

    @pytest.mark.parametrize("largeur, hauteur", [(0, 1080), (1920, -1), (0, 0)])
    def test_un_format_impossible_est_refuse(self, largeur, hauteur):
        with pytest.raises(ErreurProjet):
            nouveau_projet("x", largeur=largeur, hauteur=hauteur)

    def test_une_cadence_nulle_est_refusee(self):
        with pytest.raises(ErreurProjet):
            nouveau_projet("x", images_par_seconde=0)


class TestElements:
    @pytest.mark.parametrize("duree", [0, -1, -5000])
    def test_un_element_sans_duree_ne_se_construit_pas(self, duree):
        with pytest.raises(ErreurProjet, match="duree"):
            Element("e", "video", 0, duree, media_id="m1")

    def test_un_debut_negatif_est_refuse(self):
        with pytest.raises(ErreurProjet, match="negatif"):
            Element("e", "video", -100, 1000, media_id="m1")

    def test_un_texte_vide_n_a_rien_a_afficher(self):
        with pytest.raises(ErreurProjet, match="texte"):
            Element("e", "texte", 0, 1000, contenu="   ")

    def test_un_clip_video_sans_source_est_refuse(self):
        with pytest.raises(ErreurProjet, match="media source"):
            Element("e", "video", 0, 1000)

    def test_la_fin_est_le_debut_plus_la_duree(self):
        assert Element("e", "video", 2_000, 3_500, media_id="m1").fin_ms == 5_500

    def test_deplacer_un_clip_ne_change_pas_ce_qu_il_montre(self):
        """`debut_ms` place sur la timeline, `coupe_debut_ms` entre dans la source."""
        clip = Element("e", "video", 8_000, 2_000, media_id="m1", coupe_debut_ms=4_000)

        assert clip.debut_ms == 8_000
        assert clip.coupe_debut_ms == 4_000, "le point d'entree a suivi le deplacement"


class TestPistes:
    def test_un_element_du_mauvais_genre_est_refuse(self, projet):
        piste = projet.ajouter_piste(TypePiste.AUDIO, "musique")

        with pytest.raises(ErreurProjet, match="ne va pas sur une piste audio"):
            piste.ajouter(Element("e", "texte", 0, 1000, contenu="bonjour"))

    def test_deux_clips_qui_se_chevauchent_sont_refuses(self, projet):
        """Sur une même piste, un recouvrement est une ambiguïté : c'est
        l'ordre des pistes qui superpose, pas l'ordre d'insertion."""
        piste = projet.ajouter_piste(TypePiste.VIDEO)
        piste.ajouter(Element("a", "video", 0, 5_000, media_id="m1"))

        with pytest.raises(ErreurProjet, match="chevauchement"):
            piste.ajouter(Element("b", "video", 3_000, 4_000, media_id="m1"))

    def test_deux_clips_qui_se_touchent_sont_acceptes(self, projet):
        """Bout à bout n'est pas un chevauchement : la fin de l'un est le
        début de l'autre, c'est un montage cut ordinaire."""
        piste = projet.ajouter_piste(TypePiste.VIDEO)
        piste.ajouter(Element("a", "video", 0, 5_000, media_id="m1"))
        piste.ajouter(Element("b", "video", 5_000, 3_000, media_id="m1"))

        assert piste.duree_ms == 8_000

    def test_les_elements_restent_ordonnes_dans_le_temps(self, projet):
        piste = projet.ajouter_piste(TypePiste.VIDEO)
        piste.ajouter(Element("tard", "video", 6_000, 1_000, media_id="m1"))
        piste.ajouter(Element("tot", "video", 0, 1_000, media_id="m1"))

        assert [e.identifiant for e in piste.elements] == ["tot", "tard"]

    def test_la_duree_du_projet_est_celle_de_sa_piste_la_plus_longue(self, projet):
        courte = projet.ajouter_piste(TypePiste.VIDEO)
        longue = projet.ajouter_piste(TypePiste.AUDIO)
        courte.ajouter(Element("v", "video", 0, 3_000, media_id="m1"))
        projet.ajouter_media(Media("son", "/x/a.mp3", "audio", duree_ms=20_000))
        longue.ajouter(Element("a", "audio", 0, 9_000, media_id="son"))

        assert projet.duree_ms == 9_000


class TestMedias:
    def test_un_genre_de_media_inconnu_est_refuse(self):
        with pytest.raises(ErreurProjet, match="genre"):
            Media("m", "/x/f.xyz", "hologramme")

    def test_une_duree_inconnue_vaut_none_jamais_zero(self):
        """`0 ms` se lirait « fichier vide » ; l'inconnu se dit `None`."""
        assert Media("m", "/x/f.mp4", "video").duree_ms is None

    def test_une_duree_nulle_est_refusee(self):
        with pytest.raises(ErreurProjet, match="duree"):
            Media("m", "/x/f.mp4", "video", duree_ms=0)

    def test_un_media_absent_du_projet_se_nomme(self, projet):
        with pytest.raises(ErreurProjet, match="aucun media"):
            projet.media("jamais-importe")


class TestSerialisation:
    def test_un_projet_relu_est_identique(self, projet):
        piste = projet.ajouter_piste(TypePiste.VIDEO, "principale")
        piste.ajouter(Element("e", "video", 1_000, 4_000, media_id="m1",
                              coupe_debut_ms=500))
        texte = projet.ajouter_piste(TypePiste.TEXTE, "titres")
        texte.ajouter(Element("t", "texte", 0, 2_000, contenu="UniC Plaquiste"))

        relu = Projet.depuis_dict(projet.to_dict())

        assert relu.duree_ms == projet.duree_ms
        assert relu.format == projet.format
        assert relu.piste(piste.identifiant).elements[0].coupe_debut_ms == 500
        assert relu.piste(texte.identifiant).elements[0].contenu == "UniC Plaquiste"

    def test_le_projet_ecrit_est_du_json_lisible(self, projet, tmp_path):
        projet.ajouter_piste(TypePiste.VIDEO, "principale")
        chemin = projet.ecrire(tmp_path / "projets" / "p.json")

        assert chemin.exists()
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        assert donnees["nom"] == "chantier Almadies"
        assert Projet.lire(chemin).identifiant == projet.identifiant

    def test_un_projet_relu_est_revalide_et_non_cru_sur_parole(self, projet):
        """Un fichier sur disque n'est pas plus digne de confiance qu'autre chose."""
        corrompu = projet.to_dict()
        corrompu["pistes"] = [{
            "identifiant": "p1", "type": "video", "nom": "", "muette": False,
            "masquee": False,
            "elements": [{"identifiant": "e", "genre": "video", "debut_ms": 0,
                          "duree_ms": -3000, "media_id": "m1", "coupe_debut_ms": 0,
                          "contenu": "", "proprietes": {}}],
        }]

        with pytest.raises(ErreurProjet, match="duree"):
            Projet.depuis_dict(corrompu)

    def test_une_piste_de_type_inconnu_est_refusee_a_la_relecture(self, projet):
        corrompu = projet.to_dict()
        corrompu["pistes"] = [{"identifiant": "p", "type": "hologramme",
                               "nom": "", "elements": [], "muette": False,
                               "masquee": False}]

        with pytest.raises(ValueError):
            Projet.depuis_dict(corrompu)
