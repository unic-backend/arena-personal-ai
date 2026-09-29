"""Le connecteur LinkedIn (DEC-0183) : publier sur le profil du proprietaire.

Aucun test n'appelle LinkedIn : la couche reseau est un `httpx.MockTransport`
qui note chaque requete. Ce qui est garanti :

- sans jeton, rien ne part, et la sante dit ce qui manque ;
- un post attend la confirmation, et le coupe-circuit PUBLISH le refuse meme
  confirme ;
- un post n'est annonce publie qu'avec l'identifiant rendu par LinkedIn ;
- seules les capacites qu'une application ordinaire obtient sont declarees ;
- le jeton ne sort jamais dans un message.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.permissions.controle import ControleAcces
from core.permissions.permission_manager import PermissionManager
from social.linkedin.linkedin_connector import (
    CARACTERES_MAX,
    VARIABLE_JETON,
    VARIABLE_VERSION,
    VERSION_PAR_DEFAUT,
    LinkedInConnector,
)

JETON = "AQX-jeton-de-test-secret"
MEMBRE = {"sub": "abc123", "name": "Ousmane Diop"}
POST_CREE = httpx.Response(201, headers={"x-restli-id": "urn:li:share:7001"})


class FauxLinkedIn:
    """Rend une reponse par « METHODE chemin » et garde chaque requete."""

    def __init__(self, reponses: Dict[str, Any]) -> None:
        self.reponses = reponses
        self.requetes: List[httpx.Request] = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(requete)
        reponse = self.reponses.get(f"{requete.method} {requete.url.path}")
        if reponse is None:
            return httpx.Response(404, json={"message": f"inconnu : {requete.url.path}"})
        if isinstance(reponse, httpx.Response):
            return reponse
        return httpx.Response(200, json=reponse)

    def posts(self) -> List[Dict[str, Any]]:
        return [json.loads(r.content) for r in self.requetes if r.method == "POST"]


def _acces(tmp_path: Path, publier: bool) -> ControleAcces:
    fichier = tmp_path / "permissions.yaml"
    fichier.write_text(f"PUBLISH: {str(publier).lower()}\n", encoding="utf-8")
    return ControleAcces(permissions=PermissionManager(str(fichier)))


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setenv(VARIABLE_JETON, JETON)
    monkeypatch.delenv(VARIABLE_VERSION, raising=False)


@pytest.fixture
def sans_jeton(monkeypatch):
    monkeypatch.delenv(VARIABLE_JETON, raising=False)


def _connecteur(tmp_path: Path, reponses: Dict[str, Any], publier: bool = True):
    linkedin = FauxLinkedIn({"GET /v2/userinfo": MEMBRE, **reponses})
    return LinkedInConnector(transport=httpx.MockTransport(linkedin),
                             acces=_acces(tmp_path, publier)), linkedin


# --- Sans jeton ----------------------------------------------------------------------

def test_sans_jeton_rien_ne_part_et_la_sante_dit_ce_qui_manque(sans_jeton, tmp_path):
    connecteur, linkedin = _connecteur(tmp_path, {})

    sante = connecteur.sonder()
    resultat = connecteur.executer("profil")

    assert sante.etat == EtatSante.NON_CONFIGURE
    assert "LINKEDIN_ACCESS_TOKEN" in sante.ce_qui_manque
    assert "w_member_social" in sante.ce_qui_manque
    assert resultat.statut != Statut.SUCCES
    assert linkedin.requetes == []


# --- Sante et profil -------------------------------------------------------------------

def test_la_sante_dit_a_qui_appartient_le_jeton(configure, tmp_path):
    connecteur, linkedin = _connecteur(tmp_path, {})

    sante = connecteur.sonder()

    assert sante.etat == EtatSante.OPERATIONNEL
    assert "Ousmane Diop" in sante.message
    entetes = linkedin.requetes[0].headers
    assert entetes["Authorization"] == f"Bearer {JETON}"
    assert entetes["LinkedIn-Version"] == VERSION_PAR_DEFAUT


def test_une_sonde_remesure_au_lieu_de_reprendre_le_membre_connu(configure, tmp_path, monkeypatch):
    connecteur, linkedin = _connecteur(tmp_path, {})
    assert connecteur.executer("profil").statut == Statut.SUCCES

    linkedin.reponses["GET /v2/userinfo"] = httpx.Response(401, json={"message": "Expired token"})
    # Une minute plus tard : la sante gardee a expire, la sonde remesure.
    import social.linkedin.linkedin_connector as module
    maintenant = module.time.monotonic()
    monkeypatch.setattr(module.time, "monotonic", lambda: maintenant + 120)
    sante = connecteur.sonder()

    assert sante.etat == EtatSante.EN_PANNE
    assert "Expired token" in sante.message


def test_un_jeton_refuse_ne_sort_pas_dans_le_message(configure, tmp_path):
    refus = httpx.Response(401, json={"message": f"Invalid access token {JETON}"})
    connecteur, _ = _connecteur(tmp_path, {"GET /v2/userinfo": refus})

    sante = connecteur.sonder()

    assert sante.etat == EtatSante.EN_PANNE
    assert "401" in sante.message and JETON not in sante.message


def test_un_jeton_sans_openid_est_dit(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {"GET /v2/userinfo": {"name": "x"}})

    resultat = connecteur.executer("profil")

    assert resultat.statut == Statut.ECHEC
    assert "openid" in resultat.message


# --- Publier ---------------------------------------------------------------------------

def test_un_post_attend_la_confirmation(configure, tmp_path):
    connecteur, linkedin = _connecteur(tmp_path, {"POST /rest/posts": POST_CREE})

    resultat = connecteur.executer("publier", message="Nouveau chantier livre.")

    assert resultat.statut == Statut.A_CONFIRMER
    assert linkedin.posts() == []


def test_le_coupe_circuit_publish_refuse_meme_confirme(configure, tmp_path):
    connecteur, linkedin = _connecteur(tmp_path, {"POST /rest/posts": POST_CREE}, publier=False)

    for resultat in (connecteur.executer("publier", message="x"),
                     connecteur.executer_confirmee("publier", message="x")):
        assert resultat.statut == Statut.REFUSE
        assert "PUBLISH" in resultat.message
    assert linkedin.requetes == []


def test_confirme_le_post_part_au_nom_du_proprietaire(configure, tmp_path):
    connecteur, linkedin = _connecteur(tmp_path, {"POST /rest/posts": POST_CREE})

    resultat = connecteur.executer_confirmee(
        "publier", message="Nouveau chantier livre.", lien="https://www.unicplaquiste.com")

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "linkedin:urn:li:share:7001"
    corps = linkedin.posts()[0]
    assert corps["author"] == "urn:li:person:abc123"
    assert corps["commentary"] == "Nouveau chantier livre."
    assert corps["visibility"] == "PUBLIC" and corps["lifecycleState"] == "PUBLISHED"
    assert corps["content"]["article"]["source"] == "https://www.unicplaquiste.com"


def test_sans_identifiant_rendu_le_post_n_est_pas_annonce(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {"POST /rest/posts": httpx.Response(201)})

    resultat = connecteur.executer_confirmee("publier", message="x")

    assert resultat.statut == Statut.ECHEC
    assert "identifiant" in resultat.message


def test_un_post_trop_long_n_est_pas_envoye(configure, tmp_path):
    connecteur, linkedin = _connecteur(tmp_path, {"POST /rest/posts": POST_CREE})

    resultat = connecteur.executer_confirmee("publier", message="x" * (CARACTERES_MAX + 1))

    assert resultat.statut == Statut.ECHEC
    assert str(CARACTERES_MAX) in resultat.message
    assert linkedin.posts() == []


@pytest.mark.parametrize("lien", ["http://site.test", "javascript:alert(1)"])
def test_un_lien_non_https_n_est_pas_envoye(configure, tmp_path, lien):
    connecteur, linkedin = _connecteur(tmp_path, {"POST /rest/posts": POST_CREE})

    resultat = connecteur.executer_confirmee("publier", message="x", lien=lien)

    assert resultat.statut == Statut.ECHEC
    assert linkedin.posts() == []


def test_une_erreur_linkedin_devient_un_echec(configure, tmp_path):
    refus = httpx.Response(403, json={"message": "Not enough permissions to access: w_member_social"})
    connecteur, _ = _connecteur(tmp_path, {"POST /rest/posts": refus})

    resultat = connecteur.executer_confirmee("publier", message="x")

    assert resultat.statut == Statut.ECHEC
    assert "403" in resultat.message and "w_member_social" in resultat.message


def test_ce_qui_partira_est_montre_avant_la_confirmation(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {})

    texte = connecteur.resultat_attendu(connecteur.capacites()["publier"],
                                        message="Nouveau chantier", lien="https://x.test")

    assert "Nouveau chantier" in texte and "https://x.test" in texte


def test_seules_les_capacites_accordees_a_une_application_ordinaire_existent(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {})

    assert set(connecteur.capacites()) == {"profil", "publier"}
    assert connecteur.executer("statistiques").statut == Statut.NON_IMPLEMENTE


def test_le_registre_de_la_plateforme_le_connait():
    from apps.backend.runtime import registre

    assert "linkedin" in registre.noms()
