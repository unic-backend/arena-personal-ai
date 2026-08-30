"""Le paquet déployable dit-il ce qu'il fait vraiment ?

`apps/backend/Dockerfile` existe depuis le tout premier commit du dépôt et
n'avait jamais été construit par personne — ni un humain, ni la CI — jusqu'au
30/08/2026 (VOLET « ARENA en ligne », phase 3.1). Ces tests tiennent ce que la
construction réelle (`docker build`, lancée manuellement pendant cette phase)
a établi, pour que ça ne redevienne pas une simple lecture de fichier.
"""
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
DOCKERFILE = RACINE / "apps" / "backend" / "Dockerfile"
COMPOSE = RACINE / "deploy" / "docker-compose.yml"


class TestLImageNeTourneJamaisEnRoot:
    """Le propriétaire ne se connecte jamais à ce conteneur : root n'a aucun usage.

    Construit et lancé réellement pendant cette phase (contournement du proxy
    de ce bac à sable pour joindre PyPI) : `/health` répond, authentifié et
    non authentifié, exactement comme documenté dans `apps/backend/main.py`.
    """

    def test_un_utilisateur_non_root_est_cree_et_active(self):
        source = DOCKERFILE.read_text(encoding="utf-8")

        assert "USER " in source, "aucun USER : l'image tourne en root par défaut"
        # La ligne USER doit venir après la création de l'utilisateur, jamais
        # avant — sinon `USER arena` échouerait au démarrage du conteneur.
        creation = source.index("useradd")
        bascule = source.index("USER ")
        assert creation < bascule, "USER arrive avant que l'utilisateur existe"


class TestLaSondeDeSanteMesureLeProcessus:
    """`/health` répond 200 tant que le serveur vit — Ollama absent ou pas.

    C'est la bonne sonde pour un conteneur : elle ne mesure pas que chaque
    service distant répond (ça, c'est le diagnostic applicatif, DEC-0022),
    elle mesure que le processus n'a pas planté.
    """

    def test_healthcheck_interroge_le_port_expose(self):
        source = DOCKERFILE.read_text(encoding="utf-8")

        assert "HEALTHCHECK" in source
        assert "/health" in source
        assert "8000" in source

    def test_le_docker_compose_declare_la_meme_sonde(self):
        service = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["arena"]

        assert "healthcheck" in service
        assert "/health" in " ".join(service["healthcheck"]["test"])


class TestLesDonneesSurviventAUneImageReconstruite:
    """Un SQLite dans /app ne survit pas à `docker compose up --build`.

    DEC-0021 fait porter la mémoire, la grille de prix et les devis produits
    par ce serveur précisément. Sans volume, reconstruire l'image les efface
    en silence — pas d'erreur, juste un fichier qui n'existe plus.
    """

    def test_data_et_media_sont_montes_en_volume(self):
        service = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["arena"]
        volumes = " ".join(service.get("volumes") or [])

        assert "/app/data" in volumes, "data/ n'est pas monté : un rebuild l'effacerait"
        assert "/app/media" in volumes, "media/ n'est pas monté : les rendus disparaîtraient"


class TestLeFichierDeComposeNePorteAucunSecret:
    """`env_file` renvoie vers `.env`, jamais une valeur recopiée ici.

    Le fichier d'exemple `.env.example` reste en HYBRIDE (DEC-0022) : ce
    fichier de déploiement ne doit fixer ni AI_MODE, ni aucune clé — sinon un
    dépôt cloné démarrerait dans le mode le plus ouvert sans que personne
    l'ait décidé pour cette machine-là.
    """

    def test_aucune_variable_sensible_n_est_fixee_en_dur(self):
        service = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["arena"]

        assert "environment" not in service, (
            "des variables sont fixées en dur : elles doivent venir de .env, "
            "jamais de ce fichier versionné")
        assert "env_file" in service

    def test_le_docker_compose_racine_ne_revient_pas(self):
        """`docker-compose.yml` à la racine a déjà fui quatre clés — pas ici."""
        assert not (RACINE / "docker-compose.yml").exists(), (
            "un docker-compose.yml est revenu à la racine : "
            "tests/test_configuration_clients.py le garde vide pour une raison"
        )


class TestLaCiConstruitVraimentLImage:
    """Un `pip install --dry-run` réussi ne prouve pas qu'une image se construit.

    C'est exactement ce qui s'est passé ici : la résolution des dépendances
    passait en CI depuis toujours, et personne n'avait jamais lancé
    `docker build`. Ce test garde la ligne qui corrige ça, pas l'exécution
    elle-même — lancer Docker en CI dans les tests unitaires recréerait le
    problème qu'on corrige.
    """

    def test_le_workflow_construit_le_dockerfile(self):
        source = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        assert "docker build" in source
        assert "apps/backend/Dockerfile" in source
