"""Un modèle déclaré mais absent doit se voir au démarrage, pas au premier message.

Trois fichiers déclarent un nom de modèle et aucun ne vérifiait qu'il existe.
Un tag absent se manifestait par une erreur d'Ollama au premier message, que
rien ne reliait à sa cause.

Ces tests ne touchent jamais le réseau : le client HTTP est doublé.
"""
import logging

import httpx
import pytest

from apps.backend.verification_modeles import (
    ABSENT,
    INCONNU,
    PRESENT,
    modeles_installes,
    verifier_modeles,
)

BASE = "http://127.0.0.1:11434"


def _transport(reponse):
    """Rend un transport httpx qui répond toujours la même chose."""
    def repondre(requete: httpx.Request) -> httpx.Response:
        if callable(reponse):
            return reponse(requete)
        return reponse
    return httpx.MockTransport(repondre)


@pytest.fixture
def ollama(monkeypatch):
    """Remplace le client httpx par un double, sans toucher au réseau."""
    def _installer(reponse):
        vrai_client = httpx.AsyncClient

        def fabrique(*args, **kw):
            kw["transport"] = _transport(reponse)
            return vrai_client(*args, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", fabrique)
    return _installer


def _liste(*noms):
    return httpx.Response(200, json={"models": [{"name": n} for n in noms]})


class TestLectureDesModelesInstalles:
    async def test_les_tags_installes_sont_rendus(self, ollama):
        ollama(_liste("qwen3.5:9b", "qwen2.5-coder:14b"))
        assert await modeles_installes(BASE) == {"qwen3.5:9b", "qwen2.5-coder:14b"}

    async def test_ollama_injoignable_rend_none_et_pas_un_ensemble_vide(self, ollama):
        """« Je n'ai pas pu regarder » n'est pas « il n'y a rien »."""
        def tombe(requete):
            raise httpx.ConnectError("connection refused")

        ollama(tombe)
        assert await modeles_installes(BASE) is None

    async def test_une_reponse_en_erreur_rend_none(self, ollama):
        ollama(httpx.Response(500, text="boom"))
        assert await modeles_installes(BASE) is None

    async def test_une_liste_vide_reste_une_liste_vide(self, ollama):
        """Ollama démarré sans aucun modèle : mesuré, pas inconnu."""
        ollama(_liste())
        assert await modeles_installes(BASE) == set()


class TestEtatDesModelesDeclares:
    async def test_un_modele_installe_est_present(self, ollama):
        ollama(_liste("qwen3.5:9b"))
        assert await verifier_modeles(["qwen3.5:9b"], BASE) == {"qwen3.5:9b": PRESENT}

    async def test_un_modele_absent_est_signale(self, ollama):
        ollama(_liste("qwen2.5-coder:14b"))
        etats = await verifier_modeles(["qwen3.5:9b", "qwen2.5-coder:14b"], BASE)

        assert etats["qwen3.5:9b"] == ABSENT
        assert etats["qwen2.5-coder:14b"] == PRESENT

    async def test_ollama_eteint_ne_declare_aucun_modele_absent(self, ollama):
        """Le piège : annoncer « modèle manquant » alors qu'Ollama est éteint."""
        def tombe(requete):
            raise httpx.ConnectError("connection refused")

        ollama(tombe)
        etats = await verifier_modeles(["qwen3.5:9b"], BASE)

        assert etats == {"qwen3.5:9b": INCONNU}
        assert ABSENT not in etats.values()

    async def test_un_nom_sans_tag_vaut_latest(self, ollama):
        ollama(_liste("llama3:latest"))
        assert await verifier_modeles(["llama3"], BASE) == {"llama3": PRESENT}

    async def test_un_modele_declare_deux_fois_n_est_verifie_qu_une_fois(self, ollama):
        ollama(_liste("qwen3.5:9b"))
        etats = await verifier_modeles(["qwen3.5:9b", "qwen3.5:9b"], BASE)
        assert etats == {"qwen3.5:9b": PRESENT}


class TestJournalisation:
    async def test_l_absence_est_journalisee_avec_la_commande_pour_la_corriger(self, ollama, caplog):
        ollama(_liste("autre:7b"))

        with caplog.at_level(logging.ERROR, logger="usman.modeles"):
            await verifier_modeles(["qwen3.5:9b"], BASE)

        assert "qwen3.5:9b" in caplog.text
        assert "ollama pull" in caplog.text

    async def test_ollama_eteint_journalise_un_avertissement_pas_une_erreur(self, ollama, caplog):
        def tombe(requete):
            raise httpx.ConnectError("connection refused")

        ollama(tombe)
        with caplog.at_level(logging.WARNING, logger="usman.modeles"):
            await verifier_modeles(["qwen3.5:9b"], BASE)

        assert "non verifiee" in caplog.text
        assert "ollama pull" not in caplog.text


class TestLeDemarrageNeBloqueJamais:
    async def test_une_panne_ne_leve_aucune_exception(self, ollama):
        """Un serveur qui refuse de démarrer est moins utile qu'un serveur qui prévient."""
        def tombe(requete):
            raise httpx.ReadTimeout("operation timed out")

        ollama(tombe)
        assert await verifier_modeles(["a", "b"], BASE) == {"a": INCONNU, "b": INCONNU}

    async def test_une_reponse_illisible_ne_leve_rien(self, ollama):
        ollama(httpx.Response(200, text="ceci n'est pas du json"))
        assert await verifier_modeles(["a"], BASE) == {"a": INCONNU}
