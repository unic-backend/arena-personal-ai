"""Où joindre la machine du propriétaire, quand elle tourne.

**Le problème, en une phrase.** Son PC publie ARENA par un tunnel
`trycloudflare`, qui tire un nom au hasard **à chaque démarrage**. Il devait
recopier une nouvelle adresse dans son téléphone chaque fois qu'il allumait sa
machine — pour un PC qui tourne environ quatre heures par jour.

Le montage : le téléphone ne connaît qu'**une seule adresse**, celle du
serveur permanent. Le PC y dépose l'adresse du jour ; le téléphone la demande
et parle **directement** au PC. Rien ne transite par le serveur permanent
quand la machine répond — c'est ce qui distingue ce montage d'un relais.

La garde la moins évidente est celle de la péremption, et c'est la plus
importante : **`trycloudflare` recycle ses noms.** Une adresse vieille de
plusieurs jours peut appartenir à un inconnu, à qui le téléphone présenterait
sa clé.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.reseau.adresse_machine import DUREE_DE_VIE, AdresseMachine


@pytest.fixture
def magasin(tmp_path):
    return AdresseMachine(tmp_path / "machine.json")


def test_la_duree_de_vie_vaut_douze_heures():
    """**La constante est epinglee, pas seulement utilisee.**

    Le test de peremption calculait son horodatage a partir de
    `DUREE_DE_VIE` : passer la constante a dix ans elargissait le test dans le
    meme mouvement, et les dix-huit tests restaient verts alors que la
    peremption n'existait plus. C'est la garde la plus importante du module —
    `trycloudflare` recycle ses noms, et une adresse perimee peut appartenir a
    un inconnu a qui le telephone presenterait la cle.

    Mesure le 04/09/2026 : sabotage `DUREE_DE_VIE = timedelta(days=3650)`
    -> 18 tests passes. Avec cette garde, il en tombe deux.
    """
    assert DUREE_DE_VIE == timedelta(hours=12)


class TestAnnonce:
    def test_avant_toute_annonce_on_ne_sait_pas(self, magasin):
        """`None`, jamais une adresse inventee ni un `localhost` par defaut."""
        assert magasin.derniere() is None

    def test_une_annonce_se_relit(self, magasin):
        magasin.annoncer("https://abc.trycloudflare.com", "PC de Saer")
        derniere = magasin.derniere()

        assert derniere["adresse"] == "https://abc.trycloudflare.com"
        assert derniere["machine"] == "PC de Saer"

    def test_la_barre_finale_est_retiree(self, magasin):
        """Le telephone colle cette adresse a `/health` : une barre en trop
        donnerait `//health`, que certains serveurs refusent."""
        magasin.annoncer("https://abc.trycloudflare.com/")

        assert magasin.derniere()["adresse"] == "https://abc.trycloudflare.com"

    @pytest.mark.parametrize("mauvaise", [
        "", "   ", "pas-une-url", "ftp://abc.test", "abc.trycloudflare.com",
        "javascript:alert(1)",
    ])
    def test_une_adresse_douteuse_est_refusee_a_lecriture(self, magasin, mauvaise):
        """**Refusee a l'ecriture, pas a la lecture.** Servie plus tard, elle
        enverrait le telephone n'importe ou — et `javascript:` dans un champ
        que l'interface pourrait suivre est une porte ouverte."""
        with pytest.raises(ValueError):
            magasin.annoncer(mauvaise)

        assert magasin.derniere() is None


class TestPeremption:
    def test_une_annonce_trop_vieille_nest_plus_servie(self, magasin, tmp_path):
        """**La garde qui compte.**

        `trycloudflare` recycle ses noms : une adresse de la semaine derniere
        peut etre celle d'un inconnu aujourd'hui, et le telephone y
        presenterait la cle du proprietaire. Mieux vaut retomber sur le
        serveur permanent que parler a une machine dont on ne sait plus rien.
        """
        magasin.annoncer("https://abc.trycloudflare.com")
        fichier = tmp_path / "machine.json"
        vieux = datetime.now(timezone.utc) - timedelta(hours=13)
        contenu = fichier.read_text(encoding="utf-8")
        import json
        annonce = json.loads(contenu)
        annonce["annonce_le"] = vieux.isoformat()
        fichier.write_text(json.dumps(annonce), encoding="utf-8")

        assert magasin.derniere() is None

    def test_une_annonce_recente_est_servie(self, magasin):
        magasin.annoncer("https://abc.trycloudflare.com")

        assert magasin.derniere() is not None
        assert magasin.derniere()["age_secondes"] < 5

    def test_un_fichier_illisible_ne_leve_pas(self, tmp_path):
        """Trois causes, une seule reponse honnete : « je ne sais pas ou elle
        est ». Lever ici casserait le demarrage du telephone."""
        fichier = tmp_path / "machine.json"
        fichier.write_text("{ ceci n'est pas du json", encoding="utf-8")

        assert AdresseMachine(fichier).derniere() is None

    def test_oublier_ramene_au_serveur_permanent(self, magasin):
        magasin.annoncer("https://abc.trycloudflare.com")
        magasin.oublier()

        assert magasin.derniere() is None


class TestRoutes:
    """La chaîne complète, par HTTP, avec la clé."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        """La cle est posee sur le module de securite, **jamais** par
        `setenv` : `USMAN_API_KEY` y est une constante lue une seule fois, a
        l'import. Une variable d'environnement posee apres cet import n'atteint
        rien — et comme l'import a lieu au premier test qui touche l'API, la
        fixture passait seule et echouait dans la suite complete, ce qui est la
        pire des deux facons d'echouer. C'est la convention deja suivie par
        `test_connectors_router.py` et `test_conversations.py`.
        """
        from apps.backend import security
        monkeypatch.setattr(security, "USMAN_API_KEY", "cle-de-test")

        from apps.backend.routers import pwa_gateway
        monkeypatch.setattr(pwa_gateway, "_ADRESSE_MACHINE",
                            AdresseMachine(tmp_path / "m.json"))

        from fastapi.testclient import TestClient

        from apps.backend.main import app
        return TestClient(app)

    def test_annoncer_puis_demander(self, client):
        entete = {"Authorization": "Bearer cle-de-test"}

        assert client.get("/machine/adresse", headers=entete).json() == {"presente": False}
        client.post("/machine/adresse", headers=entete,
                    json={"adresse": "https://abc.trycloudflare.com", "machine": "PC"})
        reponse = client.get("/machine/adresse", headers=entete).json()

        assert reponse["presente"] is True
        assert reponse["adresse"] == "https://abc.trycloudflare.com"

    def test_ecrire_exige_la_cle(self, client):
        """**Sans elle, n'importe qui ferait pointer son telephone vers une
        machine choisie par un autre.**"""
        reponse = client.post("/machine/adresse",
                              json={"adresse": "https://pirate.test"})

        assert reponse.status_code == 401

    def test_lire_exige_la_cle(self, client):
        assert client.get("/machine/adresse").status_code == 401

    def test_une_adresse_folle_est_refusee_par_la_route(self, client):
        reponse = client.post("/machine/adresse",
                              headers={"Authorization": "Bearer cle-de-test"},
                              json={"adresse": "javascript:alert(1)"})

        assert reponse.status_code == 400


def test_les_deux_routes_sont_dans_lempreinte_de_lapi():
    """Une route absente de l'empreinte passerait sans que personne ne la
    relise — et celle-ci decide vers quelle machine part le telephone."""
    surface = (Path(__file__).resolve().parent / "test_surface_api.py").read_text(encoding="utf-8")

    assert '"/machine/adresse"' in surface
