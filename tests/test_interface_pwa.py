"""L'interface servie sur `/` : la PWA quand elle est compilee, l'ancienne sinon.

`apps/pwa/dist/` est ignore par Git. Un depot fraichement clone ne contient donc
pas la PWA compilee, et servir un chemin absent rendrait une page blanche sans
dire pourquoi. Ces tests tiennent les deux cas, et le fait que `/health` annonce
laquelle repond.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def pwa_compilee(tmp_path, monkeypatch):
    """Simule une PWA compilee, sans dependre de l'etat du poste."""
    fichier = tmp_path / "index.html"
    fichier.write_text("<html><body>PWA ARENA</body></html>", encoding="utf-8")
    monkeypatch.setattr(main, "INTERFACE_PWA", fichier)
    return fichier


@pytest.fixture
def pwa_absente(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "INTERFACE_PWA", tmp_path / "jamais_compilee.html")


# --- La PWA prend la place quand elle existe ----------------------------------

def test_la_pwa_compilee_est_servie_sur_la_racine(client, pwa_compilee):
    res = client.get("/")

    assert res.status_code == 200
    assert "PWA ARENA" in res.text


def test_l_interface_servie_est_la_pwa_quand_elle_existe(pwa_compilee):
    assert main.interface_servie() == pwa_compilee
    assert main.nom_interface() == "pwa"


# --- L'ancienne repond quand la PWA n'est pas compilee ------------------------

def test_sans_pwa_compilee_l_ancienne_interface_repond(client, pwa_absente):
    """Un depot fraichement clone doit rester utilisable."""
    res = client.get("/")

    assert res.status_code == 200
    assert res.text.strip() != ""


def test_l_interface_servie_retombe_sur_la_classique(pwa_absente):
    assert main.interface_servie() == main.INTERFACE_CLASSIQUE
    assert main.nom_interface() == "classique"


# --- L'ancienne n'est jamais perdue -------------------------------------------

def test_l_ancienne_interface_reste_joignable_meme_avec_la_pwa(client, pwa_compilee):
    """Retirer ce qui marche pour installer ce qui est neuf n'est pas un progres."""
    res = client.get("/ui/classique")

    assert res.status_code == 200
    assert "PWA ARENA" not in res.text


def test_l_ancienne_interface_existe_bien_dans_le_depot():
    assert main.INTERFACE_CLASSIQUE.exists()


# --- /health dit laquelle repond, sans deviner --------------------------------

def test_health_annonce_la_pwa(client, pwa_compilee):
    assert client.get("/health").json()["interface"] == "pwa"


def test_health_annonce_la_classique(client, pwa_absente):
    """Une interface manquante est un etat annonce, pas une panne silencieuse."""
    assert client.get("/health").json()["interface"] == "classique"


def test_le_chemin_de_la_pwa_est_celui_que_vite_produit():
    """`vite build` ecrit dans `dist/` : le serveur regarde exactement la."""
    assert main.INTERFACE_PWA.parts[-3:] == ("pwa", "dist", "index.html")


# --- La PWA n'a besoin de rien d'autre ----------------------------------------

def test_la_pwa_est_servie_telle_quelle_sans_assets(client, pwa_compilee):
    """`vite-plugin-singlefile` inline tout : un seul fichier suffit."""
    res = client.get("/")

    assert res.headers["content-type"].startswith("text/html")
    assert res.text == pwa_compilee.read_text(encoding="utf-8")


# --- Les fichiers que Vite ne peut pas inliner --------------------------------

@pytest.fixture
def dist_complet(tmp_path, monkeypatch):
    """Un `dist/` comme Vite le produit : l'index inline, le reste a cote."""
    dist = tmp_path / "dist"
    (dist / "icons").mkdir(parents=True)
    (dist / "index.html").write_text("<html>PWA ARENA</html>", encoding="utf-8")
    (dist / "sw.js").write_text("self.addEventListener('install', () => {});", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name":"Usman"}', encoding="utf-8")
    (dist / "offline.html").write_text("<html>hors ligne</html>", encoding="utf-8")
    (dist / "icons" / "usman.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("NE DOIT JAMAIS SORTIR", encoding="utf-8")
    monkeypatch.setattr(main, "INTERFACE_PWA", dist / "index.html")
    return dist


@pytest.mark.parametrize("chemin,attendu", [
    ("/sw.js", "addEventListener"),
    ("/manifest.webmanifest", "Usman"),
    ("/offline.html", "hors ligne"),
])
def test_les_fichiers_pwa_sont_servis(client, dist_complet, chemin, attendu):
    res = client.get(chemin)

    assert res.status_code == 200
    assert attendu in res.text


def test_le_service_worker_est_servi_depuis_la_racine(client, dist_complet):
    """Sa portee est celle du chemin d'ou il vient. Depuis /static/, il ne
    controlerait que /static/ — c'est-a-dire rien d'utile."""
    assert client.get("/sw.js").status_code == 200


def test_une_icone_est_servie(client, dist_complet):
    res = client.get("/icons/usman.svg")

    assert res.status_code == 200
    assert "<svg/>" in res.text


@pytest.mark.parametrize("nom", ["../secret.txt", "../../secret.txt", "../../../etc/passwd"])
async def test_aucune_icone_ne_sort_de_son_dossier(dist_complet, nom):
    """Sans verification, `../../.env` serait un nom d'icone valide.

    Ce test appelle la fonction **directement**. Une version passant par
    `client.get("/icons/../secret.txt")` passait deja avant que le garde-fou
    existe : Starlette normalise le chemin avant le routage, la requete
    devenait `/secret.txt` et tombait en 404 sans jamais atteindre la fonction.
    Elle passait pour la mauvaise raison — mesure le 2026-08-27 en sabotant le
    garde-fou sans qu'aucun test n'echoue.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refus:
        await main.servir_icone_pwa(nom)

    assert refus.value.status_code == 403


async def test_une_icone_legitime_passe_le_garde_fou(dist_complet):
    """Le garde-fou refuse la traversee, pas les icones."""
    reponse = await main.servir_icone_pwa("usman.svg")

    assert reponse.path.endswith("usman.svg")


def test_le_secret_voisin_ne_sort_par_aucune_url(client, dist_complet):
    """Defense en profondeur : meme normalise par le serveur, rien ne fuit."""
    for chemin in ("/icons/../secret.txt", "/secret.txt", "/icons/%2e%2e/secret.txt"):
        assert "NE DOIT JAMAIS SORTIR" not in client.get(chemin).text


def test_une_icone_absente_rend_404(client, dist_complet):
    assert client.get("/icons/jamais-creee.png").status_code == 404


@pytest.mark.parametrize("chemin", ["/sw.js", "/manifest.webmanifest", "/offline.html"])
def test_sans_pwa_compilee_les_fichiers_disent_pourquoi(client, pwa_absente, chemin):
    """404 avec la raison, pas une page blanche."""
    res = client.get(chemin)

    assert res.status_code == 404
    assert "npm run build" in res.json()["detail"]


def test_la_pwa_du_depot_a_bien_ses_fichiers_sources():
    """Ils existent dans `apps/pwa/public/` : Vite les copiera dans `dist/`."""
    public = main.BASE_DIR / "apps" / "pwa" / "public"

    for nom in ("sw.js", "manifest.webmanifest", "offline.html"):
        assert (public / nom).is_file(), f"{nom} manquant dans apps/pwa/public/"
    assert (public / "icons").is_dir()
