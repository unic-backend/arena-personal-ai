"""Le connecteur TikTok reel (DEC-0185) : l'API Content Posting.

Aucun test n'appelle TikTok : la couche reseau est un `httpx.MockTransport`
qui note chaque requete. Ce qui est garanti :

- le jeton d'acces (24 h) se renouvelle, et un nouveau jeton de
  renouvellement rendu par TikTok est confie a `persister` ;
- une video ne part jamais sans confirmation, ni quand PUBLISH est coupe ;
- un succes porte le `publish_id` ET l'envoi du fichier accepte ;
- « envoyee » n'est jamais dit « en ligne » ;
- le niveau de confidentialite est verifie contre ce que TikTok permet ;
- aucun secret ne sort dans un message.
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
from social.tiktok.tiktok_connector import (
    BASE,
    TAILLE_MORCEAU,
    URL_JETON,
    VARIABLE_CLE,
    VARIABLE_CONFIDENTIALITE,
    VARIABLE_JETON,
    VARIABLE_RENOUVELLEMENT,
    VARIABLE_SECRET,
    TikTokConnector,
    decouper,
)

SECRET = "sk-secret-de-test"
RENOUVELLEMENT = "rft.ancien"
ACCES = "act.jeton-du-jour"
ENVOI = "https://open-upload.tiktokapis.test/upload/?id=42"

COMPTE = {"data": {"creator_username": "unic_plaquiste", "creator_nickname": "UniC",
                   "privacy_level_options": ["SELF_ONLY"], "max_video_post_duration_sec": 600},
          "error": {"code": "ok", "message": ""}}


def ok(donnees: Dict[str, Any]) -> Dict[str, Any]:
    return {"data": donnees, "error": {"code": "ok", "message": ""}}


class FauxTikTok:
    """Rend une reponse par « METHODE url » et garde chaque requete."""

    def __init__(self, reponses: Dict[str, Any]) -> None:
        self.reponses = reponses
        self.requetes: List[httpx.Request] = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(requete)
        cle = f"{requete.method} {requete.url}"
        reponse = self.reponses.get(cle)
        if reponse is None:
            return httpx.Response(404, json={"error": {"code": "not_found", "message": cle}})
        if callable(reponse):
            return reponse(requete)
        if isinstance(reponse, httpx.Response):
            return reponse
        return httpx.Response(200, json=reponse)

    def vers(self, fragment: str) -> List[httpx.Request]:
        return [r for r in self.requetes if fragment in str(r.url)]


def _acces(tmp_path: Path, publier: bool) -> ControleAcces:
    fichier = tmp_path / "permissions.yaml"
    fichier.write_text(f"PUBLISH: {str(publier).lower()}\n", encoding="utf-8")
    return ControleAcces(permissions=PermissionManager(str(fichier)))


BASE_REPONSES = {
    f"POST {URL_JETON}": {"access_token": ACCES, "expires_in": 86400,
                          "refresh_token": RENOUVELLEMENT, "open_id": "o1"},
    f"POST {BASE}/post/publish/creator_info/query/": COMPTE,
}


def _connecteur(tmp_path: Path, reponses: Dict[str, Any] = None, publier: bool = True):
    tiktok = FauxTikTok({**BASE_REPONSES, **(reponses or {})})
    persistes: List[tuple] = []
    connecteur = TikTokConnector(transport=httpx.MockTransport(tiktok),
                                 persister=lambda v, x: persistes.append((v, x)),
                                 acces=_acces(tmp_path, publier))
    return connecteur, tiktok, persistes


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.delenv(VARIABLE_JETON, raising=False)
    monkeypatch.setenv(VARIABLE_CLE, "cle-app")
    monkeypatch.setenv(VARIABLE_SECRET, SECRET)
    monkeypatch.setenv(VARIABLE_RENOUVELLEMENT, RENOUVELLEMENT)
    monkeypatch.delenv(VARIABLE_CONFIDENTIALITE, raising=False)


@pytest.fixture
def sans_tiktok(monkeypatch):
    for nom in (VARIABLE_JETON, VARIABLE_CLE, VARIABLE_SECRET, VARIABLE_RENOUVELLEMENT):
        monkeypatch.delenv(nom, raising=False)


@pytest.fixture
def video(tmp_path) -> Path:
    chemin = tmp_path / "chantier.mp4"
    chemin.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 1000)
    return chemin


PUBLIER = {
    f"POST {BASE}/post/publish/video/init/": ok({"publish_id": "v_pub_1", "upload_url": ENVOI}),
    f"PUT {ENVOI}": httpx.Response(201),
}


# --- Sans connexion -------------------------------------------------------------------

def test_sans_connexion_rien_ne_part(sans_tiktok, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path)

    assert connecteur.sonder().etat == EtatSante.NON_CONFIGURE
    assert connecteur.executer_confirmee("publish_video", fichier=str(video)).statut != Statut.SUCCES
    assert tiktok.requetes == []


# --- Le jeton ----------------------------------------------------------------------------

def test_le_jeton_du_jour_s_obtient_par_le_renouvellement(configure, tmp_path):
    connecteur, tiktok, persistes = _connecteur(tmp_path)

    sante = connecteur.sonder()

    assert sante.etat == EtatSante.OPERATIONNEL and "@unic_plaquiste" in sante.message
    renouvellement = tiktok.vers("/oauth/token/")[0]
    assert dict(httpx.QueryParams(renouvellement.content.decode())) == {
        "client_key": "cle-app", "client_secret": SECRET,
        "grant_type": "refresh_token", "refresh_token": RENOUVELLEMENT}
    assert tiktok.vers("creator_info")[0].headers["Authorization"] == f"Bearer {ACCES}"
    assert persistes == [], "meme jeton de renouvellement : rien a ecrire"


def test_un_nouveau_jeton_de_renouvellement_est_garde(configure, tmp_path):
    connecteur, _, persistes = _connecteur(tmp_path, {
        f"POST {URL_JETON}": {"access_token": ACCES, "expires_in": 86400,
                              "refresh_token": "rft.nouveau"}})

    connecteur.sonder()

    assert persistes == [(VARIABLE_RENOUVELLEMENT, "rft.nouveau")]


def test_le_jeton_n_est_redemande_qu_a_son_expiration(configure, tmp_path):
    connecteur, tiktok, _ = _connecteur(tmp_path)

    connecteur.executer("compte")
    connecteur.executer("compte")

    assert len(tiktok.vers("/oauth/token/")) == 1


def test_un_renouvellement_refuse_rend_la_sante_en_panne(configure, tmp_path):
    connecteur, _, _ = _connecteur(tmp_path, {
        f"POST {URL_JETON}": {"error": "invalid_grant", "error_description": "expired"}})

    sante = connecteur.sonder()

    assert sante.etat == EtatSante.EN_PANNE
    assert "aucun jeton" in sante.message


def test_aucun_secret_ne_sort_dans_un_refus(configure, tmp_path):
    refus = httpx.Response(401, json={"error": {
        "code": "access_token_invalid", "message": f"bad {ACCES} / {SECRET} / {RENOUVELLEMENT}"}})
    connecteur, _, _ = _connecteur(tmp_path, {f"POST {BASE}/post/publish/creator_info/query/": refus})

    message = connecteur.sonder().message

    assert "401" in message
    for secret in (ACCES, SECRET, RENOUVELLEMENT):
        assert secret not in message


# --- Publier -----------------------------------------------------------------------------

def test_une_video_attend_la_confirmation(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER)

    resultat = connecteur.executer("publish_video", fichier=str(video), legende="Plafond")

    assert resultat.statut == Statut.A_CONFIRMER
    assert not tiktok.vers("/video/init/") and not tiktok.vers(ENVOI)


def test_le_coupe_circuit_publish_refuse_meme_confirme(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER, publier=False)

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video), legende="x")

    assert resultat.statut == Statut.REFUSE and "PUBLISH" in resultat.message
    assert tiktok.requetes == []


def test_confirmee_la_video_part_et_n_est_pas_dite_en_ligne(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER)

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video),
                                             legende="Faux plafond Almadies")

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "tiktok:v_pub_1"
    assert "pas encore en ligne" in resultat.message and "SELF_ONLY" in resultat.message
    debut = json.loads(tiktok.vers("/video/init/")[0].content)
    taille = video.stat().st_size
    assert debut == {"post_info": {"title": "Faux plafond Almadies", "privacy_level": "SELF_ONLY"},
                     "source_info": {"source": "FILE_UPLOAD", "video_size": taille,
                                     "chunk_size": taille, "total_chunk_count": 1}}
    envoi = tiktok.vers(ENVOI)[0]
    assert envoi.method == "PUT" and envoi.content == video.read_bytes()
    assert envoi.headers["Content-Range"] == f"bytes 0-{taille - 1}/{taille}"
    assert envoi.headers["Content-Type"] == "video/mp4"


def test_un_envoi_refuse_n_est_pas_un_succes(configure, tmp_path, video):
    connecteur, _, _ = _connecteur(tmp_path, {**PUBLIER, f"PUT {ENVOI}": httpx.Response(400)})

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video), legende="x")

    assert resultat.statut == Statut.ECHEC
    assert "morceau 1/1" in resultat.message and resultat.detail["publish_id"] == "v_pub_1"


def test_sans_publish_id_rien_n_est_envoye(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, {
        f"POST {BASE}/post/publish/video/init/": ok({}), f"PUT {ENVOI}": httpx.Response(201)})

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video), legende="x")

    assert resultat.statut == Statut.ECHEC
    assert not tiktok.vers(ENVOI)


def test_une_confidentialite_non_permise_ne_part_pas(configure, monkeypatch, tmp_path, video):
    """Une application non auditee ne publie qu'en SELF_ONLY : c'est TikTok qui le dit."""
    monkeypatch.setenv(VARIABLE_CONFIDENTIALITE, "PUBLIC_TO_EVERYONE")
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER)

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video), legende="x")

    assert resultat.statut == Statut.ECHEC
    assert "PUBLIC_TO_EVERYONE" in resultat.message and "SELF_ONLY" in resultat.message
    assert not tiktok.vers("/video/init/")


@pytest.mark.parametrize("nom, contenu, attendu", [
    ("absente.mp4", None, "introuvable"),
    ("image.png", b"png", "MP4, MOV ou WebM"),
    ("vide.mp4", b"", "vide"),
])
def test_un_fichier_impossible_ne_part_pas(configure, tmp_path, nom, contenu, attendu):
    chemin = tmp_path / nom
    if contenu is not None:
        chemin.write_bytes(contenu)
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER)

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(chemin), legende="x")

    assert resultat.statut == Statut.ECHEC and attendu in resultat.message
    assert not tiktok.vers("/init/")


def test_une_legende_trop_longue_ne_part_pas(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER)

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video), legende="x" * 2201)

    assert resultat.statut == Statut.ECHEC and "2200" in resultat.message
    assert not tiktok.vers("/init/")


# --- Brouillon et statut -----------------------------------------------------------------

def test_le_brouillon_va_dans_la_boite_sans_etre_publie(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, {
        f"POST {BASE}/post/publish/inbox/video/init/": ok({"publish_id": "v_inb_1", "upload_url": ENVOI}),
        f"PUT {ENVOI}": httpx.Response(201)})

    resultat = connecteur.executer_confirmee("envoyer_brouillon", fichier=str(video))

    assert resultat.statut == Statut.SUCCES, resultat.message
    assert resultat.preuve == "tiktok:v_inb_1" and "ouvre l'application" in resultat.message
    assert "post_info" not in json.loads(tiktok.vers("/inbox/video/init/")[0].content)


@pytest.mark.parametrize("etat, attendu", [
    ({"status": "PUBLISH_COMPLETE"}, "est publiee"),
    ({"status": "PROCESSING_UPLOAD"}, "traite encore"),
    ({"status": "FAILED", "fail_reason": "duration_check_failed"}, "duration_check_failed"),
])
def test_le_statut_dit_ce_que_tiktok_dit(configure, tmp_path, etat, attendu):
    connecteur, tiktok, _ = _connecteur(tmp_path, {
        f"POST {BASE}/post/publish/status/fetch/": ok(etat)})

    resultat = connecteur.executer("statut_publication", publish_id="v_pub_1")

    assert resultat.statut == Statut.SUCCES and attendu in resultat.message
    assert json.loads(tiktok.vers("status/fetch")[0].content) == {"publish_id": "v_pub_1"}


# --- Le decoupage --------------------------------------------------------------------------

def test_une_grosse_video_part_en_morceaux_le_dernier_prenant_le_reste(configure, tmp_path, monkeypatch):
    import social.tiktok.tiktok_connector as module

    monkeypatch.setattr(module, "MORCEAU_UNIQUE_MAX", 100)
    monkeypatch.setattr(module, "TAILLE_MORCEAU", 40)
    chemin = tmp_path / "long.mp4"
    chemin.write_bytes(bytes(range(256))[:130])
    connecteur, tiktok, _ = _connecteur(tmp_path, PUBLIER)

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(chemin), legende="x")

    assert resultat.statut == Statut.SUCCES, resultat.message
    plages = [r.headers["Content-Range"] for r in tiktok.vers(ENVOI)]
    assert plages == ["bytes 0-39/130", "bytes 40-79/130", "bytes 80-129/130"]
    assert b"".join(r.content for r in tiktok.vers(ENVOI)) == chemin.read_bytes()


def test_le_decoupage_suit_les_regles_de_tiktok():
    assert decouper(5_000_000) == {"video_size": 5_000_000, "chunk_size": 5_000_000,
                                   "total_chunk_count": 1}
    grande = 25 * TAILLE_MORCEAU + 123
    assert decouper(grande)["total_chunk_count"] == 25


def test_ce_qui_partira_est_montre_avant_la_confirmation(configure, tmp_path, video):
    connecteur, _, _ = _connecteur(tmp_path)

    texte = connecteur.resultat_attendu(connecteur.capacites()["publish_video"],
                                        fichier=str(video), legende="Faux plafond")

    assert "chantier.mp4" in texte and "SELF_ONLY" in texte and "Faux plafond" in texte


def test_une_adresse_d_envoi_sans_publish_id_n_envoie_rien(configure, tmp_path, video):
    connecteur, tiktok, _ = _connecteur(tmp_path, {
        f"POST {BASE}/post/publish/video/init/": ok({"upload_url": ENVOI}),
        f"PUT {ENVOI}": httpx.Response(201)})

    resultat = connecteur.executer_confirmee("publish_video", fichier=str(video), legende="x")

    assert resultat.statut == Statut.ECHEC
    assert not tiktok.vers(ENVOI), "sans identifiant, rien ne prouverait la publication"


def test_un_200_portant_une_erreur_est_un_refus(configure, tmp_path):
    """TikTok peut repondre 200 avec une erreur dans le corps : le code decide."""
    connecteur, _, _ = _connecteur(tmp_path, {
        f"POST {BASE}/post/publish/creator_info/query/": {
            "data": {}, "error": {"code": "scope_not_authorized", "message": "video.publish"}}})

    sante = connecteur.sonder()

    assert sante.etat == EtatSante.EN_PANNE
    assert "video.publish" in sante.message
