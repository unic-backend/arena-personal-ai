"""La capacité Software Engineering ne dit disponible que ce qu'elle a mesuré.

Même défaut à éviter que `test_disponibilite_video.py` (03/09/2026) : une
capacité annoncée disponible parce qu'un processus tourne, jamais parce
qu'une sonde a réellement répondu. DEC-0041 introduit trois backends —
`dioumtoukay`, `specialistes`, `github` — et chacun doit pouvoir tomber
indépendamment sans que les deux autres mentent sur leur propre état.
"""
import pytest

from core.connectors.base import EtatSante, Sante
from core.production.disponibilite_swe import disponibilite_swe


class _ProviderDouble:
    def __init__(self, valeur):
        self._valeur = valeur

    async def is_available(self):
        if isinstance(self._valeur, Exception):
            raise self._valeur
        return self._valeur


class _ConnecteurDouble:
    def __init__(self, sante):
        self._sante = sante

    def sonder(self):
        if isinstance(self._sante, Exception):
            raise self._sante
        return self._sante


_UN_SPECIALISTE = object()


class _DioumtoukayDouble:
    def __init__(self, analyste=_UN_SPECIALISTE, chercheur_de_bug=_UN_SPECIALISTE):
        self.analyste = analyste
        self.chercheur_de_bug = chercheur_de_bug


# --- Sans rien de branché ----------------------------------------------------------

@pytest.mark.asyncio
async def test_sans_provider_ni_connecteur_rien_nest_dit_disponible():
    etats = await disponibilite_swe(provider_code=None, connecteur_github=None, dioumtoukay=None)

    assert etats["dioumtoukay"] == {"disponible": False, "raison": "aucun modele de code branche"}
    assert etats["specialistes"]["disponible"] is False
    assert etats["github"] == {"disponible": False, "raison": "connecteur non construit"}


# --- dioumtoukay ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dioumtoukay_disponible_quand_le_moteur_repond():
    etats = await disponibilite_swe(
        provider_code=_ProviderDouble(True), connecteur_github=None,
        dioumtoukay=_DioumtoukayDouble())

    assert etats["dioumtoukay"] == {"disponible": True, "raison": ""}


@pytest.mark.asyncio
async def test_dioumtoukay_indisponible_si_le_moteur_ne_repond_pas():
    etats = await disponibilite_swe(
        provider_code=_ProviderDouble(False), connecteur_github=None,
        dioumtoukay=_DioumtoukayDouble())

    assert etats["dioumtoukay"]["disponible"] is False
    assert "ne repond pas" in etats["dioumtoukay"]["raison"]


@pytest.mark.asyncio
async def test_une_sonde_qui_leve_ne_fait_pas_tomber_le_reste():
    etats = await disponibilite_swe(
        provider_code=_ProviderDouble(RuntimeError("panne")),
        connecteur_github=_ConnecteurDouble(Sante(EtatSante.OPERATIONNEL)),
        dioumtoukay=_DioumtoukayDouble())

    assert etats["dioumtoukay"]["disponible"] is False
    assert "sonde en echec" in etats["dioumtoukay"]["raison"]
    # Le connecteur GitHub, lui, a repondu : sa ligne ne doit pas en payer le prix.
    assert etats["github"]["disponible"] is True


# --- specialistes : partagent le moteur, mais pas la garantie d'etre branches ------

@pytest.mark.asyncio
async def test_specialistes_indisponibles_si_lun_des_deux_manque():
    etats = await disponibilite_swe(
        provider_code=_ProviderDouble(True), connecteur_github=None,
        dioumtoukay=_DioumtoukayDouble(analyste=None))

    assert etats["specialistes"]["disponible"] is False
    assert "RepoEngineerAgent" in etats["specialistes"]["raison"]


@pytest.mark.asyncio
async def test_specialistes_suivent_le_moteur_quand_les_deux_sont_branches():
    etats = await disponibilite_swe(
        provider_code=_ProviderDouble(False), connecteur_github=None,
        dioumtoukay=_DioumtoukayDouble())

    # Le moteur ne repond pas : les specialistes non plus, meme branches.
    assert etats["specialistes"]["disponible"] is False


# --- github ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_disponible_quand_le_connecteur_repond():
    etats = await disponibilite_swe(
        provider_code=None,
        connecteur_github=_ConnecteurDouble(Sante(EtatSante.OPERATIONNEL)),
        dioumtoukay=None)

    assert etats["github"] == {"disponible": True, "raison": ""}


@pytest.mark.asyncio
async def test_github_rapporte_ce_qui_manque():
    etats = await disponibilite_swe(
        provider_code=None,
        connecteur_github=_ConnecteurDouble(Sante(
            EtatSante.NON_CONFIGURE, message="Aucun jeton GitHub configure.",
            ce_qui_manque="USMAN_GITHUB_TOKEN dans .env")),
        dioumtoukay=None)

    assert etats["github"]["disponible"] is False
    assert "USMAN_GITHUB_TOKEN" in etats["github"]["raison"]
