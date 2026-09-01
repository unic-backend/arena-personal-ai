"""L'interface doit fonctionner sans Internet.

Le projet se revendique local-first (`DEC-0002`). Le tableau de bord chargeait
pourtant sa mise en forme depuis un CDN : sans connexion, il s'affichait sans
style. Mesuré le 26/08/2026 dans un vrai navigateur, réseau externe coupé :
l'en-tête faisait 137,875 px au lieu de 64, et le corps n'était plus en flex.
"""
import hashlib
import os
import re
import threading
import time

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend.config import BASE_DIR

INDEX = BASE_DIR / "apps" / "frontend" / "index.html"
VENDOR = BASE_DIR / "apps" / "frontend" / "vendor"
PROVENANCE = VENDOR / "PROVENANCE.md"


# --- Aucune dépendance réseau -------------------------------------------------

def test_l_interface_ne_reference_aucune_adresse_externe():
    externes = re.findall(r'(?:src|href)="(https?://[^"]+)"', INDEX.read_text(encoding="utf-8"))

    assert externes == [], f"l'interface depend encore de : {externes}"


def test_la_mise_en_forme_est_servie_localement():
    contenu = INDEX.read_text(encoding="utf-8")

    assert 'src="/static/tailwind.js"' in contenu
    assert "cdn.tailwindcss.com" not in contenu


def test_le_fichier_embarque_est_present_et_non_vide():
    fichier = VENDOR / "tailwind.js"

    assert fichier.exists()
    assert fichier.stat().st_size > 100_000, "un fichier tronque casserait la mise en forme"


# --- Provenance ----------------------------------------------------------------

def test_le_fichier_tiers_declare_son_origine():
    """Un fichier qu'on n'a pas écrit doit dire d'où il vient."""
    assert PROVENANCE.exists()
    texte = PROVENANCE.read_text(encoding="utf-8")

    assert "cdn.tailwindcss.com" in texte
    assert "MIT" in texte


def test_l_empreinte_declaree_correspond_au_fichier_reel():
    """Sinon la provenance ne prouve rien : n'importe quel fichier pourrait être là."""
    declaree = re.search(r"SHA-256 \| `([0-9a-f]{64})`", PROVENANCE.read_text(encoding="utf-8"))
    assert declaree, "aucune empreinte declaree dans PROVENANCE.md"

    reelle = hashlib.sha256((VENDOR / "tailwind.js").read_bytes()).hexdigest()

    assert reelle == declaree.group(1), (
        "le fichier embarque ne correspond plus a l'empreinte declaree ; "
        "mettre PROVENANCE.md a jour apres tout remplacement"
    )


def test_la_taille_declaree_correspond_au_fichier_reel():
    declaree = re.search(r"Taille \| ([0-9]+) octets", PROVENANCE.read_text(encoding="utf-8"))
    assert declaree

    assert (VENDOR / "tailwind.js").stat().st_size == int(declaree.group(1))


# --- Le backend le sert-il vraiment ? -----------------------------------------

@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def test_le_backend_sert_le_fichier_de_mise_en_forme(client):
    reponse = client.get("/static/tailwind.js")

    assert reponse.status_code == 200
    assert "javascript" in reponse.headers["content-type"]
    assert len(reponse.content) > 100_000


def test_la_page_servie_ne_pointe_pas_vers_l_exterieur(client):
    assert "cdn.tailwindcss.com" not in client.get("/").text


# --- Rendu réel dans un navigateur --------------------------------------------

@pytest.fixture
def navigateur():
    pytest.importorskip("playwright", reason="playwright n'est pas installe.")
    from playwright.sync_api import sync_playwright

    chemins = list(BASE_DIR.parent.glob("**/chrome-linux/chrome"))
    for candidat in ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome", *map(str, chemins)]:
        if os.path.exists(candidat):
            break
    else:
        pytest.skip("Aucun navigateur Chromium disponible.")

    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=candidat, args=["--no-sandbox"])
        yield nav
        nav.close()


@pytest.fixture
def serveur_local():
    # Meme regle que `modele_whisper_disponible` : une dependance optionnelle
    # absente se SAUTE, elle ne fait pas erreur au montage de la fixture.
    try:
        import uvicorn
    except ImportError:
        pytest.skip("uvicorn n'est pas installe sur cette machine.")

    port = 8937
    serveur = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=serveur.run, daemon=True).start()
    for _ in range(60):
        if serveur.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    serveur.should_exit = True


@pytest.mark.integration
def test_la_mise_en_forme_s_applique_sans_acces_a_internet(navigateur, serveur_local):
    """Toute requête sortant vers Internet est bloquée : si le style tient, il est local."""
    page = navigateur.new_page()
    sorties = []

    def filtrer(route, requete):
        if requete.url.startswith(serveur_local):
            route.continue_()
        else:
            sorties.append(requete.url)
            route.abort()

    page.route("**/*", filtrer)
    page.goto(serveur_local + "/", wait_until="networkidle")
    page.wait_for_timeout(1200)

    hauteur = page.locator("header").first.evaluate("e => getComputedStyle(e).height")
    affichage = page.evaluate("getComputedStyle(document.body).display")
    charge = page.evaluate("typeof window.tailwind !== 'undefined'")
    page.close()

    assert sorties == [], f"la page sort encore vers : {sorties}"
    assert hauteur == "64px", f"la classe h-16 n'est pas appliquee (hauteur : {hauteur})"
    assert affichage == "flex"
    assert charge is True
