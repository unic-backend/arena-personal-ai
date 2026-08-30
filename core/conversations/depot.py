"""Le coffre a conversations : ce que le telephone et le PC se partagent.

Jusqu'ici les conversations vivaient dans le `localStorage` de chaque
navigateur — donc nulle part en commun. Le proprietaire voyait sur son
telephone des echanges absents de son PC, avec la meme adresse et la meme cle,
ce qui est le comportement normal d'un stockage local, jamais une panne.

Deux choix de conception, et ils se tiennent :

**1. La conversation est stockee entiere, en JSON, sans etre decoupee en
colonnes.** Le serveur est un coffre, pas un modele : la forme d'une
conversation appartient a l'interface, qui la fait evoluer souvent (variantes,
pieces jointes, activite...). La decouper ici obligerait a migrer la base a
chaque changement d'ecran, et ferait perdre en silence les champs que le
serveur ne connaitrait pas encore.

**2. La plus recente gagne (`updated_at`).** Un seul proprietaire, deux
appareils qu'il n'utilise pas en meme temps : une fusion ligne a ligne
couterait cher et n'aurait presque jamais l'occasion de servir. La date vient
du client, parce que c'est lui qui sait quand il a ecrit — le serveur, lui, ne
fait qu'arbitrer.

Une suppression n'efface pas la ligne : elle pose une **pierre tombale**
(`supprimee = 1`). Sans elle, l'appareil qui n'etait pas la au moment de la
suppression re-enverrait la conversation, et elle ressusciterait a chaque
synchronisation.
"""
import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("usman.conversations")

#: Au-dela, la conversation est refusee — jamais tronquee en silence. Le disque
#: du serveur fait 0,5 Go : une seule conversation ne doit pas pouvoir le
#: remplir. 2 Mo, c'est deja tres au-dela d'un long echange en texte.
TAILLE_MAX_OCTETS = 2 * 1024 * 1024


class ConversationRefusee(ValueError):
    """La conversation ne peut pas etre enregistree, et on dit pourquoi."""


class DepotConversations:
    """Enregistre et rend les conversations, sur le disque persistant."""

    def __init__(self, db_path: str = "data/database/memory.db",
                 taille_max: int = TAILLE_MAX_OCTETS):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.taille_max = taille_max
        self._init_db()

    def _connexion(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connexion()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    updated_at INTEGER NOT NULL,
                    supprimee INTEGER NOT NULL DEFAULT 0,
                    contenu TEXT NOT NULL
                )
            """)
            conn.commit()

    # --- Ecriture ------------------------------------------------------------

    @staticmethod
    def _date_de(conversation: Dict[str, Any]) -> int:
        """La date de derniere ecriture, en millisecondes.

        Absente ou illisible, elle vaut 0 : la conversation existe quand meme,
        mais elle ne peut ecraser aucune version datee. Inventer la date du jour
        ferait gagner l'arrivante a tous les coups, ce qui est exactement ce que
        l'arbitrage doit eviter.
        """
        valeur = conversation.get("updatedAt")
        return int(valeur) if isinstance(valeur, (int, float)) else 0

    def deposer(self, conversations: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        """Enregistre celles qui sont plus recentes que la version conservee.

        Returns:
            Le nombre de conversations reellement ecrites, et les identifiants
            refuses avec leur raison deja journalisee. Une conversation refusee
            n'arrete pas les autres : perdre le lot entier pour une seule ligne
            trop grosse serait pire que la refuser seule.
        """
        ecrites, refusees = 0, []
        with closing(self._connexion()) as conn:
            for conversation in conversations:
                identifiant = conversation.get("id")
                if not isinstance(identifiant, str) or not identifiant:
                    refusees.append("(sans identifiant)")
                    continue

                contenu = json.dumps(conversation, ensure_ascii=False)
                if len(contenu.encode("utf-8")) > self.taille_max:
                    logger.warning("Conversation %s refusee : %d octets, maximum %d.",
                                   identifiant, len(contenu.encode("utf-8")), self.taille_max)
                    refusees.append(identifiant)
                    continue

                date = self._date_de(conversation)
                supprimee = 1 if conversation.get("supprimee") else 0
                # `excluded` est la ligne qu'on tentait d'inserer. La condition
                # est l'arbitrage lui-meme : on n'ecrase que du plus ancien.
                curseur = conn.execute(
                    """
                    INSERT INTO conversations (id, updated_at, supprimee, contenu)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        supprimee = excluded.supprimee,
                        contenu = excluded.contenu
                    WHERE excluded.updated_at > conversations.updated_at
                    """,
                    (identifiant, date, supprimee, contenu),
                )
                ecrites += curseur.rowcount if curseur.rowcount > 0 else 0
            conn.commit()
        return ecrites, refusees

    def supprimer(self, identifiant: str, date: int) -> bool:
        """Pose une pierre tombale. Rend Faux si une version plus recente existe."""
        with closing(self._connexion()) as conn:
            curseur = conn.execute(
                """
                INSERT INTO conversations (id, updated_at, supprimee, contenu)
                VALUES (?, ?, 1, '{}')
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at, supprimee = 1, contenu = '{}'
                WHERE excluded.updated_at > conversations.updated_at
                """,
                (identifiant, date),
            )
            conn.commit()
            return curseur.rowcount > 0

    # --- Lecture -------------------------------------------------------------

    def lister(self, depuis: Optional[int] = None) -> List[Dict[str, Any]]:
        """Les conversations conservees, les supprimees comprises.

        Les pierres tombales voyagent avec le reste : c'est ainsi qu'un appareil
        absent au moment de la suppression apprend qu'elle a eu lieu. Elles sont
        rendues comme `{"id": ..., "supprimee": True, "updatedAt": ...}`, sans
        contenu — il n'y en a plus.
        """
        requete = "SELECT id, updated_at, supprimee, contenu FROM conversations"
        parametres: Tuple[Any, ...] = ()
        if depuis is not None:
            requete += " WHERE updated_at > ?"
            parametres = (int(depuis),)
        requete += " ORDER BY updated_at DESC"

        resultat = []
        with closing(self._connexion()) as conn:
            for ligne in conn.execute(requete, parametres):
                if ligne["supprimee"]:
                    resultat.append({"id": ligne["id"], "supprimee": True,
                                     "updatedAt": ligne["updated_at"]})
                    continue
                try:
                    resultat.append(json.loads(ligne["contenu"]))
                except json.JSONDecodeError:
                    # Une ligne illisible est signalee, jamais rendue a moitie :
                    # une conversation tronquee ressemble a une conversation.
                    logger.error("Conversation %s illisible en base : ignoree.", ligne["id"])
        return resultat

    def compter(self) -> int:
        """Combien de conversations vivantes le coffre contient."""
        with closing(self._connexion()) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE supprimee = 0"
            ).fetchone()[0]
