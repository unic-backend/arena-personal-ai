"""Une tâche interrompue reprend là où elle s'est arrêtée.

**Le manque mesuré le 07/09/2026** (DEC-0072, comparaison avec
`langchain-ai/open-swe`) : `DioumtoukayAgent` s'arrête à douze actions ou vingt
minutes, rend honnêtement *« la suite reste à faire »*, et ne garde qu'un
**résumé en prose** dans la mémoire longue. « Reprends ce que tu faisais »
relançait donc le travail depuis zéro. `core/execution/travaux.py` ne pouvait
pas aider : sa file est purement en mémoire.

Ces tests tiennent la différence entre une **phrase** (« la suite reste à
faire ») et un **état** (« la suite reprendra ici »).
"""
import json
from pathlib import Path

import pytest

from core.execution.reprise import (
    AGE_MAX_SECONDES,
    TERMINEES_GARDEES,
    EtatTache,
    JournalDeReprise,
)

DEMANDE = "corrige le bug de calcul dans metre.py"


@pytest.fixture
def fichier(tmp_path) -> Path:
    return tmp_path / "travaux" / "reprises.json"


class TestUneTacheInterrompueReprend:
    """Le cœur de DEC-0072. Rien d'autre dans ce fichier ne compte autant."""

    def test_un_autre_processus_retrouve_le_travail_sur_le_disque(self, fichier):
        """La garantie réelle : ARENA redémarre, le travail est toujours là.

        Deux journaux distincts, comme deux exécutions successives d'ARENA.
        Rien n'est partagé en mémoire — seul le fichier fait le lien.
        """
        premier = JournalDeReprise(fichier=fichier)
        tache = premier.ouvrir(DEMANDE)
        for outil in ("lire", "chercher", "executer"):
            premier.noter(tache, outil, "metre.py", ok=True, resume=f"{outil} fait")
        premier.interrompre(tache, "plafond de douze actions atteint")

        second = JournalDeReprise(fichier=fichier)
        reprise = second.ouvrir(DEMANDE)

        assert reprise.identifiant == tache.identifiant, "le travail a ete perdu"
        assert len(reprise.etapes) == 3
        assert reprise.etat is EtatTache.EN_COURS

    def test_ce_qui_a_ete_fait_revient_sous_forme_utilisable(self, fichier):
        """Reprendre, c'est repartir avec le journal, pas avec un format neuf."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "metre.py", ok=True, resume="200 lignes lues")
        journal.noter(tache, "executer", "pytest", ok=False, resume="1 echec")
        journal.interrompre(tache)

        deja = JournalDeReprise(fichier=fichier).ouvrir(DEMANDE).deja_fait()

        assert deja == ["lire metre.py -> ok : 200 lignes lues",
                        "executer pytest -> echec : 1 echec"]

    def test_une_demande_differente_ne_reprend_pas_l_autre(self, fichier):
        """Continuer un travail sur un autre sujet serait pire que recommencer."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "metre.py")
        journal.interrompre(tache)

        autre = JournalDeReprise(fichier=fichier).ouvrir("refais le site vitrine")

        assert autre.identifiant != tache.identifiant
        assert autre.etapes == []

    def test_une_tache_terminee_ne_se_reprend_jamais(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "metre.py")
        journal.terminer(tache, "corrige")

        suivante = JournalDeReprise(fichier=fichier).ouvrir(DEMANDE)

        assert suivante.identifiant != tache.identifiant

    def test_une_tache_echouee_ne_se_reprend_pas_non_plus(self, fichier):
        """Rejouer un echec dont la cause n'a pas change le refait a l'identique."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "x")
        journal.echouer(tache, "aucun moteur joignable")

        assert JournalDeReprise(fichier=fichier).ouvrir(DEMANDE).etapes == []


class TestChaqueEtapeEstEcriteToutDeSuite:
    """Écrire à la fin perdrait exactement ce qu'on cherche à garder."""

    def test_le_fichier_contient_l_etape_avant_toute_cloture(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)

        journal.noter(tache, "remplacer", "metre.py", ok=True, resume="1 remplacement")

        # Aucune cloture n'a eu lieu : on simule une tache tuee ici meme.
        sur_disque = json.loads(fichier.read_text(encoding="utf-8"))
        etapes = sur_disque["taches"][0]["etapes"]
        assert len(etapes) == 1
        assert etapes[0]["outil"] == "remplacer"

    def test_l_ecriture_est_atomique_aucun_fichier_a_moitie_ecrit(self, fichier):
        """Un journal illisible au moment ou il sert ne sert a rien."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        for index in range(20):
            journal.noter(tache, "lire", f"f{index}.py")

        # Le fichier est toujours du JSON valide, et aucun temporaire ne traine.
        assert json.loads(fichier.read_text(encoding="utf-8"))["taches"]
        assert list(fichier.parent.glob(".reprises-*.tmp")) == []


class TestLeBalayageLibereLesTachesMortes:
    """L'idée de `reconcile.py` d'Open SWE, sans sa plateforme.

    Sans ce filet, une tâche dont le processus est mort reste « en cours »
    pour toujours : elle est perdue en se déclarant vivante.
    """

    def test_une_tache_qui_n_avance_plus_devient_reprenable(self, fichier):
        journal = JournalDeReprise(fichier=fichier, age_max=0.0)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "metre.py")

        liberees = JournalDeReprise(fichier=fichier, age_max=0.0).balayer()

        assert tache.identifiant in liberees

    def test_une_tache_vivante_n_est_pas_liberee(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "metre.py")

        assert JournalDeReprise(fichier=fichier).balayer() == []
        assert JournalDeReprise(fichier=fichier).lire(
            tache.identifiant).etat is EtatTache.EN_COURS

    def test_un_horodatage_illisible_est_traite_comme_ancien(self, fichier):
        """Se tromper dans ce sens fait reprendre en double. Dans l'autre, on perd."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "x")
        brut = json.loads(fichier.read_text(encoding="utf-8"))
        brut["taches"][0]["maj_le"] = "pas une date"
        fichier.write_text(json.dumps(brut), encoding="utf-8")

        assert JournalDeReprise(fichier=fichier).balayer() == [tache.identifiant]

    def test_l_age_par_defaut_depasse_le_plafond_de_l_agent(self):
        """20 minutes de travail ne doivent jamais etre prises pour une mort."""
        from agents.dioumtoukay.dioumtoukay_agent import DUREE_MAX_SECONDES

        assert AGE_MAX_SECONDES > DUREE_MAX_SECONDES


class TestUnJournalEnPanneNEmportePasLeTravail:
    """Perdre le travail parce que sa mémoire est en panne serait absurde."""

    def test_un_fichier_corrompu_repart_a_vide_sans_lever(self, fichier):
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text("{ceci n'est pas du json", encoding="utf-8")

        journal = JournalDeReprise(fichier=fichier)

        assert journal.inventaire() == []
        assert journal.ouvrir(DEMANDE).etapes == []

    def test_une_seule_tache_abimee_n_emporte_pas_les_autres(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        bonne = journal.ouvrir(DEMANDE)
        journal.noter(bonne, "lire", "metre.py")
        journal.interrompre(bonne)
        brut = json.loads(fichier.read_text(encoding="utf-8"))
        brut["taches"].append({"pas_d_identifiant": True})
        fichier.write_text(json.dumps(brut), encoding="utf-8")

        relu = JournalDeReprise(fichier=fichier)

        assert [t.identifiant for t in relu.inventaire()] == [bonne.identifiant]

    def test_un_dossier_impossible_a_ecrire_ne_leve_pas(self, tmp_path):
        """Le travail continue ; seule sa memoire manque, et le log le dit."""
        barrage = tmp_path / "barrage"
        barrage.write_text("je suis un fichier, pas un dossier", encoding="utf-8")

        journal = JournalDeReprise(fichier=barrage / "sous" / "j.json")
        tache = journal.ouvrir(DEMANDE)
        journal.noter(tache, "lire", "x")

        assert len(tache.etapes) == 1, "le travail doit continuer en memoire"


class TestLaPurgeNeMangeJamaisDuTravail:
    def test_les_terminees_les_plus_anciennes_sont_oubliees(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        for index in range(TERMINEES_GARDEES + 5):
            tache = journal.ouvrir(f"demande {index}")
            journal.terminer(tache, "ok")

        assert len(journal.inventaire(EtatTache.TERMINEE)) == TERMINEES_GARDEES

    def test_une_tache_reprenable_survit_a_toutes_les_purges(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        precieuse = journal.ouvrir(DEMANDE)
        journal.noter(precieuse, "remplacer", "metre.py")
        journal.interrompre(precieuse, "a reprendre")

        for index in range(TERMINEES_GARDEES + 10):
            journal.terminer(journal.ouvrir(f"bruit {index}"), "ok")

        assert JournalDeReprise(fichier=fichier).lire(precieuse.identifiant) is not None
