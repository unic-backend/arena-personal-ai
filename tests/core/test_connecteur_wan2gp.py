"""WanGP : generer une video chez soi, sans qu'une phrase suffise a la lancer.

Deux tests portent l'integration.
`test_generer_ne_part_jamais_sans_confirmation` : une generation occupe la carte
graphique plusieurs minutes ; elle ne part pas parce qu'une phrase y ressemblait.
`test_sans_serveur_le_connecteur_dit_ce_qui_manque` : WanGP eteint, ARENA le
mesure et donne la commande, au lieu de supposer.
"""
from typing import Any, Dict, Optional

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.wan2gp import Wan2GPConnector
from core.mcp.transport import Reponse

OUTILS = {"tools": [{"name": "wangp_generate"}, {"name": "wangp_get_job"},
                    {"name": "wangp_models"}]}


class FauxClient:
    """Un serveur MCP de test : il note ce qu'on lui demande, sans reseau."""

    def __init__(self, outils: Optional[Dict[str, Any]] = None,
                 reponses: Optional[Dict[str, Any]] = None, panne: str = "") -> None:
        self.url = "http://faux/mcp"
        self._outils = outils if outils is not None else OUTILS
        self._reponses = reponses or {}
        self._panne = panne
        self.appels = []

    def outils(self) -> Reponse:
        if self._panne:
            return Reponse(ok=False, raison=self._panne)
        return Reponse(ok=True, resultat=self._outils)

    def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
        self.appels.append((nom, dict(arguments or {})))
        if self._panne:
            return Reponse(ok=False, raison=self._panne)
        return Reponse(ok=True, resultat={
            "structuredContent": self._reponses.get(nom, {"job_id": "job-42"})})


def connecteur(**kwargs) -> Wan2GPConnector:
    return Wan2GPConnector(client=FauxClient(**kwargs))


# --- Les deux tests que l'integration doit passer -------------------------------

def test_generer_ne_part_jamais_sans_confirmation():
    faux = FauxClient()
    wan = Wan2GPConnector(client=faux)

    resultat = wan.executer("generer", source={"prompt": "un chantier a Medina"})

    assert resultat.statut is not Statut.SUCCES
    assert faux.appels == [], "l'appel a atteint WanGP sans confirmation"


def test_sans_serveur_le_connecteur_dit_ce_qui_manque():
    wan = connecteur(panne="ConnectError: refused")

    sante = wan.sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "wgp.py --mcp" in sante.ce_qui_manque, "la commande de lancement manque"
    assert sante.mesure_le, "une sante sans date n'est pas une mesure"


# --- La sonde interroge, elle ne suppose pas ------------------------------------

def test_un_serveur_qui_repond_sans_savoir_generer_est_en_panne():
    wan = connecteur(outils={"tools": [{"name": "wangp_list_gallery"}]})

    assert wan.sante().etat is EtatSante.EN_PANNE


def test_un_serveur_complet_est_operationnel():
    wan = connecteur()

    sante = wan.sante()

    assert sante.etat is EtatSante.OPERATIONNEL
    assert "generation disponible" in sante.message


# --- Ce que la confirmation autorise, et ce qu'elle ne change pas ----------------

def test_une_generation_confirmee_rend_l_identifiant_comme_preuve():
    faux = FauxClient()
    wan = Wan2GPConnector(client=faux)

    resultat = wan.executer_confirmee("generer", source={"prompt": "chantier"})

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "job-42", "sans identifiant, rien ne prouve la generation"
    assert faux.appels[0][0] == "wangp_generate"


def test_une_generation_sans_identifiant_n_est_pas_un_succes():
    faux = FauxClient(reponses={"wangp_generate": {"etat": "accepte"}})
    wan = Wan2GPConnector(client=faux)

    resultat = wan.executer_confirmee("generer", source={"prompt": "chantier"})

    assert resultat.statut is Statut.ECHEC
    assert resultat.preuve is None


def test_une_generation_sans_description_n_atteint_pas_wangp():
    faux = FauxClient()
    wan = Wan2GPConnector(client=faux)

    resultat = wan.executer_confirmee("generer")

    assert resultat.statut is Statut.ECHEC
    assert faux.appels == [], "un appel vide est parti quand meme"


# --- Ce que l'appelant ne choisit pas --------------------------------------------

def test_l_appelant_ne_choisit_pas_l_appel_mcp():
    faux = FauxClient()
    wan = Wan2GPConnector(client=faux)

    wan.executer("modeles", query="wan", limit=5, outil="wangp_io", chemin="../")

    assert faux.appels == [("wangp_models", {"query": "wan", "limit": 5})]


def test_une_capacite_non_declaree_n_atteint_jamais_wangp():
    faux = FauxClient()
    wan = Wan2GPConnector(client=faux)

    resultat = wan.executer("supprimer_tout")

    assert resultat.statut is not Statut.SUCCES
    assert faux.appels == []


def test_aucune_capacite_de_lecture_n_ecrit():
    lectures = ["modeles", "etat_travail", "galerie"]
    capacites = connecteur().capacites()

    assert not any(capacites[nom].ecriture for nom in lectures)
    assert capacites["generer"].ecriture is True


# --- Le transport ------------------------------------------------------------------

def test_un_serveur_absent_ne_leve_jamais():
    from core.mcp.transport import ClientMcp

    reponse = ClientMcp("http://127.0.0.1:1").outils()

    assert reponse.ok is False
    assert reponse.raison, "une panne sans raison n'aide personne"


def test_une_reponse_en_flux_d_evenements_est_lue():
    import httpx

    from core.mcp.transport import _charge

    brute = httpx.Response(
        200, headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":"1","result":{"tools":[]}}\n\n')

    assert _charge(brute) == {"jsonrpc": "2.0", "id": "1", "result": {"tools": []}}
