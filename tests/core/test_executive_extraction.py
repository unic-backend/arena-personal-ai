"""Extraction deterministe de chiffres — jamais devinee (mission §13)."""
from core.executive.extraction import (
    extraire_echeancier,
    extraire_jours_pres_de,
    extraire_montant_pres_de,
    extraire_scenario_projet,
)

#: Le scenario synthetique exact de la mission (§38), en anglais comme ecrit.
SCENARIO_MISSION_38 = """
Construction company receives a project worth 10,000,000.

Material cost: 5,000,000
Labor: 2,000,000
Transport cost: 500,000

Payment: 50% advance, 30% mid-project, 20% completion

Deadline: 14 days
Supplier risk: possible 5-day delay
"""


class TestExtraireMontant:
    def test_montant_anglais_virgules(self):
        assert extraire_montant_pres_de(SCENARIO_MISSION_38, ("project worth",)) == 10_000_000

    def test_montant_absent_rend_none(self):
        assert extraire_montant_pres_de("aucun chiffre ici", ("project worth",)) is None

    def test_montant_francais_espaces(self):
        texte = "materiaux : 5 000 000 FCFA"
        assert extraire_montant_pres_de(texte, ("materiaux",)) == 5_000_000

    def test_decimale_reelle_preservee(self):
        texte = "prix unitaire : 4500.50"
        assert extraire_montant_pres_de(texte, ("prix unitaire",)) == 4500.50


class TestExtraireEcheancier:
    def test_trois_etapes_reconnues(self):
        etapes = extraire_echeancier(SCENARIO_MISSION_38)
        pourcentages = sorted(p for _, p in etapes)
        assert pourcentages == [20.0, 30.0, 50.0]

    def test_le_libelle_ne_traverse_jamais_un_saut_de_ligne(self):
        """Bug reel trouve au test de redemarrage (§50) : le dernier
        libelle d'un echeancier suivi d'une ligne vide puis d'une autre
        phrase ("20% completion\\n\\nDeadline: 14 days") fusionnait
        "completion" avec "Deadline" au lieu de s'arreter a la ligne."""
        texte = "Payment: 50% advance, 30% mid-project, 20% completion\n\nDeadline: 14 days"
        etapes = extraire_echeancier(texte)
        libelles = [libelle for libelle, _ in etapes]
        assert libelles == ["advance", "mid-project", "completion"]
        assert not any("\n" in libelle for libelle in libelles)
        assert not any("Deadline" in libelle for libelle in libelles)

    def test_aucun_echeancier_rend_liste_vide(self):
        assert extraire_echeancier("rien ici") == []


class TestExtraireJours:
    def test_delai_de_14_jours(self):
        assert extraire_jours_pres_de(SCENARIO_MISSION_38, ("deadline",)) == 14

    def test_retard_de_5_jours(self):
        assert extraire_jours_pres_de(SCENARIO_MISSION_38, ("delay",)) == 5

    def test_absent_rend_none(self):
        assert extraire_jours_pres_de("rien ici", ("deadline",)) is None


class TestExtraireScenarioProjet:
    def test_le_scenario_complet_de_la_mission(self):
        scenario = extraire_scenario_projet(SCENARIO_MISSION_38)
        assert scenario["revenu"] == 10_000_000
        assert scenario["couts"]["materials"] == 5_000_000
        assert scenario["couts"]["labor"] == 2_000_000
        assert scenario["couts"]["transport"] == 500_000
        assert scenario["jours_disponibles"] == 14
        assert scenario["jours_risque"] == 5
        assert sorted(p for _, p in scenario["echeancier"]) == [20.0, 30.0, 50.0]
        assert [libelle for libelle, _ in scenario["echeancier"]] == [
            "advance", "mid-project", "completion"]

    def test_texte_sans_chiffres_rend_des_champs_vides_jamais_devines(self):
        scenario = extraire_scenario_projet("Devrions-nous accepter ce projet ?")
        assert scenario["revenu"] is None
        assert scenario["couts"] == {}
        assert scenario["echeancier"] == []
        assert scenario["jours_disponibles"] is None
