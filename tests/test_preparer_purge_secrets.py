"""Le script de préparation de la purge trouve-t-il bien les secrets, et rien d'autre ?

Un script qui rate un secret laisse la fuite en place ; un script qui prend une
référence `${VAR}` pour un secret réécrirait l'historique pour rien.
"""
import importlib.util
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "preparer_purge_secrets", RACINE / "scripts" / "preparer_purge_secrets.py"
)
purge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(purge)


# Valeurs inventées, de la même forme que celles trouvées dans l'historique.
# Aucune valeur réelle ici : ce fichier serait sinon lui-même une fuite, et la
# purge le réécrirait — faisant échouer l'étape de vérification du runbook.
VALEURS_DE_FORME_SECRETE = [
    "exemple-cle-2099",
    "exemple_secret_key_00000",
    "0123456789abcdef0123456789abcdef",
]


@pytest.mark.parametrize("valeur", VALEURS_DE_FORME_SECRETE)
def test_une_vraie_valeur_est_reconnue(valeur):
    assert purge.est_un_secret(valeur) is True


@pytest.mark.parametrize(
    "valeur",
    ["${ARENA_API_KEY}", "${CREDS_KEY}", "", "   ", "court", "abc"],
)
def test_une_reference_ou_une_valeur_courte_est_ignoree(valeur):
    assert purge.est_un_secret(valeur) is False


def test_les_guillemets_ne_font_pas_passer_une_reference_pour_un_secret():
    assert purge.est_un_secret('"${ARENA_API_KEY}"') is False


def test_le_masquage_ne_revele_pas_la_valeur():
    valeur = "exemple-cle-2099"          # 16 caractères, valeur inventée

    masque = purge.masquer(valeur)

    assert valeur not in masque
    assert masque.startswith("exem")
    assert masque.endswith("(16 car.)")
    assert "cle" not in masque, "le milieu de la valeur ne doit pas apparaître"


def test_une_valeur_tres_courte_est_entierement_masquee():
    assert purge.masquer("abc") == "…" * 3


def test_le_motif_librechat_isole_la_cle():
    fichier, motif = purge.EMPLACEMENTS[0]
    contenu = '      apiKey: "valeur-secrete-ici"\n      baseURL: "http://x"\n'

    assert fichier == "librechat.yaml"
    assert motif.findall(contenu) == ["valeur-secrete-ici"]


def test_le_motif_compose_isole_les_variables_sensibles():
    _, motif = purge.EMPLACEMENTS[1]
    contenu = (
        "      - CREDS_KEY=valeur-une\n"
        "      - JWT_SECRET=valeur-deux\n"
        "      - WEBUI_NAME=ARENA\n"          # pas un secret : ne doit pas sortir
        "      - ARENA_API_KEY=${ARENA_API_KEY}\n"
    )

    trouves = motif.findall(contenu)

    assert "valeur-une" in trouves
    assert "valeur-deux" in trouves
    assert "ARENA" not in trouves
    assert [v for v in trouves if purge.est_un_secret(v)] == ["valeur-une", "valeur-deux"]


def test_le_script_lit_l_historique_reel_du_depot():
    """Sur ce dépôt, l'historique contient bien des secrets à purger."""
    trouves = purge.secrets_de_l_historique()

    assert len(trouves) >= 5, f"attendu au moins 5 secrets, trouvé {len(trouves)}"
    assert all(purge.est_un_secret(v) for v in trouves)
    assert not any(v.startswith("${") for v in trouves)
