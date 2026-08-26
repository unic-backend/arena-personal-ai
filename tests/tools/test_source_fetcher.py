"""Lecture d'une page web citée comme source.

Aucun test ne sort sur Internet : les réponses HTTP sont simulées par un
transport httpx, donc le vrai code de `fetch()` est exécuté de bout en bout.
"""
import functools

import httpx
import pytest

from tools.search.source_fetcher import SourceFetcher, adresse_interne, extraire_texte

PAGE = """<!doctype html>
<html><head>
  <title>Sortie de Python 3.14</title>
  <style>body { color: red; }</style>
  <script>var traqueur = 1;</script>
</head><body>
  <h1>Python 3.14 est disponible</h1>
  <p>La version    3.14 apporte le multi-interpr&eacute;teur.</p>
  <noscript>Activez JavaScript</noscript>
  <p>Deuxi&egrave;me paragraphe.</p>
</body></html>"""


# --- Extraction du texte -------------------------------------------------------

def test_le_texte_lisible_est_extrait():
    texte, _ = extraire_texte(PAGE)

    assert "Python 3.14 est disponible" in texte
    assert "Deuxième paragraphe." in texte


def test_les_scripts_et_styles_ne_sont_pas_du_texte():
    texte, _ = extraire_texte(PAGE)

    assert "var traqueur" not in texte
    assert "color: red" not in texte
    assert "Activez JavaScript" not in texte


def test_le_titre_de_la_page_est_recupere():
    _, titre = extraire_texte(PAGE)

    assert titre == "Sortie de Python 3.14"


def test_les_entites_html_sont_decodees():
    texte, _ = extraire_texte(PAGE)

    assert "multi-interpréteur" in texte
    assert "&eacute;" not in texte


def test_les_espaces_multiples_sont_reduits():
    texte, _ = extraire_texte(PAGE)

    assert "version 3.14" in texte
    assert "    " not in texte


def test_le_texte_brut_passe_tel_quel():
    texte, titre = extraire_texte("  ligne un\nligne deux  ", "text/plain")

    assert texte == "ligne un\nligne deux"
    assert titre is None


def test_une_page_mal_formee_ne_fait_pas_tomber_l_extraction():
    texte, _ = extraire_texte("<p>début <div><span>sans fermeture")

    assert "début" in texte


# --- Refus des adresses internes ----------------------------------------------

@pytest.mark.parametrize("hote", ["localhost", "127.0.0.1", "0.0.0.0", "169.254.1.1", "10.0.0.1"])
def test_une_adresse_locale_ou_privee_est_reconnue(hote):
    assert adresse_interne(hote) is True


def test_un_nom_irresolvable_est_traite_comme_interne():
    """On refuse ce qu'on ne peut pas vérifier, plutôt que de supposer."""
    assert adresse_interne("nom-qui-n-existe-pas.invalid") is True


def test_une_adresse_publique_est_acceptee(monkeypatch):
    monkeypatch.setattr(
        "tools.search.source_fetcher.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    assert adresse_interne("exemple.test") is False


# --- Requêtes simulées ---------------------------------------------------------

def lecteur_avec(reponse: httpx.Response, **options) -> SourceFetcher:
    """Fabrique un lecteur dont les requêtes HTTP renvoient `reponse`."""
    transport = httpx.MockTransport(lambda requete: reponse)
    outil = SourceFetcher(autoriser_adresses_internes=True, **options)
    return outil, transport


@pytest.fixture
def client_simule(monkeypatch):
    """Remplace le client httpx par un client branché sur un transport simulé."""
    def _installer(transport):
        monkeypatch.setattr(
            "tools.search.source_fetcher.httpx.AsyncClient",
            functools.partial(httpx.AsyncClient, transport=transport),
        )
    return _installer


async def test_une_page_lisible_est_rapportee_avec_son_texte(client_simule):
    outil, transport = lecteur_avec(
        httpx.Response(200, text=PAGE, headers={"content-type": "text/html; charset=utf-8"})
    )
    client_simule(transport)

    res = await outil.fetch("https://exemple.test/python-314")

    assert res["status"] == "FETCHED"
    assert res["title"] == "Sortie de Python 3.14"
    assert "Python 3.14 est disponible" in res["text"]
    assert res["truncated"] is False


async def test_une_erreur_http_est_signalee_pas_devinee(client_simule):
    outil, transport = lecteur_avec(httpx.Response(404, text="rien ici"))
    client_simule(transport)

    res = await outil.fetch("https://exemple.test/absent")

    assert res["status"] == "FAILED"
    assert "404" in res["reason"]
    assert res["text"] == ""


async def test_un_pdf_ou_une_image_est_refuse_faute_d_etre_lisible(client_simule):
    outil, transport = lecteur_avec(
        httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})
    )
    client_simule(transport)

    res = await outil.fetch("https://exemple.test/doc.pdf")

    assert res["status"] == "FAILED"
    assert "application/pdf" in res["reason"]


async def test_une_page_trop_longue_est_tronquee_et_le_dit(client_simule):
    longue = "<html><body>" + "<p>phrase de remplissage.</p>" * 2000 + "</body></html>"
    outil, transport = lecteur_avec(
        httpx.Response(200, text=longue, headers={"content-type": "text/html"}),
        caracteres_max=500,
    )
    client_simule(transport)

    res = await outil.fetch("https://exemple.test/longue")

    assert res["status"] == "FETCHED"
    assert res["truncated"] is True
    assert len(res["text"]) == 500


async def test_un_delai_depasse_est_rapporte(client_simule, monkeypatch):
    def expire(requete):
        raise httpx.ConnectTimeout("trop lent", request=requete)

    outil = SourceFetcher(autoriser_adresses_internes=True, delai_secondes=1)
    client_simule(httpx.MockTransport(expire))

    res = await outil.fetch("https://exemple.test/lente")

    assert res["status"] == "FAILED"
    assert "delai" in res["reason"].lower()


# --- Refus avant toute requête -------------------------------------------------

@pytest.mark.parametrize(
    "url, motif",
    [
        ("file:///etc/passwd", "schema"),
        ("ftp://exemple.test/x", "schema"),
        ("javascript:alert(1)", "schema"),
        ("pas une url", "schema"),
    ],
)
async def test_un_schema_non_web_est_refuse(url, motif):
    res = await SourceFetcher().fetch(url)

    assert res["status"] == "REFUSED"
    assert motif in res["reason"]


async def test_une_adresse_interne_est_refusee_sans_requete(client_simule):
    """Les URL viennent d'un moteur de recherche : elles ne sont pas de confiance."""
    def ne_doit_pas_etre_appele(requete):
        raise AssertionError("une requête a été envoyée vers une adresse interne")

    client_simule(httpx.MockTransport(ne_doit_pas_etre_appele))

    res = await SourceFetcher().fetch("http://127.0.0.1:8000/api/chat")

    assert res["status"] == "REFUSED"
    assert "interne" in res["reason"]
