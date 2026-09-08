"""La capacité `file_conversion` ne dit disponible que ce qu'elle a mesuré.

Même discipline que `test_disponibilite_swe.py` (DEC-0073) : une capacité
annoncée disponible parce qu'un connecteur existe, jamais parce qu'une sonde
a réellement répondu.
"""
import pytest

from core.connectors.base import EtatSante, Sante
from core.production.disponibilite_conversion import disponibilite_conversion


class _ConnecteurDouble:
    def __init__(self, sante):
        self._sante = sante

    def sonder(self):
        if isinstance(self._sante, Exception):
            raise self._sante
        return self._sante


@pytest.mark.asyncio
async def test_sans_connecteur_rien_nest_dit_disponible():
    etat = await disponibilite_conversion(None)
    assert etat == {"disponible": False, "raison": "connecteur non construit", "formats": []}


@pytest.mark.asyncio
async def test_operationnel_rend_la_vraie_matrice():
    etat = await disponibilite_conversion(_ConnecteurDouble(Sante(EtatSante.OPERATIONNEL)))
    assert etat["disponible"] is True
    assert etat["raison"] == ""
    assert len(etat["formats"]) > 0
    assert all("source" in ligne and "cible" in ligne for ligne in etat["formats"])


@pytest.mark.asyncio
async def test_non_configure_rapporte_ce_qui_manque():
    etat = await disponibilite_conversion(_ConnecteurDouble(Sante(
        EtatSante.NON_CONFIGURE, message="Aucun moteur disponible.",
        ce_qui_manque="LibreOffice, Pillow, ffmpeg ou WeasyPrint")))
    assert etat["disponible"] is False
    assert "LibreOffice" in etat["raison"]
    assert etat["formats"] == []


@pytest.mark.asyncio
async def test_une_sonde_qui_leve_ne_fait_pas_planter_le_rapport():
    etat = await disponibilite_conversion(_ConnecteurDouble(RuntimeError("panne")))
    assert etat["disponible"] is False
    assert "sonde en echec" in etat["raison"]
