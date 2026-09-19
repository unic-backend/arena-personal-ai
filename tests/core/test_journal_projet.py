"""L'état durable d'un projet : ce qui survit à un redémarrage, et ce qui ne
doit SURTOUT pas être rejoué.

Quatre tests portent l'étape, parce qu'ils décrivent quatre façons dont ce
module ferait perdre du travail ou en referait :

- `test_une_etape_dont_l_artefact_a_disparu_n_est_plus_reutilisable` : se fier
  au statut seul rendrait un projet qui se dit fini sans fichier au bout.
- `test_une_etape_en_cours_au_redemarrage_n_est_pas_reussie` : rien ne tourne
  au démarrage ; une étape laissée `RUNNING` a été décidée sans qu'on sache ce
  qu'elle a donné.
- `test_un_artefact_annonce_mais_absent_n_est_pas_retenu` : un outil qui
  annonce un fichier sans l'écrire ne doit pas faire croire à une livraison.
- `test_une_entree_differente_rend_l_etape_a_refaire` : c'est la règle
  d'idempotence — même job, même étape, **même entrée**.

Aucun test ici n'écrit hors de `tmp_path`.
"""
import json

import pytest

from core.production.journal_projet import (
    EtatJob,
    JournalProjets,
    empreinte,
)


@pytest.fixture
def journal(tmp_path):
    return JournalProjets(tmp_path / "journal.json")


@pytest.fixture
def artefact(tmp_path):
    fichier = tmp_path / "rendu.mp4"
    fichier.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return str(fichier)


def _projet(journal, etapes=("vision", "montage")):
    job = journal.ouvrir("fabrique une video de chantier",
                         graphe=[{"id": e, "capacite": e} for e in etapes])
    journal.declarer_etapes(job.job_id, [
        {"step_id": e, "capacite": e, "entree": {"reference": 0}} for e in etapes])
    return job


# --- Le cycle de vie ---------------------------------------------------------------

def test_un_job_existe_sur_le_disque_avant_sa_premiere_etape(journal):
    """Sinon un crash pendant l'étape 1 ne laisserait aucune trace du projet."""
    job = journal.ouvrir("fabrique une video")

    charge = json.loads(journal.fichier.read_text(encoding="utf-8"))
    assert [j["job_id"] for j in charge["jobs"]] == [job.job_id]
    assert charge["jobs"][0]["status"] == "RUNNING"


def test_les_six_etats_sont_ceux_demandes():
    """La liste est fermée : un septième état implicite serait une supposition."""
    assert {e.value for e in EtatJob} == {
        "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "PAUSED"}


def test_chaque_etape_porte_ce_qu_un_ingenieur_doit_pouvoir_lire(journal, artefact):
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision", entree={"reference": 0})
    journal.conclure_etape(job.job_id, "vision", EtatJob.REUSSI,
                           sortie={"statut": "SUCCESS"}, artefact=artefact,
                           preuve={"secondes": 1.5, "tentatives": 1}, essais=1)

    etape = journal.lire(job.job_id).etape("vision").to_dict()
    for champ in ("step_id", "status", "created_at", "updated_at", "input",
                  "output", "artifact", "proof", "error", "retry_count"):
        assert champ in etape, champ
    assert etape["artifact"] == artefact
    assert etape["proof"]["secondes"] == 1.5


# --- Ce qui survit au redémarrage ----------------------------------------------------

def test_le_journal_se_relit_apres_un_redemarrage(journal, artefact, tmp_path):
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision")
    journal.conclure_etape(job.job_id, "vision", EtatJob.REUSSI,
                           sortie={"statut": "SUCCESS"}, artefact=artefact)

    relu = JournalProjets(tmp_path / "journal.json")

    assert relu.lire(job.job_id).etape("vision").etat is EtatJob.REUSSI
    assert relu.lire(job.job_id).deja_fait() == {"vision": {"statut": "SUCCESS"}}


def test_une_etape_en_cours_au_redemarrage_n_est_pas_reussie(journal, tmp_path):
    """Le processus est mort entre la décision et le résultat.

    L'étape n'est ni réussie ni échouée : on ne sait pas. La nommer est la
    seule façon de ne pas la rejouer en aveugle.
    """
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision")  # tuée ici

    relu = JournalProjets(tmp_path / "journal.json")
    reprise = relu.lire(job.job_id)

    assert reprise.etat is EtatJob.SUSPENDU
    assert reprise.etape("vision").confirmee is False
    assert reprise.etape("vision").reutilisable is False
    assert reprise.a_verifier() == ["vision"]


def test_une_etape_running_ecrite_confirmee_est_normalisee_au_chargement(tmp_path):
    """Un fichier venu d'ailleurs peut porter une contradiction.

    `RUNNING` **et** `confirmee` ne peut pas être vrai : une étape confirmée a
    un résultat connu, donc elle n'est plus en cours. Le journal lit un fichier
    sur un disque — c'est précisément l'endroit où ses propres invariants ne
    sont pas garantis. Il normalise plutôt que de faire confiance, sinon une
    étape dont on ne sait rien serait comptée comme sûre.
    """
    (tmp_path / "journal.json").write_text(json.dumps({"jobs": [{
        "job_id": "venu-d-ailleurs", "project_id": "p", "objectif": "o",
        "status": "RUNNING",
        "steps": [{"step_id": "montage", "capacite": "montage",
                   "status": "RUNNING", "confirmee": True}],
    }]}), encoding="utf-8")

    job = JournalProjets(tmp_path / "journal.json").lire("venu-d-ailleurs")

    assert job.etat is EtatJob.SUSPENDU
    assert job.etape("montage").confirmee is False
    assert job.a_verifier() == ["montage"]


def test_un_job_suspendu_dont_tout_tient_n_est_pas_reprenable(journal, artefact,
                                                              tmp_path):
    """Sinon on enverrait le propriétaire relancer un travail déjà fait."""
    job = journal.ouvrir("fabrique une video")
    journal.declarer_etapes(job.job_id, [{"step_id": "vision", "capacite": "vision"}])
    journal.demarrer_etape(job.job_id, "vision")
    journal.conclure_etape(job.job_id, "vision", EtatJob.REUSSI, artefact=artefact)
    journal.suspendre(job.job_id, "coupure")

    relu = JournalProjets(tmp_path / "journal.json")

    assert relu.lire(job.job_id).reprenable is False
    assert relu.reprenables() == []


def test_un_job_suspendu_dont_il_reste_du_travail_est_reprenable(journal, artefact):
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision")
    journal.conclure_etape(job.job_id, "vision", EtatJob.REUSSI, artefact=artefact)
    journal.suspendre(job.job_id, "coupure")

    assert journal.lire(job.job_id).reprenable is True
    assert [j.job_id for j in journal.reprenables()] == [job.job_id]


# --- La règle qui empêche de refaire un travail --------------------------------------

def test_une_etape_reussie_avec_son_artefact_est_reutilisable(journal, artefact):
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "montage")
    journal.conclure_etape(job.job_id, "montage", EtatJob.REUSSI,
                           sortie={"preuve": artefact}, artefact=artefact)

    assert journal.lire(job.job_id).etape("montage").reutilisable is True


def test_une_etape_dont_l_artefact_a_disparu_n_est_plus_reutilisable(journal,
                                                                     artefact,
                                                                     tmp_path):
    """Le statut dit « réussi », le fichier n'est plus là.

    Sauter l'étape rendrait un projet qui se déclare fini sans rien livrer.
    """
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "montage")
    journal.conclure_etape(job.job_id, "montage", EtatJob.REUSSI, artefact=artefact)
    assert journal.lire(job.job_id).etape("montage").reutilisable is True

    (tmp_path / "rendu.mp4").unlink()

    assert journal.lire(job.job_id).etape("montage").reutilisable is False
    assert journal.lire(job.job_id).deja_fait() == {}


def test_un_artefact_annonce_mais_absent_n_est_pas_retenu(journal):
    """Ce qui n'existe pas n'est pas un artefact — et la raison est écrite."""
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "montage")
    etape = journal.conclure_etape(job.job_id, "montage", EtatJob.REUSSI,
                                   artefact="/nulle/part/final.mp4")

    assert etape.artefact is None
    assert "absent du disque" in etape.erreur


def test_une_etape_echouee_n_est_jamais_reutilisable(journal):
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision")
    journal.conclure_etape(job.job_id, "vision", EtatJob.ECHOUE, erreur="timeout")

    assert journal.lire(job.job_id).etape("vision").reutilisable is False


def test_une_etape_sans_artefact_se_reutilise_sur_son_statut(journal):
    """Une analyse ne produit pas de fichier : il n'y a rien à vérifier."""
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision")
    journal.conclure_etape(job.job_id, "vision", EtatJob.REUSSI,
                           sortie={"statut": "SUCCESS", "message": "une photo"})

    assert journal.lire(job.job_id).etape("vision").reutilisable is True


# --- L'idempotence : même entrée, ou rien ---------------------------------------------

def test_une_entree_differente_rend_l_etape_a_refaire(journal):
    """Même job, même étape, **entrée différente** : ce n'est pas le même travail."""
    avant = empreinte({"reference": 0, "demande": "monte les rushes"})
    apres = empreinte({"reference": 0, "demande": "monte en vertical"})

    assert avant != apres


def test_une_entree_identique_donne_la_meme_empreinte_quel_que_soit_l_ordre():
    assert empreinte({"a": 1, "b": 2}) == empreinte({"b": 2, "a": 1})


def test_une_entree_non_serialisable_ne_fait_pas_tomber_la_production():
    """Un paramètre exotique rend une empreinte, jamais une exception."""
    assert empreinte({"objet": object()})


def test_redeclarer_le_graphe_n_efface_pas_ce_qui_a_abouti(journal, artefact):
    """C'est ce qui rend la reprise possible : le même graphe, rejoué, ne
    remet pas à zéro les étapes déjà faites."""
    job = _projet(journal)
    journal.demarrer_etape(job.job_id, "vision")
    journal.conclure_etape(job.job_id, "vision", EtatJob.REUSSI, artefact=artefact)

    journal.declarer_etapes(job.job_id, [
        {"step_id": "vision", "capacite": "vision"},
        {"step_id": "montage", "capacite": "montage"}])

    assert journal.lire(job.job_id).etape("vision").etat is EtatJob.REUSSI
    assert len(journal.lire(job.job_id).etapes) == 2


# --- Annuler -------------------------------------------------------------------------

def test_annuler_est_definitif_et_idempotent(journal):
    job = _projet(journal)
    journal.annuler(job.job_id, "annule")
    journal.annuler(job.job_id, "annule encore")

    assert journal.lire(job.job_id).etat is EtatJob.ANNULE


def test_un_job_deja_reussi_ne_redevient_pas_annulable(journal, artefact):
    """Sinon un double appel effacerait un succès."""
    job = _projet(journal)
    journal.conclure(job.job_id, EtatJob.REUSSI, artefact_final=artefact)
    journal.annuler(job.job_id)

    assert journal.lire(job.job_id).etat is EtatJob.REUSSI


def test_un_job_annule_n_est_pas_reprenable(journal):
    job = _projet(journal)
    journal.annuler(job.job_id)

    assert journal.lire(job.job_id).reprenable is False


# --- Un journal cassé ne casse pas la production --------------------------------------

def test_un_journal_illisible_repart_a_vide_sans_lever(tmp_path):
    (tmp_path / "journal.json").write_text("{ceci n'est pas du json", encoding="utf-8")

    journal = JournalProjets(tmp_path / "journal.json")

    assert journal.reprenables() == []
    assert journal.ouvrir("un projet").job_id


def test_un_job_illisible_est_ignore_sans_emporter_les_autres(tmp_path):
    bon = {"job_id": "ok", "project_id": "p", "objectif": "o", "status": "PAUSED",
           "steps": [{"step_id": "a", "status": "PENDING"}]}
    (tmp_path / "journal.json").write_text(
        json.dumps({"jobs": [{"pas_de_job_id": True}, bon]}), encoding="utf-8")

    journal = JournalProjets(tmp_path / "journal.json")

    assert journal.lire("ok") is not None


def test_conclure_une_etape_d_un_job_inconnu_ne_leve_pas(journal):
    assert journal.conclure_etape("job-fantome", "vision", EtatJob.REUSSI) is None
    assert journal.demarrer_etape("job-fantome", "vision") is None
    assert journal.conclure("job-fantome", EtatJob.REUSSI) is None
