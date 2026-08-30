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
ENTRYPOINT = RACINE / "apps" / "backend" / "entrypoint.sh"
COMPOSE = RACINE / "deploy" / "docker-compose.yml"


class TestLImageNeTourneJamaisEnRootUneFoisDemarree:
    """Le propriétaire ne se connecte jamais à ce conteneur : root n'a aucun usage.

    D'abord construite avec un `USER arena` fixe dans le Dockerfile — et ça
    cassait au premier démarrage sur un volume monté depuis l'hôte : un volume
    arrive root:root, `USER arena` ne peut plus rien y écrire, et
    `PermissionError: /app/data/rag` tuait le conteneur avant même que
    `/health` réponde. Reproduit et corrigé pendant cette phase.

    `entrypoint.sh` corrige les permissions du volume **avant** de passer la
    main, et `gosu` — jamais `sudo` — ne permet aucun retour à root ensuite.
    Vérifié en rejouant le scénario exact : conteneur démarré sur un volume
    root:root fraîchement créé, `docker exec ... ls -la /app/data` montrant
    `arena arena`, `/health` répondant authentifié et non authentifié.
    """

    def test_le_conteneur_ne_demarre_plus_directement_en_utilisateur_fixe(self):
        source = DOCKERFILE.read_text(encoding="utf-8")

        # Le proprietaire du volume ne peut etre corrige qu'AVANT le
        # changement d'utilisateur : un `USER arena` fixe dans le Dockerfile
        # rendrait `entrypoint.sh` incapable de faire le chown en premier.
        assert "\nUSER " not in source, (
            "USER est fixe dans le Dockerfile : entrypoint.sh ne pourra plus "
            "corriger les permissions d'un volume avant de lacher les privileges")

    def test_l_entree_corrige_les_permissions_puis_bascule_sans_retour(self):
        # Le code executable seulement : le prologue en prose nomme `gosu`
        # avant `chown` a plusieurs reprises pour l'expliquer, ce qui fausserait
        # une recherche sur le fichier entier.
        code = ENTRYPOINT.read_text(encoding="utf-8").split("set -e", 1)[-1]

        chown = code.index("chown")
        bascule = code.index("gosu")
        assert chown < bascule, "les permissions doivent etre corrigees avant de lacher root"
        assert "sudo " not in code, (
            "sudo permettrait un retour a root : gosu ne le permet pas, c'est voulu")

    def test_le_dockerfile_reference_bien_cet_entrypoint(self):
        source = DOCKERFILE.read_text(encoding="utf-8")

        assert "entrypoint.sh" in source
        assert "chmod +x" in source, "sans ça, l'entrypoint n'est pas executable au demarrage"


class TestLaCiVerifieLePermissionDuVolume:
    """Le bug du test ci-dessus n'était visible qu'avec un vrai volume monté.

    `docker build` seul ne le voit jamais : c'est exactement pourquoi il a
    fallu construire et LANCER l'image avec un volume pour le trouver. La CI
    rejoue ce lancement à chaque build, sans démarrer uvicorn.
    """

    def test_le_workflow_lance_l_image_sur_un_volume_root(self):
        source = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        assert "entrypoint.sh" in source
        assert "docker run" in source


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
