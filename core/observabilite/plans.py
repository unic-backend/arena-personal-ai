"""Ce qu'un plan a fait, et pourquoi il s'est arrete — apres coup, pas seulement dans les logs.

Le manque, tel que DEC-0100 le nommait en le laissant ouvert : `stop_reason`
existait — `RaisonDArret`, sept valeurs, porte par `EtatBoucle` — mais **il ne
sortait jamais de la boucle**. Il finissait dans une ligne de journal
applicatif, c'est-a-dire nulle part ou quelqu'un puisse le retrouver le
lendemain. `plan_id` et `memory_hits` n'existaient pas du tout.

Consequence concrete : quand une demande du proprietaire aboutissait a une
reponse incomplete, rien ne disait si le plan avait **atteint son objectif**,
**epuise son budget de tours**, ou **manque de temps**. Les trois se
ressemblent vues de l'exterieur, et elles appellent trois gestes differents.

## Ce qui est enregistre, et ce qui ne l'est pas

Une ligne par execution de plan : son identifiant, la demande HTTP qui l'a
cause (`core/observabilite/fil.py`), le type de tache, l'objectif, la raison
d'arret, les tours, les etapes, les secondes, les appels d'outils, et combien
de souvenirs le plan a consultes.

**Jamais le contenu.** Ni l'objectif d'un plan prive, ni les souvenirs lus :
l'objectif est deja une phrase du proprietaire et il est garde tel quel parce
qu'il est ce qui rend la ligne lisible, mais rien d'autre du corps de la
demande n'entre ici. Meme regle que `core/models/usage.py` — « un appel
distant, tel qu'il sera compte. **Sans le texte de la demande.** »

## Trois regles

1. **`appels_outils` vaut `None` quand aucun compteur n'est branche.** C'est la
   regle 5 de la boucle, et la casser ici ferait lire « ce plan n'a appele
   aucun outil » la ou la verite est « personne n'a compte ».
2. **Une execution hors demande porte `requete = None`.** Un script ou une
   tache de fond n'a pas de demande derriere lui, et lui en inventer une ferait
   chercher une demande qui n'a jamais existe.
3. **Une ecriture qui echoue ne leve pas.** Meme discipline que
   `core/actions/journal.py` : perdre la trace d'un plan est regrettable,
   empecher le plan de rendre son resultat l'est davantage.
"""
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.observabilite.plans")

#: Combien de plans sont lus au plus pour un rapport.
LIMITE_PAR_DEFAUT = 200


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class PlanExecute:
    """Une execution de boucle, telle qu'elle sera relue.

    Attributes:
        plan_id: l'identifiant de CETTE execution. Deux executions du meme
            objectif en ont deux differents : c'est ce qui permet de les
            distinguer quand la premiere a echoue.
        objectif: ce que le plan cherchait a faire, tel quel.
        raison_d_arret: la valeur de `RaisonDArret`. **Jamais vide** — la boucle
            ne sort jamais sans raison, et une ligne sans raison signalerait un
            chemin qui contourne `_arreter`.
        requete: l'identifiant de la demande HTTP, ou `None` hors demande.
        type_tache: l'intention, ou `None` hors intention.
        appels_outils: `None` quand aucun compteur n'etait branche.
        souvenirs_consultes: combien de souvenirs la recuperation a rendus
            pendant ce plan. `0` est une mesure ici — le plan a tourne et n'a
            rien consulte.
    """

    plan_id: str
    objectif: str
    raison_d_arret: str
    atteint: bool
    tours: int
    etapes: int
    secondes: float
    requete: Optional[str] = None
    type_tache: Optional[str] = None
    appels_outils: Optional[int] = None
    souvenirs_consultes: int = 0
    horodatage: str = field(default_factory=_maintenant)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id, "objectif": self.objectif,
            "raison_d_arret": self.raison_d_arret, "atteint": self.atteint,
            "tours": self.tours, "etapes": self.etapes,
            "secondes": round(self.secondes, 3),
            "requete": self.requete, "type_tache": self.type_tache,
            "appels_outils": self.appels_outils,
            "souvenirs_consultes": self.souvenirs_consultes,
            "horodatage": self.horodatage,
        }


class JournalDesPlans:
    """Ecrit et relit les executions de plan. Ne decide rien."""

    TABLE = "plans_executes"

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
                    plan_id             TEXT PRIMARY KEY,
                    horodatage          TEXT NOT NULL,
                    objectif            TEXT NOT NULL,
                    raison_d_arret      TEXT NOT NULL,
                    atteint             INTEGER NOT NULL,
                    tours               INTEGER NOT NULL,
                    etapes              INTEGER NOT NULL,
                    secondes            REAL NOT NULL,
                    requete             TEXT,
                    type_tache          TEXT,
                    appels_outils       INTEGER,
                    souvenirs_consultes INTEGER NOT NULL DEFAULT 0
                )
            """)
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_requete "
                f"ON {self.TABLE} (requete)"
            )
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_horodatage "
                f"ON {self.TABLE} (horodatage DESC)"
            )
            connexion.commit()

    def enregistrer(self, plan: PlanExecute) -> bool:
        """Ecrit une execution. Rend False si l'ecriture a echoue, sans lever."""
        try:
            with closing(self._connexion()) as connexion:
                connexion.execute(
                    f"INSERT OR REPLACE INTO {self.TABLE} (plan_id, horodatage, objectif, "
                    f"raison_d_arret, atteint, tours, etapes, secondes, requete, "
                    f"type_tache, appels_outils, souvenirs_consultes) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (plan.plan_id, plan.horodatage, plan.objectif, plan.raison_d_arret,
                     int(plan.atteint), plan.tours, plan.etapes, plan.secondes,
                     plan.requete, plan.type_tache, plan.appels_outils,
                     plan.souvenirs_consultes),
                )
                connexion.commit()
            return True
        except Exception as erreur:  # noqa: BLE001 — une trace ne bloque jamais un plan
            logger.error("Journal des plans : ecriture impossible (%s).", erreur)
            return False

    @staticmethod
    def _depuis_ligne(ligne: sqlite3.Row) -> PlanExecute:
        return PlanExecute(
            plan_id=ligne["plan_id"], horodatage=ligne["horodatage"],
            objectif=ligne["objectif"], raison_d_arret=ligne["raison_d_arret"],
            atteint=bool(ligne["atteint"]), tours=ligne["tours"],
            etapes=ligne["etapes"], secondes=ligne["secondes"],
            requete=ligne["requete"], type_tache=ligne["type_tache"],
            appels_outils=ligne["appels_outils"],
            souvenirs_consultes=ligne["souvenirs_consultes"],
        )

    def dernieres(self, limite: int = LIMITE_PAR_DEFAUT,
                  requete_id: Optional[str] = None) -> List[PlanExecute]:
        """Les executions les plus recentes d'abord, filtrees par demande si voulu.

        `requete_id` est ce qui relie une demande HTTP aux plans qu'elle a
        declenches : avec `/api/actions?request_id=…`, une demande se suit
        desormais de son premier octet jusqu'a la raison pour laquelle son plan
        s'est arrete.
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

    def resume(self, limite: int = LIMITE_PAR_DEFAUT,
               requete_id: Optional[str] = None) -> Dict[str, Any]:
        """Les plans, et la repartition de leurs raisons d'arret.

        Returns:
            La liste et un compte par raison. Un rapport vide est une reponse :
            il dit qu'aucun plan n'a encore tourne, jamais que tout va bien.
        """
        plans = self.dernieres(limite=limite, requete_id=requete_id)
        par_raison: Dict[str, int] = {}
        for plan in plans:
            par_raison[plan.raison_d_arret] = par_raison.get(plan.raison_d_arret, 0) + 1
        return {
            "plans": [p.to_dict() for p in plans],
            "total": len(plans),
            "par_raison_d_arret": dict(sorted(par_raison.items())),
            "atteints": sum(1 for p in plans if p.atteint),
            "note": (
                "« atteint » veut dire que la boucle a rendu OBJECTIF_ATTEINT, "
                "pas que le resultat est bon : elle mesure l'arret, pas la "
                "qualite. Aucun plan n'est juge ici."
            ),
        }
