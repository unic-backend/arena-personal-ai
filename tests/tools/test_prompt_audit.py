"""`auditer_prompt` : un prompt mal forme ne doit jamais partir sur WanGP.

Chaque cas reproduit une des categories de controle de
`Hell-Grind-AIGC-Skill` (renmu2017, MIT) — voir DEC-0015. Aucun reseau, aucun
modele : uniquement des regex sur du texte.
"""
import pytest

from tools.video.prompt_audit import auditer_prompt


class TestPromptVide:
    def test_prompt_vide_n_est_jamais_pret(self):
        audit = auditer_prompt("", support="video")

        assert audit.pret is False
        assert audit.score == 0
        assert any(p.code == "P-VIDE" for p in audit.problemes)

    def test_prompt_seulement_des_espaces_compte_comme_vide(self):
        audit = auditer_prompt("   \n  ", support="video")

        assert audit.pret is False
        assert audit.problemes[0].code == "P-VIDE"


class TestSujetManquant:
    def test_sans_aucun_sujet_identifiable(self):
        audit = auditer_prompt(
            "Pluie sur le toit, 5 secondes, camera fixe, fin sur le toit, "
            "ambiance pluie.",
            support="video")

        assert any(p.code == "P-SUJET-MANQUANT" for p in audit.problemes)

    def test_un_sujet_nomme_ne_leve_pas_l_erreur(self):
        audit = auditer_prompt(
            "Une femme fatiguee sort de l'atelier sous la pluie, 6 secondes, "
            "camera fixe puis fin sur son visage, ambiance pluie.",
            support="video")

        assert not any(p.code == "P-SUJET-MANQUANT" for p in audit.problemes)


class TestVideoExigeDureeCameraAudio:
    PROMPT_SANS_DUREE = (
        "Une femme fatiguee sort de l'atelier sous la pluie, fin sur son "
        "visage, ambiance pluie."
    )

    def test_video_sans_duree_est_bloquante(self):
        audit = auditer_prompt(self.PROMPT_SANS_DUREE, support="video")

        assert audit.pret is False
        assert any(p.code == "P-DUREE-MANQUANTE" and p.gravite == "erreur"
                   for p in audit.problemes)

    def test_image_sans_duree_n_est_pas_bloquant(self):
        audit = auditer_prompt("Une femme fatiguee assise dans l'atelier.", support="image")

        assert not any(p.code == "P-DUREE-MANQUANTE" for p in audit.problemes)

    def test_video_sans_fin_de_camera(self):
        audit = auditer_prompt(
            "Une femme sort de l'atelier sous la pluie, 6 secondes, ambiance pluie.",
            support="video")

        assert any(p.code == "P-FIN-CAMERA-MANQUANTE" for p in audit.problemes)

    def test_video_sans_audio(self):
        audit = auditer_prompt(
            "Une femme sort de l'atelier sous la pluie, 6 secondes, fin sur son visage.",
            support="video")

        assert any(p.code == "P-AUDIO-MANQUANT" for p in audit.problemes)

    def test_un_prompt_complet_est_pret(self):
        audit = auditer_prompt(
            "Une femme fatiguee sort de l'atelier sous la pluie, 6 secondes, "
            "camera fixe puis fin sur son visage, ambiance pluie et pas sur "
            "le bitume, sans musique.",
            support="video")

        assert audit.pret is True
        assert audit.score == 100


class TestConflitMouvement:
    def test_immobile_et_en_mouvement_dans_le_meme_prompt(self):
        audit = auditer_prompt(
            "Le sujet reste completement immobile, 5 secondes, mais continue "
            "de courir vers la porte, ambiance calme, fin sur la porte.",
            support="video")

        assert audit.pret is False
        assert any(p.code == "P-CONFLIT-MOUVEMENT" for p in audit.problemes)


class TestConflitCamera:
    def test_deux_mouvements_de_camera_incompatibles(self):
        audit = auditer_prompt(
            "Un sujet marche, 5 secondes, la camera avance vers lui puis "
            "recule en meme temps, ambiance rue, fin sur son visage.",
            support="video")

        assert any(p.code == "P-CONFLIT-CAMERA" for p in audit.problemes)

    def test_camera_verrouillee_et_en_mouvement(self):
        audit = auditer_prompt(
            "Un sujet marche, 5 secondes, camera verrouillee qui avance vers "
            "lui, ambiance rue, fin sur son visage.",
            support="video")

        assert any(p.code == "P-CONFLIT-CAMERA" for p in audit.problemes)


class TestChronologieDepassee:
    def test_un_temps_fort_depasse_la_duree_totale(self):
        audit = auditer_prompt(
            "Un sujet marche vers la porte, duree totale 5 secondes, de "
            "0-8 secondes il traverse la piece, ambiance rue, fin sur la porte.",
            support="video")

        assert any(p.code == "P-CHRONOLOGIE-DEPASSEE" for p in audit.problemes)

    def test_un_temps_fort_dans_les_limites_ne_leve_rien(self):
        audit = auditer_prompt(
            "Un sujet marche vers la porte, duree totale 8 secondes, de "
            "0-5 secondes il traverse la piece, ambiance rue, fin sur la porte.",
            support="video")

        assert not any(p.code == "P-CHRONOLOGIE-DEPASSEE" for p in audit.problemes)


class TestAvertissementsNeBloquentPas:
    def test_reference_sans_portee_est_un_avertissement_seul(self):
        audit = auditer_prompt(
            "Un sujet identique a la reference marche vers la porte, "
            "6 secondes, camera fixe, fin sur la porte, ambiance rue.",
            support="video")

        problemes = {p.code: p.gravite for p in audit.problemes}
        assert problemes.get("P-PORTEE-REFERENCE") == "avertissement"
        # Un avertissement seul, sans autre erreur, laisse le prompt pret.
        assert audit.pret is True

    def test_parametres_prives_hors_adaptateur(self):
        audit = auditer_prompt(
            "Un sujet marche vers la porte, 6 secondes, camera fixe, fin sur "
            "la porte, ambiance rue, seed 42, steps 30.",
            support="video")

        assert any(p.code == "P-PLATEFORME-MELANGEE" and p.gravite == "avertissement"
                   for p in audit.problemes)


class TestModulesDetectesEtScore:
    def test_les_modules_detectes_correspondent_au_contenu(self):
        audit = auditer_prompt(
            "Un sujet marche vers la porte, 6 secondes, camera fixe, fin sur "
            "la porte, ambiance rue, lumiere chaude, regard vers la porte.",
            support="video")

        assert "sujet" in audit.modules_detectes
        assert "duree" in audit.modules_detectes
        assert "camera" in audit.modules_detectes

    def test_le_score_baisse_avec_chaque_erreur(self):
        complet = auditer_prompt(
            "Un sujet marche vers la porte, 6 secondes, camera fixe, fin sur "
            "la porte, ambiance rue.",
            support="video")
        incomplet = auditer_prompt("Un sujet marche vers la porte.", support="video")

        assert incomplet.score < complet.score

    def test_support_inconnu_leve(self):
        with pytest.raises(ValueError):
            auditer_prompt("quoi que ce soit", support="audio")


class TestToDict:
    def test_to_dict_est_serialisable(self):
        audit = auditer_prompt("", support="video")
        corps = audit.to_dict()

        assert corps["pret"] is False
        assert corps["problemes"][0]["code"] == "P-VIDE"
