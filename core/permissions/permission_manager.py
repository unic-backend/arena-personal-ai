import logging
from pathlib import Path

import yaml

from core.fichier_suivi import date_de

logger = logging.getLogger("usman.security.permissions")

class PermissionManager:
    """Gestionnaire central des permissions d'Usman et de ses agents."""

    DEFAULT_PERMISSIONS = {
        "READ_FILES": True,
        "WRITE_FILES": True,
        "EXECUTE_COMMANDS": False,  # BLOQUÉ PAR DÉFAUT (Sécurité)
        "SEARCH_WEB": True,
        "DOWNLOAD_MEDIA": True,
        "PROCESS_MEDIA": True,
        "SEND_MESSAGES": True,
        "PUBLISH": False,       # BLOQUÉ PAR DÉFAUT (Sécurité)
        "DELETE": False         # BLOQUÉ PAR DÉFAUT (Sécurité)
    }

    def __init__(self, config_path: str = "config/permissions.yaml"):
        self.config_path = Path(config_path).resolve()
        self.permissions = self.DEFAULT_PERMISSIONS.copy()
        self._load_config()
        self._date = date_de(self.config_path)

    def _relire_si_change(self):
        """Relit le fichier quand sa date de modification a change.

        Le fichier n'etait lu qu'a la construction, et cet objet est un
        singleton cree au demarrage du serveur : un booleen modifie dans
        `config/permissions.yaml` n'etait applique qu'au redemarrage suivant.
        Mesure du 01/09/2026, meme defaut que `PolitiqueDePermissions`.

        Les defauts de la classe sont remis avant la relecture : sans cela,
        une cle retiree du fichier garderait la valeur qu'elle avait avant,
        au lieu de revenir a son defaut — et les trois defauts qui comptent
        (`EXECUTE_COMMANDS`, `PUBLISH`, `DELETE`) sont a `False`.
        """
        date = date_de(self.config_path)
        if date == self._date:
            return
        self.permissions = self.DEFAULT_PERMISSIONS.copy()
        self._load_config()
        self._date = date
        logger.info("Permissions relues (%s).",
                    "fichier absent" if date is None else "fichier modifie")

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        self.permissions.update(data)
                        logger.info("Configuration des permissions chargée.")
            except Exception as e:
                logger.error(f"Erreur chargement permissions.yaml: {e}")
        else:
            self.save_config()

    def save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.permissions, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde permissions.yaml: {e}")

    def is_allowed(self, permission_name: str) -> bool:
        """Vérifie si une action est autorisée."""
        self._relire_si_change()
        allowed = self.permissions.get(permission_name, False)
        if not allowed:
            logger.warning(f"🔒 Action refusée par le système de permissions : {permission_name}")
        return allowed

    def set_permission(self, permission_name: str, allowed: bool):
        if permission_name in self.DEFAULT_PERMISSIONS:
            self.permissions[permission_name] = allowed
            self.save_config()
