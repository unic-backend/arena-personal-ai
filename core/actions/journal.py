"""Le journal des actions : ce qu'ARENA a tente, sur quoi, et ce qui en est sorti.

La specification en demande neuf champs par action — identifiant, horodatage,
outil, cible, parametres, niveau de permission, resultat, erreurs, etat de
verification. Aucun n'existait : la table `agent_logs` etait creee depuis le
premier jour et n'avait jamais recu une ligne (mesure le 2026-08-27 ; `grep`
ne trouvait que le `CREATE TABLE`).

Trois choix portent ce module, et chacun ferme une facon de mentir :

1. **Le journal ne peut pas contredire l'action.** `depuis_resultat()` derive le
   resultat *et* l'etat de verification du `ResultatAction` lui-meme. Personne
   ne les passe separement, donc personne ne peut ecrire « SUCCESS » a cote
   d'une action qui n'a rien fait.

2. **Aucun secret n'entre.** Les parametres sont le point d'entree evident d'un
   jeton ou d'un mot de passe. Ils sont masques a la construction — pas a la
   lecture, ou il serait deja trop tard : la valeur serait sur le disque.

3. **Un journal qui tombe ne fait pas tomber l'action.** Une ecriture qui echoue
   est signalee et rendue par `enregistrer()`, elle ne leve pas. Perdre la trace
   d'un envoi est grave ; empecher l'envoi parce que la trace a echoue l'est
   davantage.
"""
import json
import logging
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, Statut

logger = logging.getLogger("usman.actions.journal")

# Fragments de noms de champs qui portent un secret. Compares en minuscules, en
# sous-chaine : `USMAN_API_KEY`, `access_token` et `mot_de_passe` sont couverts.
FRAGMENTS_SECRETS = (
    "password", "passwd", "mot_de_passe", "secret", "token", "jeton",
    "api_key", "apikey", "cle_api", "authorization", "credential",
    "private_key", "cookie", "session_key",
)

MASQUE = "[secret retire]"

# Un journal n'est pas un entrepot : une piece jointe de 4 Mo n'y a pas sa place.
LONGUEUR_MAX_VALEUR = 2000
TRONQUE = "… [tronque]"


class EtatVerification(str, Enum):
    """Ce que l'on sait de l'effet reel de l'action, apres coup."""

    VERIFIEE = "VERIFIED"          # un effet a eu lieu et une preuve l'atteste
    NON_VERIFIEE = "UNVERIFIED"    # un effet est possible, rien ne l'atteste
    SANS_OBJET = "NOT_APPLICABLE"  # rien n'a ete tente : il n'y a rien a verifier


# Les statuts pour lesquels aucun effet n'a ete tente. Leur verification est
# sans objet, et la dire « non verifiee » laisserait croire a un doute.
STATUTS_SANS_TENTATIVE = frozenset({
    Statut.NON_CONFIGURE, Statut.REFUSE, Statut.A_CONFIRMER, Statut.NON_IMPLEMENTE,
})


def _est_secret(nom: str) -> bool:
    """Dit si un nom de parametre annonce une valeur qui ne doit pas etre ecrite."""
    minuscule = str(nom).lower()
    return any(fragment in minuscule for fragment in FRAGMENTS_SECRETS)


def masquer(parametres: Any) -> Any:
    """Remplace toute valeur portant un nom de secret, a n'importe quelle profondeur.

    Le masquage porte sur le **nom** du champ, jamais sur la forme de la valeur :
    reconnaitre un jeton a son allure rate ceux qui n'y ressemblent pas, et c'est
    exactement ceux-la qui finissent dans un journal.
    """
    if isinstance(parametres, dict):
        return {
            nom: MASQUE if _est_secret(nom) else masquer(valeur)
            for nom, valeur in parametres.items()
        }
    if isinstance(parametres, (list, tuple)):
        return [masquer(element) for element in parametres]
    if isinstance(parametres, str) and len(parametres) > LONGUEUR_MAX_VALEUR:
        return parametres[:LONGUEUR_MAX_VALEUR] + TRONQUE
    return parametres


def _maintenant() -> str:
    """Horodatage UTC, isole pour que les tests le fixent."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ActionEnregistree:
    """Les neuf champs d'une action, tels que la specification les demande.

    Attributes:
        identifiant: unique, genere ici — jamais fourni par l'appelant.
        horodatage: UTC, en ISO 8601.
        outil: ce qui a agi (`tiktok`, `gmail`, `publisher`).
        action: ce qui a ete tente (`publish_video`, `send`).
        cible: sur quoi (`TikTok`, `client@example.com`).
        parametres: les arguments, secrets masques.
        niveau_permission: la permission qui gouvernait l'action.
        resultat: la valeur d'un `Statut`.
        erreurs: le message d'erreur, ou None.
        verification: ce que l'on sait de l'effet reel.
        preuve: ce qui atteste l'effet, quand il y en a un.
    """

    outil: str
    action: str
    cible: str
    resultat: str
    niveau_permission: str = "INCONNU"
    parametres: Dict[str, Any] = field(default_factory=dict)
    erreurs: Optional[str] = None
    verification: EtatVerification = EtatVerification.NON_VERIFIEE
    preuve: Optional[str] = None
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    horodatage: str = field(default_factory=_maintenant)

    def __post_init__(self) -> None:
        # Le masquage a lieu ici, avant toute ecriture : une passe faite au
        # moment de l'ecriture laisserait l'objet circuler avec le secret dedans.
        object.__setattr__(self, "parametres", masquer(dict(self.parametres or {})))

    @classmethod
    def depuis_resultat(
        cls,
        resultat: ResultatAction,
        outil: str,
        parametres: Optional[Dict[str, Any]] = None,
        niveau_permission: str = "INCONNU",
        erreurs: Optional[str] = None,
    ) -> "ActionEnregistree":
        """Construit l'entree a partir du resultat, pour qu'ils ne divergent pas.

        C'est le seul chemin recommande. Le resultat et l'etat de verification
        sont deduits, jamais passes : un appelant ne peut donc pas journaliser
        une reussite a cote d'une action qui n'a rien fait.
        """
        if resultat.a_eu_lieu:
            verification = EtatVerification.VERIFIEE
        elif resultat.statut in STATUTS_SANS_TENTATIVE:
            verification = EtatVerification.SANS_OBJET
        else:
            verification = EtatVerification.NON_VERIFIEE

        return cls(
            outil=outil,
            action=resultat.action,
            cible=resultat.cible,
            resultat=resultat.statut.value,
            niveau_permission=niveau_permission,
            parametres=parametres or {},
            erreurs=erreurs,
            verification=verification,
            preuve=resultat.preuve,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Forme transportable. Les cles sont celles de la specification."""
        return {
            "id": self.identifiant,
            "horodatage": self.horodatage,
            "outil": self.outil,
            "action": self.action,
            "cible": self.cible,
            "parametres": self.parametres,
            "niveau_permission": self.niveau_permission,
            "resultat": self.resultat,
            "erreurs": self.erreurs,
            "verification": self.verification.value,
            "preuve": self.preuve,
        }


class JournalDesActions:
    """Ecrit et relit les actions. SQLite, meme fichier que la memoire.

    L'ancienne table `agent_logs` n'est plus creee : ses cinq colonnes ne
    pouvaient porter ni les parametres, ni le niveau de permission, ni les
    erreurs, ni la verification. Elle n'a jamais recu de ligne, donc il n'y a
    rien a migrer. Sur une base existante elle subsiste, vide et inoffensive.
    """

    TABLE = "journal_actions"

    def __init__(self, db_path: str = "data/database/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._creer_table()

    def _connexion(self) -> sqlite3.Connection:
        connexion = sqlite3.connect(self.db_path)
        connexion.row_factory = sqlite3.Row
        return connexion

    def _creer_table(self) -> None:
        with closing(self._connexion()) as connexion:
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    identifiant       TEXT PRIMARY KEY,
                    horodatage        TEXT NOT NULL,
                    outil             TEXT NOT NULL,
                    action            TEXT NOT NULL,
                    cible             TEXT NOT NULL,
                    parametres        TEXT NOT NULL,
                    niveau_permission TEXT NOT NULL,
                    resultat          TEXT NOT NULL,
                    erreurs           TEXT,
                    verification      TEXT NOT NULL,
                    preuve            TEXT
                )
            """)
            # L'ordre de lecture est toujours « le plus recent d'abord ».
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_horodatage "
                f"ON {self.TABLE} (horodatage DESC)"
            )
            connexion.commit()

    def enregistrer(self, action: ActionEnregistree) -> bool:
        """Ecrit une action. Rend False si l'ecriture a echoue, sans lever.

        Une exception ici remonterait jusqu'a l'appelant et pourrait annuler une
        action deja partie. Le journal signale sa panne ; il ne la propage pas.
        """
        try:
            with closing(self._connexion()) as connexion:
                connexion.execute(
                    f"INSERT INTO {self.TABLE} (identifiant, horodatage, outil, action, cible, "
                    f"parametres, niveau_permission, resultat, erreurs, verification, preuve) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        action.identifiant, action.horodatage, action.outil, action.action,
                        action.cible, json.dumps(action.parametres, ensure_ascii=False),
                        action.niveau_permission, action.resultat, action.erreurs,
                        action.verification.value, action.preuve,
                    ),
                )
                connexion.commit()
            return True
        except Exception as erreur:
            logger.error("Journal des actions : ecriture impossible (%s).", erreur)
            return False

    @staticmethod
    def _depuis_ligne(ligne: sqlite3.Row) -> ActionEnregistree:
        """Reconstruit l'objet exactement tel qu'il a ete ecrit."""
        return ActionEnregistree(
            identifiant=ligne["identifiant"],
            horodatage=ligne["horodatage"],
            outil=ligne["outil"],
            action=ligne["action"],
            cible=ligne["cible"],
            parametres=json.loads(ligne["parametres"]),
            niveau_permission=ligne["niveau_permission"],
            resultat=ligne["resultat"],
            erreurs=ligne["erreurs"],
            verification=EtatVerification(ligne["verification"]),
            preuve=ligne["preuve"],
        )

    def lire(self, identifiant: str) -> Optional[ActionEnregistree]:
        """Relit une action par son identifiant, ou None."""
        with closing(self._connexion()) as connexion:
            ligne = connexion.execute(
                f"SELECT * FROM {self.TABLE} WHERE identifiant = ?", (identifiant,)
            ).fetchone()
        return self._depuis_ligne(ligne) if ligne else None

    def dernieres(self, limite: int = 50, cible: Optional[str] = None) -> List[ActionEnregistree]:
        """Les actions les plus recentes d'abord, filtrees par cible si demande."""
        requete = f"SELECT * FROM {self.TABLE}"
        arguments: List[Any] = []
        if cible:
            requete += " WHERE cible = ?"
            arguments.append(cible)
        requete += " ORDER BY horodatage DESC, rowid DESC LIMIT ?"
        arguments.append(limite)

        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()
        return [self._depuis_ligne(ligne) for ligne in lignes]
