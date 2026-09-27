"""Intelligence de réunion : uniquement des mesures et faits observables."""

import pytest

from core.meetings.intelligence import (
    construire_prompt_reunion,
    est_demande_analyse_reunion,
    formater_metriques_reunion,
    mesurer_reunion,
)


@pytest.mark.parametrize("phrase", [
    "Fais le compte rendu de cette réunion.",
    "Résume cet appel enregistré et donne les actions.",
    "Analyse cet enregistrement et donne les points clés.",
    "Quels sont les action items de ce meeting ?",
])
def test_une_analyse_de_reunion_est_reconnue(phrase):
    assert est_demande_analyse_reunion(phrase)


@pytest.mark.parametrize("phrase", [
    "Transcris cette réunion.",
    "Réunion des agents",
    "Fais une réunion des agents pour débattre.",
    "Appelle Mamadou demain.",
    "Analyse cette vidéo de chantier.",
])
def test_ce_qui_n_est_pas_une_analyse_de_reunion_reste_hors_du_chemin(phrase):
    assert not est_demande_analyse_reunion(phrase)


def test_les_metriques_sont_calculees_depuis_la_transcription_et_la_duree():
    texte = "Bonjour équipe. On valide le devis ? Fatou envoie le PDF demain."

    metriques = mesurer_reunion(
        texte,
        [{"start": 0.0, "end": 10.0, "text": texte}],
        120.0,
    )

    assert metriques["word_count"] == 11
    assert metriques["question_count"] == 1
    assert metriques["duration_seconds"] == 120.0
    assert metriques["words_per_minute"] == 5.5
    assert metriques["segment_count"] == 1
    assert metriques["speaker_separation_available"] is False
    assert metriques["speaker_talk_ratio"] == {}


def test_aucune_duree_n_est_inventee_quand_whisper_ne_la_fournit_pas():
    metriques = mesurer_reunion("Bonjour tout le monde", None, None)

    assert metriques["duration_seconds"] is None
    assert metriques["words_per_minute"] is None
    assert metriques["segment_count"] is None


def test_un_seul_label_de_locuteur_ne_devient_pas_une_diarisation():
    metriques = mesurer_reunion(
        "un deux trois",
        [{"speaker": "A", "text": "un deux trois"}],
        10,
    )

    assert metriques["speaker_separation_available"] is False
    assert metriques["speaker_word_counts"] == {}
    assert metriques["speaker_talk_ratio"] == {}


def test_des_labels_reels_permettent_un_ratio_sans_deviner_les_identites():
    metriques = mesurer_reunion(
        "un deux trois quatre cinq",
        [
            {"speaker": "A", "text": "un deux trois"},
            {"speaker": "B", "text": "quatre cinq"},
        ],
        20,
    )

    assert metriques["speaker_separation_available"] is True
    assert metriques["speaker_word_counts"] == {"A": 3, "B": 2}
    assert metriques["speaker_talk_ratio"] == {"A": 0.6, "B": 0.4}


def test_le_prompt_interdit_les_actions_et_locuteurs_inventes():
    metriques = mesurer_reunion("On reparle du devis.", None, None)
    prompt = construire_prompt_reunion("On reparle du devis.", metriques)

    assert "UNIQUEMENT" in prompt
    assert "N'ajoute aucun fait absent" in prompt
    assert "Une action doit être explicitement soutenue" in prompt
    assert "N'invente jamais l'identité d'un locuteur" in prompt
    assert "<TRANSCRIPTION>" in prompt



def test_le_format_visible_ne_transforme_pas_les_absences_en_zero():
    texte = formater_metriques_reunion(
        mesurer_reunion("Bonjour ?", None, None)
    )

    assert "Durée : non disponible" in texte
    assert "Débit : non disponible" in texte
    assert "Questions détectées : 1" in texte
    assert "pas de diarisation fiable" in texte
