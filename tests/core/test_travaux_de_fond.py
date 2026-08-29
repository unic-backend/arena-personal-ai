"""Les travaux de fond : ils avancent, le chat ne les attend pas.

Le test que la phase doit passer est
`test_le_chat_repond_pendant_qu_un_travail_tourne` : un tour de conversation
se termine alors qu'un travail long est encore en cours, et sa duree tient
dans le budget de la voie legere.
"""
import asyncio

import pytest

import core.execution.travaux as travaux_module
from core.execution.mesures import ETAT_MESURE, VERDICT_DANS_LE_BUDGET, chronometrer
from core.execution.travaux import EtatTravail, FileDeTravaux, Travail
from core.execution.voies import Voie

# --- Le test que la phase doit passer ------------------------------------------

async def test_le_chat_repond_pendant_qu_un_travail_tourne():
    file = FileDeTravaux()
    bloque = asyncio.Event()

    async def travail_long():
        await bloque.wait()          # tient la place tant qu'on ne le libere pas
        return "indexation finie"

    travail = file.soumettre("indexation", travail_long)
    await asyncio.sleep(0)           # laisse la boucle demarrer le travail

    assert travail.etat is EtatTravail.EN_COURS, "le travail doit vraiment tourner"

    async def un_tour_de_chat():
        await asyncio.sleep(0.01)
        return "reponse"

    mesure = await chronometrer("tour de chat", Voie.LEGERE, un_tour_de_chat)

    assert mesure.etat == ETAT_MESURE
    assert mesure.verdict == VERDICT_DANS_LE_BUDGET
    assert travail.etat is EtatTravail.EN_COURS, "le chat n'a pas attendu la fin"

    bloque.set()
    fini = await file.attendre(travail.identifiant)
    assert fini.etat is EtatTravail.TERMINE
    assert fini.resultat == "indexation finie"


async def test_soumettre_n_execute_rien():
    file = FileDeTravaux()
    demarre = False

    def corps():
        nonlocal demarre
        demarre = True

    travail = file.soumettre("calcul", corps)

    assert travail.etat is EtatTravail.EN_ATTENTE
    assert demarre is False, "le corps a tourne dans l'appelant : c'est bloquant"

    await file.attendre(travail.identifiant)
    assert demarre is True


# --- Une panne de fond reste au fond --------------------------------------------

async def test_une_panne_de_travail_ne_remonte_jamais():
    file = FileDeTravaux()

    def tombe():
        raise ConnectionError("le serveur d'indexation ne repond pas")

    travail = file.soumettre("indexation", tombe)
    fini = await file.attendre(travail.identifiant)

    assert fini.etat is EtatTravail.ECHOUE
    assert "serveur d'indexation" in fini.raison
    assert fini.resultat is None, "un travail echoue ne rend pas un resultat plausible"


async def test_un_travail_echoue_n_empeche_pas_les_suivants():
    file = FileDeTravaux()

    def tombe():
        raise RuntimeError("panne")

    rate = file.soumettre("premier", tombe)
    bon = file.soumettre("second", lambda: 42)
    await file.fermer()

    assert file.lire(rate.identifiant).etat is EtatTravail.ECHOUE
    assert file.lire(bon.identifiant).resultat == 42


# --- Le parallelisme est borne ---------------------------------------------------

async def test_dix_travaux_soumis_ne_font_pas_dix_travaux_simultanes():
    file = FileDeTravaux(parallelisme=2)
    bloque = asyncio.Event()
    simultanes = 0
    pointe = 0

    async def occupe():
        nonlocal simultanes, pointe
        simultanes += 1
        pointe = max(pointe, simultanes)
        await bloque.wait()
        simultanes -= 1

    for numero in range(10):
        file.soumettre(f"travail {numero}", occupe)
    await asyncio.sleep(0)

    assert pointe <= 2, f"{pointe} travaux en meme temps pour un parallelisme de 2"
    assert file.en_cours <= 2

    bloque.set()
    await file.fermer()


def test_une_file_sans_execution_est_refusee():
    with pytest.raises(ValueError, match="n'est pas une file"):
        FileDeTravaux(parallelisme=0)


# --- La progression se compte ----------------------------------------------------

async def test_la_progression_suit_les_unites_traitees():
    file = FileDeTravaux()

    def indexer(travail: Travail):
        for _ in range(4):
            travail.faits += 1

    travail = file.soumettre("indexation", indexer, total=4, passer_le_travail=True)
    fini = await file.attendre(travail.identifiant)

    assert fini.faits == 4
    assert fini.progression == 1.0


def test_un_total_inconnu_ne_vaut_ni_zero_ni_cent_pour_cent():
    travail = Travail(nom="indexation")

    assert travail.total is None
    assert travail.progression is None, "0.0 se lirait « rien n'avance », et c'est faux"


def test_la_progression_ne_depasse_jamais_un():
    travail = Travail(nom="indexation", total=2, faits=5)

    assert travail.progression == 1.0


# --- L'annulation -----------------------------------------------------------------

async def test_annuler_deux_fois_n_annule_qu_une_fois():
    file = FileDeTravaux()
    bloque = asyncio.Event()

    async def occupe():
        await bloque.wait()

    travail = file.soumettre("longue analyse", occupe)
    await asyncio.sleep(0)

    assert file.annuler(travail.identifiant) is True
    assert file.annuler(travail.identifiant) is False
    assert travail.etat is EtatTravail.ANNULE

    bloque.set()


async def test_un_travail_termine_ne_s_annule_plus():
    file = FileDeTravaux()
    travail = file.soumettre("calcul", lambda: 1)
    await file.attendre(travail.identifiant)

    assert file.annuler(travail.identifiant) is False
    assert travail.etat is EtatTravail.TERMINE


def test_annuler_un_travail_inconnu_rend_faux():
    assert FileDeTravaux().annuler("identifiant-qui-n-existe-pas") is False


# --- L'inventaire ------------------------------------------------------------------

async def test_l_inventaire_montre_aussi_les_echecs():
    file = FileDeTravaux()

    def tombe():
        raise RuntimeError("panne")

    file.soumettre("rate", tombe)
    file.soumettre("reussi", lambda: 1)
    await file.fermer()

    etats = {travail.nom: travail.etat for travail in file.inventaire()}

    assert etats == {"rate": EtatTravail.ECHOUE, "reussi": EtatTravail.TERMINE}
    assert len(file.inventaire(EtatTravail.ECHOUE)) == 1


# --- L'historique des travaux finis est borne ---------------------------------

async def test_l_historique_des_travaux_finis_est_borne(monkeypatch):
    """`_travaux`/`_taches` grossissaient sans fin, meme pour des travaux deja
    TERMINE : un serveur de longue duree les accumulerait pour toujours. Seuls
    les `TRAVAUX_TERMINES_GARDES` plus recents doivent rester."""
    monkeypatch.setattr(travaux_module, "TRAVAUX_TERMINES_GARDES", 3)
    file = FileDeTravaux()

    for numero in range(10):
        travail = file.soumettre(f"travail {numero}", lambda n=numero: n)
        await file.attendre(travail.identifiant)

    assert len(file.inventaire()) == 3, "l'historique doit rester plafonne"
    noms = {t.nom for t in file.inventaire()}
    assert noms == {"travail 7", "travail 8", "travail 9"}, "seuls les plus recents restent"


async def test_un_travail_en_cours_n_est_jamais_purge(monkeypatch):
    """La purge ne touche que les travaux FINIS : un travail encore EN_COURS
    ne doit jamais disparaitre, meme quand l'historique deborde autour de lui."""
    monkeypatch.setattr(travaux_module, "TRAVAUX_TERMINES_GARDES", 1)
    file = FileDeTravaux(parallelisme=2)
    bloque = asyncio.Event()

    async def occupe():
        await bloque.wait()

    en_cours = file.soumettre("encore en cours", occupe)
    await asyncio.sleep(0)

    for numero in range(5):
        fini = file.soumettre(f"fini {numero}", lambda n=numero: n)
        await file.attendre(fini.identifiant)

    encore_la = file.lire(en_cours.identifiant)
    assert encore_la is not None, "un travail EN_COURS ne doit jamais etre purge"
    assert encore_la.etat is EtatTravail.EN_COURS

    bloque.set()
    await file.fermer()
