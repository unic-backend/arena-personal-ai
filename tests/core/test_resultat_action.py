"""Un succes exige une preuve, et une action qui n'a pas eu lieu n'en porte pas.

Ces deux regles sont la raison d'etre du module. Elles sont testees dans les
deux sens : on ne peut pas fabriquer un succes, et on ne peut pas decorer un
refus d'une preuve qu'il n'a pas.
"""
import dataclasses

import pytest

from core.actions.resultat import (
    STATUTS_AVEC_EFFET,
    ResultatAction,
    Statut,
    a_confirmer,
    echec,
    non_configure,
    non_implemente,
    partiel,
    refuse,
    succes,
)

# --- La regle centrale --------------------------------------------------------

@pytest.mark.parametrize("statut", sorted(STATUTS_AVEC_EFFET, key=lambda s: s.value))
def test_un_statut_avec_effet_sans_preuve_est_refuse(statut):
    with pytest.raises(ValueError, match="sans preuve"):
        ResultatAction(statut, "publish_video", "TikTok", "pretendument publie")


@pytest.mark.parametrize("preuve", ["", "   ", None])
def test_une_preuve_vide_ne_compte_pas(preuve):
    with pytest.raises(ValueError, match="sans preuve"):
        ResultatAction(Statut.SUCCES, "send", "client@example.com", "envoye", preuve)


def test_un_succes_avec_preuve_se_construit():
    resultat = succes("publish_video", "TikTok", "Publiee.", "https://tiktok.com/v/123")
    assert resultat.statut is Statut.SUCCES
    assert resultat.a_eu_lieu is True
    assert resultat.preuve == "https://tiktok.com/v/123"


def test_un_partiel_exige_aussi_sa_preuve():
    assert partiel("archive", "Gmail", "9 sur 12 archives.", "ids: 1-9").a_eu_lieu is True
    with pytest.raises(ValueError):
        ResultatAction(Statut.PARTIEL, "archive", "Gmail", "9 sur 12")


# --- La regle inverse ---------------------------------------------------------

@pytest.mark.parametrize("statut", [
    Statut.ECHEC, Statut.NON_CONFIGURE, Statut.REFUSE,
    Statut.A_CONFIRMER, Statut.NON_IMPLEMENTE,
])
def test_une_action_qui_n_a_pas_eu_lieu_ne_peut_pas_porter_de_preuve(statut):
    with pytest.raises(ValueError, match="rien n'a eu lieu"):
        ResultatAction(statut, "publish_video", "TikTok", "message", "https://preuve/1")


@pytest.mark.parametrize("fabrique,attendu", [
    (lambda: echec("publish_video", "TikTok", "reseau injoignable"), Statut.ECHEC),
    (lambda: non_configure("publish_video", "TikTok", "un jeton"), Statut.NON_CONFIGURE),
    (lambda: refuse("publish_video", "TikTok", "PUBLISH"), Statut.REFUSE),
    (lambda: a_confirmer("send", "client@example.com", "pret a partir"), Statut.A_CONFIRMER),
    (lambda: non_implemente("delete", "Gmail", "pas de chemin"), Statut.NON_IMPLEMENTE),
])
def test_aucun_constructeur_sans_effet_ne_declare_un_effet(fabrique, attendu):
    resultat = fabrique()
    assert resultat.statut is attendu
    assert resultat.a_eu_lieu is False
    assert resultat.preuve is None


# --- Ce que voit l'appelant ---------------------------------------------------

def test_non_configure_dit_ce_qui_manque_et_que_rien_n_est_parti():
    message = non_configure("publish_video", "TikTok", "un jeton OAuth").message
    assert "un jeton OAuth" in message
    assert "Rien n'a ete envoye" in message


def test_refuse_nomme_la_permission_en_cause():
    assert "PUBLISH" in refuse("publish_video", "TikTok", "PUBLISH").message


def test_le_statut_traverse_l_api_en_anglais():
    assert non_configure("a", "b", "c").to_dict()["status"] == "NOT_CONFIGURED"
    assert succes("a", "b", "ok", "id-1").to_dict()["status"] == "SUCCESS"


def test_le_dictionnaire_porte_a_eu_lieu_pour_qui_ne_lit_pas_le_statut():
    assert non_configure("a", "b", "c").to_dict()["a_eu_lieu"] is False
    assert succes("a", "b", "ok", "id-1").to_dict()["a_eu_lieu"] is True


def test_une_action_sans_effet_n_expose_pas_de_champ_preuve():
    assert "preuve" not in refuse("a", "b", "PUBLISH").to_dict()


def test_le_detail_est_transporte_quand_il_existe():
    corps = non_configure("publish_video", "TikTok", "un jeton", titre="Mon titre").to_dict()
    assert corps["detail"]["titre"] == "Mon titre"


def test_un_resultat_est_immuable():
    resultat = refuse("publish_video", "TikTok", "PUBLISH")
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultat.statut = Statut.SUCCES
