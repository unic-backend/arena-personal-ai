"""L'audit de la surface publique dit-il la vérité ?

VOLET « ARENA en ligne », phases 4.1 puis 4.2. `scripts/auditer_surface_publique.py`
mesure l'application réelle (`TestClient`), jamais son code source — ce fichier
protège cette promesse de deux façons :

1. `Constat.est_un_defaut` est testé seul, sans dépendre de l'application
   (sabotage direct sur le dataclass).
2. `auditer()` est appelé pour de vrai et doit désormais retrouver **zéro**
   défaut : la 4.2 a fermé les deux trouvés par la 4.1 (`/media/rendered`
   exige la clé, la documentation FastAPI est fermée par défaut). Une
   régression sur l'un ou l'autre doit faire échouer ce fichier.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

from auditer_surface_publique import ROUTES_DELIBEREMENT_PUBLIQUES, Constat, auditer  # noqa: E402


def test_defaut_si_repond_sans_cle_et_pas_sur_la_liste_publique():
    """Une route qui répond (< 400) sans y être autorisée est un défaut."""
    c = Constat(chemin="/api/quelque-chose", code=200, attendu_public=False)
    assert c.est_un_defaut is True


def test_pas_de_defaut_si_deliberement_public():
    """Une route publique assumée qui répond n'est pas un défaut."""
    c = Constat(chemin="/health", code=200, attendu_public=True)
    assert c.est_un_defaut is False


def test_pas_de_defaut_si_la_route_refuse():
    """Une route protégée qui répond 401/403/404/405 n'est pas un défaut."""
    for code in (401, 403, 404, 405, 500):
        c = Constat(chemin="/api/actions", code=code, attendu_public=False)
        assert c.est_un_defaut is False, f"code {code} ne devrait pas etre un defaut"


def test_audit_ne_trouve_plus_aucun_defaut():
    """Phase 4.2 : les deux défauts mesurés en 4.1 doivent être fermés."""
    constats = auditer()
    defauts = [c.chemin for c in constats if c.est_un_defaut]
    assert defauts == [], f"routes encore joignables sans cle : {defauts}"


def test_le_mount_media_exige_desormais_la_cle():
    """Le fichier depose dans /media/rendered ne repond plus sans cle.

    Avant la 4.2, ce meme appel rendait le fichier en HTTP 200 — prouve a la
    main le 30/08/2026. Il doit desormais refuser.
    """
    constats = auditer()
    media = [c for c in constats if c.chemin.startswith("/media/rendered/")]
    assert media, "l'audit doit sonder le mount /media/rendered"
    assert media[0].code == 401
    assert media[0].est_un_defaut is False


def test_la_documentation_est_fermee_par_defaut():
    """`/openapi.json`, `/docs` et `/redoc` ne doivent plus repondre sans cle.

    `APP_ENV` n'est pas positionne dans cet environnement de test : c'est
    exactement le cas — le plus probable — que `docs_actives()` doit fermer.
    """
    constats = auditer()
    par_chemin = {c.chemin: c for c in constats}
    for chemin in ("/openapi.json", "/docs", "/redoc"):
        assert chemin in par_chemin, f"{chemin} doit etre sonde"
        assert par_chemin[chemin].code == 404
        assert par_chemin[chemin].est_un_defaut is False


def test_aucune_route_api_reelle_n_est_publique():
    """Regression : aucune route `/api/*` ou `/v1/*` ne doit apparaitre comme un defaut.

    Toutes ont `Depends(verify_api_key)` — si l'une d'elles ressort en
    defaut, c'est une vraie regression de securite, pas une fausse alerte.
    """
    constats = auditer()
    api = [c for c in constats if c.chemin.startswith(("/api/", "/v1/"))]
    assert api, "l'audit doit couvrir des routes /api et /v1"
    en_defaut = [c.chemin for c in api if c.est_un_defaut]
    assert en_defaut == [], f"routes API publiques sans cle : {en_defaut}"


def test_routes_deliberement_publiques_couvre_les_pages_de_l_interface():
    """La liste blanche ne doit contenir que des pages d'interface, pas des API."""
    for chemin in ROUTES_DELIBEREMENT_PUBLIQUES:
        assert not chemin.startswith("/api/") and not chemin.startswith("/v1/")
