"""Persistance des jetons OAuth, pour survivre a un redemarrage du processus.

Trouve le 31/08/2026, en testant Gmail juste apres l'avoir connecte pour de
vrai (DEC-0024) sur l'hebergement Railway du proprietaire : `GOOGLE_REFRESH_
TOKEN`, obtenu via `/connectors/gmail/auth`, n'etait ecrit que dans
`os.environ` (effet immediat sur le processus courant) et, en best-effort,
dans un fichier `.env` sur disque. Sur un hebergement comme Railway, les
variables d'environnement sont injectees par la plateforme au demarrage du
conteneur — **aucun fichier `.env` n'existe sur le disque** pour porter
l'ecriture. Un redeploiement (nouveau conteneur, donc nouveau processus)
perdait le jeton, qui n'avait jamais existe nulle part ailleurs que dans la
memoire du processus precedent : Gmail redevenait `NOT_CONFIGURED` a chaque
mise a jour du code, forcant a tout reconnecter.

Ce module ecrit a la place dans la meme base SQLite que la memoire
personnelle (`data/database/memory.db`) — deja prouvee persistante sur son
hebergement par DEC-0021 (« la memoire... vit la ou ARENA vit »). Au
demarrage, `apps/backend/runtime.py` recharge ce qui y est enregistre dans
`os.environ` : un processus neuf retrouve le jeton sans repasser par Google.

**Deux regles :**

1. **Une valeur vide efface, elle ne s'enregistre pas.** `/connectors/{id}/
   disconnect` appelle `enregistrer()` avec une chaine vide : la ligne est
   retiree de la base, pas gardee comme une valeur vide qui ressemblerait a
   un jeton valable.
2. **Une base illisible ne casse rien.** `charger_tout()` rend un
   dictionnaire vide plutot que de lever — un disque neuf, sans base encore
   creee, doit demarrer comme n'importe quel autre premier lancement.
"""
import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Dict

logger = logging.getLogger("usman.connecteurs.stockage_jetons")

TABLE = "secrets_oauth"


def _connexion(db_path: str) -> sqlite3.Connection:
    chemin = Path(db_path)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    connexion = sqlite3.connect(db_path)
    connexion.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} ("
        f"  variable TEXT PRIMARY KEY,"
        f"  valeur TEXT NOT NULL,"
        f"  ecrit_le REAL NOT NULL"
        f")"
    )
    connexion.commit()
    return connexion


def enregistrer(db_path: str, variable: str, valeur: str) -> None:
    """Ecrit ou remplace une valeur. Une chaine vide efface (deconnexion)."""
    with closing(_connexion(db_path)) as connexion:
        if valeur:
            connexion.execute(
                f"INSERT INTO {TABLE} (variable, valeur, ecrit_le) VALUES (?, ?, ?) "
                f"ON CONFLICT(variable) DO UPDATE SET "
                f"valeur = excluded.valeur, ecrit_le = excluded.ecrit_le",
                (variable, valeur, time.time()),
            )
        else:
            connexion.execute(f"DELETE FROM {TABLE} WHERE variable = ?", (variable,))
        connexion.commit()


def charger_tout(db_path: str) -> Dict[str, str]:
    """Tout ce qui est enregistre. Un disque neuf rend un dictionnaire vide."""
    try:
        with closing(_connexion(db_path)) as connexion:
            lignes = connexion.execute(f"SELECT variable, valeur FROM {TABLE}").fetchall()
        return {variable: valeur for variable, valeur in lignes}
    except sqlite3.Error as erreur:
        logger.warning(
            "Jetons persistants illisibles (%s) : demarre comme si aucun "
            "n'etait enregistre.", erreur)
        return {}
