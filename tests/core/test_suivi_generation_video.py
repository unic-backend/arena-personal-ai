"""Suivre une video jusqu'au fichier, pendant que la conversation continue.

Le test que ce module doit passer est `test_le_chat_n_attend_pas_la_video` :
le suivi tourne en fond, le tour de chat se termine avant lui.
"""
import asyncio

from core.connectors.suivi_video import Suivi, suivre_en_fond, suivre_generation
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
