import pytest

from tools.search.page_context import CARACTERES_CONTEXTE_MAX, LecteurContextePage


class FauxFetcher:
    def __init__(self, resultat):
        self.resultat = resultat

    async def fetch(self, url):
        self.url = url
        return self.resultat


@pytest.mark.asyncio
async def test_contexte_garde_url_titre_provenance_et_marque_externe():
    fetcher = FauxFetcher({
        "status": "FETCHED", "url": "https://example.test/article",
        "title": "Article", "text": "fait mesure", "truncated": False,
        "characters": 11,
    })
    resultat = await LecteurContextePage(fetcher=fetcher).lire(
        "https://example.test/article")

    assert resultat["status"] == "READY"
    assert resultat["provenance"] == "https://example.test/article"
    assert resultat["titre"] == "Article"
    assert "fait mesure" in resultat["texte"]
    assert resultat["confiance"] == "external"


@pytest.mark.asyncio
async def test_contexte_est_borne_sans_perdre_le_signal_tronque():
    fetcher = FauxFetcher({
        "status": "FETCHED", "url": "https://example.test/long",
        "title": None, "text": "x" * (CARACTERES_CONTEXTE_MAX + 500),
        "truncated": False, "characters": CARACTERES_CONTEXTE_MAX + 500,
    })
    resultat = await LecteurContextePage(fetcher=fetcher).lire(
        "https://example.test/long")

    assert resultat["tronque"] is True
    assert len(resultat["texte"]) < CARACTERES_CONTEXTE_MAX + 1000


@pytest.mark.asyncio
async def test_refus_source_est_transmis_sans_inventer_de_contenu():
    fetcher = FauxFetcher({
        "status": "REFUSED", "url": "http://127.0.0.1",
        "reason": "adresse interne", "text": "",
    })
    resultat = await LecteurContextePage(fetcher=fetcher).lire(
        "http://127.0.0.1")

    assert resultat == {
        "status": "REFUSED", "url": "http://127.0.0.1",
        "reason": "adresse interne",
    }
