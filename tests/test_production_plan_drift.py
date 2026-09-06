"""`plan_drift.py` : une opération Drift n'est jamais devinée, seulement
validée contre le VRAI schéma que Drift annonce dans le même appel."""
from pathlib import Path

import pytest

from core.production.plan_drift import (
    TOOLBOXES_FERMEES,
    PlanDriftRefuse,
    extraire_json,
    inventaire_depuis,
    prompt_de_planification,
    valider_operations,
)

#: Un schéma proche de la forme MCP (`tools/list`) — l'hypothèse explicite du
#: module, seule forme vérifiable sans le vrai Drift.
SCHEMA_TIMELINE = {"tools": [
    {"name": "split_on_beats", "inputSchema": {"properties": {"clip_id": {"type": "string"}}, "required": ["clip_id"]}},
    {"name": "place_clip", "inputSchema": {
        "properties": {"path": {"type": "string"}, "track": {"type": "string"}},
        "required": ["path", "track"]}},
]}
SCHEMA_TEXT = {"tools": [
    {"name": "add_title", "inputSchema": {"properties": {"text": {"type": "string"}}, "required": ["text"]}},
]}


class TestExtraireJson:
    def test_un_tableau_json_est_lu(self):
        assert extraire_json('voici : [{"a": 1}] merci') == [{"a": 1}]

    def test_du_texte_sans_json_leve(self):
        with pytest.raises(PlanDriftRefuse):
            extraire_json("aucun json ici")


class TestInventaireDepuis:
    def test_un_fichier_existant_entre_dans_l_inventaire(self, tmp_path: Path):
        fichier = tmp_path / "chantier.mp4"
        fichier.write_bytes(b"x")

        inventaire = inventaire_depuis([str(fichier)])

        assert inventaire == {"chantier": str(fichier.resolve())}

    def test_un_fichier_absent_n_entre_pas(self, tmp_path: Path):
        assert inventaire_depuis([str(tmp_path / "absent.mp4")]) == {}


class TestValiderOperations:
    def test_une_operation_connue_et_valide_passe(self):
        brut = [{"toolbox": "timeline", "operation": "split_on_beats", "parametres": {"clip_id": "c1"}}]

        ops, refus = valider_operations(brut, {"timeline": SCHEMA_TIMELINE}, {})

        assert ops == [{"toolbox": "timeline", "op": "split_on_beats", "params": {"clip_id": "c1"}}]
        assert refus == []

    def test_une_toolbox_hors_liste_fermee_est_refusee(self):
        brut = [{"toolbox": "invente", "operation": "x", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {}, {})

    def test_une_toolbox_jamais_chargee_est_refusee(self):
        """Une toolbox du bon nom mais dont le schéma n'a pas été récupéré
        dans CET appel n'a jamais été vérifiée — jamais supposée correcte."""
        brut = [{"toolbox": "timeline", "operation": "split_on_beats", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {}, {})

    def test_une_operation_absente_du_vrai_schema_est_refusee(self):
        brut = [{"toolbox": "timeline", "operation": "operation_qui_n_existe_pas", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse) as erreur:
            valider_operations(brut, {"timeline": SCHEMA_TIMELINE}, {})
        assert "split_on_beats" in str(erreur.value), "les vraies operations doivent etre nommees"

    def test_un_parametre_inconnu_du_schema_est_refuse(self):
        brut = [{"toolbox": "timeline", "operation": "split_on_beats",
                 "parametres": {"clip_id": "c1", "parametre_invente": 1}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {"timeline": SCHEMA_TIMELINE}, {})

    def test_un_parametre_requis_manquant_est_refuse(self):
        brut = [{"toolbox": "timeline", "operation": "split_on_beats", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {"timeline": SCHEMA_TIMELINE}, {})

    def test_le_modele_ne_cite_jamais_un_chemin_en_clair(self):
        """`path` est une clé média (CLES_MEDIA) : un nom hors inventaire
        est refusé, jamais accepté comme un chemin littéral — la valeur
        rejetée peut apparaître dans le message de refus (diagnostic), mais
        n'atteint JAMAIS `ops`, donc jamais Drift."""
        brut = [{"toolbox": "timeline", "operation": "place_clip",
                 "parametres": {"path": "/etc/passwd", "track": "v1"}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {"timeline": SCHEMA_TIMELINE}, {"chantier": "/vrai/chantier.mp4"})

    def test_un_nom_de_l_inventaire_est_substitue_par_le_vrai_chemin(self):
        brut = [{"toolbox": "timeline", "operation": "place_clip",
                 "parametres": {"path": "chantier", "track": "v1"}}]

        ops, refus = valider_operations(
            brut, {"timeline": SCHEMA_TIMELINE}, {"chantier": "/vrai/chantier.mp4"})

        assert ops[0]["params"]["path"] == "/vrai/chantier.mp4"
        assert refus == []

    def test_deux_toolboxes_dans_le_meme_plan(self):
        brut = [
            {"toolbox": "timeline", "operation": "split_on_beats", "parametres": {"clip_id": "c1"}},
            {"toolbox": "text", "operation": "add_title", "parametres": {"text": "Avant/Après"}},
        ]

        ops, refus = valider_operations(
            brut, {"timeline": SCHEMA_TIMELINE, "text": SCHEMA_TEXT}, {})

        assert len(ops) == 2
        assert refus == []

    def test_un_plan_entierement_refuse_leve(self):
        brut = [{"toolbox": "invente", "operation": "x", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {}, {})

    def test_une_ligne_partiellement_mauvaise_n_empeche_pas_les_autres(self):
        brut = [
            {"toolbox": "timeline", "operation": "split_on_beats", "parametres": {"clip_id": "c1"}},
            {"toolbox": "invente", "operation": "x", "parametres": {}},
        ]

        ops, refus = valider_operations(brut, {"timeline": SCHEMA_TIMELINE}, {})

        assert len(ops) == 1
        assert len(refus) == 1

    def test_un_plan_qui_n_est_pas_une_liste_leve(self):
        with pytest.raises(PlanDriftRefuse):
            valider_operations({"autre_chose": True}, {}, {})


class TestFormeInattendue:
    """Une forme de schéma qui diverge de l'hypothèse posée dans le module
    (MCP `tools/list`) refuse proprement — jamais une exception, jamais une
    opération devinée."""

    def test_un_schema_qui_n_est_pas_un_dict_refuse_sans_lever(self):
        brut = [{"toolbox": "timeline", "operation": "split_on_beats", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {"timeline": "pas un schema"}, {})

    def test_un_schema_vide_refuse_toute_operation(self):
        brut = [{"toolbox": "timeline", "operation": "split_on_beats", "parametres": {}}]

        with pytest.raises(PlanDriftRefuse):
            valider_operations(brut, {"timeline": {}}, {})


class TestPromptDePlanification:
    def test_seules_les_operations_chargees_apparaissent(self):
        prompt = prompt_de_planification("coupe les silences", {"timeline": SCHEMA_TIMELINE}, {})

        assert "split_on_beats" in prompt
        assert "place_clip" in prompt
        assert "add_title" not in prompt

    def test_aucun_chemin_n_apparait_dans_le_prompt(self, tmp_path: Path):
        fichier = tmp_path / "chantier.mp4"
        fichier.write_bytes(b"x")
        inventaire = inventaire_depuis([str(fichier)])

        prompt = prompt_de_planification("monte cette video", {}, inventaire)

        assert str(fichier.resolve()) not in prompt
        assert "chantier" in prompt


class TestToolboxesFermees:
    def test_les_dix_toolboxes_documentees_sont_presentes(self):
        assert set(TOOLBOXES_FERMEES) == {
            "media", "timeline", "canvas", "playback", "text", "effects",
            "subtitles", "audio", "ai", "scene",
        }
