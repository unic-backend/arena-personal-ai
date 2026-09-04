"""L'audit de la surface publique dit-il la vérité ?

VOLET « ARENA en ligne », phases 4.1, 4.2, puis 04/09/2026 (DEC-0045).
`scripts/auditer_surface_publique.py` mesure l'application réelle
(`TestClient`), jamais son code source — ce fichier protège cette promesse
de plusieurs façons :

1. `Constat.est_un_defaut` est testé seul, sans dépendre de l'application
   (sabotage direct sur le dataclass).
2. `auditer()` est appelé pour de vrai et doit désormais retrouver **zéro**
   défaut : la 4.2 a fermé les deux trouvés par la 4.1 (`/media/rendered`
   exige la clé, la documentation FastAPI est fermée par défaut). Une
   régression sur l'un ou l'autre doit faire échouer ce fichier.
3. **04/09/2026** : le script n'envoyait que des `GET`, quelle que soit la
   vraie méthode d'une route — un `POST` non protégé répondait `405` à un
   `GET`, compté comme « protégé » sans que la clé n'ait jamais été
   vérifiée. Les routes paramétrées (`/connectors/{fournisseur}/...`)
   étaient en plus sautées entièrement. Les tests ci-dessous verrouillent
   que le script appelle bien la VRAIE méthode de chaque route, avec un
   paramètre substitué quand elle en attend un, et un corps assez valide
   pour qu'une route non protégée puisse réellement réussir (200) plutôt
   que d'échouer sur sa propre validation (422) — ce qui masquerait
   exactement le défaut que ce script existe pour trouver.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

from auditer_surface_publique import (  # noqa: E402
    CORPS_MINIMAL,
    VALEURS_DE_SONDE_PAR_PARAMETRE,
    Constat,
    _chemin_concret,
    _routes_api_declarees,
    auditer,
)


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


# --- 04/09/2026 : la vraie méthode, pas GET par défaut -------------------------

def test_chemin_concret_substitue_chaque_parametre():
    assert _chemin_concret("/health") == "/health"
    assert _chemin_concret("/icons/{nom}") == "/icons/sonde-audit"
    assert "{" not in _chemin_concret("/connectors/{fournisseur}/status")


def test_chemin_concret_utilise_la_valeur_dediee_du_parametre():
    """`{fournisseur}` ne prend pas une valeur inventée qui échouerait sur la
    propre logique de la route avant d'avoir pu dire quoi que ce soit sur
    l'authentification."""
    assert VALEURS_DE_SONDE_PAR_PARAMETRE["fournisseur"] == "gmail"
    assert _chemin_concret("/connectors/{fournisseur}/status") == "/connectors/gmail/status"


def test_toutes_les_routes_parametrees_sont_reellement_appelees():
    """Aucune route déclarée n'est plus jamais sautée à cause d'un `{...}`.

    `/media/rendered/{nom}` est la seule exception légitime : elle a sa
    propre sonde dédiée (`_auditer_mount_media`), avec un vrai fichier écrit
    sur disque — un placeholder générique n'y prouverait rien.
    """
    constats = auditer()
    chemins_vus = {c.chemin for c in constats}
    routes_parametrees = [
        g for g, _ in _routes_api_declarees()
        if "{" in g and g != "/media/rendered/{nom}"
    ]

    assert routes_parametrees, "aucune route parametree a verifier : le test ne prouve rien"
    manquantes = [g for g in routes_parametrees if g not in chemins_vus]
    assert manquantes == [], f"routes parametrees jamais sondees : {manquantes}"


def test_une_route_post_privee_de_sa_dependance_est_un_defaut_reel():
    """Sabotage direct : `dependencies=[Depends(verify_api_key)]` retiré de
    `/api/upload` doit produire un vrai `[DEFAUT]`, code 200 — la preuve que
    l'audit appelle désormais la vraie méthode POST avec un corps qui
    traverse la validation du fichier, au lieu d'un GET qui ne prouvait rien.
    """
    import importlib

    from apps.backend.routers import media as media_module

    route_originale = None
    for route in media_module.router.routes:
        if getattr(route, "path", None) == "/api/upload":
            route_originale = route
            break
    assert route_originale is not None, "route /api/upload introuvable"
    dependances_originales = list(route_originale.dependencies)

    try:
        route_originale.dependencies = []
        # Le graphe de dependances de FastAPI est deja construit a l'import :
        # reconstruire l'app pour que le retrait soit vraiment pris en compte.
        import apps.backend.main as main_module
        importlib.reload(main_module)

        import auditer_surface_publique as script
        importlib.reload(script)
        constats = script.auditer()
        upload = [c for c in constats if c.chemin == "/api/upload"]
        assert upload, "/api/upload doit etre sonde"
        assert upload[0].code == 200, "le corps minimal doit traverser la validation du fichier"
        assert upload[0].est_un_defaut is True, "une route sabotee doit etre un defaut reel"
    finally:
        route_originale.dependencies = dependances_originales
        importlib.reload(main_module)
        importlib.reload(script)


def test_le_corps_minimal_couvre_toutes_les_routes_qui_exigent_un_fichier():
    """Toute route dont la signature exige `File(...)`/`Form(...)` obligatoire
    a un corps dédié — sinon un corps vide échoue sur SA PROPRE validation
    (422) avant d'avoir pu dire quoi que ce soit sur l'authentification,
    masquant exactement le defaut que ce script existe pour trouver.
    """
    for gabarit in ("/api/upload", "/files", "/api/speech/transcribe", "/api/process-video"):
        assert gabarit in CORPS_MINIMAL, f"{gabarit} exige un fichier mais n'a pas de corps dedie"
