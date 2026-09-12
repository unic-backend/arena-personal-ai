"""La chaine complete : plan -> metre -> devis -> PDF, avec un plan de test connu.

Phase 7 de l'audit document/PDF/plan (`docs/audits/document_construction_audit.md`).
Chaque module de cette chaine a deja ses propres tests unitaires (OpenTakeoff,
`metre_plan.py`, `calcul_materiaux.py`, `devis_pdf.py`) — ce fichier ne les
repete pas. Il tient la chose que ces tests unitaires, pris separement, ne
peuvent pas voir : que le fil passe bien de l'un a l'autre jusqu'a un vrai
fichier PDF sur disque.

Trouve en l'ecrivant (30/08/2026) : ce fil etait coupe. `_proposer_le_document`
transmettait la PHRASE brute au connecteur devis, qui la relisait pour ses
propres dimensions — jamais le metre deja calcule depuis le plan. Un devis
demande apres la mesure d'un plafond ou d'un mur echouait donc a la
confirmation avec « aucune dimension lue », alors que le plan en donnait une.
Voir `core/connectors/devis.py::lignes_depuis_parametres` pour le correctif.

`ClientMcpStdio` est remplace par un double scripte, comme dans
`tests/core/test_connecteur_opentakeoff.py` : aucun test ici ne lance Node ni
le vrai moteur OpenTakeoff — non disponible sur cette machine (pas de
`OPENTAKEOFF_MCP_DIR` construit ici). `DevisConnector`, lui, est le vrai
connecteur : le PDF ecrit est un vrai fichier, relu avec `pypdf`.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

pypdf = pytest.importorskip("pypdf", reason="pypdf n'est pas installe.")
from pypdf import PdfReader  # noqa: E402

import core.connectors.opentakeoff as opentakeoff_mod  # noqa: E402
from agents.plaquiste.calcul_materiaux import quantites_pour  # noqa: E402
from agents.plaquiste.plaquiste_agent import PlaquisteAgent, charger_metier  # noqa: E402
from core.actions.resultat import Statut  # noqa: E402
from core.connectors.devis import DevisConnector  # noqa: E402
from core.connectors.opentakeoff import ConnecteurOpenTakeoff  # noqa: E402
from core.connectors.registre import RegistreConnecteurs  # noqa: E402
from core.mcp.transport import Reponse  # noqa: E402

METIER = charger_metier()
DESTINATAIRE = {"client": "Fast Group", "lieu": "Almadies", "objet": "cloisons BA13"}

#: Un plan connu : une seule piece, des mesures rondes pour verifier la
#: conversion pieds -> metres a la main (500 pi2 x 0,09290304 = 46,45 m2 ;
#: 90 pi lineaires x 0,3048 = 27,43 ml).
PIECE_CONNUE = {
    "detected": 1,
    "rooms": [{"label": "101", "area_sf": 500.0, "perimeter_lf": 90.0,
               "confidence": 1.0, "shape_id": "shp-1",
               "condition": opentakeoff_mod.CONDITION_SURFACE}],
}


class ModeleDouble:
    """Le modele n'intervient jamais dans le chiffrage : seul son texte varie."""

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        return "Voici le calcul."


def _reponse(detail: Dict[str, Any]) -> Dict[str, Any]:
    return {"structuredContent": detail, "content": []}


def _echec_outil(message: str) -> Dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def fabriquer_faux_client(script: Dict[str, Any]):
    """Meme contrat que `ClientMcpStdio`, scripte par nom d'outil — voir
    `tests/core/test_connecteur_opentakeoff.py`, dont ce double est une copie
    minimale (pas d'inter-dependance entre fichiers de test)."""

    class FauxClientMcpStdio:
        def __init__(self, commande, dossier, delai=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def outils(self) -> Reponse:
            return Reponse(ok=True, resultat={"tools": [{"name": n} for n in script]})

        def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
            fabrique = script.get(nom)
            if fabrique is None:
                return Reponse(ok=True, resultat=_echec_outil(f"outil {nom} non scripte"))
            return fabrique(arguments) if callable(fabrique) else fabrique

    return FauxClientMcpStdio


def _script_plan_connu(hauteur_disponible: bool = True) -> Dict[str, Any]:
    return {
        "load_plan": Reponse(ok=True, resultat=_reponse(
            {"sheets": [{"sheet": "plan_connu.pdf#1"}]})),
        "set_scale": Reponse(ok=True, resultat=_reponse({"upp": 0.01})),
        "detect_rooms": Reponse(ok=True, resultat=_reponse(PIECE_CONNUE)),
        "derive_base": Reponse(ok=True, resultat=_reponse({})),
        "takeoff_summary": Reponse(ok=True, resultat=_reponse(
            {"totals": {"total_sf_net": 500.0, "lf_net": 90.0}})),
    }


@pytest.fixture
def plan_connu(tmp_path: Path) -> Path:
    chemin = tmp_path / "plan_connu.pdf"
    chemin.write_bytes(b"%PDF-1.4 plan de test connu\n")
    return chemin


@pytest.fixture
def registre(monkeypatch, tmp_path) -> RegistreConnecteurs:
    """Le vrai registre, le vrai connecteur devis, OpenTakeoff derriere un
    double scripte — la meme construction que le serveur reel
    (`apps/backend/runtime.py`), juste sans processus MCP externe."""
    monkeypatch.setattr(opentakeoff_mod, "_commande", lambda: ["node", "dist/server.js"])
    script = _script_plan_connu()
    monkeypatch.setattr(opentakeoff_mod, "ClientMcpStdio", fabriquer_faux_client(script))

    inventaire = RegistreConnecteurs()
    inventaire.declarer("opentakeoff", lambda: ConnecteurOpenTakeoff())
    inventaire.declarer("devis", lambda: DevisConnector(metier=METIER, dossier=tmp_path / "devis"))
    return inventaire


def _propose_puis_confirme(registre: RegistreConnecteurs, appel_devis: tuple) -> Any:
    """Rejoue exactement ce que fait le proprietaire : la proposition capturee
    par `_proposer_le_document` est confirmee telle quelle, sans rien y
    changer — la meme discipline que `FileDAttente.confirmer()`."""
    _, _, parametres = appel_devis
    return registre.executer_confirmee("devis", "produire", **parametres)


class _RegistreEspion:
    """Enveloppe le vrai registre : capture ce qui part vers `devis.produire`
    sans changer son comportement — les autres appels passent tels quels."""

    def __init__(self, delegue: RegistreConnecteurs):
        self._delegue = delegue
        self.appels: List[tuple] = []

    def executer(self, nom, capacite, **parametres):
        resultat = self._delegue.executer(nom, capacite, **parametres)
        if (nom, capacite) == ("devis", "produire"):
            self.appels.append((nom, capacite, dict(parametres)))
        return resultat

    def executer_confirmee(self, nom, capacite, **parametres):
        return self._delegue.executer_confirmee(nom, capacite, **parametres)


class TestPlafondMesureJusquauPdf:
    """Plafond plat : sa surface au sol EST sa surface, sans hauteur a donner."""

    @pytest.mark.asyncio
    async def test_le_pdf_reel_porte_les_quantites_du_plan_mesure(self, registre, plan_connu):
        espion = _RegistreEspion(registre)
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=espion)

        resultat = await agent.run(
            f"calcule le faux plafond du plan {plan_connu}, fais le pdf du devis",
            context=DESTINATAIRE)

        assert resultat["plan"]["surface_totale_m2"] == pytest.approx(46.45, abs=0.01)
        assert espion.appels, "aucun appel a devis.produire"

        # Plus de confirmation depuis le 04/09/2026 (demande du proprietaire) :
        # la phrase suffit, le fichier existe au retour de `run()`. C'est plus
        # fort que l'ancien test, qui devait rejouer une confirmation pour
        # obtenir le PDF.
        document = resultat["document"]
        assert document["statut"] == "SUCCESS", document.get("message")
        chemin_pdf = Path(document["preuve"])
        assert chemin_pdf.exists(), "le succes ne designe pas un fichier reel"

        texte = PdfReader(str(chemin_pdf)).pages[0].extract_text()
        attendu = quantites_pour(46.45, METIER, faces=1)
        assert attendu.besoins, "rien a verifier : le calcul de reference est vide"
        for besoin in attendu.besoins:
            assert besoin.article in texte, f"« {besoin.article} » absent du PDF reel"
        assert f"{attendu.total_connu:,}".replace(",", " ") in texte.replace("\xa0", " ") \
            or str(attendu.total_connu) in texte, "le total chiffre n'apparait pas dans le PDF"


class TestMurMesureJusquauPdf:
    """Mur : perimetre mesure x hauteur dictee, deux faces par defaut."""

    @pytest.mark.asyncio
    async def test_le_pdf_reel_porte_les_quantites_du_mur_mesure(self, registre, plan_connu):
        espion = _RegistreEspion(registre)
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=espion)

        resultat = await agent.run(
            f"calcule la cloison, hauteur de 2,50 m, plan {plan_connu}, fais le pdf du devis",
            context=DESTINATAIRE)

        # perimetre 27,43 ml x hauteur 2,50 m x 2 faces = 137,15 m2 developpes
        assert resultat["metre"]["surface_developpee"] == pytest.approx(137.15, abs=0.1)
        confirme = _propose_puis_confirme(registre, espion.appels[0])

        assert confirme.statut is Statut.SUCCES, confirme.message
        texte = PdfReader(confirme.preuve).pages[0].extract_text()
        attendu = quantites_pour(resultat["metre"]["surface_developpee"], METIER, faces=2)
        for besoin in attendu.besoins:
            assert besoin.article in texte


class TestRampantMesureNeProduitRien:
    """Un rampant suit la pente du toit : aucune mesure de ce plan ne le
    chiffre, meme avec une hauteur — la chaine doit refuser, pas inventer."""

    @pytest.mark.asyncio
    async def test_confirmer_echoue_proprement_sans_fichier_ecrit(self, registre, plan_connu, tmp_path):
        espion = _RegistreEspion(registre)
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=espion)

        resultat = await agent.run(
            f"calcule le rampant, hauteur de 2,50 m, plan {plan_connu}, fais le pdf du devis",
            context=DESTINATAIRE)

        assert resultat["metre"] is None
        confirme = _propose_puis_confirme(registre, espion.appels[0])

        assert confirme.statut is Statut.ECHEC
        assert not (tmp_path / "devis").exists() or not list((tmp_path / "devis").glob("*")), (
            "un fichier a ete ecrit alors qu'aucun metre n'etait calculable")


class TestLAdresseDuPdfRemonteJusquALaReponse:
    """Le dernier metre : du connecteur jusqu'au compte-rendu de `run()`.

    Trouve par sabotage le 04/09/2026 : remplacer la propagation de `url` dans
    `_proposer_le_document` par `None` ne faisait echouer AUCUN test. Les tests
    de la passerelle nourrissent un dictionnaire deja fait ; ceux du connecteur
    s'arretent en dessous de l'agent. Le seul maillon qui avait deja perdu ce
    lien une fois n'etait couvert nulle part.

    Sans cette adresse, le PDF existe sur le serveur et aucun ecran de son
    telephone ne peut l'atteindre.
    """

    @pytest.mark.asyncio
    async def test_le_document_produit_porte_l_adresse_qui_l_ouvre(
        self, registre, plan_connu, monkeypatch, tmp_path
    ):
        # Le connecteur n'annonce une adresse que pour un fichier REELLEMENT
        # servi par `GET /media/rendered/{nom:path}` : on fait donc du dossier de ce
        # test le dossier servi, plutot que de faire semblant.
        dossier_servi = tmp_path / "devis"
        monkeypatch.setattr("core.connectors.devis.RENDERED_DIR", dossier_servi)

        agent = PlaquisteAgent(provider=ModeleDouble(), metier=METIER, registre=registre)
        resultat = await agent.run(
            f"calcule le faux plafond du plan {plan_connu}, fais le pdf du devis",
            context=DESTINATAIRE)

        document = resultat["document"]
        assert document["statut"] == "SUCCESS", document.get("message")
        adresse = document.get("url")
        assert adresse, "le PDF est ecrit mais rien ne dit par ou l'ouvrir"
        assert adresse.startswith("/media/rendered/"), adresse
        assert Path(document["preuve"]).name == adresse.rsplit("/", 1)[-1], (
            "l'adresse annoncee ne designe pas le fichier reellement ecrit")
