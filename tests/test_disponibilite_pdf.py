"""La capacité `pdf` ne dit disponible que ce qu'elle a mesuré."""
import pytest

from core.connectors.base import EtatSante, Sante
from core.production.disponibilite_pdf import disponibilite_pdf


class _ConnecteurDouble:
    def __init__(self, sante):
        self._sante = sante

    def sonder(self):
        if isinstance(self._sante, Exception):
            raise self._sante
        return self._sante


@pytest.mark.asyncio
async def test_sans_connecteur_rien_nest_dit_disponible():
    etat = await disponibilite_pdf(None)
    assert etat == {"disponible": False, "raison": "connecteur non construit"}


@pytest.mark.asyncio
async def test_operationnel():
    etat = await disponibilite_pdf(_ConnecteurDouble(Sante(EtatSante.OPERATIONNEL)))
    assert etat == {"disponible": True, "raison": ""}


@pytest.mark.asyncio
async def test_une_sonde_qui_leve_ne_fait_pas_planter_le_rapport():
    etat = await disponibilite_pdf(_ConnecteurDouble(RuntimeError("panne")))
    assert etat["disponible"] is False
    assert "sonde en echec" in etat["raison"]
