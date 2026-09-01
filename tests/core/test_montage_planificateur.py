"""La frontière entre le modèle et la timeline.

La mission OpenCut l'exige en une phrase : *« Do not let the LLM directly
manipulate arbitrary internal state without validation. »* Ces tests disent
ce que « validation » veut dire ici, et le cas qui compte vraiment est
`TestLeModeleNeChoisitAucunFichier` : un plan est une donnée, il peut venir
d'un texte injecté dans une transcription que le modèle vient de lire.
"""
import json

import pytest

from core.connectors.montage import OPERATIONS_OUVERTES
from core.montage.planificateur import (
    PlanRefuse,
    extraire_json,
    inventaire_depuis,
    prompt_de_planification,
    valider_plan,
)

INVENTAIRE = {"chantier": "/data/media/source/chantier.mp4",
              "logo": "/data/media/source/logo.png"}


def plan_minimal(*lignes) -> list:
    return [{"operation": "creer_projet", "nom": "test",
             "largeur": 1080, "hauteur": 1920}, *lignes]


class TestLeModeleNeChoisitAucunFichier:
    """La seule barrière réelle : le modèle nomme, il ne désigne pas."""

    def test_un_chemin_cite_par_le_modele_est_refuse(self):
        _, refus = valider_plan(
            plan_minimal({"operation": "importer_media", "chemin": "/etc/passwd"}),
            INVENTAIRE)
        assert any("chemin" in r for r in refus)

    def test_un_chemin_meme_plausible_est_refuse(self):
        """Un chemin qui EXISTE n'est pas plus légitime : il n'a pas été ouvert."""
        _, refus = valider_plan(
            plan_minimal({"operation": "importer_media",
                          "chemin": INVENTAIRE["chantier"]}),
            INVENTAIRE)
        assert any("chemin" in r for r in refus)

    def test_un_nom_hors_inventaire_est_refuse_et_liste_le_disponible(self):
        _, refus = valider_plan(
            plan_minimal({"operation": "importer_media", "nom": "cle_privee"}),
            INVENTAIRE)
        assert any("cle_privee" in r and "chantier" in r for r in refus)

    def test_un_nom_de_l_inventaire_devient_le_vrai_chemin(self):
        operations, refus = valider_plan(
            plan_minimal({"operation": "importer_media", "nom": "chantier"}),
            INVENTAIRE)
        assert refus == []
        assert operations[1]["chemin"] == INVENTAIRE["chantier"]

    def test_le_prompt_ne_montre_aucun_chemin(self):
        """Un chemin dans le prompt apprend une arborescence et invite à en citer."""
        prompt = prompt_de_planification("monte ça", INVENTAIRE)
        assert "chantier" in prompt
        for chemin in INVENTAIRE.values():
            assert chemin not in prompt
        assert "/data/media" not in prompt


class TestOperationsFermees:
    def test_une_operation_hors_liste_est_refusee_et_nommee(self):
        _, refus = valider_plan(
            plan_minimal({"operation": "rm", "chemin": "/"}), INVENTAIRE)
        assert any("rm" in r for r in refus)

    def test_une_methode_privee_ne_passe_pas(self):
        _, refus = valider_plan(
            plan_minimal({"operation": "_exige_un_projet"}), INVENTAIRE)
        assert any("_exige_un_projet" in r for r in refus)

    @pytest.mark.parametrize("operation", sorted(OPERATIONS_OUVERTES))
    def test_chaque_operation_ouverte_a_une_signature_lisible(self, operation):
        """La validation lit les paramètres sur `Montage` : elle ne peut pas dériver."""
        from core.montage.planificateur import _parametres_acceptes
        acceptes, _ = _parametres_acceptes(operation)
        assert acceptes, f"{operation} n'expose aucun paramètre"

    def test_un_parametre_inconnu_fait_refuser_la_ligne(self):
        _, refus = valider_plan(
            plan_minimal({"operation": "ajouter_piste", "type": "video",
                          "executer": "rm -rf /"}), INVENTAIRE)
        assert any("executer" in r for r in refus)

    def test_ajouter_texte_accepte_ses_proprietes_libres(self):
        """`ajouter_texte(**proprietes)` : refuser ses extras casserait le style."""
        operations, refus = valider_plan(
            plan_minimal({"operation": "ajouter_texte", "piste_id": "t",
                          "texte": "UniC", "debut_ms": 0, "duree_ms": 1_000,
                          "taille": 72}), INVENTAIRE)
        assert refus == []
        assert operations[1]["taille"] == 72


class TestAucunPlanDeRepli:
    """Un plan invalide se rapporte. Il ne devient jamais une vidéo noire."""

    def test_un_plan_vide_leve(self):
        with pytest.raises(PlanRefuse):
            valider_plan([], INVENTAIRE)

    def test_un_plan_entierement_refuse_leve_avec_les_raisons(self):
        with pytest.raises(PlanRefuse) as erreur:
            valider_plan([{"operation": "rm"}], INVENTAIRE)
        assert "rm" in str(erreur.value)

    def test_ce_qui_n_est_pas_une_liste_leve(self):
        with pytest.raises(PlanRefuse):
            valider_plan("monte la vidéo stp", INVENTAIRE)

    def test_un_objet_portant_operations_est_accepte(self):
        """Les modèles enveloppent souvent : `{"operations": [...]}`."""
        operations, _ = valider_plan({"operations": plan_minimal()}, INVENTAIRE)
        assert operations[0]["operation"] == "creer_projet"


class TestExtractionJson:
    def test_du_json_entoure_de_prose_se_retrouve(self):
        texte = 'Voici le plan :\n```json\n[{"operation": "creer_projet"}]\n```\nVoilà.'
        assert extraire_json(texte) == [{"operation": "creer_projet"}]

    def test_sans_json_lisible_le_plan_est_refuse(self):
        with pytest.raises(PlanRefuse):
            extraire_json("Je ne sais pas monter cette vidéo, désolé.")

    def test_un_json_tronque_est_refuse_pas_devine(self):
        with pytest.raises(PlanRefuse):
            extraire_json('[{"operation": "creer_projet", "nom":]')


class TestInventaire:
    def test_un_fichier_absent_n_entre_pas(self, tmp_path):
        reel = tmp_path / "chantier.mp4"
        reel.write_bytes(b"x")
        inventaire = inventaire_depuis([str(reel), str(tmp_path / "fantome.mp4")])
        assert sorted(inventaire) == ["chantier"]

    def test_un_dossier_n_entre_pas(self, tmp_path):
        (tmp_path / "rushes").mkdir()
        assert inventaire_depuis([str(tmp_path / "rushes")]) == {}


class TestChaineComplete:
    def test_une_reponse_de_modele_realiste_devient_un_plan_executable(self):
        """Ce que le modèle rend vraiment : de la prose, du JSON, une erreur dedans."""
        reponse = (
            "Bien sûr ! Voici le montage :\n\n```json\n" + json.dumps([
                {"operation": "creer_projet", "nom": "chantier",
                 "largeur": 1080, "hauteur": 1920},
                {"operation": "importer_media", "nom": "chantier"},
                {"operation": "importer_media", "nom": "logo"},
                {"operation": "telecharger", "url": "http://ailleurs/x"},
                {"operation": "ajouter_piste", "type": "video", "nom": "principale"},
            ]) + "\n```\nDis-moi si ça te va."
        )
        operations, refus = valider_plan(extraire_json(reponse), INVENTAIRE)

        assert [o["operation"] for o in operations] == [
            "creer_projet", "importer_media", "importer_media", "ajouter_piste"]
        assert len(refus) == 1 and "telecharger" in refus[0]
