"""La chronologie : elle rend ce qui est enregistre, et rien d'autre.

Le test qui compte le plus est `test_une_action_traverse_toute_la_chaine` : il
part d'une demande de publication et va jusqu'a la ligne de chronologie, sans
ecrire une seule fois dans le journal a la main.
"""
import pytest

from agents.publisher.publisher_agent import PublisherAgent
from core.actions.journal import ActionEnregistree, EtatVerification, JournalDesActions
from core.actions.resultat import non_configure, refuse, succes
from core.actions.timeline import SANS_PREUVE, en_lignes, formater, resume, to_dict


@pytest.fixture
def journal(tmp_path):
    return JournalDesActions(db_path=str(tmp_path / "journal.db"))


@pytest.fixture
def video_factice(tmp_path):
    chemin = tmp_path / "video.mp4"
    chemin.write_bytes(b"fichier present")
    return chemin


def _action(**remplacements) -> ActionEnregistree:
    valeurs = {
        "outil": "tiktok", "action": "publish_video", "cible": "TikTok",
        "resultat": "NOT_CONFIGURED", "horodatage": "2026-08-27T08:32:00+00:00",
        "verification": EtatVerification.SANS_OBJET,
    }
    valeurs.update(remplacements)
    return ActionEnregistree(**valeurs)


# --- La chaine complete -------------------------------------------------------

async def test_une_action_traverse_toute_la_chaine(provider_factory, journal, video_factice):
    """De la demande a la ligne de chronologie, sans ecriture manuelle."""
    agent = PublisherAgent(provider=provider_factory("Titre\n#tech"), journal=journal)

    await agent.run("Les tendances tech", context={"video_path": str(video_factice)})

    lignes = en_lignes(journal.dernieres())
    assert len(lignes) == 1
    assert lignes[0]["service"] == "tiktok"
    assert lignes[0]["action"] == "publish_video"
    assert lignes[0]["cible"] == "TikTok"
    assert lignes[0]["resultat"] == "DENIED"
    assert lignes[0]["verification"] == "NOT_APPLICABLE"


async def test_chaque_chemin_de_l_agent_laisse_une_trace(
    provider_factory, journal, video_factice
):
    agent = PublisherAgent(provider=provider_factory(), journal=journal)

    await agent.run("Sujet", context={"video_path": "/inexistant.mp4"})   # FAILED
    await agent.run("Sujet", context={"video_path": str(video_factice)})  # DENIED
    agent.permissions.permissions["PUBLISH"] = True
    await agent.run("Sujet", context={"video_path": str(video_factice)})  # NEEDS_CONFIRMATION

    resultats = {a.resultat for a in journal.dernieres()}
    assert resultats == {"FAILED", "DENIED", "NEEDS_CONFIRMATION"}


async def test_le_chemin_de_la_video_journalise_n_est_pas_perdu(
    provider_factory, journal, video_factice
):
    agent = PublisherAgent(provider=provider_factory(), journal=journal)

    await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert journal.dernieres()[0].parametres["fichier"] == str(video_factice)


async def test_sans_journal_l_agent_fonctionne_quand_meme(provider_factory, video_factice):
    """Un journal absent ne doit jamais empecher une action de se derouler."""
    agent = PublisherAgent(provider=provider_factory(), journal=None)

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == "DENIED"


async def test_un_journal_en_panne_n_empeche_pas_l_action(
    provider_factory, journal, video_factice, monkeypatch
):
    monkeypatch.setattr(journal, "enregistrer", lambda action: False)
    agent = PublisherAgent(provider=provider_factory(), journal=journal)

    assert (await agent.run("S", context={"video_path": str(video_factice)}))["status"] == "DENIED"


# --- La plateforme branche bien le journal ------------------------------------

def test_le_publieur_de_la_plateforme_a_un_journal():
    """Le defaut d'`agent_logs` etait qu'aucun code ne l'ecrivait. Ce test le tient."""
    from apps.backend import runtime

    assert runtime.publisher_agent.journal is not None
    assert runtime.publisher_agent.journal is runtime.journal


# --- Le rendu -----------------------------------------------------------------

def test_l_heure_est_extraite_de_l_horodatage():
    assert en_lignes([_action()])[0]["heure"] == "08:32"


def test_un_horodatage_illisible_est_rendu_tel_quel():
    assert en_lignes([_action(horodatage="pas une date")])[0]["heure"] == "pas une date"


def test_une_preuve_absente_a_un_signe_a_elle():
    """Vide serait ambigu : preuve manquante, ou action qui n'en attendait pas ?"""
    assert en_lignes([_action()])[0]["preuve"] == SANS_PREUVE


def test_une_preuve_presente_est_affichee():
    ligne = en_lignes([_action(resultat="SUCCESS", preuve="https://tiktok.com/v/9",
                               verification=EtatVerification.VERIFIEE)])[0]
    assert ligne["preuve"] == "https://tiktok.com/v/9"


def test_le_statut_est_affiche_en_toutes_lettres_jamais_en_symbole():
    """Deux symboles pour sept etats forcerait a ranger NOT_CONFIGURED du
    mauvais cote. Le statut s'ecrit."""
    rendu = formater([_action(), _action(resultat="DENIED")])

    assert "NOT_CONFIGURED" in rendu
    assert "DENIED" in rendu
    assert "✅" not in rendu and "❌" not in rendu


def test_les_colonnes_de_la_specification_sont_toutes_la():
    rendu = formater([_action()])
    for colonne in ("HEURE", "ACTION", "SERVICE", "CIBLE", "RESULTAT", "VERIFICATION"):
        assert colonne in rendu


def test_un_journal_vide_le_dit():
    assert formater([]) == "Aucune action enregistree."


def test_les_colonnes_sont_alignees():
    rendu = formater([_action(cible="TikTok"), _action(cible="un-nom-de-cible-tres-long")])
    lignes = rendu.splitlines()

    assert len({len(ligne) for ligne in lignes[2:]}) == 1


# --- Le resume ----------------------------------------------------------------

def test_le_resume_compte_par_resultat():
    compte = resume([_action(), _action(), _action(resultat="DENIED")])

    assert compte["total"] == 3
    assert compte["NOT_CONFIGURED"] == 2
    assert compte["DENIED"] == 1


def test_avec_effet_verifie_ne_compte_que_les_effets_prouves():
    compte = resume([
        _action(),
        _action(resultat="SUCCESS", preuve="p1", verification=EtatVerification.VERIFIEE),
        _action(resultat="FAILED", verification=EtatVerification.NON_VERIFIEE),
    ])

    assert compte["avec_effet_verifie"] == 1


def test_un_journal_vide_a_un_resume_a_zero():
    assert resume([]) == {"total": 0, "avec_effet_verifie": 0}


def test_la_forme_transportable_porte_resume_et_actions():
    corps = to_dict([_action()])

    assert corps["resume"]["total"] == 1
    assert corps["actions"][0]["service"] == "tiktok"


# --- Rien n'est invente -------------------------------------------------------

def test_la_chronologie_ne_derive_aucun_etat():
    """Elle affiche ce que le journal contient, meme si c'est etonnant."""
    entree = ActionEnregistree.depuis_resultat(succes("a", "b", "ok", "p"), "outil")
    ligne = en_lignes([entree])[0]

    assert ligne["resultat"] == entree.resultat
    assert ligne["verification"] == entree.verification.value


@pytest.mark.parametrize("fabrique,attendu", [
    (lambda: non_configure("publish_video", "TikTok", "un jeton"), "NOT_CONFIGURED"),
    (lambda: refuse("publish_video", "TikTok", "PUBLISH"), "DENIED"),
])
def test_les_etats_sans_effet_gardent_leur_nom_dans_la_chronologie(fabrique, attendu):
    entree = ActionEnregistree.depuis_resultat(fabrique(), "tiktok")

    assert en_lignes([entree])[0]["resultat"] == attendu
