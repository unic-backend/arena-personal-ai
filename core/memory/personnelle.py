"""La memoire personnelle : ce qu'ARENA sait de son proprietaire, et d'ou il le sait.

La memoire actuelle tient en trois tables et six messages. `/chat` construit son
prompt avec `get_recent_history(limit=6)` : au-dela, ARENA ne se souvient de
rien. « Continue le projet d'il y a quatre mois » est impossible, et pas par
manque de place — par manque de structure.

Ce module ajoute la structure. Il ne remplace pas `MemoryManager` : la
conversation courante et les faits cles y restent, et `migrer_depuis()` importe
ce qui s'y trouve deja sans rien effacer.

**Quatre regles, et la premiere est celle qui coute le plus cher a enfreindre :**

1. **Une supposition ne devient jamais un fait toute seule.** La specification
   le demande explicitement : FAIT, PREFERENCE, INFERENCE et CONTEXTE_TEMPORAIRE
   sont quatre natures distinctes. Une `INFERENCE` ne devient `FAIT` que par
   `confirmer()`, qui exige une source nouvelle. Aucun autre chemin ne l'y mene.

2. **Rien n'entre sans source.** Un souvenir sans origine est une affirmation
   sans auteur ; six mois plus tard, personne ne peut le verifier ni le corriger.
   Un depot sans source est refuse.

3. **Le contexte temporaire expire.** « Il est sur le chantier de Medina » est
   vrai aujourd'hui. Le garder trois mois ferait dire a ARENA une chose fausse
   avec l'assurance d'un fait.

4. **L'importance se declare, elle ne s'invente pas.** Elle vit entre 0 et 1,
   vaut 0,5 par defaut — le milieu, pas le haut. Un souvenir n'est pas important
   parce qu'il vient d'etre ecrit.

Mission ARENA x AI MEMORY VAULT (11/09/2026, DEC-0090) : audit de
`ai-encryption-tool/ai`, rapport complet -> `docs/audits/ai_memory_vault_audit.md`.
Trois manques reels, mesures avant d'ecrire une ligne (aucun `rejeter()`, aucun
`supprimer()`, aucun chiffrement au repos dans ce module) -> combles ICI, jamais
dans un second systeme de memoire :

5. **Rejeter n'est pas « ne pas encore approuver ».** `Nature.INFERENCE` porte
   deja le « pas encore approuve » (promu par `confirmer()`, jamais seul). Ce
   qui manquait est distinct : un souvenir que le proprietaire a explicitement
   dit FAUX. `Etat.REJETE` (via `rejeter()`) l'exclut de la lecture par defaut,
   sans le detruire — une decision se garde, meme celle de dire non.

6. **Un souvenir sensible n'est illisible en clair nulle part sur le disque.**
   `sensible=True` (via `core/memory/chiffrement.py`) chiffre `contenu` avant
   l'ecriture (AES-256-GCM, cle derivee d'une phrase de passe jamais dans le
   code). Sans coffre configure, `retenir(..., sensible=True)` refuse plutot
   que d'ecrire en clair sous couvert de securite.
"""
import json
import logging
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.journal import masquer
from core.memory.chiffrement import VARIABLE_PASSPHRASE, Coffre, EchecDechiffrement
from scripts.scanner_secrets import MOTIFS_NOMMES as _MOTIFS_SECRETS_CONNUS
from scripts.scanner_secrets import masquer as _masquer_valeur

logger = logging.getLogger("usman.memoire.personnelle")


class TypeSouvenir(str, Enum):
    """Quatre memoires, parce qu'on ne se souvient pas de tout de la meme facon."""

    EPISODIQUE = "EPISODIC"      # ce qui s'est passe, date : « le 4 aout, 18 parois »
    SEMANTIQUE = "SEMANTIC"      # ce qui est vrai : « le tarif pose est 5000 F/m2 »
    PROCEDURALE = "PROCEDURAL"   # comment on fait : « un devis se numerote UC-AAAA-MMJJ »
    TACHE = "TASK"               # ce qui reste a faire


class Nature(str, Enum):
    """D'ou vient ce qu'on croit savoir. La specification en demande quatre.

    L'ordre compte : `INFERENCE` est ce qu'ARENA a deduit, pas ce qu'on lui a
    dit. Les confondre est la facon la plus discrete de fabriquer un mensonge
    durable.
    """

    FAIT = "FACT"                            # le proprietaire l'a dit, ou un document l'atteste
    PREFERENCE = "PREFERENCE"                # un gout, qui peut changer sans etre faux
    INFERENCE = "INFERENCE"                  # ARENA l'a deduit : jamais un fait
    CONTEXTE_TEMPORAIRE = "TEMPORARY_CONTEXT"  # vrai maintenant, faux bientot


class Etat(str, Enum):
    """Le cycle de vie d'un souvenir — orthogonal a sa nature.

    `Nature` dit D'OU vient ce qu'on croit savoir (fait, deduction...).
    `Etat` dit CE QUI EN A ETE DECIDE depuis. Une `INFERENCE` jamais confirmee
    est deja lisible (elle porte sa reserve dans sa nature) ; un souvenir
    `REJETE` ne doit plus apparaitre du tout dans la lecture par defaut, quelle
    que soit sa nature — c'est la seule chose que `Nature` seule ne pouvait pas
    dire.
    """

    ACTIF = "ACTIVE"        # lu normalement
    REJETE = "REJECTED"     # le proprietaire a dit non — garde, jamais rendu par defaut
    ARCHIVE = "ARCHIVED"    # retire du service courant, garde pour l'audit


# Un contexte temporaire sans echeance explicite vaut pour la journee.
DUREE_CONTEXTE_HEURES = 12

# Le milieu, jamais le haut : un souvenir n'est pas important parce qu'il est neuf.
IMPORTANCE_PAR_DEFAUT = 0.5


def _maintenant() -> datetime:
    """Isole pour que les tests fixent l'heure."""
    return datetime.now(timezone.utc)


def _motif_secret_dans(contenu: str) -> Optional[str]:
    """Le contenu porte-t-il, litteralement, la forme d'un secret connu ?

    Reutilise `scripts/scanner_secrets.py::MOTIFS_NOMMES` — la meme liste a
    haute confiance qui protege un commit, jamais une seconde liste inventee
    ici. Rend le nom du motif trouve (jamais la valeur), ou None.
    """
    for nom, motif in _MOTIFS_SECRETS_CONNUS:
        if motif.search(contenu):
            return nom
    return None


@dataclass(frozen=True)
class Souvenir:
    """Une chose retenue, avec sa nature, son origine et son poids.

    Attributes:
        contenu: le souvenir lui-meme, en clair.
        type: episodique, semantique, procedural ou tache.
        nature: fait, preference, inference ou contexte temporaire.
        source: d'ou il vient. Obligatoire.
        projet: le chantier, le client ou le dossier auquel il se rattache.
        importance: entre 0 et 1, declaree par l'appelant.
        metadonnees: informations libres, secrets masques.
        expire_le: pour un contexte temporaire, la date au-dela de laquelle il
            ne doit plus etre rendu.
        occurrences: combien de fois le souvenir a ete revu ou reconfirme.
        etat: actif, rejete ou archive — le cycle de vie, distinct de la nature.
        sensible: si vrai, `contenu` est chiffre au repos (voir `chiffrement.py`).
            Cette instance en memoire porte toujours le clair ; seule la ligne
            SQL est chiffree.
    """

    contenu: str
    type: TypeSouvenir
    nature: Nature
    source: str
    projet: Optional[str] = None
    importance: float = IMPORTANCE_PAR_DEFAUT
    metadonnees: Dict[str, Any] = field(default_factory=dict)
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    cree_le: str = ""
    vu_le: str = ""
    expire_le: Optional[str] = None
    occurrences: int = 1
    etat: Etat = Etat.ACTIF
    sensible: bool = False

    def est_perime(self, maintenant: Optional[datetime] = None) -> bool:
        """Vrai si le souvenir a une echeance et qu'elle est passee."""
        if not self.expire_le:
            return False
        try:
            limite = datetime.fromisoformat(self.expire_le)
        except ValueError:
            logger.warning("Echeance illisible (%s) : souvenir traite comme perime.",
                           self.expire_le)
            return True
        return (maintenant or _maintenant()) >= limite

    @property
    def est_une_supposition(self) -> bool:
        """Vrai pour ce qu'ARENA a deduit plutot qu'appris."""
        return self.nature is Nature.INFERENCE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifiant,
            "contenu": self.contenu,
            "type": self.type.value,
            "nature": self.nature.value,
            "source": self.source,
            "projet": self.projet,
            "importance": self.importance,
            "metadonnees": self.metadonnees,
            "cree_le": self.cree_le,
            "vu_le": self.vu_le,
            "expire_le": self.expire_le,
            "occurrences": self.occurrences,
            "etat": self.etat.value,
            "sensible": self.sensible,
        }


@dataclass(frozen=True)
class Entite:
    """Une personne, un chantier, une entreprise, un document.

    Elle porte sa source comme un souvenir : une entite apparue sans origine est
    une entite que personne ne peut confirmer.
    """

    nom: str
    type: str
    source: str
    projet: Optional[str] = None
    metadonnees: Dict[str, Any] = field(default_factory=dict)
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    cree_le: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifiant, "nom": self.nom, "type": self.type,
            "source": self.source, "projet": self.projet,
            "metadonnees": self.metadonnees, "cree_le": self.cree_le,
        }


@dataclass(frozen=True)
class Relation:
    """Un lien entre deux entites, avec sa propre source.

    La source de la relation n'est pas celle des entites : savoir que deux
    personnes existent ne dit pas d'ou vient l'idee qu'elles travaillent
    ensemble.
    """

    depuis: str
    lien: str
    vers: str
    source: str
    projet: Optional[str] = None
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    cree_le: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifiant, "depuis": self.depuis, "lien": self.lien,
            "vers": self.vers, "source": self.source, "projet": self.projet,
            "cree_le": self.cree_le,
        }


class MemoirePersonnelle:
    """Ecrit et relit les souvenirs, les entites et leurs liens."""

    TABLE_SOUVENIRS = "souvenirs"
    TABLE_ENTITES = "entites"
    TABLE_RELATIONS = "relations"

    def __init__(self, db_path: str = "data/database/memory.db",
                 coffre: Optional[Coffre] = None) -> None:
        """coffre: le service de chiffrement pour les souvenirs `sensible=True`.

        None par defaut : ARENA fonctionne identiquement sans lui, pour tout
        souvenir non sensible — c'est la mission ARENA x AI MEMORY VAULT (§11,
        local-first) qui l'exige : le chiffrement est une option, jamais une
        dependance de la memoire elle-meme.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.coffre = coffre
        self._creer_tables()

    def _connexion(self) -> sqlite3.Connection:
        connexion = sqlite3.connect(self.db_path)
        connexion.row_factory = sqlite3.Row
        # WAL : le serveur MCP (core/mcp/memory_server.py) et le backend ARENA
        # sont deux PROCESSUS distincts qui peuvent ecrire ce meme fichier en
        # meme temps — journal_mode par defaut (rollback) verrouille tout le
        # fichier pendant une ecriture, WAL laisse un lecteur continuer.
        connexion.execute("PRAGMA journal_mode=WAL")
        connexion.execute("PRAGMA busy_timeout=5000")
        return connexion

    def _creer_tables(self) -> None:
        with closing(self._connexion()) as connexion:
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_SOUVENIRS} (
                    identifiant  TEXT PRIMARY KEY,
                    contenu      TEXT NOT NULL,
                    type         TEXT NOT NULL,
                    nature       TEXT NOT NULL,
                    source       TEXT NOT NULL,
                    projet       TEXT,
                    importance   REAL NOT NULL,
                    metadonnees  TEXT NOT NULL,
                    cree_le      TEXT NOT NULL,
                    vu_le        TEXT NOT NULL,
                    expire_le    TEXT,
                    occurrences  INTEGER NOT NULL DEFAULT 1,
                    etat         TEXT NOT NULL DEFAULT 'ACTIVE',
                    sensible     INTEGER NOT NULL DEFAULT 0
                )
            """)
            # Migration d'une base existante (creee avant le 11/09/2026, DEC-0090) :
            # `CREATE TABLE IF NOT EXISTS` ne touche pas une table deja la, donc les
            # deux colonnes manquent sur un fichier deja en service. `ADD COLUMN`
            # est idempotent ici seulement parce qu'on le protege nous-memes —
            # SQLite le refuse sur une colonne deja presente.
            colonnes = {
                ligne["name"]
                for ligne in connexion.execute(
                    f"PRAGMA table_info({self.TABLE_SOUVENIRS})"
                ).fetchall()
            }
            if "etat" not in colonnes:
                connexion.execute(
                    f"ALTER TABLE {self.TABLE_SOUVENIRS} ADD COLUMN etat TEXT NOT NULL DEFAULT 'ACTIVE'"
                )
            if "sensible" not in colonnes:
                connexion.execute(
                    f"ALTER TABLE {self.TABLE_SOUVENIRS} ADD COLUMN sensible INTEGER NOT NULL DEFAULT 0"
                )
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_ENTITES} (
                    identifiant TEXT PRIMARY KEY,
                    nom         TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    source      TEXT NOT NULL,
                    projet      TEXT,
                    metadonnees TEXT NOT NULL,
                    cree_le     TEXT NOT NULL,
                    UNIQUE (nom, type)
                )
            """)
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_RELATIONS} (
                    identifiant TEXT PRIMARY KEY,
                    depuis      TEXT NOT NULL,
                    lien        TEXT NOT NULL,
                    vers        TEXT NOT NULL,
                    source      TEXT NOT NULL,
                    projet      TEXT,
                    cree_le     TEXT NOT NULL,
                    UNIQUE (depuis, lien, vers)
                )
            """)
            for colonne in ("projet", "type", "nature", "etat"):
                connexion.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_souvenirs_{colonne} "
                    f"ON {self.TABLE_SOUVENIRS} ({colonne})"
                )
            connexion.commit()

    # --- Ecriture -------------------------------------------------------------

    def retenir(
        self,
        contenu: str,
        type: TypeSouvenir,
        nature: Nature,
        source: str,
        projet: Optional[str] = None,
        importance: float = IMPORTANCE_PAR_DEFAUT,
        metadonnees: Optional[Dict[str, Any]] = None,
        duree_heures: Optional[int] = None,
        sensible: bool = False,
    ) -> Souvenir:
        """Retient quelque chose. La source est obligatoire.

        Args:
            sensible: si vrai, `contenu` est chiffre au repos (`coffre` doit
                etre configure — voir `core/memory/chiffrement.py`).

        Raises:
            ValueError: contenu vide, source vide, importance hors de [0, 1],
                contenu ayant la forme d'un secret connu (mission §35 — un
                secret appartient au stockage de secrets, jamais a la memoire
                semantique), ou `sensible=True` sans coffre configure.
        """
        if not (contenu or "").strip():
            raise ValueError("Un souvenir vide n'est pas un souvenir.")
        if not (source or "").strip():
            raise ValueError(
                "Un souvenir sans source est une affirmation sans auteur : "
                "personne ne pourra le verifier ni le corriger."
            )
        if not 0.0 <= importance <= 1.0:
            raise ValueError(f"L'importance vit entre 0 et 1, pas {importance}.")

        motif = _motif_secret_dans(contenu)
        if motif is not None:
            raise ValueError(
                f"Ce contenu a la forme d'un secret connu ({motif}) : "
                f"{_masquer_valeur(contenu.strip())}. Un secret appartient au "
                "stockage de secrets (variables d'environnement), jamais a la "
                "memoire semantique."
            )
        if sensible and self.coffre is None:
            raise ValueError(
                "sensible=True exige un coffre configure "
                f"({VARIABLE_PASSPHRASE} absente) : refuse plutot que "
                "d'ecrire ce souvenir en clair sous couvert de securite."
            )

        debut = _maintenant()
        expire_le = None
        if nature is Nature.CONTEXTE_TEMPORAIRE:
            heures = duree_heures if duree_heures is not None else DUREE_CONTEXTE_HEURES
            expire_le = (debut + timedelta(hours=heures)).isoformat(timespec="seconds")
        elif duree_heures is not None:
            expire_le = (debut + timedelta(hours=duree_heures)).isoformat(timespec="seconds")

        souvenir = Souvenir(
            contenu=contenu.strip(), type=type, nature=nature, source=source.strip(),
            projet=projet, importance=importance,
            metadonnees=masquer(dict(metadonnees or {})),
            cree_le=debut.isoformat(timespec="seconds"),
            vu_le=debut.isoformat(timespec="seconds"),
            expire_le=expire_le,
            sensible=sensible,
        )
        self._ecrire(souvenir)
        return souvenir

    def _ecrire(self, souvenir: Souvenir) -> None:
        contenu_stocke = (
            self.coffre.chiffrer(souvenir.contenu) if souvenir.sensible else souvenir.contenu
        )
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"INSERT INTO {self.TABLE_SOUVENIRS} (identifiant, contenu, type, nature, "
                f"source, projet, importance, metadonnees, cree_le, vu_le, expire_le, "
                f"occurrences, etat, sensible) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    souvenir.identifiant, contenu_stocke, souvenir.type.value,
                    souvenir.nature.value, souvenir.source, souvenir.projet,
                    souvenir.importance,
                    json.dumps(souvenir.metadonnees, ensure_ascii=False),
                    souvenir.cree_le, souvenir.vu_le, souvenir.expire_le,
                    souvenir.occurrences, souvenir.etat.value, int(souvenir.sensible),
                ),
            )
            connexion.commit()

    def confirmer(self, identifiant: str, source: str) -> Optional[Souvenir]:
        """Le **seul** chemin par lequel une inference devient un fait.

        Elle exige une source nouvelle : c'est ce qui distingue « le
        proprietaire me l'a confirme » de « je le pense depuis assez longtemps
        pour y croire ».

        Args:
            identifiant: le souvenir a confirmer.
            source: qui ou quoi le confirme. Obligatoire.

        Returns:
            Le souvenir mis a jour, ou None s'il n'existe pas.

        Raises:
            ValueError: source vide.
        """
        if not (source or "").strip():
            raise ValueError(
                "Confirmer sans source, c'est promouvoir une supposition en fait "
                "sur la foi de rien."
            )

        souvenir = self.lire(identifiant)
        if souvenir is None:
            return None

        nouvelle_nature = (
            Nature.FAIT if souvenir.nature is Nature.INFERENCE else souvenir.nature
        )
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"UPDATE {self.TABLE_SOUVENIRS} SET nature = ?, source = ?, vu_le = ?, "
                f"occurrences = occurrences + 1 WHERE identifiant = ?",
                (
                    nouvelle_nature.value,
                    f"{souvenir.source} + {source.strip()}",
                    _maintenant().isoformat(timespec="seconds"),
                    identifiant,
                ),
            )
            connexion.commit()
        return self.lire(identifiant)

    def _changer_etat(self, identifiant: str, nouvel_etat: Etat, source: str,
                       verbe: str) -> Optional[Souvenir]:
        """Le coeur commun de `rejeter`/`archiver`/`reactiver` : un changement
        d'etat est toujours trace (source, horodatage), jamais anonyme."""
        if not (source or "").strip():
            raise ValueError(
                f"{verbe} sans source ne dit pas QUI a decide — "
                "personne ne pourra le corriger."
            )
        souvenir = self.lire(identifiant)
        if souvenir is None:
            return None
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"UPDATE {self.TABLE_SOUVENIRS} SET etat = ?, source = ?, vu_le = ?, "
                f"occurrences = occurrences + 1 WHERE identifiant = ?",
                (
                    nouvel_etat.value,
                    f"{souvenir.source} + {source.strip()}",
                    _maintenant().isoformat(timespec="seconds"),
                    identifiant,
                ),
            )
            connexion.commit()
        return self.lire(identifiant)

    def rejeter(self, identifiant: str, source: str) -> Optional[Souvenir]:
        """Le proprietaire (ou une regle de validation) dit que ce souvenir est
        FAUX. Distinct de "pas encore confirme" : un `INFERENCE` jamais
        confirme reste lisible avec sa reserve, un souvenir `REJETE` ne
        reapparait plus dans la lecture normale (`souvenirs()`), quelle que
        soit sa nature. Rien n'est detruit : `lire()` par identifiant et
        `souvenirs(inclure_rejetes=True)` continuent de le rendre."""
        return self._changer_etat(identifiant, Etat.REJETE, source, "Rejeter")

    def archiver(self, identifiant: str, source: str) -> Optional[Souvenir]:
        """Retire un souvenir du service courant sans le rejeter (il n'etait
        pas faux, il n'est plus pertinent) ni le detruire — pour l'audit."""
        return self._changer_etat(identifiant, Etat.ARCHIVE, source, "Archiver")

    def reactiver(self, identifiant: str, source: str) -> Optional[Souvenir]:
        """Annule un `rejeter()`/`archiver()` anterieur. Une decision de
        gouvernance se corrige, elle ne s'enferme pas."""
        return self._changer_etat(identifiant, Etat.ACTIF, source, "Reactiver")

    def supprimer(self, identifiant: str) -> bool:
        """Suppression reelle, definitive — jamais un tombstone qui continuerait
        d'occuper une place. Utilisee quand `rejeter()` (garder, mais exclu) ne
        suffit pas : un import errone, un doublon exact, une demande explicite
        d'effacement (mission §28/§36 — le proprietaire garde le controle de
        la retention).

        Il n'existe qu'UN endroit ou un souvenir vit (`TABLE_SOUVENIRS`) —
        contrairement a AI Memory Vault (base + index vectoriel Qdrant
        separes, DEC-0090), la recherche semantique d'ARENA
        (`core/memory/semantique.py::recuperer_semantique`) reembete a la
        volee depuis `souvenirs()` a chaque appel, jamais depuis un index
        persistant : rien d'autre a purger pour qu'un souvenir supprime
        cesse reellement d'apparaitre.

        Returns:
            Vrai si un souvenir a ete supprime, faux s'il n'existait pas.
        """
        with closing(self._connexion()) as connexion:
            curseur = connexion.execute(
                f"DELETE FROM {self.TABLE_SOUVENIRS} WHERE identifiant = ?", (identifiant,)
            )
            connexion.commit()
        return curseur.rowcount > 0

    # --- Lecture --------------------------------------------------------------

    def _depuis_ligne(self, ligne: sqlite3.Row) -> Souvenir:
        colonnes = ligne.keys()
        etat = Etat(ligne["etat"]) if "etat" in colonnes and ligne["etat"] else Etat.ACTIF
        sensible = bool(ligne["sensible"]) if "sensible" in colonnes else False
        contenu = ligne["contenu"]
        if sensible:
            contenu = self._dechiffrer_ou_signaler(ligne["identifiant"], contenu)
        return Souvenir(
            identifiant=ligne["identifiant"], contenu=contenu,
            type=TypeSouvenir(ligne["type"]), nature=Nature(ligne["nature"]),
            source=ligne["source"], projet=ligne["projet"],
            importance=ligne["importance"], metadonnees=json.loads(ligne["metadonnees"]),
            cree_le=ligne["cree_le"], vu_le=ligne["vu_le"],
            expire_le=ligne["expire_le"], occurrences=ligne["occurrences"],
            etat=etat, sensible=sensible,
        )

    def _dechiffrer_ou_signaler(self, identifiant: str, contenu_stocke: str) -> str:
        """Dechiffre un contenu sensible, ou rend un etat lisible plutot que de
        faire echouer toute une lecture (`souvenirs()`) pour UNE ligne illisible.

        Jamais de texte en clair fabrique : l'appelant sait que le souvenir
        existe et pourquoi il ne peut pas le lire, jamais une supposition sur
        son contenu.
        """
        if self.coffre is None:
            return "[souvenir sensible — coffre non configure dans ce processus]"
        try:
            return self.coffre.dechiffrer(contenu_stocke)
        except EchecDechiffrement as erreur:
            logger.warning(
                "Souvenir sensible %s illisible avec le coffre configure : %s",
                identifiant, erreur,
            )
            return "[souvenir sensible — dechiffrement refuse (mauvaise cle ou donnee alteree)]"

    def lire(self, identifiant: str) -> Optional[Souvenir]:
        """Relit un souvenir par son identifiant, perime ou non."""
        with closing(self._connexion()) as connexion:
            ligne = connexion.execute(
                f"SELECT * FROM {self.TABLE_SOUVENIRS} WHERE identifiant = ?", (identifiant,)
            ).fetchone()
        return self._depuis_ligne(ligne) if ligne else None

    def souvenirs(
        self,
        type: Optional[TypeSouvenir] = None,
        nature: Optional[Nature] = None,
        projet: Optional[str] = None,
        limite: int = 50,
        inclure_perimes: bool = False,
        inclure_rejetes: bool = False,
        inclure_archives: bool = False,
    ) -> List[Souvenir]:
        """Les souvenirs, filtres. Les perimes, rejetes et archives sont ecartes
        sauf demande expresse.

        Rendre un contexte temporaire perime ferait dire a ARENA une chose fausse
        avec l'assurance d'un fait. Rendre un souvenir REJETE dans la lecture
        normale annulerait le sens meme de `rejeter()` — le proprietaire a dit
        non, pas "pas encore" — c'est pour cela que les trois se demandent.
        """
        etats_admis = [Etat.ACTIF.value]
        if inclure_rejetes:
            etats_admis.append(Etat.REJETE.value)
        if inclure_archives:
            etats_admis.append(Etat.ARCHIVE.value)

        requete = f"SELECT * FROM {self.TABLE_SOUVENIRS} WHERE etat IN ({','.join('?' * len(etats_admis))})"
        arguments: List[Any] = list(etats_admis)
        if type is not None:
            requete += " AND type = ?"
            arguments.append(type.value)
        if nature is not None:
            requete += " AND nature = ?"
            arguments.append(nature.value)
        if projet is not None:
            requete += " AND projet = ?"
            arguments.append(projet)
        requete += " ORDER BY importance DESC, cree_le DESC, rowid DESC LIMIT ?"
        arguments.append(limite)

        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()

        souvenirs = [self._depuis_ligne(ligne) for ligne in lignes]
        if inclure_perimes:
            return souvenirs
        return [souvenir for souvenir in souvenirs if not souvenir.est_perime()]

    def projets(self) -> List[str]:
        """Les projets connus, tries. C'est par la qu'on retrouve un chantier ancien."""
        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(
                f"SELECT DISTINCT projet FROM {self.TABLE_SOUVENIRS} "
                f"WHERE projet IS NOT NULL ORDER BY projet"
            ).fetchall()
        return [ligne["projet"] for ligne in lignes]

    # --- Entites et relations --------------------------------------------------

    def enregistrer_entite(
        self, nom: str, type: str, source: str,
        projet: Optional[str] = None, metadonnees: Optional[Dict[str, Any]] = None,
    ) -> Entite:
        """Enregistre une entite. Reenregistrer la meme met a jour sa source.

        Raises:
            ValueError: nom vide ou source vide.
        """
        if not (nom or "").strip():
            raise ValueError("Une entite sans nom n'est pas une entite.")
        if not (source or "").strip():
            raise ValueError("Une entite sans source ne peut etre confirmee par personne.")

        entite = Entite(
            nom=nom.strip(), type=type, source=source.strip(), projet=projet,
            metadonnees=masquer(dict(metadonnees or {})),
            cree_le=_maintenant().isoformat(timespec="seconds"),
        )
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"INSERT INTO {self.TABLE_ENTITES} (identifiant, nom, type, source, projet, "
                f"metadonnees, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?) "
                f"ON CONFLICT(nom, type) DO UPDATE SET source = excluded.source, "
                f"projet = COALESCE(excluded.projet, projet), "
                f"metadonnees = excluded.metadonnees",
                (
                    entite.identifiant, entite.nom, entite.type, entite.source,
                    entite.projet, json.dumps(entite.metadonnees, ensure_ascii=False),
                    entite.cree_le,
                ),
            )
            connexion.commit()
        return entite

    def entites(self, projet: Optional[str] = None, type: Optional[str] = None) -> List[Entite]:
        """Les entites connues, filtrees."""
        requete = f"SELECT * FROM {self.TABLE_ENTITES} WHERE 1 = 1"
        arguments: List[Any] = []
        if projet is not None:
            requete += " AND projet = ?"
            arguments.append(projet)
        if type is not None:
            requete += " AND type = ?"
            arguments.append(type)
        requete += " ORDER BY nom"

        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()
        return [
            Entite(
                identifiant=ligne["identifiant"], nom=ligne["nom"], type=ligne["type"],
                source=ligne["source"], projet=ligne["projet"],
                metadonnees=json.loads(ligne["metadonnees"]), cree_le=ligne["cree_le"],
            )
            for ligne in lignes
        ]

    def relier(
        self, depuis: str, lien: str, vers: str, source: str, projet: Optional[str] = None,
    ) -> Relation:
        """Relie deux entites. La relation porte **sa propre** source.

        Raises:
            ValueError: source vide.
        """
        if not (source or "").strip():
            raise ValueError(
                "Une relation sans source est une supposition sur un lien : "
                "savoir que deux entites existent ne dit pas qu'elles sont liees."
            )

        relation = Relation(
            depuis=depuis, lien=lien, vers=vers, source=source.strip(), projet=projet,
            cree_le=_maintenant().isoformat(timespec="seconds"),
        )
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"INSERT INTO {self.TABLE_RELATIONS} (identifiant, depuis, lien, vers, "
                f"source, projet, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?) "
                f"ON CONFLICT(depuis, lien, vers) DO UPDATE SET source = excluded.source",
                (
                    relation.identifiant, relation.depuis, relation.lien, relation.vers,
                    relation.source, relation.projet, relation.cree_le,
                ),
            )
            connexion.commit()
        return relation

    def relations(self, depuis: Optional[str] = None, vers: Optional[str] = None) -> List[Relation]:
        """Les liens connus, filtres par extremite."""
        requete = f"SELECT * FROM {self.TABLE_RELATIONS} WHERE 1 = 1"
        arguments: List[Any] = []
        if depuis is not None:
            requete += " AND depuis = ?"
            arguments.append(depuis)
        if vers is not None:
            requete += " AND vers = ?"
            arguments.append(vers)
        requete += " ORDER BY cree_le DESC"

        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()
        return [
            Relation(
                identifiant=ligne["identifiant"], depuis=ligne["depuis"], lien=ligne["lien"],
                vers=ligne["vers"], source=ligne["source"], projet=ligne["projet"],
                cree_le=ligne["cree_le"],
            )
            for ligne in lignes
        ]

    # --- Migration --------------------------------------------------------------

    def migrer_depuis_long_terme(self, source: str = "long_term_memory") -> int:
        """Importe `long_term_memory` sans rien effacer ni modifier.

        L'ancienne table reste intacte : `MemoryManager` continue de la lire et
        de l'ecrire. Une migration qui supprime sa source ne se rejoue pas, et
        ne se verifie plus.

        Les entrees importees sont des `FAIT` — le proprietaire les a posees
        lui-meme, ce ne sont pas des deductions d'ARENA.

        Returns:
            Le nombre de lignes importees. Les doublons ne sont pas reimportes.
        """
        with closing(self._connexion()) as connexion:
            existe = connexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='long_term_memory'"
            ).fetchone()
            if not existe:
                logger.info("Aucune table long_term_memory : rien a migrer.")
                return 0

            anciennes = connexion.execute(
                "SELECT category, key, value, metadata FROM long_term_memory"
            ).fetchall()

            deja = {
                ligne["contenu"]
                for ligne in connexion.execute(
                    f"SELECT contenu FROM {self.TABLE_SOUVENIRS} WHERE source LIKE ?",
                    (f"{source}%",),
                ).fetchall()
            }

        importees = 0
        for ancienne in anciennes:
            contenu = f"{ancienne['key']} : {ancienne['value']}"
            if contenu in deja:
                continue
            try:
                metadonnees = json.loads(ancienne["metadata"]) if ancienne["metadata"] else {}
            except (json.JSONDecodeError, TypeError):
                metadonnees = {"metadata_brute": ancienne["metadata"]}
            self.retenir(
                contenu=contenu,
                type=TypeSouvenir.SEMANTIQUE,
                nature=Nature.FAIT,
                source=f"{source}.{ancienne['category']}",
                metadonnees=metadonnees,
            )
            importees += 1

        logger.info("Migration memoire : %s entree(s) importee(s).", importees)
        return importees
