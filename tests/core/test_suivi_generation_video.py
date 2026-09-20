"""Suivre une video jusqu'au fichier, pendant que la conversation continue.

Le test que ce module doit passer est `test_le_chat_n_attend_pas_la_video` :
le suivi tourne en fond, le tour de chat se termine avant lui.
"""
import asyncio

import pytest

from core.connectors.suivi_video import (
    Suivi,
    fabrique_de_reprise,
    suivre_en_fond,
    suivre_generation,
)
from core.execution.travaux import EtatTravail, FileDeTravaux, Travail


class FauxConnecteur:
    """Rend les instantanes prevus, un par interrogation."""

    def __init__(self, instantanes):
        self.instantanes = list(instantanes)
        self.appels = 0

    def executer(self, capacite, **parametres):
        self.appels += 1
        # Une fois la liste epuisee, on rend le dernier instantane : un test qui
        # inventerait une fin de tache mesurerait le faux, pas le module.
        instantane = (self.instantanes.pop(0) if len(self.instantanes) > 1
                      else self.instantanes[0] if self.instantanes else None)

        class _Resultat:
            detail = {"donnees": instantane}
        return _Resultat()


EN_COURS = {"done": False, "result": {"total_tasks": 4, "successful_tasks": 1}}
FINI = {"done": True, "result": {"success": True, "total_tasks": 4, "successful_tasks": 4,
                                 "generated_files": ["outputs/chantier.mp4"]}}


# --- Le test que ce module doit passer ------------------------------------------

async def test_le_chat_n_attend_pas_la_video():
    file = FileDeTravaux()
    connecteur = FauxConnecteur([EN_COURS, EN_COURS, FINI])

    travail = suivre_en_fond(connecteur, file, "job-7", intervalle=0)
    await asyncio.sleep(0)

    assert travail.etat is EtatTravail.EN_COURS, "le suivi doit tourner en fond"

    async def un_tour_de_chat():
        await asyncio.sleep(0)
        return "reponse"

    assert await un_tour_de_chat() == "reponse"

    fini = await file.attendre(travail.identifiant)
    assert fini.etat is EtatTravail.TERMINE
    assert fini.resultat.fichiers == ["outputs/chantier.mp4"]


# --- La progression vient de WanGP ------------------------------------------------

async def test_la_progression_suit_les_taches_annoncees():
    travail = Travail(nom="generation")
    connecteur = FauxConnecteur([EN_COURS, FINI])

    await suivre_generation(connecteur, "job-7", travail, intervalle=0)

    assert travail.total == 4
    assert travail.faits == 4
    assert travail.progression == 1.0


async def test_un_total_encore_inconnu_ne_devient_pas_zero():
    travail = Travail(nom="generation")
    connecteur = FauxConnecteur([{"done": False, "result": None}, FINI])

    await suivre_generation(connecteur, "job-7", travail, intervalle=0)

    assert travail.total == 4, "le total arrive quand WanGP le donne"


# --- Ce qui ne reussit pas le dit ---------------------------------------------------

async def test_une_generation_annulee_n_est_pas_une_reussite():
    annulee = {"done": True, "cancel_requested": True,
               "result": {"success": False, "cancelled": True, "generated_files": []}}
    suivi = await suivre_generation(FauxConnecteur([annulee]), "job-7", intervalle=0)

    assert suivi.termine is True
    assert suivi.reussi is False
    assert suivi.annule is True
    assert "annulee" in suivi.raison


async def test_une_generation_en_erreur_rapporte_le_nombre_d_erreurs():
    ratee = {"done": True, "result": {"success": False, "errors": [{"m": "vram"}, {"m": "x"}],
                                      "generated_files": []}}
    suivi = await suivre_generation(FauxConnecteur([ratee]), "job-7", intervalle=0)

    assert suivi.reussi is False
    assert "2 erreur(s)" in suivi.raison
    assert suivi.fichiers == []


async def test_un_serveur_muet_fait_abandonner_le_suivi():
    muet = FauxConnecteur([{"pas": "un instantane"}] * 9)
    suivi = await suivre_generation(muet, "job-7", intervalle=0)

    assert suivi.termine is True
    assert suivi.reussi is False
    assert "exploitable" in suivi.raison


async def test_le_plafond_arrete_le_suivi_et_le_dit():
    sans_fin = FauxConnecteur([EN_COURS] * 50)
    suivi = await suivre_generation(sans_fin, "job-7", intervalle=1.0, plafond=3.0)

    assert suivi.termine is True
    assert suivi.reussi is False
    assert "abandonne" in suivi.raison
    assert "continue peut-etre" in suivi.raison, "WanGP peut continuer : ne pas le laisser croire arrete"


async def test_sans_identifiant_il_n_y_a_rien_a_suivre():
    suivi = await suivre_generation(FauxConnecteur([]), "", intervalle=0)

    assert suivi == Suivi(job_id="", termine=True,
                          raison="aucun identifiant de tache a suivre")


class TestRepriseApresRedemarrage:
    """Le suivi d'une génération est le SEUL travail de fond qui se reprend
    vraiment après un redémarrage — et pour une raison précise : son état ne
    vit pas dans ARENA, il vit chez WanGP. Reprendre, c'est redemander « où en
    est la tâche job_id ? ». Aucune écriture n'est rejouée.
    """

    async def test_un_suivi_declare_ce_qu_il_est(self, tmp_path):
        """Le descripteur porte des DONNÉES, jamais du code.

        Sans lui, un suivi coupé par un redémarrage resterait interrompu à
        jamais : personne ne saurait quelle tâche WanGP il regardait.
        """
        file = FileDeTravaux(fichier=tmp_path / "file.json")
        travail = suivre_en_fond(FauxConnecteur([EN_COURS]), file, "job-7",
                                 intervalle=0)

        assert travail.descripteur["type"] == "suivi_generation_video"
        assert travail.descripteur["parametres"]["job_id"] == "job-7"
        assert travail.reprenable is False, "il tourne : il n'y a rien a reprendre"
        file.annuler(travail.identifiant)

    async def test_deux_suivis_de_la_meme_generation_sont_un_seul_travail(self, tmp_path):
        """Redemander « où en est ma vidéo ? » ne lance pas un second suivi."""
        file = FileDeTravaux(fichier=tmp_path / "file.json")
        connecteur = FauxConnecteur([EN_COURS])
        un = suivre_en_fond(connecteur, file, "job-7", intervalle=0)
        deux = suivre_en_fond(connecteur, file, "job-7", intervalle=0)

        # Tant que le premier TOURNE, la cle ne s'applique pas (elle ne vaut
        # que pour un travail DEJA TERMINE) : ce sont donc deux travaux, et
        # c'est voulu — un suivi en cours n'est pas un resultat acquis.
        assert un.identifiant != deux.identifiant
        assert un.cle == deux.cle == "suivi_generation_video:job-7"
        file.annuler(un.identifiant)
        file.annuler(deux.identifiant)

    async def test_un_suivi_coupe_par_un_redemarrage_est_repris(self, tmp_path):
        """Le parcours complet : coupé, relu, reconstruit, relancé."""
        chemin = tmp_path / "file.json"
        file = FileDeTravaux(fichier=chemin)
        travail = suivre_en_fond(FauxConnecteur([EN_COURS]), file, "job-7",
                                 intervalle=0)
        await asyncio.sleep(0)  # il demarre, donc il s'ecrit EN_COURS

        # Le serveur redemarre : nouvelle file, nouveau connecteur.
        relue = FileDeTravaux(fichier=chemin)
        assert relue.lire(travail.identifiant).etat is EtatTravail.INTERROMPU

        connecteur = FauxConnecteur([FINI])
        repris = relue.reprendre_les_interrompus(
            {"suivi_generation_video": fabrique_de_reprise(connecteur)})

        assert len(repris) == 1
        suivi = (await relue.attendre(repris[0].identifiant, delai=2.0)).resultat
        assert suivi.job_id == "job-7"
        assert suivi.reussi is True
        assert connecteur.appels >= 1, "WanGP doit avoir ete reinterroge"

    def test_un_suivi_sans_job_id_ne_se_reprend_pas(self):
        """Mieux vaut refuser que reconstruire un suivi qui ne regarde rien."""
        fabriquer = fabrique_de_reprise(FauxConnecteur([EN_COURS]))

        with pytest.raises(ValueError):
            fabriquer({})
