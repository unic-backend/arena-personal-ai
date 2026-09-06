"""La chaine complete : fichier IFC -> analyse -> murs -> materiaux -> PDF.

Smoke test reel (mission BIM, 05/09/2026, section 16) : `ConnecteurIfc` et
`DevisConnector` sont les VRAIS connecteurs, IfcOpenShell est reellement
installe et lit un vrai fichier IFC (`tests/fixtures/ifc/exemple.ifc`,
engendre par IfcOpenShell lui-meme — voir `tests/core/test_connecteur_ifc.py`).
Rien n'est simule au-dela du modele de langage, qui n'intervient jamais dans
le chiffrage (meme discipline que `tests/test_plaquiste_bout_en_bout.py`).
"""
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf", reason="pypdf n'est pas installe.")
from pypdf import PdfReader  # noqa: E402

from agents.plaquiste.calcul_materiaux import quantites_pour  # noqa: E402
from agents.plaquiste.plaquiste_agent import PlaquisteAgent, charger_metier  # noqa: E402
from core.connectors.devis import DevisConnector  # noqa: E402
from core.connectors.ifc import ConnecteurIfc  # noqa: E402
from core.connectors.ifc_generation import ConnecteurIfcGeneration  # noqa: E402
from core.connectors.registre import RegistreConnecteurs  # noqa: E402
from core.production.ifc_lecture import elements, ouvrir  # noqa: E402

METIER = charger_metier()
DESTINATAIRE = {"client": "Fast Group", "lieu": "Almadies", "objet": "cloisons BA13"}
FIXTURE_SOURCE = Path(__file__).resolve().parent / "fixtures" / "ifc" / "exemple.ifc"


class ModeleDouble:
    """Le modele n'intervient jamais dans le chiffrage : seul son texte varie."""

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        return "Voici le calcul."


@pytest.fixture
def fichier_ifc(tmp_path: Path) -> Path:
    """Une copie du fichier IFC de test, HORS du depot d'ARENA (`tmp_path`) :
    `chemin_hors_du_depot()` refuserait le fichier de fixture s'il etait cite
    directement — un chemin sous `tests/` fait partie du depot lui-meme,
    exactement comme un plan PDF de test doit vivre hors du depot."""
    chemin = tmp_path / "batiment.ifc"
    chemin.write_bytes(FIXTURE_SOURCE.read_bytes())
    return chemin


@pytest.fixture
def registre(tmp_path) -> RegistreConnecteurs:
    inventaire = RegistreConnecteurs()
    inventaire.declarer("ifc", lambda: ConnecteurIfc())
    inventaire.declarer("devis", lambda: DevisConnector(metier=METIER, dossier=tmp_path / "devis"))
    inventaire.declarer(
        "ifc_generation", lambda: ConnecteurIfcGeneration(dossier=tmp_path / "rendus"))
    return inventaire


class TestIfcJusquauPdf:
    @pytest.mark.asyncio
    async def test_les_murs_ifc_produisent_un_devis_reel(self, registre, fichier_ifc):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)

        resultat = await agent.run(
            f"analyse le fichier {fichier_ifc}, fais le metre et le pdf du devis",
            context=DESTINATAIRE)

        # Le fichier de fixture porte 3 murs (2 avec une quantite exploitable,
        # 13.5 + 20.0 = 33.5 m2 une face), 1 porte, 1 fenetre, 2 niveaux.
        ifc = resultat["ifc"]
        assert ifc["comptes"]["mur"] == 3
        assert ifc["comptes"]["porte"] == 1
        assert ifc["surface_m2"] == 33.5

        # 33.5 m2 (une face) x 2 faces par defaut = 67 m2 developpes.
        assert resultat["metre"]["surface_developpee"] == pytest.approx(67.0, abs=0.01)

        document = resultat["document"]
        assert document["statut"] == "SUCCESS", document.get("message")
        chemin_pdf = Path(document["preuve"])
        assert chemin_pdf.exists(), "le succes ne designe pas un fichier reel"

        texte = PdfReader(str(chemin_pdf)).pages[0].extract_text()
        attendu = quantites_pour(67.0, METIER, faces=2)
        assert attendu.besoins, "rien a verifier : le calcul de reference est vide"
        for besoin in attendu.besoins:
            assert besoin.article in texte, f"« {besoin.article} » absent du PDF reel"

    @pytest.mark.asyncio
    async def test_un_chemin_ifc_dans_le_depot_est_refuse(self, registre):
        """Meme frontiere que les plans PDF (DEC-0020) : un chemin qui tombe
        dans le depot d'ARENA n'est jamais ouvert, IFC compris."""
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)

        chemin_interdit = str(FIXTURE_SOURCE)
        resultat = await agent.run(f"analyse le fichier {chemin_interdit}", context=DESTINATAIRE)

        assert resultat["ifc"]["statut"] == "REFUSE"
        assert resultat["metre"] is None


class TestSansIfcOpenShell:
    @pytest.mark.asyncio
    async def test_sans_ifcopenshell_installe_reste_non_configure(
        self, registre, fichier_ifc, monkeypatch
    ):
        import builtins

        reel = builtins.__import__

        def bloque_ifcopenshell(name, *args, **kwargs):
            if name == "ifcopenshell" or name.startswith("ifcopenshell."):
                raise ModuleNotFoundError("No module named 'ifcopenshell'")
            return reel(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", bloque_ifcopenshell)
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)

        resultat = await agent.run(f"analyse le fichier {fichier_ifc}", context=DESTINATAIRE)

        assert resultat["ifc"]["statut"] == "NOT_CONFIGURED"


class TestCroquisIfcJusquauFichierReel:
    """Génération (DEC-0056), pas lecture : un fichier IFC réel est écrit et
    relu, sans rapport avec `fichier_ifc`/`FIXTURE_SOURCE` ci-dessus."""

    @pytest.mark.asyncio
    async def test_le_croquis_ifc_est_un_fichier_reel_et_coherent(self, registre):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)

        resultat = await agent.run(
            "genere le croquis ifc de cette cloison de 5,40 x 2,50 m", context=DESTINATAIRE)

        croquis = resultat["croquis_ifc"]
        assert croquis["statut"] == "SUCCESS", croquis["message"]
        chemin_ecrit = Path(croquis["preuve"])
        assert chemin_ecrit.is_file()

        murs = elements(ouvrir(str(chemin_ecrit)), "IfcWall")
        assert len(murs) == 1
        assert murs[0].surface_m2 == 13.5

    @pytest.mark.asyncio
    async def test_sans_dimensions_est_incomplet_jamais_invente(self, registre):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)

        resultat = await agent.run("genere le croquis ifc de cette cloison", context=DESTINATAIRE)

        assert resultat["croquis_ifc"]["statut"] == "INCOMPLET"

    @pytest.mark.asyncio
    async def test_analyser_un_fichier_ifc_ne_declenche_pas_une_generation(
        self, registre, fichier_ifc
    ):
        """La frontiere qui compte (DEC-0056) : LIRE ne doit jamais aussi ECRIRE."""
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)

        resultat = await agent.run(f"analyse le fichier {fichier_ifc}", context=DESTINATAIRE)

        assert resultat["croquis_ifc"] is None
