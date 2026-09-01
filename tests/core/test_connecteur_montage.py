"""Le connecteur de montage : la timeline atteignable, et la vidéo prouvée.

Deux défauts trouvés **en jouant la chaîne complète**, pas en relisant le
code — les deux passaient la composition et tombaient au rendu. Ces tests
les tiennent :

1. un plan citait des identifiants générés pendant sa propre exécution ;
2. `ajouter_clip` gardait la référence du plan au lieu de l'identifiant
   résolu, donc le rendu ne retrouvait pas le média.
"""
import shutil
import subprocess

import pytest

from core.actions.resultat import Statut
from core.connectors.montage import OPERATIONS_OUVERTES, ConnecteurMontage


@pytest.fixture
def ffmpeg_reel() -> str:
    chemin = shutil.which("ffmpeg")
    if not chemin:
        pytest.skip("ffmpeg n'est pas installé sur cette machine.")
    return chemin


@pytest.fixture
def sources(ffmpeg_reel, tmp_path):
    video, logo = tmp_path / "chantier.mp4", tmp_path / "logo.png"
    subprocess.run([ffmpeg_reel, "-v", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30:duration=8",
                    "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    subprocess.run([ffmpeg_reel, "-v", "error", "-y", "-f", "lavfi",
                    "-i", "color=c=blue:s=400x160:d=1", "-frames:v", "1", str(logo)],
                   check=True, capture_output=True)
    return {"video": video, "logo": logo}


def plan_reel(sources) -> list:
    """Le plan tel qu'un modèle l'écrirait : **que des noms**, aucun identifiant."""
    return [
        {"operation": "creer_projet", "nom": "Reel Almadies",
         "largeur": 1080, "hauteur": 1920},
        {"operation": "importer_media", "chemin": str(sources["video"]), "nom": "chantier"},
        {"operation": "importer_media", "chemin": str(sources["logo"]), "nom": "logo"},
        {"operation": "ajouter_piste", "type": "video", "nom": "principale"},
        {"operation": "ajouter_piste", "type": "image", "nom": "marque"},
        {"operation": "ajouter_piste", "type": "texte", "nom": "titres"},
        {"operation": "ajouter_clip", "piste_id": "principale", "media_id": "chantier",
         "debut_ms": 0, "duree_ms": 5_000, "coupe_debut_ms": 1_000},
        {"operation": "ajouter_clip", "piste_id": "marque", "media_id": "logo",
         "debut_ms": 0, "duree_ms": 5_000},
        {"operation": "ajouter_texte", "piste_id": "titres",
         "texte": "Chantier de l'Almadies : avant / apres",
         "debut_ms": 500, "duree_ms": 4_000},
    ]


class TestFrontiere:
    """Ce que le modèle a le droit de demander — et rien d'autre."""

    def test_une_operation_hors_liste_est_refusee_et_nommee(self, tmp_path):
        c = ConnecteurMontage(dossier=tmp_path)

        r = c.executer("composer", operations=[
            {"operation": "creer_projet", "nom": "x"},
            {"operation": "supprimer_le_disque", "chemin": "/"},
        ])

        assert any("supprimer_le_disque" in e for e in r.detail["erreurs"])

    def test_une_methode_privee_ne_s_appelle_pas_par_son_nom(self, tmp_path):
        """La liste fermée ne vaut que si elle est vraiment fermée."""
        c = ConnecteurMontage(dossier=tmp_path)

        r = c.executer("composer", operations=[
            {"operation": "creer_projet", "nom": "x"},
            {"operation": "_exige_un_projet", "operation_nom": "x"},
        ])

        assert any("_exige_un_projet" in e for e in r.detail["erreurs"])

    def test_la_liste_ouverte_ne_contient_que_des_operations_reelles(self):
        from core.montage.operations import Montage

        for nom in OPERATIONS_OUVERTES:
            assert callable(getattr(Montage, nom, None)), f"{nom} n'existe pas"

    def test_un_plan_vide_est_refuse(self, tmp_path):
        assert ConnecteurMontage(dossier=tmp_path).executer(
            "composer", operations=[]).statut is Statut.ECHEC

    def test_une_erreur_n_arrete_pas_les_operations_suivantes(self, tmp_path):
        """Un modèle qui se trompe d'une ligne doit voir laquelle, pas tout perdre."""
        c = ConnecteurMontage(dossier=tmp_path)

        r = c.executer("composer", operations=[
            {"operation": "creer_projet", "nom": "x", "largeur": 1080, "hauteur": 1920},
            {"operation": "importer_media", "chemin": "/nulle/part.mp4"},
            {"operation": "ajouter_piste", "type": "video", "nom": "principale"},
        ])

        assert r.statut is Statut.SUCCES
        assert len(r.detail["erreurs"]) == 1
        assert any(p["nom"] == "principale" for p in r.detail["pistes"]), (
            "l'operation suivant l'echec n'a pas ete jouee"
        )


class TestConfirmation:
    def test_composer_n_ecrit_aucun_fichier(self, tmp_path):
        c = ConnecteurMontage(dossier=tmp_path / "rendus")

        c.executer("composer", operations=[
            {"operation": "creer_projet", "nom": "x", "largeur": 1080, "hauteur": 1920}])

        assert not (tmp_path / "rendus").exists(), "composer a ecrit sur le disque"

    @pytest.mark.integration
    def test_rendre_ne_part_jamais_sans_confirmation(self, sources, tmp_path):
        c = ConnecteurMontage(dossier=tmp_path / "rendus")

        r = c.executer("rendre", operations=plan_reel(sources))

        assert r.statut is not Statut.SUCCES
        assert not list((tmp_path / "rendus").glob("*.mp4")) if (
            tmp_path / "rendus").exists() else True


@pytest.mark.integration
class TestChaineComplete:
    """De la suite d'opérations au fichier vidéo, vérifié après écriture."""

    def test_un_plan_ne_cite_que_ses_propres_noms(self, sources, tmp_path):
        """Le défaut n°1 : un plan ne connaît pas les identifiants générés."""
        c = ConnecteurMontage(dossier=tmp_path / "rendus")

        r = c.executer("composer", operations=plan_reel(sources))

        assert r.statut is Statut.SUCCES
        assert r.detail["erreurs"] == [], r.detail["erreurs"]
        assert r.detail["duree_ms"] == 5_000

    def test_le_clip_garde_l_identifiant_resolu_pas_la_reference(self, sources, tmp_path):
        """Le défaut n°2 : la composition passait, le rendu ne retrouvait rien."""
        c = ConnecteurMontage(dossier=tmp_path / "rendus")

        r = c.executer("composer", operations=plan_reel(sources))

        projet = r.detail["projet"]
        identifiants = set(projet["medias"])
        for piste in projet["pistes"]:
            for element in piste["elements"]:
                if element["media_id"]:
                    assert element["media_id"] in identifiants, (
                        f"« {element['media_id']} » est une reference de plan, "
                        "pas un identifiant : le rendu ne la retrouvera pas")

    def test_le_rendu_confirme_produit_une_vraie_video_verifiee(self, sources, tmp_path):
        c = ConnecteurMontage(dossier=tmp_path / "rendus")

        r = c.executer_confirmee("rendre", operations=plan_reel(sources))

        assert r.statut is Statut.SUCCES, r.message
        from pathlib import Path
        fichier = Path(r.preuve)
        assert fichier.exists() and fichier.stat().st_size > 1_000
        assert r.detail["largeur"], r.detail["hauteur"] == (1080, 1920)
        assert abs(r.detail["duree_ms"] - 5_000) <= 400

        # Vérification indépendante : le conteneur se relit-il vraiment ?
        sonde = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
             "-of", "csv=p=0", str(fichier)], capture_output=True, text=True)
        assert "h264" in sonde.stdout

    def test_le_projet_reste_editable_a_cote_de_la_video(self, sources, tmp_path):
        """« preserve an editable project representation » — la mission."""
        import json

        c = ConnecteurMontage(dossier=tmp_path / "rendus")
        r = c.executer_confirmee("rendre", operations=plan_reel(sources))

        projet = json.loads(open(r.detail["projet_json"], encoding="utf-8").read())
        assert {p["type"] for p in projet["pistes"]} == {"video", "image", "texte"}

        from core.montage.projet import Projet
        assert Projet.depuis_dict(projet).duree_ms == 5_000, (
            "le projet ecrit ne se relit pas dans le modele"
        )


class TestSansFfmpeg:
    """Le défaut que cette machine cachait, et que le CI a montré.

    `sonder()` rendait `NON_CONFIGURE` sans ffmpeg. La base lit la santé
    AVANT toute capacité, donc `composer` — du Python pur, aucun binaire —
    était refusé lui aussi. Ici ffmpeg est rendu introuvable de force, sur
    la machine qui l'a comme sur celle qui ne l'a pas.
    """

    @pytest.fixture
    def sans_ffmpeg(self, monkeypatch):
        monkeypatch.setattr("core.connectors.montage.shutil.which", lambda _: None)

    def test_composer_marche_sans_ffmpeg(self, sans_ffmpeg, tmp_path):
        r = ConnecteurMontage(dossier=tmp_path).executer("composer", operations=[
            {"operation": "creer_projet", "nom": "x", "largeur": 1080, "hauteur": 1920},
            {"operation": "ajouter_piste", "type": "texte", "nom": "titres"},
            {"operation": "ajouter_texte", "piste_id": "titres", "texte": "UniC",
             "debut_ms": 0, "duree_ms": 2_000},
        ])
        assert r.statut is Statut.SUCCES, r.message

        # La timeline composée sans ffmpeg est une vraie timeline, relisible.
        from core.montage.projet import Projet
        assert Projet.depuis_dict(r.detail["projet"]).duree_ms == 2_000

    def test_rendre_refuse_et_nomme_ce_qui_manque(self, sans_ffmpeg, tmp_path):
        r = ConnecteurMontage(dossier=tmp_path).executer_confirmee("rendre", operations=[
            {"operation": "creer_projet", "nom": "x", "largeur": 1080, "hauteur": 1920},
            {"operation": "ajouter_piste", "type": "texte", "nom": "titres"},
            {"operation": "ajouter_texte", "piste_id": "titres", "texte": "UniC",
             "debut_ms": 0, "duree_ms": 2_000},
        ])
        assert r.statut is Statut.NON_CONFIGURE
        assert "ffmpeg" in r.message

    def test_la_sante_dit_ce_qui_est_perdu(self, sans_ffmpeg, tmp_path):
        sante = ConnecteurMontage(dossier=tmp_path).sante()
        assert sante.utilisable, "sans ffmpeg le montage reste possible"
        assert "aucun rendu" in sante.message
        assert "ffmpeg" in sante.ce_qui_manque
