"""Permissions d'Usman : ce qui est autorisé, et surtout ce qui ne l'est pas."""
import pytest

from core.permissions.permission_manager import PermissionManager

RACINE = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
CONFIG_DU_DEPOT = RACINE / "config" / "permissions.yaml"


@pytest.fixture
def permissions_du_depot() -> PermissionManager:
    """Le fichier livré dans le dépôt, désigné en absolu.

    Le chemin par défaut est relatif au répertoire courant : le désigner
    explicitement évite qu'un test passe pour la mauvaise raison.
    """
    return PermissionManager(config_path=str(CONFIG_DU_DEPOT))


@pytest.fixture
def permissions_sans_fichier(tmp_path) -> PermissionManager:
    """Aucun fichier de configuration : seules les valeurs par défaut du code s'appliquent."""
    return PermissionManager(config_path=str(tmp_path / "permissions.yaml"))


@pytest.mark.parametrize("permission", ["READ_FILES", "WRITE_FILES", "PROCESS_MEDIA"])
def test_les_actions_courantes_sont_autorisees(permissions_du_depot, permission):
    assert permissions_du_depot.is_allowed(permission) is True


@pytest.mark.parametrize("permission", ["PUBLISH", "DELETE", "EXECUTE_COMMANDS"])
def test_les_actions_a_effet_externe_sont_bloquees(permissions_du_depot, permission):
    assert permissions_du_depot.is_allowed(permission) is False


@pytest.mark.parametrize("permission", ["PUBLISH", "DELETE", "EXECUTE_COMMANDS"])
def test_le_blocage_tient_meme_sans_fichier_de_configuration(permissions_sans_fichier, permission):
    """Le YAML est cherché en chemin relatif : sans lui, le défaut du code doit tenir."""
    assert permissions_sans_fichier.is_allowed(permission) is False


def test_une_permission_inconnue_est_refusee(permissions_du_depot):
    assert permissions_du_depot.is_allowed("PERMISSION_QUI_N_EXISTE_PAS") is False


def test_une_permission_peut_etre_ouverte_puis_persistee(permissions_sans_fichier):
    permissions_sans_fichier.set_permission("EXECUTE_COMMANDS", True)

    assert permissions_sans_fichier.is_allowed("EXECUTE_COMMANDS") is True
    # Une nouvelle instance relit le fichier écrit : le changement a bien été gardé.
    relu = PermissionManager(config_path=str(permissions_sans_fichier.config_path))
    assert relu.is_allowed("EXECUTE_COMMANDS") is True
