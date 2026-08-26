"""Empreinte de la surface HTTP d'ARENA.

Ce fichier est un **filet de sécurité pour le remaniement** de `main.py` : il fige
la liste des routes, leurs méthodes, et surtout les dépendances attachées à
chacune — c'est là que vivent l'authentification et la limitation de débit.

Déplacer du code ne doit rien changer ici. Si un de ces tests échoue après un
remaniement, c'est que le remaniement a modifié le comportement, pas seulement
l'organisation.
"""
import pytest
from fastapi.routing import APIRoute

from apps.backend import main

# Route → (méthodes, dépendances attendues, dans l'ordre de déclaration).
SURFACE_ATTENDUE = {
    "/": (["GET"], []),
    "/health": (["GET"], []),
    "/v1/models": (["GET"], ["verify_api_key"]),
    "/v1/chat/completions": (["POST"], ["verify_api_key", "limiter_debit"]),
    "/api/upload": (["POST"], ["verify_api_key"]),
    "/api/process-video": (["POST"], ["verify_api_key", "limiter_debit"]),
    "/api/chat": (["POST"], ["verify_api_key", "limiter_debit"]),
    "/api/chat/stream": (["POST"], ["verify_api_key", "limiter_debit"]),
}


def routes_declarees() -> dict:
    trouvees = {}
    for route in main.app.routes:
        if isinstance(route, APIRoute):
            dependances = [d.dependency.__name__ for d in route.dependencies]
            trouvees[route.path] = (sorted(route.methods - {"HEAD", "OPTIONS"}), dependances)
    return trouvees


def test_la_liste_des_routes_est_exactement_celle_attendue():
    assert sorted(routes_declarees()) == sorted(SURFACE_ATTENDUE)


@pytest.mark.parametrize("chemin", sorted(SURFACE_ATTENDUE))
def test_chaque_route_garde_ses_methodes_et_ses_dependances(chemin):
    methodes_attendues, dependances_attendues = SURFACE_ATTENDUE[chemin]
    methodes, dependances = routes_declarees()[chemin]

    assert methodes == methodes_attendues
    assert dependances == dependances_attendues


def test_toute_route_metier_exige_la_cle_api():
    """Aucune route `/api` ou `/v1` ne doit être atteignable sans authentification."""
    ouvertes = [
        chemin for chemin, (_, deps) in routes_declarees().items()
        if (chemin.startswith("/api") or chemin.startswith("/v1"))
        and "verify_api_key" not in deps
    ]

    assert ouvertes == [], f"routes metier sans authentification : {ouvertes}"


def test_toute_route_appelant_le_modele_est_limitee_en_debit():
    """Un appel au modèle occupe le GPU : aucune de ces routes ne doit être libre."""
    routes = routes_declarees()
    for chemin in ["/api/chat", "/api/chat/stream", "/v1/chat/completions", "/api/process-video"]:
        assert "limiter_debit" in routes[chemin][1], f"{chemin} n'est pas limitee"


def test_le_dossier_des_rendus_reste_servi():
    montages = [r.path for r in main.app.routes if r.path.startswith("/media")]

    assert "/media/rendered" in montages


def test_le_chemin_du_projet_est_pret_avant_tout_import_du_paquet():
    """Garantie donnée par Python, pas par l'ordre de tri des imports.

    `runtime.py` importe les agents ; sans la racine du dépôt dans `sys.path`,
    cet import échoue. Le placer dans `apps/backend/__init__.py` le fait
    exécuter en premier quoi qu'il arrive.
    """
    import sys

    from apps.backend import BASE_DIR

    assert str(BASE_DIR) in sys.path
    assert (BASE_DIR / "agents").is_dir()


def test_la_configuration_ne_cree_aucun_objet():
    """Un module de configuration qui instancie devient une dépendance de tout."""
    from apps.backend import config

    instances = [
        nom for nom, valeur in vars(config).items()
        if not nom.startswith("_")
        and hasattr(valeur, "__dict__")
        and not isinstance(valeur, type)
        and type(valeur).__module__.startswith(("agents", "core", "tools", "apps"))
    ]

    assert instances == [], f"config.py instancie : {instances}"


def test_les_objets_partages_ne_sont_crees_qu_une_fois():
    """Deux MemoryManager sur la même base, ou deux providers, seraient un défaut."""
    from apps.backend import main, runtime

    assert main.memory is runtime.memory
    assert main.fast_provider is runtime.fast_provider
    assert main.orchestrator is runtime.orchestrator
    assert main.fresh_agent is runtime.fresh_agent


def test_les_reglages_lus_dans_l_environnement_restent_accessibles():
    """Le remaniement ne doit pas faire disparaître un réglage."""
    for nom in [
        "ALLOWED_ORIGINS", "ARENA_API_KEY", "MEDIA_DIR", "RENDERED_DIR",
        "TAILLE_MAX_ENVOI", "TAILLE_BLOC_ENVOI", "EXTENSIONS_MEDIA_AUTORISEES",
        "REQUETES_MAX", "FENETRE_SECONDES", "AGENTS_SPECIALISES",
    ]:
        assert hasattr(main, nom), f"{nom} n'est plus accessible depuis apps.backend.main"


def test_les_agents_restent_accessibles():
    for nom in [
        "orchestrator", "coder_agent", "researcher_agent", "trend_agent",
        "video_agent", "editor_agent", "subtitle_agent", "clip_selector",
        "publisher_agent", "browser_agent", "repo_engineer", "swe_agent",
        "fresh_agent", "fast_provider", "deep_provider", "memory", "permissions",
    ]:
        assert hasattr(main, nom), f"{nom} n'est plus accessible depuis apps.backend.main"


def test_les_fonctions_partagees_restent_accessibles():
    for nom in [
        "verify_api_key", "limiter_debit", "validate_media_path", "client_de",
        "get_arena_system_prompt", "date_du_jour", "dispatch_request",
        "formater_sources", "valider_nom_de_fichier", "ecrire_par_blocs",
        "limiteur",
    ]:
        assert hasattr(main, nom), f"{nom} n'est plus accessible depuis apps.backend.main"
