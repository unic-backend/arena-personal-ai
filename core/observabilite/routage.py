"""Le journal du routage : la date, la phrase, l'intention, les agents appeles.

**Le manque, mesure le 30/09/2026, chantier « la consigne dit la verite »**
(DEC-0192, DEC-0193). Ces deux decisions ont corrige ce que `config/jarvis.md`
RACONTAIT du routage. Elles laissaient explicitement ouvert un troisieme
chantier, distinct : « la disponibilite reelle des capacites et le journal de
routage sont deux chantiers separes. » Rien, avant ce module, ne gardait la
trace de ce que `dispatch_request` avait reellement decide : l'intention
calculee et les agents appeles n'existaient que le temps de la requete, dans
des variables locales, puis disparaissaient. Un « pourquoi ma phrase d'hier
est-elle partie chez PLAQUISTE ? » n'avait aucune reponse la journee suivante.

## Un seul point d'ecriture

`dispatch_request` (`apps/backend/routers/chat.py`) est le SEUL appelant : la
docstring de cette fonction le dit deja pour le type de tache (13/09/2026),
et la meme raison vaut ici — poser la trace ailleurs la manquerait pour l'un
des cinq appelants, et un routage resterait invisible sans que rien ne le
signale.

## Aucune detection ajoutee

Ce module ne decide JAMAIS si une demande est une chaine. Il relit ce que
`core/agent/equipe.py::executer` a deja execute et deja restitue dans le
champ `equipe` de sa reponse (liste ordonnee de `{intention, agent, status}`).
Une demande simple n'a pas ce champ : elle enregistre l'unique agent appele.
Ajouter ici un decoupage, un regex ou un second classeur romprait la regle 1
d'`equipe.py` (« le decoupage est deterministe, et il a lieu a un seul
endroit ») pour un gain nul : la chaine executee est deja connue au moment ou
ce module intervient.

## Trois regles, memes que les journaux voisins

1. **Le journal ne peut pas contredire l'execution.** `depuis_dispatch()`
   derive l'intention et les agents du resultat rendu par `dispatch_request`
   lui-meme — personne ne les fournit a la main, donc personne ne peut
   ecrire un agent qui n'a pas tourne.
2. **Une execution hors demande porte `requete = None`.** Meme regle que
   `core/observabilite/plans.py` : un script ou une tache de fond n'a pas de
   demande HTTP derriere lui.
3. **Une ecriture qui echoue ne bloque jamais la reponse.** Meme discipline
   que `core/actions/journal.py` : perdre une ligne de journal est regrettable,
   empecher la reponse de partir a cause de cette ligne l'est davantage.
"""
import json
import logging
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.observabilite.fil import fil_courant

logger = logging.getLogger("usman.observabilite.routage")

#: Combien de lignes sont relues au plus par defaut.
LIMITE_PAR_DEFAUT = 200


def _maintenant() -> str:
    """Horodatage UTC, isole pour que les tests le fixent."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AppelRoute:
    """Un passage par `dispatch_request`, tel qu'il sera relu.

    Attributes:
        identifiant: unique, genere ici — jamais fourni par l'appelant.
        horodatage: UTC, en ISO 8601.
        phrase: la phrase du proprietaire, mot pour mot (`message_actuel` ou
            `prompt` — la meme donnee que celle qui nomme la tache racine).
        intention: l'intention retenue pour cette demande. Pour une chaine,
            celle rendue par `equipe.executer()` (l'intention de la DERNIERE
            etape executee), jamais celle du premier morceau seul.
        agents: les agents reellement appeles, dans l'ordre ou ils ont
            tourne. Une demande simple en compte un ; une chaine en compte
            autant que d'etapes executees — jusqu'a l'echec qui l'a arretee,
            jamais celles qui restaient planifiees.
        etapes: vide pour une demande simple. Pour une chaine, la liste que
            `equipe.executer()` a deja construite (`{intention, agent,
            status}` par etape reellement executee) — copiee telle quelle,
            jamais recalculee.
        requete: l'identifiant de la demande HTTP, ou `None` hors demande
            (script, tache de fond, test). Pris au fil courant
            (`core/observabilite/fil.py`), jamais fourni par l'appelant.
    """

    phrase: str
    intention: str
    agents: List[str] = field(default_factory=list)
    etapes: List[Dict[str, Any]] = field(default_factory=list)
    requete: Optional[str] = field(default_factory=fil_courant)
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    horodatage: str = field(default_factory=_maintenant)

    @classmethod
    def depuis_dispatch(cls, phrase: str, intention: str,
                         reponse: Dict[str, Any]) -> "AppelRoute":
        """Construit l'entree a partir de ce que `dispatch_request` a rendu.

        C'est le seul chemin recommande : les agents et les etapes sont
        derives de `reponse`, jamais passes separement, pour que personne ne
        puisse journaliser un agent qui n'a pas ete appele.

        Args:
            phrase: la phrase exacte du proprietaire.
            intention: l'intention retenue pour cette demande.
            reponse: le dictionnaire rendu par `equipe.executer()` (chaine)
                ou `_aiguiller()` (demande simple).
        """
        equipe = reponse.get("equipe")
        if isinstance(equipe, list) and equipe:
            etapes = [
                {
                    "intention": str(e.get("intention") or ""),
                    "agent": str(e.get("agent") or ""),
                    "status": str(e.get("status") or ""),
                }
                for e in equipe
            ]
            agents = [e["agent"] for e in etapes if e["agent"]]
        else:
            etapes = []
            agent = reponse.get("agent")
            agents = [str(agent)] if agent else []
        return cls(phrase=phrase, intention=intention, agents=agents, etapes=etapes)

    def to_dict(self) -> Dict[str, Any]:
        """Forme transportable."""
        return {
            "id": self.identifiant,
            "horodatage": self.horodatage,
            "phrase": self.phrase,
            "intention": self.intention,
            "agents": self.agents,
            "etapes": self.etapes,
            "requete": self.requete,
        }


class JournalDeRoutage:
    """Ecrit et relit les passages par `dispatch_request`. Ne decide rien.

    SQLite, meme fichier que la memoire, le journal des actions et celui des
    plans (`data/database/memory.db`) — table distincte, meme discipline.
    """

    TABLE = "journal_routage"

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
                    identifiant TEXT PRIMARY KEY,
                    horodatage  TEXT NOT NULL,
                    phrase      TEXT NOT NULL,
                    intention   TEXT NOT NULL,
                    agents      TEXT NOT NULL,
                    etapes      TEXT NOT NULL,
                    requete     TEXT
                )
            """)
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_horodatage "
                f"ON {self.TABLE} (horodatage DESC)"
            )
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_requete "
                f"ON {self.TABLE} (requete)"
            )
            connexion.commit()

    def enregistrer(self, appel: AppelRoute) -> bool:
        """Ecrit un passage. Rend False si l'ecriture a echoue, sans lever.

        Une exception ici remonterait jusqu'a `dispatch_request` et pourrait
        casser une reponse deja prete. Le journal signale sa panne ; il ne la
        propage pas — meme discipline que `core/actions/journal.py`.
        """
        try:
            with closing(self._connexion()) as connexion:
                connexion.execute(
                    f"INSERT INTO {self.TABLE} (identifiant, horodatage, phrase, "
                    f"intention, agents, etapes, requete) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        appel.identifiant, appel.horodatage, appel.phrase,
                        appel.intention, json.dumps(appel.agents, ensure_ascii=False),
                        json.dumps(appel.etapes, ensure_ascii=False), appel.requete,
                    ),
                )
                connexion.commit()
            return True
        except Exception as erreur:  # noqa: BLE001 - une trace ne bloque jamais la reponse
            logger.error("Journal de routage : ecriture impossible (%s).", erreur)
            return False

    @staticmethod
    def _depuis_ligne(ligne: sqlite3.Row) -> AppelRoute:
        """Reconstruit l'objet exactement tel qu'il a ete ecrit."""
        return AppelRoute(
            identifiant=ligne["identifiant"], horodatage=ligne["horodatage"],
            phrase=ligne["phrase"], intention=ligne["intention"],
            agents=json.loads(ligne["agents"]), etapes=json.loads(ligne["etapes"]),
            requete=ligne["requete"] if "requete" in ligne.keys() else None,
        )

    def dernieres(self, limite: int = LIMITE_PAR_DEFAUT,
                  requete_id: Optional[str] = None) -> List[AppelRoute]:
        """Les passages les plus recents d'abord, filtres par demande si voulu.

        Args:
            limite: combien au plus.
            requete_id: l'identifiant d'une demande HTTP — celui qui relie ce
                passage aux actions et au plan qu'il a pu declencher.
        """
        requete = f"SELECT * FROM {self.TABLE}"
        arguments: List[Any] = []
        if requete_id:
            requete += " WHERE requete = ?"
            arguments.append(requete_id)
        requete += " ORDER BY horodatage DESC, rowid DESC LIMIT ?"
        arguments.append(limite)
        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()
        return [self._depuis_ligne(ligne) for ligne in lignes]
