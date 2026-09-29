"""Le connecteur Meta (DEC-0179) : Facebook et Instagram par la Graph API.

Aucun test n'appelle Meta : la couche reseau est un `httpx.MockTransport` qui
note chaque requete. Trois garanties portent ce fichier :

- sans jeton, rien ne part, et la sante dit ce qui manque ;
- une publication ne part jamais sans confirmation, et jamais quand le
  coupe-circuit PUBLISH est coupe — meme confirmee ;
- le jeton ne sort jamais dans un message.
"""
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.permissions.controle import ControleAcces
from core.permissions.permission_manager import PermissionManager
from social.meta.meta_connector import (
    VARIABLE_INSTAGRAM,
    VARIABLE_JETON,
    VARIABLE_PAGE,
    VARIABLE_VERSION,
    MetaConnector,
)

JETON = "EAAG-jeton-de-test-secret"


class FauxMeta:
    """Rend une reponse par chemin et garde chaque requete recue."""

    def __init__(self, reponses: Dict[str, Any]) -> None:
        self.reponses = reponses
        self.requetes: List[httpx.Request] = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(requete)
        chemin = requete.url.path.removeprefix("/v23.0")
        reponse = self.reponses.get(f"{requete.method} {chemin}")
        if reponse is None:
            return httpx.Response(404, json={"error": {"message": f"inconnu : {chemin}"}})
        if isinstance(reponse, httpx.Response):
            return reponse
        return httpx.Response(200, json=reponse)

    def corps(self, index: int) -> Dict[str, str]:
        return dict(httpx.QueryParams(self.requetes[index].content.decode()))


def _acces(tmp_path: Path, publier: bool) -> ControleAcces:
    fichier = tmp_path / "permissions.yaml"
    fichier.write_text(f"PUBLISH: {str(publier).lower()}\nSEND_MESSAGES: true\n", encoding="utf-8")
    return ControleAcces(permissions=PermissionManager(str(fichier)))


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setenv(VARIABLE_JETON, JETON)
    monkeypatch.setenv(VARIABLE_PAGE, "111")
    monkeypatch.setenv(VARIABLE_INSTAGRAM, "999")
    monkeypatch.delenv(VARIABLE_VERSION, raising=False)


@pytest.fixture
def sans_jeton(monkeypatch):
    for nom in (VARIABLE_JETON, VARIABLE_PAGE, VARIABLE_INSTAGRAM):
        monkeypatch.delenv(nom, raising=False)


PAGE = {"id": "111", "name": "Unic Plaquiste"}


def _connecteur(tmp_path: Path, reponses: Dict[str, Any], publier: bool = True):
    meta = FauxMeta({"GET /111": PAGE, **reponses})
    return MetaConnector(transport=httpx.MockTransport(meta), acces=_acces(tmp_path, publier)), meta


# --- Sans jeton ----------------------------------------------------------------------

def test_sans_jeton_rien_ne_part_et_la_sante_dit_ce_qui_manque(sans_jeton, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {})

    sante = connecteur.sonder()
    resultat = connecteur.executer("page_infos")

    assert sante.etat == EtatSante.NON_CONFIGURE
    assert "META_PAGE_ACCESS_TOKEN" in sante.ce_qui_manque
    assert "docs/CONNECTER_MES_COMPTES.md" in sante.ce_qui_manque
    assert resultat.statut != Statut.SUCCES
    assert meta.requetes == [], "aucune requete sans jeton"


def test_la_sante_est_mesuree_et_gardee_une_minute(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {})

    assert connecteur.sonder().etat == EtatSante.OPERATIONNEL
    assert "Unic Plaquiste" in connecteur.sonder().message
    assert len(meta.requetes) == 1, "la seconde sonde reprend la mesure"


def test_un_jeton_refuse_rend_la_sante_en_panne_sans_le_jeton(configure, tmp_path):
    refus = httpx.Response(400, json={"error": {"message": f"Invalid OAuth access token {JETON}"}})
    connecteur, _ = _connecteur(tmp_path, {"GET /111": refus})

    sante = connecteur.sonder()

    assert sante.etat == EtatSante.EN_PANNE
    assert "Invalid OAuth" in sante.message
    assert JETON not in sante.message


# --- Lire ------------------------------------------------------------------------------

def test_les_publications_instagram_sont_lues_avec_leur_preuve(configure, tmp_path):
    medias = {"data": [{"id": "m1", "caption": "Faux plafond Almadies", "like_count": 42}]}
    connecteur, meta = _connecteur(tmp_path, {"GET /999/media": medias})

    resultat = connecteur.executer("instagram_publications", limite=5)

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "meta:GET:/999/media"
    assert resultat.detail["donnees"] == medias["data"]
    requete = meta.requetes[-1]
    assert requete.url.params["limit"] == "5"
    assert requete.url.params["access_token"] == JETON, "le jeton voyage dans la requete"


def test_la_limite_est_bornee(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {"GET /111/posts": {"data": []}})

    connecteur.executer("page_publications", limite=10_000)

    assert meta.requetes[-1].url.params["limit"] == "25"


def test_sans_compte_instagram_la_lecture_le_dit(configure, monkeypatch, tmp_path):
    monkeypatch.delenv(VARIABLE_INSTAGRAM)
    connecteur, meta = _connecteur(tmp_path, {})

    resultat = connecteur.executer("instagram_infos")

    assert resultat.statut == Statut.ECHEC
    assert "META_IG_USER_ID" in resultat.message
    assert all("/999" not in str(r.url) for r in meta.requetes)


def test_des_commentaires_sans_publication_ne_sont_pas_demandes(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {})

    resultat = connecteur.executer("commentaires")

    assert resultat.statut == Statut.ECHEC
    assert "publication_id" in resultat.message


def test_une_erreur_meta_devient_un_echec_sans_le_jeton(configure, tmp_path):
    refus = httpx.Response(403, json={"error": {"message": f"Permissions error, token {JETON}"}})
    connecteur, _ = _connecteur(tmp_path, {"GET /111/posts": refus})

    resultat = connecteur.executer("page_publications")

    assert resultat.statut == Statut.ECHEC
    assert "403" in resultat.message and "Permissions error" in resultat.message
    assert JETON not in resultat.message


# --- Publier ---------------------------------------------------------------------------

def test_une_publication_attend_la_confirmation(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {"POST /111/feed": {"id": "111_5"}})

    resultat = connecteur.executer("publier_facebook", message="Chantier livre !")

    assert resultat.statut == Statut.A_CONFIRMER
    assert not [r for r in meta.requetes if r.method == "POST"], "rien n'est parti"


def test_le_coupe_circuit_publish_refuse_meme_confirme(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {"POST /111/feed": {"id": "111_5"}}, publier=False)

    for resultat in (connecteur.executer("publier_facebook", message="x"),
                     connecteur.executer_confirmee("publier_facebook", message="x")):
        assert resultat.statut == Statut.REFUSE
        assert "PUBLISH" in resultat.message
    assert meta.requetes == []


def test_confirmee_la_publication_facebook_part_avec_sa_preuve(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {"POST /111/feed": {"id": "111_5"}})

    resultat = connecteur.executer_confirmee(
        "publier_facebook", message="Chantier livre !", lien="https://www.unicplaquiste.com")

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "facebook:111_5"
    assert meta.corps(-1) == {"message": "Chantier livre !", "link": "https://www.unicplaquiste.com",
                              "access_token": JETON}


def test_sans_identifiant_rendu_la_publication_n_est_pas_annoncee(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {"POST /111/feed": {}})

    resultat = connecteur.executer_confirmee("publier_facebook", message="x")

    assert resultat.statut == Statut.ECHEC
    assert "identifiant" in resultat.message


def test_instagram_publie_en_deux_temps(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {
        "POST /999/media": {"id": "conteneur-7"},
        "POST /999/media_publish": {"id": "ig-42"},
    })

    resultat = connecteur.executer_confirmee(
        "publier_instagram", image_url="https://cdn.test/plafond.jpg", legende="Avant / apres")

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "instagram:ig-42"
    posts = [i for i, r in enumerate(meta.requetes) if r.method == "POST"]
    assert meta.corps(posts[0])["image_url"] == "https://cdn.test/plafond.jpg"
    assert meta.corps(posts[0])["caption"] == "Avant / apres"
    assert meta.corps(posts[1])["creation_id"] == "conteneur-7"


def test_un_conteneur_non_publie_est_dit(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {
        "POST /999/media": {"id": "conteneur-7"},
        "POST /999/media_publish": httpx.Response(400, json={"error": {"message": "Media not ready"}}),
    })

    resultat = connecteur.executer_confirmee(
        "publier_instagram", image_url="https://cdn.test/a.jpg", legende="x")

    assert resultat.statut == Statut.ECHEC
    assert "conteneur-7" in resultat.message and "Media not ready" in resultat.message


@pytest.mark.parametrize("image", [None, "", "http://cdn.test/a.jpg", "C:/photos/a.jpg"])
def test_instagram_exige_une_adresse_https(configure, tmp_path, image):
    connecteur, meta = _connecteur(tmp_path, {})

    resultat = connecteur.executer_confirmee("publier_instagram", image_url=image, legende="x")

    assert resultat.statut == Statut.ECHEC
    assert "https://" in resultat.message
    assert not [r for r in meta.requetes if r.method == "POST"]


# --- Repondre --------------------------------------------------------------------------

@pytest.mark.parametrize("reseau, chemin", [("instagram", "/c1/replies"), ("facebook", "/c1/comments")])
def test_la_reponse_suit_le_chemin_du_reseau(configure, tmp_path, reseau, chemin):
    connecteur, meta = _connecteur(tmp_path, {f"POST {chemin}": {"id": "r9"}})

    resultat = connecteur.executer_confirmee(
        "repondre_commentaire", commentaire_id="c1", message="Merci !", reseau=reseau)

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "meta:r9"
    assert meta.requetes[-1].url.path.endswith(chemin)


def test_une_reponse_attend_aussi_la_confirmation(configure, tmp_path):
    connecteur, meta = _connecteur(tmp_path, {"POST /c1/comments": {"id": "r9"}})

    resultat = connecteur.executer("repondre_commentaire", commentaire_id="c1", message="Merci !")

    assert resultat.statut == Statut.A_CONFIRMER
    assert not [r for r in meta.requetes if r.method == "POST"]


def test_ce_qui_partira_est_montre_avant_la_confirmation(configure, tmp_path):
    connecteur, _ = _connecteur(tmp_path, {})
    capacite = connecteur.capacites()["publier_instagram"]

    texte = connecteur.resultat_attendu(capacite, image_url="https://cdn.test/a.jpg", legende="Avant / apres")

    assert "https://cdn.test/a.jpg" in texte and "Avant / apres" in texte


def test_le_registre_de_la_plateforme_le_connait():
    from apps.backend.runtime import registre

    assert "meta" in registre.noms()
