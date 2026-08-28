"""Le metre se calcule. Il ne se devine plus.

Le test qui porte ce correctif est
`test_les_quantites_sont_celles_de_son_devis_reel` : la demande qui a servi de
reference (18 parois de 5,40 x 2,50 m) doit ressortir avec les quantites
reellement commandees sur le devis UC-2026-0804-FG2.

Mesure du 2026-08-28 : avant ce branchement, `calcul_materiaux` n'etait importe
que par le script de mesures. Le modele inventait les quantites.
"""
import pytest

from agents.plaquiste.metre import lire_demande
from agents.plaquiste.plaquiste_agent import PlaquisteAgent

#: Ce qui a reellement ete commande sur le devis de reference.
DEVIS_REEL = {
    "Plaque standard BA13": 234,
    "Montant 7 cm (70 mm)": 288,
    "Rails 7 cm (70 mm)": 54,
    "Seau enduit": 10,
    "Seau Katex": 4,
    "Paquet papier enduit": 1,
    "Laine de verre (paquet)": 18,
}


class FauxModele:
    """Capture l'instruction systeme au lieu d'appeler un modele."""

    def __init__(self) -> None:
        self.instruction = ""

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.instruction = system_prompt or ""
        return "Voici le chiffrage."


@pytest.fixture
def agent():
    return PlaquisteAgent(provider=FauxModele())


# --- Le test qui porte le correctif ---------------------------------------------

async def test_les_quantites_sont_celles_de_son_devis_reel(agent):
    sortie = await agent.run("Calcule les materiaux pour 18 parois de 5,40 x 2,50 m")

    metre = sortie["metre"]
    assert metre is not None, "le calculateur n'a pas tourne"
    assert metre["surface_developpee"] == 486.0
    assert metre["parois"] == 18 and metre["parois_estimees"] is False
    for article, quantite in DEVIS_REEL.items():
        assert metre["quantites"][article] == quantite, f"{article} ne correspond plus au devis"


async def test_les_quantites_calculees_entrent_dans_l_instruction(agent):
    await agent.run("Calcule les materiaux pour 18 parois de 5,40 x 2,50 m")

    instruction = agent.provider.instruction
    assert "234" in instruction, "le modele ne voit pas le chiffrage calcule"
    assert "ne les recalcule pas" in instruction
    assert "18 parois de 5.4 x 2.5 m" in instruction, "la lecture des dimensions n'est pas dite"


# --- Sans dimensions, aucun chiffre n'est fabrique --------------------------------

async def test_une_demande_sans_dimensions_ne_fabrique_aucun_chiffre(agent):
    sortie = await agent.run("Quel est ton tarif de pose au metre carre ?")

    assert sortie["metre"] is None
    assert "CALCUL DES MATERIAUX" not in agent.provider.instruction


async def test_une_conversation_ordinaire_ne_declenche_pas_de_metre(agent):
    sortie = await agent.run("Bonjour, tout va bien sur le chantier ?")

    assert sortie["metre"] is None


# --- Ce que la lecture reconnait ---------------------------------------------------

@pytest.mark.parametrize("phrase,surface,faces", [
    ("Combien de plaques pour 120 m2 de cloison ?", 120.0, 2),
    ("Un doublage de 45 m2", 45.0, 1),
    ("Faux plafond de 30 metres carres", 30.0, 1),
])
def test_les_formulations_courantes_sont_lues(phrase, surface, faces):
    demande = lire_demande(phrase)

    assert demande is not None
    assert demande.surface == surface
    assert demande.faces == faces, "une face de trop double la facture du client"


def test_une_surface_deja_developpee_n_est_pas_doublee_une_seconde_fois():
    demande = lire_demande("486 m2 developpes")

    assert demande.deja_developpee is True


def test_ce_qui_a_ete_lu_est_toujours_dit():
    demande = lire_demande("18 parois de 5,40 x 2,50 m")

    assert "18 parois" in demande.lu and "243" in demande.lu
