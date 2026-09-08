"""`core/production/plan_video.py` — le graphe d'un projet Video, valide.

Meme discipline que `core/montage/planificateur.py`, deja verifiee sur le
montage : une capacite hors de la liste fermee est refusee et nommee,
jamais devinee. DEC-0037.
"""
import pytest

from core.production.plan_video import (
    CAPACITES_VIDEO,
    PlanRefuse,
    extraire_json,
    valider_graphe,
)


class TestExtraireJson:
    def test_un_json_pur_est_rendu_tel_quel(self):
        assert extraire_json('[{"id": "a"}]') == [{"id": "a"}]

    def test_un_json_entoure_de_texte_est_extrait(self):
        assert extraire_json('Voici : [{"id": "a"}] voila.') == [{"id": "a"}]

    def test_sans_json_leve_plan_refuse(self):
        with pytest.raises(PlanRefuse):
            extraire_json("je ne sais pas")


class TestValiderGraphe:
    def test_un_graphe_simple_passe(self):
        etapes, refus = valider_graphe([
            {"id": "a", "capacite": "vision"},
        ])
        assert len(etapes) == 1
        assert etapes[0].id == "a"
        assert etapes[0].capacite == "vision"
        assert refus == []

    def test_une_capacite_hors_liste_est_refusee_et_nommee(self):
        etapes, refus = valider_graphe([
            {"id": "a", "capacite": "vision"},
            {"id": "b", "capacite": "capacite_inexistante"},
        ])
        assert [e.id for e in etapes] == ["a"]
        assert any("capacite_inexistante" in r for r in refus)

    def test_toutes_les_capacites_video_sont_acceptees(self):
        plan = [{"id": f"e{i}", "capacite": c} for i, c in enumerate(CAPACITES_VIDEO)]
        etapes, refus = valider_graphe(plan)
        assert {e.capacite for e in etapes} == set(CAPACITES_VIDEO)
        assert refus == []

    def test_un_id_duplique_est_refuse(self):
        etapes, refus = valider_graphe([
            {"id": "a", "capacite": "vision"},
            {"id": "a", "capacite": "transcription"},
        ])
        assert len(etapes) == 1
        assert "deja utilise" in refus[0]

    def test_les_dependances_sont_transmises(self):
        etapes, _ = valider_graphe([
            {"id": "a", "capacite": "vision"},
            {"id": "b", "capacite": "moneyprinter", "depend_de": ["a"]},
        ])
        assert etapes[1].depend_de == ("a",)

    def test_un_plan_qui_n_est_pas_une_liste_est_refuse(self):
        with pytest.raises(PlanRefuse):
            valider_graphe("pas un plan")

    def test_un_plan_entierement_refuse_leve_plan_refuse(self):
        with pytest.raises(PlanRefuse):
            valider_graphe([{"id": "a", "capacite": "inconnue"}])

    def test_un_plan_vide_leve_plan_refuse(self):
        with pytest.raises(PlanRefuse):
            valider_graphe([])

    def test_une_etape_sans_id_est_refusee(self):
        etapes, refus = valider_graphe([
            {"id": "a", "capacite": "vision"},
            {"capacite": "moneyprinter"},
        ])
        assert len(etapes) == 1
        assert "aucun id" in refus[0]

    def test_des_parametres_qui_ne_sont_pas_un_objet_sont_refuses(self):
        etapes, refus = valider_graphe([
            {"id": "a", "capacite": "vision"},
            {"id": "b", "capacite": "narration", "parametres": "pas un objet"},
        ])
        assert len(etapes) == 1
        assert "parametres" in refus[0]

    def test_le_mode_team_restreint_aux_capacites_choisies(self):
        with pytest.raises(PlanRefuse, match="narration"):
            valider_graphe(
                [{"id": "a", "capacite": "narration"}],
                capacites_autorisees=("vision", "transcription"),
            )


class TestMontageSurEcritureRefuse:
    """DEC-0037 : le fichier reel d'une generation/narration n'existe
    qu'apres confirmation du proprietaire, jamais dans le meme passage —
    un montage qui en dependrait directement est refuse au moment du plan."""

    @pytest.mark.parametrize("capacite_ecriture", [
        "wangp", "moneyprinter", "narration",
        "krillin_subtitle", "krillin_tts", "krillin_render_horizontal",
        "krillin_render_vertical", "krillin_cover",
    ])
    def test_un_montage_qui_depend_d_une_ecriture_est_refuse(self, capacite_ecriture):
        etapes, refus = valider_graphe([
            {"id": "generer", "capacite": capacite_ecriture},
            {"id": "assembler", "capacite": "montage", "depend_de": ["generer"]},
        ])
        assert [e.id for e in etapes] == ["generer"]
        assert any("assembler" in r and f"({capacite_ecriture})" in r for r in refus)

    def test_un_montage_qui_depend_d_une_lecture_passe(self):
        etapes, refus = valider_graphe([
            {"id": "lire", "capacite": "vision"},
            {"id": "assembler", "capacite": "montage", "depend_de": ["lire"]},
        ])
        assert {e.id for e in etapes} == {"lire", "assembler"}
        assert refus == []
