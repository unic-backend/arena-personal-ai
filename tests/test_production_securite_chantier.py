"""`securite_chantier.py` : traduire ce que SiteGuard detecte, sans jamais
recalculer sa logique de risque ni presenter une detection comme une
certitude (mission securite chantier, 05/09/2026, §6)."""
from core.production.securite_chantier import (
    RAPPEL_PRUDENCE,
    RapportSecurite,
    depuis_detection,
    formater,
)

DETAIL_AVEC_RISQUE = {
    "detections": [
        {"class": "person", "confidence": 0.91, "bbox": [10, 10, 50, 90]},
        {"class": "person", "confidence": 0.88, "bbox": [100, 10, 150, 90]},
        {"class": "no_helmet", "confidence": 0.76, "bbox": [10, 10, 30, 30]},
    ],
    "risks": [
        {"type": "no_helmet", "level": "high", "count": 1,
         "message": "1 personne semble ne pas porter de casque.", "detection_ids": [2]},
    ],
}


class TestDepuisDetection:
    def test_traduit_detections_et_risques(self):
        rapport = depuis_detection("chantier.jpg", DETAIL_AVEC_RISQUE)

        assert rapport.personnes == 2
        assert len(rapport.detections) == 3
        assert rapport.risques[0].niveau == "high"
        assert rapport.risques[0].compte == 1

    def test_un_detail_vide_ne_leve_pas(self):
        rapport = depuis_detection("chantier.jpg", {})

        assert rapport.detections == []
        assert rapport.risques == []
        assert rapport.personnes == 0


class TestFormater:
    def test_le_compte_de_personnes_et_le_risque_apparaissent(self):
        rapport = depuis_detection("chantier.jpg", DETAIL_AVEC_RISQUE)

        rendu = formater(rapport)

        assert "2 personne(s)" in rendu
        assert "casque" in rendu
        assert "élevé" in rendu

    def test_aucune_detection_le_dit_sans_rien_inventer(self):
        rapport = RapportSecurite(image="vide.jpg")

        rendu = formater(rapport)

        assert "vide.jpg" in rendu
        assert "Aucun élément" in rendu

    def test_aucun_risque_signale_est_dit_explicitement(self):
        rapport = depuis_detection("chantier.jpg", {
            "detections": [{"class": "person", "confidence": 0.9, "bbox": [0, 0, 1, 1]}],
            "risks": [],
        })

        rendu = formater(rapport)

        assert "Aucun risque signalé" in rendu

    def test_le_rappel_de_prudence_est_toujours_present(self):
        """La regle mission (§6) : une detection reste une observation
        probabiliste, jamais une certitude — sur CHAQUE rapport, avec ou
        sans risque detecte."""
        avec_risque = formater(depuis_detection("a.jpg", DETAIL_AVEC_RISQUE))
        sans_rien = formater(RapportSecurite(image="b.jpg"))

        assert RAPPEL_PRUDENCE in avec_risque
        assert RAPPEL_PRUDENCE in sans_rien

    def test_un_niveau_inconnu_n_est_pas_invente(self):
        rapport = depuis_detection("chantier.jpg", {
            "detections": [{"class": "person", "confidence": 0.9, "bbox": [0, 0, 1, 1]}],
            "risks": [{"type": "x", "level": "critique-jamais-vu", "count": 1, "message": "m"}],
        })

        rendu = formater(rapport)

        assert "critique-jamais-vu" in rendu
