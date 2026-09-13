"""Ce que chaque type de tache coute reellement, mesure appel par appel.

Le manque, tel que l'audit PHASE 0 le nomme (section E) : le routeur choisit un
fournisseur — d'abord sur la confidentialite, ce qui est la bonne garantie — mais
**il ne garde aucune trace de ce que ce choix a donne, par type de tache**. Rien
ne dit que Groq echoue une fois sur trois sur `CODE_EXECUTION` alors qu'il tient
sans faillir sur `CHAT`, ni que le local repond en 400 ms sur l'un et en huit
secondes sur l'autre.

## Pourquoi un magasin separe de `CompteurUsage`

C'est la premiere chose mesuree avant d'ecrire une ligne, et elle a change la
conception. `CompteurUsage` **est** le quota : `verdict()` compte les lignes du
jour et coupe le cloud au plafond. Y faire entrer les appels locaux — qu'il
ecarte aujourd'hui par `if nom == LOCAL: return` — couperait le cloud sans qu'un
seul appel distant soit parti :

    3 appels LOCAUX enregistres dans CompteurUsage
    -> cloud autorise = False, « plafond atteint : 3 requete(s) cloud »

Or une statistique par type de tache qui ignorerait le local serait aveugle sur
le fournisseur le plus sollicite. Les deux besoins sont donc incompatibles dans
la meme table : celui-ci a la sienne, et elle ne decide d'aucun plafond.

## Trois regles, et la premiere est la plus facile a enfreindre

1. **Un taux sur zero passage vaut `None`, jamais 0 % ni 100 %.** Un
   fournisseur qui n'a jamais servi un type de tache n'a pas « 0 % de
   reussite » : il n'a pas de taux. Ecrire un zero ferait ecarter un
   fournisseur qui n'a simplement jamais ete essaye.
2. **Aucune qualite n'est mesuree ici.** Il n'existe aucune source honnete pour
   un score de qualite dans ce depot : la calculer par un autre modele en
   ferait une affirmation de plus a verifier, et l'inventer serait exactement
   ce que ce depot refuse partout ailleurs. `QUALITE_NON_MESUREE` le dit dans
   chaque rapport, avec ce qu'il faudrait pour l'avoir vraiment.
3. **La statistique rapporte, elle ne choisit pas.** Rien ici n'est lu par le
   routeur au moment de router. Un routeur qui changerait son choix d'apres des
   mesures a peine commencees changerait de comportement sur des donnees
   minces — et pourrait passer devant le classement de confidentialite, que
   l'audit dit lui-meme de ne pas toucher. S'en servir pour choisir est une
   seconde decision, et elle appartient au proprietaire.
"""
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.models.statistiques")

#: Ce qui remplace un score de qualite, dans chaque rapport. Ecrit ici plutot
#: que laisse a la docstring : un appelant HTTP ne lit pas les docstrings.
QUALITE_NON_MESUREE = (
    "Aucune qualite n'est mesuree. Il n'existe pas de source honnete pour un "
    "tel score ici : le calculer par un autre modele en ferait une affirmation "
    "de plus a verifier. La seule source reelle est le proprietaire — il "
    "faudrait qu'une reponse puisse etre notee par lui, ce qui n'existe pas "
    "encore. Un chiffre invente serait pire que cette absence."
)

#: Le type de tache d'un appel qui ne vient pas d'une intention connue : un
#: script, une tache de fond, un appel direct. `None` en base, et le rapport le
#: nomme ainsi plutot que de le ranger avec `CHAT`.
HORS_INTENTION = "HORS_INTENTION"

#: Combien de passages sont lus au plus pour un rapport.
LIMITE_PAR_DEFAUT = 5000


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _taux(numerateur: int, total: int) -> Optional[float]:
    """Un taux, ou `None` quand il n'y a rien a diviser.

    La regle qui coute le plus cher a enfreindre : `0.0` sur zero passage se
    lirait « ce fournisseur echoue toujours » et le ferait ecarter alors qu'il
    n'a jamais ete essaye.
    """
    if total <= 0:
        return None
    return round(numerateur / total, 4)


@dataclass(frozen=True)
class Passage:
    """Un appel a un fournisseur, tel qu'il sera compte. **Sans le texte.**

    Attributes:
        type_tache: l'intention qui a cause l'appel, ou `HORS_INTENTION`.
        fournisseur: `local`, `groq`, `deepinfra`…
        modele: le modele reellement servi.
        succes: l'appel a-t-il rendu quelque chose d'utilisable.
        repli: cet appel etait-il un repli apres l'echec d'un autre.
        secondes: la duree mesuree, ou `None` si le fournisseur n'en rend pas.
            **Jamais `0.0`** : un zero se lirait « instantane ».
        classement: le niveau de confidentialite qui a gouverne le choix.
    """

    type_tache: str
    fournisseur: str
    modele: str
    succes: bool
    repli: bool = False
    secondes: Optional[float] = None
    classement: str = ""
    horodatage: str = field(default_factory=_maintenant)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type_tache": self.type_tache, "fournisseur": self.fournisseur,
            "modele": self.modele, "succes": self.succes, "repli": self.repli,
            "secondes": self.secondes, "classement": self.classement,
            "horodatage": self.horodatage,
        }


class StatistiquesRoutage:
    """Enregistre chaque passage et le rend par type de tache. Ne decide rien."""

    TABLE = "routage_passages"

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
                    horodatage  TEXT NOT NULL,
                    type_tache  TEXT NOT NULL,
                    fournisseur TEXT NOT NULL,
                    modele      TEXT NOT NULL,
                    succes      INTEGER NOT NULL,
                    repli       INTEGER NOT NULL,
                    secondes    REAL,
                    classement  TEXT NOT NULL
                )
            """)
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_type "
                f"ON {self.TABLE} (type_tache)"
            )
            connexion.commit()

    def enregistrer(self, passage: Passage) -> bool:
        """Ecrit un passage. Rend False si l'ecriture a echoue, **sans lever**.

        Meme discipline que `core/actions/journal.py` : perdre une mesure est
        regrettable, empecher une reponse parce que la mesure a echoue l'est
        davantage.
        """
        try:
            with closing(self._connexion()) as connexion:
                connexion.execute(
                    f"INSERT INTO {self.TABLE} (horodatage, type_tache, fournisseur, "
                    f"modele, succes, repli, secondes, classement) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (passage.horodatage, passage.type_tache, passage.fournisseur,
                     passage.modele, int(passage.succes), int(passage.repli),
                     passage.secondes, passage.classement),
                )
                connexion.commit()
            return True
        except Exception as erreur:  # noqa: BLE001 — une mesure ne bloque jamais une reponse
            logger.error("Statistiques de routage : ecriture impossible (%s).", erreur)
            return False

    def passages(self, type_tache: Optional[str] = None,
                 limite: int = LIMITE_PAR_DEFAUT) -> List[Passage]:
        """Les passages les plus recents d'abord, filtres par type si demande."""
        requete = f"SELECT * FROM {self.TABLE}"
        arguments: List[Any] = []
        if type_tache:
            requete += " WHERE type_tache = ?"
            arguments.append(type_tache)
        requete += " ORDER BY horodatage DESC, rowid DESC LIMIT ?"
        arguments.append(limite)
        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()
        return [
            Passage(
                type_tache=ligne["type_tache"], fournisseur=ligne["fournisseur"],
                modele=ligne["modele"], succes=bool(ligne["succes"]),
                repli=bool(ligne["repli"]), secondes=ligne["secondes"],
                classement=ligne["classement"], horodatage=ligne["horodatage"],
            )
            for ligne in lignes
        ]

    @staticmethod
    def _resumer(passages: List[Passage]) -> Dict[str, Any]:
        """Le resume d'un groupe de passages. Tous les taux peuvent valoir `None`."""
        total = len(passages)
        durees = [p.secondes for p in passages if p.secondes is not None]
        return {
            "passages": total,
            "taux_de_succes": _taux(sum(1 for p in passages if p.succes), total),
            "taux_de_repli": _taux(sum(1 for p in passages if p.repli), total),
            # `None` quand aucun fournisseur n'a rendu de duree : un `0.0` se
            # lirait « instantane », et une mediane sur zero echantillon n'existe
            # pas.
            "mediane_secondes": round(median(durees), 4) if durees else None,
            "durees_mesurees": len(durees),
            "qualite": None,
        }

    def par_type_de_tache(self, limite: int = LIMITE_PAR_DEFAUT) -> Dict[str, Any]:
        """Ce que chaque type de tache a donne, fournisseur par fournisseur.

        Returns:
            Un rapport par type de tache, et `qualite` toujours `None` avec sa
            raison. Un rapport vide est une reponse : il dit qu'aucun appel n'a
            encore ete mesure, jamais que tout va bien.
        """
        tous = self.passages(limite=limite)
        par_type: Dict[str, List[Passage]] = {}
        for passage in tous:
            par_type.setdefault(passage.type_tache, []).append(passage)

        rapport = {}
        for type_tache, groupe in sorted(par_type.items()):
            par_fournisseur: Dict[str, List[Passage]] = {}
            for passage in groupe:
                par_fournisseur.setdefault(passage.fournisseur, []).append(passage)
            rapport[type_tache] = {
                **self._resumer(groupe),
                "par_fournisseur": {
                    nom: self._resumer(sous_groupe)
                    for nom, sous_groupe in sorted(par_fournisseur.items())
                },
            }

        return {
            "par_type_de_tache": rapport,
            "types_mesures": len(rapport),
            "passages_totaux": len(tous),
            "qualite": QUALITE_NON_MESUREE,
            "note": (
                "Ces mesures ne sont lues par personne au moment de router : "
                "elles rapportent, elles ne choisissent pas. Le classement de "
                "confidentialite reste seul maitre du choix."
            ),
        }
