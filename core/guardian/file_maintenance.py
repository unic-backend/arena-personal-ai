"""Une mémoire de maintenance persistante — pour ne pas redécouvrir le même
constat à chaque cycle, et ne jamais dire « corrigé » sans preuve.

Même discipline que `core/actions/attente.py` (état en base, jamais en
mémoire du processus) et `core/actions/resultat.py` (un état ne se
construit pas sans ce qu'il exige) : `TERMINEE` n'existe que si une
vérification a réellement tourné — pas parce qu'une modification a été
tentée.

**Le cycle de vie (mission du 29/08/2026, §21), traduit en français :**

    DECOUVERTE -> TRIAGEE -> PRETE -> EN_COURS -> VERIFICATION -> TERMINEE
                                                                 -> ECHOUEE
                           -> DIFFEREE

Ce module ne fait tourner AUCUNE modification lui-même — voir DEC-0014 :
une garde qui modifie le dépôt sans qu'une pull request passe devant le
propriétaire violerait la règle non négociable du projet (« il ne peut pas
lancer les tests, la PR est l'endroit où il voit ce qui entre »). Les états
`EN_COURS`/`VERIFICATION`/`TERMINEE` existent pour la prochaine phase, une
fois cette garantie posée ; aujourd'hui, un cycle ne fait que peupler
`DECOUVERTE`/`TRIAGEE` et retenir ce qui a déjà été vu.
"""
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from core.guardian.diagnostics import Constat

logger = logging.getLogger("usman.guardian.file_maintenance")

CHEMIN_BASE_PAR_DEFAUT = "data/database/memory.db"


class EtatTache(str, Enum):
    """Le cycle de vie complet — voir la docstring du module pour ce qui
    tourne réellement aujourd'hui."""

    DECOUVERTE = "DISCOVERED"
    TRIAGEE = "TRIAGED"
    PRETE = "READY"
    EN_COURS = "WORKING"
    VERIFICATION = "VERIFYING"
    TERMINEE = "COMPLETED"
    ECHOUEE = "FAILED"
    DIFFEREE = "DEFERRED"


#: Ordre de priorite, du plus urgent au moins urgent — juste pour trier
#: l'affichage ; P0 et P1 n'ont aucun constat qui les produit aujourd'hui
#: (aucune categorie reelle n'atteint ce niveau, voir diagnostics.py).
ORDRE_GRAVITE = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Tache:
    """Une ligne de la file — un constat, avec son état et son histoire."""

    empreinte: str
    categorie: str
    gravite: str
    description: str
    fichier: str
    preuve: str
    etat: EtatTache
    decouverte_le: str
    vue_pour_la_derniere_fois_le: str
    occurrences: int
    tentatives: int = 0

    def to_dict(self) -> dict:
        return {
            "empreinte": self.empreinte, "categorie": self.categorie,
            "gravite": self.gravite, "description": self.description,
            "fichier": self.fichier, "preuve": self.preuve,
            "etat": self.etat.value, "decouverte_le": self.decouverte_le,
            "vue_pour_la_derniere_fois_le": self.vue_pour_la_derniere_fois_le,
            "occurrences": self.occurrences, "tentatives": self.tentatives,
        }


class FileDeMaintenance:
    """La mémoire de maintenance. SQLite, la même base que le reste d'ARENA."""

    def __init__(self, db_path: str = CHEMIN_BASE_PAR_DEFAUT) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._creer_table()

    def _connexion(self) -> sqlite3.Connection:
        connexion = sqlite3.connect(self.db_path)
        connexion.row_factory = sqlite3.Row
        return connexion

    def _creer_table(self) -> None:
        with closing(self._connexion()) as connexion:
            connexion.execute("""
                CREATE TABLE IF NOT EXISTS taches_maintenance (
                    empreinte TEXT PRIMARY KEY,
                    categorie TEXT NOT NULL,
                    gravite TEXT NOT NULL,
                    description TEXT NOT NULL,
                    fichier TEXT NOT NULL,
                    preuve TEXT NOT NULL,
                    etat TEXT NOT NULL,
                    decouverte_le TEXT NOT NULL,
                    vue_pour_la_derniere_fois_le TEXT NOT NULL,
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    tentatives INTEGER NOT NULL DEFAULT 0
                )
            """)
            # Un cycle qui ne trouve RIEN laisse la table des taches vide :
            # sans cette ligne, une memoire jamais consultee et une memoire
            # qui vient de confirmer un depot propre seraient indiscernables.
            connexion.execute("""
                CREATE TABLE IF NOT EXISTS gardien_meta (
                    cle TEXT PRIMARY KEY,
                    valeur TEXT NOT NULL
                )
            """)
            connexion.commit()

    def marquer_cycle_termine(self, horodatage: Optional[str] = None) -> None:
        """Enregistre qu'un cycle a tourné — même quand il n'a rien trouvé.
        Appelée par `Gardien.executer_cycle()` à chaque cycle, sans exception."""
        with closing(self._connexion()) as connexion:
            connexion.execute(
                "INSERT INTO gardien_meta (cle, valeur) VALUES ('dernier_cycle_le', ?) "
                "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                (horodatage or _maintenant(),))
            connexion.commit()

    def dernier_cycle_le(self) -> Optional[str]:
        """L'horodatage du dernier cycle, ou `None` si aucun n'a jamais tourné."""
        with closing(self._connexion()) as connexion:
            ligne = connexion.execute(
                "SELECT valeur FROM gardien_meta WHERE cle = 'dernier_cycle_le'").fetchone()
        return ligne["valeur"] if ligne else None

    def _depuis_ligne(self, ligne: sqlite3.Row) -> Tache:
        return Tache(
            empreinte=ligne["empreinte"], categorie=ligne["categorie"],
            gravite=ligne["gravite"], description=ligne["description"],
            fichier=ligne["fichier"], preuve=ligne["preuve"],
            etat=EtatTache(ligne["etat"]), decouverte_le=ligne["decouverte_le"],
            vue_pour_la_derniere_fois_le=ligne["vue_pour_la_derniere_fois_le"],
            occurrences=ligne["occurrences"], tentatives=ligne["tentatives"],
        )

    def enregistrer_constats(self, constats: List[Constat]) -> "ResultatTriage":
        """Un constat déjà vu (même empreinte) devient une réapparition, pas
        une nouvelle tâche — c'est ce qui évite de redécouvrir le même
        problème à chaque cycle. Un constat disparu (plus produit par le
        diagnostic) n'est PAS effacé : une tâche existante reste jusqu'à
        `marquer_resolue`, pour qu'une régression future retrouve son
        historique."""
        maintenant = _maintenant()
        nouvelles, revues = 0, 0
        with closing(self._connexion()) as connexion:
            for constat in constats:
                existante = connexion.execute(
                    "SELECT empreinte, occurrences FROM taches_maintenance WHERE empreinte = ?",
                    (constat.empreinte,)).fetchone()
                if existante is None:
                    connexion.execute(
                        "INSERT INTO taches_maintenance "
                        "(empreinte, categorie, gravite, description, fichier, preuve, "
                        " etat, decouverte_le, vue_pour_la_derniere_fois_le, occurrences) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                        (constat.empreinte, constat.categorie, constat.gravite,
                         constat.description, constat.fichier, constat.preuve,
                         EtatTache.DECOUVERTE.value, maintenant, maintenant))
                    nouvelles += 1
                else:
                    connexion.execute(
                        "UPDATE taches_maintenance SET occurrences = ?, "
                        "vue_pour_la_derniere_fois_le = ?, preuve = ? WHERE empreinte = ?",
                        (existante["occurrences"] + 1, maintenant, constat.preuve,
                         constat.empreinte))
                    revues += 1
            connexion.commit()
        return ResultatTriage(nouvelles=nouvelles, revues=revues, total=len(constats))

    def marquer_resolue(self, empreinte: str) -> bool:
        """Une tâche dont le diagnostic ne trouve plus trace — vérifiée
        résolue, jamais supposée : `executer_cycle` n'appelle ceci que pour
        une empreinte absente du dernier passage ET encore ouverte."""
        with closing(self._connexion()) as connexion:
            curseur = connexion.execute(
                "UPDATE taches_maintenance SET etat = ? WHERE empreinte = ? "
                "AND etat NOT IN (?, ?)",
                (EtatTache.TERMINEE.value, empreinte,
                 EtatTache.TERMINEE.value, EtatTache.ECHOUEE.value))
            connexion.commit()
            return curseur.rowcount > 0

    def ouvertes(self, categorie: Optional[str] = None) -> List[Tache]:
        """Tout ce qui n'est ni terminé ni différé — trié du plus urgent au
        moins urgent, à ancienneté égale la plus ancienne d'abord."""
        with closing(self._connexion()) as connexion:
            if categorie:
                lignes = connexion.execute(
                    "SELECT * FROM taches_maintenance WHERE etat NOT IN (?, ?) "
                    "AND categorie = ?",
                    (EtatTache.TERMINEE.value, EtatTache.DIFFEREE.value, categorie)
                ).fetchall()
            else:
                lignes = connexion.execute(
                    "SELECT * FROM taches_maintenance WHERE etat NOT IN (?, ?)",
                    (EtatTache.TERMINEE.value, EtatTache.DIFFEREE.value)
                ).fetchall()
        taches = [self._depuis_ligne(ligne) for ligne in lignes]
        return sorted(taches, key=lambda t: (
            ORDRE_GRAVITE.index(t.gravite) if t.gravite in ORDRE_GRAVITE else len(ORDRE_GRAVITE),
            t.decouverte_le))

    def toutes(self) -> List[Tache]:
        with closing(self._connexion()) as connexion:
            lignes = connexion.execute("SELECT * FROM taches_maintenance").fetchall()
        return [self._depuis_ligne(ligne) for ligne in lignes]


@dataclass(frozen=True)
class ResultatTriage:
    nouvelles: int
    revues: int
    total: int
