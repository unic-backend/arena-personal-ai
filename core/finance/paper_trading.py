"""Portefeuille simule — comptabilite deterministe, aucun ordre reel.

Mission §10/§11/§14 (voir docs/DECISIONS.md) : ARENA ne signe jamais de
transaction et ne detient jamais de cle de portefeuille. Ce module simule un
compte de A a Z, en SQLite, pour que le moteur de risque et l'agent finance
puissent etre evalues sans jamais toucher un centime ni un jeton reel — et
pour que le proprietaire puisse s'entrainer a lire une analyse sans consequence.

Aucune capacite « acheter/vendre reel » n'existe nulle part dans ce depot :
regarder `core/connectors/market_data.py` suffit a le verifier, il ne declare
que des lectures. Ce module est la seule chose qui ressemble a un « trade »,
et il ne fait jamais rien sortir d'ARENA.
"""
import logging
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("usman.finance.paper_trading")

SOLDE_INITIAL_DEFAUT = 100_000.0


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Transaction:
    identifiant: str
    horodatage: str
    portefeuille: str
    actif: str
    sens: str  # "ACHAT" ou "VENTE"
    quantite: float
    prix: float
    valeur: float
    solde_especes_apres: float
    pnl_realise: Optional[float] = None  # rempli seulement pour une VENTE

    def to_dict(self) -> Dict[str, object]:
        return {
            "identifiant": self.identifiant, "horodatage": self.horodatage,
            "portefeuille": self.portefeuille, "actif": self.actif, "sens": self.sens,
            "quantite": self.quantite, "prix": self.prix, "valeur": self.valeur,
            "solde_especes_apres": self.solde_especes_apres, "pnl_realise": self.pnl_realise,
        }


@dataclass(frozen=True)
class ResultatOrdreSimule:
    """Ce qu'une tentative d'achat/vente simulee a produit. Jamais un
    `ResultatAction` (`core/actions/resultat.py`) : ce vocabulaire est reserve
    aux actions a EFFET EXTERNE, et rien ici ne quitte ARENA — c'est
    exactement le point de ce module."""

    reussi: bool
    message: str
    transaction: Optional[Transaction] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "reussi": self.reussi, "message": self.message,
            "transaction": self.transaction.to_dict() if self.transaction else None,
        }


@dataclass(frozen=True)
class Position:
    actif: str
    quantite: float
    prix_moyen_achat: float

    def valeur(self, prix_actuel: float) -> float:
        return self.quantite * prix_actuel

    def pnl_non_realise(self, prix_actuel: float) -> float:
        return (prix_actuel - self.prix_moyen_achat) * self.quantite


class PortefeuilleSimule:
    """Un compte simule : especes + positions, persiste en SQLite (meme
    fichier que la memoire et le journal — `data/database/memory.db`, deux
    tables dediees). Plusieurs portefeuilles peuvent coexister, distingues
    par `nom` — un seul par defaut aujourd'hui, mais rien n'empeche le
    proprietaire d'en ouvrir un second pour comparer deux strategies."""

    TABLE_COMPTES = "finance_comptes_simules"
    TABLE_POSITIONS = "finance_positions_simulees"
    TABLE_TRANSACTIONS = "finance_transactions_simulees"

    def __init__(
        self, nom: str = "defaut", db_path: str = "data/database/memory.db",
        solde_initial: float = SOLDE_INITIAL_DEFAUT,
    ) -> None:
        self.nom = nom
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._solde_initial = solde_initial
        self._creer_tables()
        self._initialiser_compte_si_absent()

    def _connexion(self) -> sqlite3.Connection:
        connexion = sqlite3.connect(self.db_path)
        connexion.row_factory = sqlite3.Row
        return connexion

    def _creer_tables(self) -> None:
        with closing(self._connexion()) as connexion:
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_COMPTES} (
                    portefeuille    TEXT PRIMARY KEY,
                    solde_especes   REAL NOT NULL,
                    solde_initial   REAL NOT NULL,
                    cree_le         TEXT NOT NULL
                )
            """)
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_POSITIONS} (
                    portefeuille       TEXT NOT NULL,
                    actif              TEXT NOT NULL,
                    quantite           REAL NOT NULL,
                    prix_moyen_achat   REAL NOT NULL,
                    PRIMARY KEY (portefeuille, actif)
                )
            """)
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_TRANSACTIONS} (
                    identifiant           TEXT PRIMARY KEY,
                    horodatage            TEXT NOT NULL,
                    portefeuille          TEXT NOT NULL,
                    actif                 TEXT NOT NULL,
                    sens                  TEXT NOT NULL,
                    quantite              REAL NOT NULL,
                    prix                  REAL NOT NULL,
                    valeur                REAL NOT NULL,
                    solde_especes_apres   REAL NOT NULL,
                    pnl_realise           REAL
                )
            """)
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_TRANSACTIONS}_horodatage "
                f"ON {self.TABLE_TRANSACTIONS} (horodatage DESC)"
            )
            connexion.commit()

    def _initialiser_compte_si_absent(self) -> None:
        with closing(self._connexion()) as connexion:
            ligne = connexion.execute(
                f"SELECT 1 FROM {self.TABLE_COMPTES} WHERE portefeuille = ?", (self.nom,)
            ).fetchone()
            if ligne is None:
                connexion.execute(
                    f"INSERT INTO {self.TABLE_COMPTES} (portefeuille, solde_especes, solde_initial, cree_le) "
                    f"VALUES (?, ?, ?, ?)",
                    (self.nom, self._solde_initial, self._solde_initial, _maintenant()),
                )
                connexion.commit()

    def solde_especes(self) -> float:
        with closing(self._connexion()) as connexion:
            ligne = connexion.execute(
                f"SELECT solde_especes FROM {self.TABLE_COMPTES} WHERE portefeuille = ?", (self.nom,)
            ).fetchone()
            return float(ligne["solde_especes"]) if ligne else 0.0

    def positions(self) -> Dict[str, Position]:
        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(
                f"SELECT actif, quantite, prix_moyen_achat FROM {self.TABLE_POSITIONS} "
                f"WHERE portefeuille = ? AND quantite > 0", (self.nom,)
            ).fetchall()
            return {
                ligne["actif"]: Position(ligne["actif"], ligne["quantite"], ligne["prix_moyen_achat"])
                for ligne in lignes
            }

    def acheter(self, actif: str, quantite: float, prix: float) -> ResultatOrdreSimule:
        """Achat simule. Refuse si le solde d'especes ne couvre pas le cout —
        aucun decouvert, aucune marge : la simulation ne peut jamais faire
        croire une capacite de levier qu'ARENA n'offre pas reellement."""
        if quantite <= 0 or prix <= 0:
            return ResultatOrdreSimule(False, "Quantite et prix doivent etre positifs.")

        cout = quantite * prix
        with closing(self._connexion()) as connexion:
            solde = float(connexion.execute(
                f"SELECT solde_especes FROM {self.TABLE_COMPTES} WHERE portefeuille = ?", (self.nom,)
            ).fetchone()["solde_especes"])

            if cout > solde:
                return ResultatOrdreSimule(
                    False, f"Solde insuffisant : {solde:.2f} disponible, {cout:.2f} necessaire.")

            position = connexion.execute(
                f"SELECT quantite, prix_moyen_achat FROM {self.TABLE_POSITIONS} "
                f"WHERE portefeuille = ? AND actif = ?", (self.nom, actif)
            ).fetchone()

            if position is None:
                nouvelle_quantite, nouveau_prix_moyen = quantite, prix
            else:
                ancienne_quantite = position["quantite"]
                nouvelle_quantite = ancienne_quantite + quantite
                # Prix moyen pondere par la quantite — la comptabilite
                # standard d'une position qui s'agrandit par lots.
                nouveau_prix_moyen = (
                    (ancienne_quantite * position["prix_moyen_achat"] + cout) / nouvelle_quantite
                )

            nouveau_solde = solde - cout
            connexion.execute(
                f"INSERT INTO {self.TABLE_POSITIONS} (portefeuille, actif, quantite, prix_moyen_achat) "
                f"VALUES (?, ?, ?, ?) ON CONFLICT(portefeuille, actif) DO UPDATE SET "
                f"quantite = excluded.quantite, prix_moyen_achat = excluded.prix_moyen_achat",
                (self.nom, actif, nouvelle_quantite, nouveau_prix_moyen),
            )
            connexion.execute(
                f"UPDATE {self.TABLE_COMPTES} SET solde_especes = ? WHERE portefeuille = ?",
                (nouveau_solde, self.nom),
            )
            transaction = Transaction(
                identifiant=str(uuid.uuid4()), horodatage=_maintenant(), portefeuille=self.nom,
                actif=actif, sens="ACHAT", quantite=quantite, prix=prix, valeur=cout,
                solde_especes_apres=nouveau_solde,
            )
            self._inserer_transaction(connexion, transaction)
            connexion.commit()

        return ResultatOrdreSimule(True, f"Achat simule : {quantite} {actif} a {prix:.2f}.", transaction)

    def vendre(self, actif: str, quantite: float, prix: float) -> ResultatOrdreSimule:
        """Vente simulee. Refuse si la position ne couvre pas la quantite —
        aucune vente a decouvert."""
        if quantite <= 0 or prix <= 0:
            return ResultatOrdreSimule(False, "Quantite et prix doivent etre positifs.")

        with closing(self._connexion()) as connexion:
            position = connexion.execute(
                f"SELECT quantite, prix_moyen_achat FROM {self.TABLE_POSITIONS} "
                f"WHERE portefeuille = ? AND actif = ?", (self.nom, actif)
            ).fetchone()

            detenue = position["quantite"] if position else 0.0
            if quantite > detenue:
                return ResultatOrdreSimule(
                    False, f"Position insuffisante : {detenue} {actif} detenu, {quantite} demande.")

            produit = quantite * prix
            pnl_realise = (prix - position["prix_moyen_achat"]) * quantite
            nouvelle_quantite = detenue - quantite

            connexion.execute(
                f"UPDATE {self.TABLE_POSITIONS} SET quantite = ? WHERE portefeuille = ? AND actif = ?",
                (nouvelle_quantite, self.nom, actif),
            )
            solde = float(connexion.execute(
                f"SELECT solde_especes FROM {self.TABLE_COMPTES} WHERE portefeuille = ?", (self.nom,)
            ).fetchone()["solde_especes"])
            nouveau_solde = solde + produit
            connexion.execute(
                f"UPDATE {self.TABLE_COMPTES} SET solde_especes = ? WHERE portefeuille = ?",
                (nouveau_solde, self.nom),
            )
            transaction = Transaction(
                identifiant=str(uuid.uuid4()), horodatage=_maintenant(), portefeuille=self.nom,
                actif=actif, sens="VENTE", quantite=quantite, prix=prix, valeur=produit,
                solde_especes_apres=nouveau_solde, pnl_realise=pnl_realise,
            )
            self._inserer_transaction(connexion, transaction)
            connexion.commit()

        return ResultatOrdreSimule(
            True, f"Vente simulee : {quantite} {actif} a {prix:.2f} (P&L realise {pnl_realise:+.2f}).",
            transaction)

    @staticmethod
    def _inserer_transaction(connexion: sqlite3.Connection, transaction: Transaction) -> None:
        connexion.execute(
            f"INSERT INTO {PortefeuilleSimule.TABLE_TRANSACTIONS} "
            f"(identifiant, horodatage, portefeuille, actif, sens, quantite, prix, valeur, "
            f"solde_especes_apres, pnl_realise) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (transaction.identifiant, transaction.horodatage, transaction.portefeuille,
             transaction.actif, transaction.sens, transaction.quantite, transaction.prix,
             transaction.valeur, transaction.solde_especes_apres, transaction.pnl_realise),
        )

    def historique(self, limite: int = 50) -> List[Transaction]:
        with closing(self._connexion()) as connexion:
            # `rowid DESC` en second tri : l'horodatage n'a qu'une precision
            # a la seconde (comme `core/actions/journal.py`), donc deux
            # transactions dans la meme seconde departagent sur l'ordre
            # d'insertion reel plutot que sur un ordre SQLite indefini.
            lignes = connexion.execute(
                f"SELECT * FROM {self.TABLE_TRANSACTIONS} WHERE portefeuille = ? "
                f"ORDER BY horodatage DESC, rowid DESC LIMIT ?", (self.nom, limite)
            ).fetchall()
            return [
                Transaction(
                    identifiant=ligne["identifiant"], horodatage=ligne["horodatage"],
                    portefeuille=ligne["portefeuille"], actif=ligne["actif"], sens=ligne["sens"],
                    quantite=ligne["quantite"], prix=ligne["prix"], valeur=ligne["valeur"],
                    solde_especes_apres=ligne["solde_especes_apres"], pnl_realise=ligne["pnl_realise"],
                )
                for ligne in lignes
            ]

    def valeur_totale(self, prix_actuels: Dict[str, float]) -> float:
        """Especes + valeur marquee au marche des positions. Une position
        dont le prix actuel n'est pas fourni n'est PAS comptee a zero — elle
        est ignoree du total, et `positions_sans_prix` le signale (voir
        `resume`)."""
        total = self.solde_especes()
        for actif, position in self.positions().items():
            if actif in prix_actuels:
                total += position.valeur(prix_actuels[actif])
        return total

    def resume(self, prix_actuels: Dict[str, float]) -> Dict[str, object]:
        positions = self.positions()
        sans_prix = [a for a in positions if a not in prix_actuels]
        pnl_par_position = {
            actif: position.pnl_non_realise(prix_actuels[actif])
            for actif, position in positions.items() if actif in prix_actuels
        }
        return {
            "portefeuille": self.nom,
            "solde_especes": self.solde_especes(),
            "solde_initial": self._solde_initial,
            "positions": {a: {"quantite": p.quantite, "prix_moyen_achat": p.prix_moyen_achat}
                         for a, p in positions.items()},
            "valeur_totale": self.valeur_totale(prix_actuels),
            "pnl_non_realise": pnl_par_position,
            "positions_sans_prix": sans_prix,
        }
