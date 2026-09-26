from core.production.presenter_qualite import (
    EtatPresentateur,
    PhasePresentateur,
    avancer,
    controler_transition,
)


def test_ne_saute_jamais_une_phase():
    etat = EtatPresentateur()
    resultat = controler_transition(
        etat, PhasePresentateur.AUDIO_VERROUILLE,
        {"audio": "voix.wav", "duree_audio": 12.0},
    )
    assert resultat.autorise is False
    assert etat.phase is PhasePresentateur.INTAKE


def test_audio_exige_fichier_et_duree_reelle():
    etat = EtatPresentateur(phase=PhasePresentateur.CONTENU_VERROUILLE)
    resultat = avancer(
        etat, PhasePresentateur.AUDIO_VERROUILLE,
        {"audio": "voix.wav", "duree_audio": 0},
    )
    assert resultat.autorise is False
    assert "preuve manquante : duree_audio" in resultat.blocages


def test_generation_presentateur_exige_pilote_cout_et_task_id():
    etat = EtatPresentateur(phase=PhasePresentateur.PLAN_VISUEL_VERROUILLE)
    resultat = avancer(
        etat, PhasePresentateur.PRESENTATEUR_GENERE,
        {"presentateur": "candidate.mp4", "task_id": "remote-42",
         "pilot_ok": True, "cout_approuve": True},
    )
    assert resultat.autorise is True
    assert etat.phase is PhasePresentateur.PRESENTATEUR_GENERE
    assert etat.task_ids == ["remote-42"]


def test_trois_candidats_payants_rejetes_bloquent_une_nouvelle_generation():
    etat = EtatPresentateur(
        phase=PhasePresentateur.PLAN_VISUEL_VERROUILLE,
        essais_payants_rejetes=3,
    )
    resultat = avancer(
        etat, PhasePresentateur.PRESENTATEUR_GENERE,
        {"presentateur": "candidate.mp4", "task_id": "remote-43",
         "pilot_ok": True, "cout_approuve": True},
    )
    assert resultat.autorise is False
    assert any("3 candidats" in blocage for blocage in resultat.blocages)


def test_livraison_ne_devient_verifiee_qu_apres_decode_et_revue_visuelle():
    etat = EtatPresentateur(phase=PhasePresentateur.RENDU)
    refuse = avancer(
        etat, PhasePresentateur.VERIFIE,
        {"decode_ok": True, "revue_visuelle_ok": False},
    )
    assert refuse.autorise is False
    accepte = avancer(
        etat, PhasePresentateur.VERIFIE,
        {"decode_ok": True, "revue_visuelle_ok": True},
    )
    assert accepte.autorise is True
    assert etat.phase is PhasePresentateur.VERIFIE


def test_task_id_est_dedoublonne_pour_permettre_la_reprise():
    etat = EtatPresentateur()
    etat.enregistrer_task_id("remote-1")
    etat.enregistrer_task_id("remote-1")
    assert etat.task_ids == ["remote-1"]
