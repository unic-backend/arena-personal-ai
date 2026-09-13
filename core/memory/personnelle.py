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
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.actions.journal import masquer
from core.memory.chiffrement import VARIABLE_PASSPHRASE, Coffre, EchecDechiffrement
from scripts.scanner_secrets import MOTIFS_NOMMES as _MOTIFS_SECRETS_CONNUS
from scripts.scanner_secrets import masquer as _masquer_valeur

logger = logging.getLogger("usman.memoire.personnelle")


class TypeSouvenir(str, Enum):
    """Six memoires, parce qu'on ne se souvient pas de tout de la meme facon.

    Les quatre premieres sont d'origine. `DECISION` et `ERREUR` sont ajoutees
    le 13/09/2026, et elles ne sont PAS des episodes deguises :

    - un episode raconte **ce qui s'est passe**, et il est neutre ; une decision
      dit **ce qui a ete tranche**, donc ce qui n'est plus a rediscuter. Classee
      `EPISODIQUE`, elle se retrouve en concurrence d'importance avec tous les
      autres evenements du meme jour, et ARENA repose une question deja reglee ;
    - une erreur porte, en plus du fait, un **« ne pas refaire »**. C'est la
      seule categorie dont l'interet est d'etre remontee AVANT de recommencer,
      pas apres.

    Aucun changement de schema : la colonne `type` est `TEXT` sans contrainte
    `CHECK`. Une base existante lit et ecrit ces deux valeurs sans migration —
    c'est precisement pourquoi l'extension d'une zone verrouillee passe par
    l'enumeration et jamais par la table.
    """

    EPISODIQUE = "EPISODIC"      # ce qui s'est passe, date : « le 4 aout, 18 parois »
    SEMANTIQUE = "SEMANTIC"      # ce qui est vrai : « le tarif pose est 5000 F/m2 »
    PROCEDURALE = "PROCEDURAL"   # comment on fait : « un devis se numerote UC-AAAA-MMJJ »
    TACHE = "TASK"               # ce qui reste a faire
    DECISION = "DECISION"        # ce qui a ete tranche : « on ne travaille plus avec X »
    ERREUR = "MISTAKE"           # ce qui a rate, pour ne pas le refaire


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

# Ce qui joint les sources dans le champ `source` lisible. Nomme parce que la
# lecture d'une ligne d'avant DEC-0104 s'en sert pour savoir si le souvenir a
# deja ete confirme — pas pour compter combien de fois.
SEPARATEUR_SOURCES = " + "


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
        valide_depuis: la date A PARTIR DE LAQUELLE le contenu est vrai. C'est
            le miroir d'`expire_le`, et ce n'est pas `cree_le` : celui-ci dit
            quand le souvenir a ete ECRIT, celui-la depuis quand il est VRAI.
            « A partir du 1er octobre, le tarif passe a 5500 » s'enregistre en
            septembre et ne doit pas etre servi comme verite courante avant
            octobre. `None` veut dire « vrai depuis toujours », ce qui est le
            cas de la quasi-totalite des souvenirs.
        sources: les sources DISTINCTES qui affirment le contenu, dans leur
            ordre d'arrivee. `source` dit qui l'a dit en premier ; celle-ci dit
            combien de voix differentes le disent. Un document qui se repete
            trois fois reste UNE voix, et c'est toute la difference entre
            « corrobore » et « insiste ».
        occurrences: combien de fois le souvenir a ete revu ou reconfirme —
            distinct de `sources` : trois occurrences pour une seule source,
            c'est une source qui se repete, pas une confirmation.
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
    valide_depuis: Optional[str] = None
    sources: Tuple[str, ...] = ()
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

    def pas_encore_vrai(self, maintenant: Optional[datetime] = None) -> bool:
        """Vrai si le souvenir annonce une verite qui n'a pas encore commence.

        Le miroir exact d'`est_perime`. Sans lui, « a partir du 1er octobre, le
        tarif passe a 5500 » serait servi des septembre comme le tarif courant,
        et ARENA repondrait un prix faux avec l'assurance d'un fait — la faute
        precise que `DUREE_CONTEXTE_HEURES` evite dans l'autre sens.

        Une date illisible est traitee comme **pas encore vraie**, par la meme
        prudence qu'`est_perime` traite une echeance illisible comme passee :
        des deux erreurs possibles, taire un souvenir est moins couteux que
        d'affirmer une chose fausse.
        """
        if not self.valide_depuis:
            return False
        try:
            debut = datetime.fromisoformat(self.valide_depuis)
        except ValueError:
            logger.warning("Debut de validite illisible (%s) : souvenir tenu "
                           "pour pas encore vrai.", self.valide_depuis)
            return True
        return (maintenant or _maintenant()) < debut

    def est_en_vigueur(self, maintenant: Optional[datetime] = None) -> bool:
        """Vrai quand le souvenir est vrai MAINTENANT : commence et pas fini."""
        return not self.pas_encore_vrai(maintenant) and not self.est_perime(maintenant)

    @property
    def nombre_de_sources(self) -> Optional[int]:
        """Combien de voix DISTINCTES affirment le contenu — ou `None`.

        Derive de `sources`, jamais stocke : un compteur range a cote de la
        liste finit par la contredire, et c'est alors le compteur qu'on croit.

        `None` veut dire « jamais compte ici », et ce n'est pas `1`. Le cas
        reel est un souvenir ecrit avant le 13/09/2026 et deja confirme : son
        champ `source` porte « a + b », on sait qu'il a ete corrobore mais pas
        par combien de voix distinctes — decouper la chaine pour le deviner
        fabriquerait un chiffre. Un souvenir jamais confirme, lui, est sans
        ambiguite a une voix.
        """
        return len(self.sources) or None

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
            "valide_depuis": self.valide_depuis,
            "sources": list(self.sources),
            # Rendu a cote de la liste pour que l'appelant n'ait pas a la
            # compter lui-meme — et `None` plutot que `0` quand rien n'a compte.
            "nombre_de_sources": self.nombre_de_sources,
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


#: Ce que `_dechiffrer_ou_signaler` rend quand il ne PEUT pas lire un souvenir
#: sensible. Deux etats, jamais un texte en clair suppose. Ils sont nommes
#: parce qu'une recherche par mot-cle doit pouvoir les RECONNAITRE pour ne pas
#: les fouiller : sans cela, la question « pourquoi ce coffre ? » ferait
#: remonter tous les souvenirs illisibles, au seul motif que le mot « coffre »
#: figure dans leur message d'echec.
SANS_COFFRE = "[souvenir sensible — coffre non configure dans ce processus]"
DECHIFFREMENT_REFUSE = (
    "[souvenir sensible — dechiffrement refuse (mauvaise cle ou donnee alteree)]"
)


def est_un_echec_de_lecture(contenu: str) -> bool:
    """Vrai quand `contenu` est l'un des deux etats ci-dessus, pas un souvenir.

    A utiliser avant de FILTRER un contenu sensible sur des mots : un message
    d'echec n'est pas du texte du proprietaire, et le traiter comme tel
    fabriquerait une correspondance.
    """
    return contenu in (SANS_COFFRE, DECHIFFREMENT_REFUSE)


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
                    sensible     INTEGER NOT NULL DEFAULT 0,
                    valide_depuis TEXT,
                    sources      TEXT
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
            # Migration du 13/09/2026, meme forme que les deux au-dessus.
            # `NULL` sur une ligne existante veut dire « vrai depuis toujours »,
            # ce qui est exact : aucun souvenir d'avant n'annoncait une verite a
            # venir. **Aucune ligne n'est touchee.**
            if "valide_depuis" not in colonnes:
                connexion.execute(
                    f"ALTER TABLE {self.TABLE_SOUVENIRS} ADD COLUMN valide_depuis TEXT"
                )
            # Migration du 13/09/2026 (DEC-0104), meme forme que les trois
            # au-dessus. `NULL` ne veut PAS dire « zero source » : il veut dire
            # « les sources distinctes n'ont jamais ete comptees pour cette
            # ligne », et `_depuis_ligne` ne comble ce vide que quand la reponse
            # est certaine. **Aucune ligne n'est touchee.**
            if "sources" not in colonnes:
                connexion.execute(
                    f"ALTER TABLE {self.TABLE_SOUVENIRS} ADD COLUMN sources TEXT"
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
            # L'index du TRI, et non d'un filtre. Les quatre ci-dessus servent
            # les `WHERE` ; aucun ne sert `ORDER BY importance DESC, cree_le
            # DESC`, que TOUTE lecture de la memoire execute (`souvenirs()` et
            # `souvenirs_correspondant_a_des_mots()`, donc deux fois par
            # question). SQLite construisait donc un TEMP B-TREE a chaque fois.
            # Mesure du 12/09/2026, par `souvenirs(limite=500)` lui-meme sur
            # 50 000 souvenirs (500 rendus) : **20,56 ms sans l'index, 5,05 ms
            # avec** — x4,1. Le plan passe de
            # « idx_souvenirs_etat + USE TEMP B-TREE FOR ORDER BY » a
            # « idx_souvenirs_tri » seul.
            #
            # Pas de `DESC` dans l'index, et c'est mesure, pas suppose : les
            # deux colonnes descendent ENSEMBLE, donc SQLite parcourt l'index
            # croissant a l'envers. A 50 000 souvenirs, avec DESC 0,49 ms,
            # sans DESC 0,50 ms, et aucun TEMP B-TREE dans les deux cas — le
            # plus simple des deux est garde.
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_souvenirs_tri "
                f"ON {self.TABLE_SOUVENIRS} (etat, importance, cree_le)"
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
        valide_depuis: Optional[str] = None,
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
            valide_depuis=valide_depuis,
            # La premiere voix. `source` est deja validee non vide plus haut.
            sources=(source.strip(),),
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
                f"occurrences, etat, sensible, valide_depuis, sources) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    souvenir.identifiant, contenu_stocke, souvenir.type.value,
                    souvenir.nature.value, souvenir.source, souvenir.projet,
                    souvenir.importance,
                    json.dumps(souvenir.metadonnees, ensure_ascii=False),
                    souvenir.cree_le, souvenir.vu_le, souvenir.expire_le,
                    souvenir.occurrences, souvenir.etat.value, int(souvenir.sensible),
                    souvenir.valide_depuis,
                    json.dumps(list(souvenir.sources), ensure_ascii=False),
                ),
            )
            connexion.commit()

    def confirmer(self, identifiant: str, source: str) -> Optional[Souvenir]:
        """Le **seul** chemin par lequel une inference devient un fait.

        Elle exige une source **nouvelle**, et depuis DEC-0104 elle le verifie
        vraiment. Avant, elle se contentait de le promettre : trois appels avec
        `devis_aout.pdf` rendaient `source = "devis_aout.pdf + devis_aout.pdf +
        devis_aout.pdf"` et une `INFERENCE` devenue `FAIT` sur une seule voix
        qui s'etait repetee. Mesure du 13/09/2026, avant correction.

        Une source deja connue ne corrobore rien. Le souvenir est quand meme
        **revu** — `vu_le` et `occurrences` bougent, parce que c'est vrai : il a
        ete redit. Mais `nature` ne bouge pas, et le nombre de voix ne bouge
        pas. « Trois fois par une source » et « une fois par trois sources »
        cessent de se ressembler.

        Args:
            identifiant: le souvenir a confirmer.
            source: qui ou quoi le confirme. Obligatoire.

        Returns:
            Le souvenir mis a jour, ou None s'il n'existe pas. Comparer
            `nombre_de_sources` avant et apres dit si la voix etait nouvelle.

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

        propre = source.strip()
        if propre in self._voix_deja_connues(souvenir):
            return self._revoir_sans_corroborer(identifiant)

        nouvelle_nature = (
            Nature.FAIT if souvenir.nature is Nature.INFERENCE else souvenir.nature
        )
        voix = (*souvenir.sources, propre) if souvenir.sources else ()
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"UPDATE {self.TABLE_SOUVENIRS} SET nature = ?, source = ?, vu_le = ?, "
                f"sources = ?, occurrences = occurrences + 1 WHERE identifiant = ?",
                (
                    nouvelle_nature.value,
                    f"{souvenir.source}{SEPARATEUR_SOURCES}{propre}",
                    _maintenant().isoformat(timespec="seconds"),
                    # Une ligne dont les voix n'ont jamais ete comptees le reste :
                    # y ecrire `[nouvelle]` affirmerait qu'elle n'a qu'une voix
                    # alors que son champ `source` en montre plusieurs.
                    json.dumps(list(voix), ensure_ascii=False) if voix else None,
                    identifiant,
                ),
            )
            connexion.commit()
        return self.lire(identifiant)

    @staticmethod
    def _voix_deja_connues(souvenir: Souvenir) -> Tuple[str, ...]:
        """Les sources qui affirment deja ce souvenir, liste tenue ou non.

        Quand la liste existe, elle fait foi. Sinon on decoupe le champ `source`
        — pour un test d'APPARTENANCE seulement, jamais pour compter : savoir si
        une chaine donnee figure parmi les segments est fiable dans les deux
        sens, alors que savoir combien il y a de segments ne l'est pas.
        """
        if souvenir.sources:
            return souvenir.sources
        return tuple(
            segment.strip()
            for segment in (souvenir.source or "").split(SEPARATEUR_SOURCES)
            if segment.strip()
        )

    def _revoir_sans_corroborer(self, identifiant: str) -> Optional[Souvenir]:
        """Une source qui se repete : le souvenir est revu, jamais renforce.

        `nature` et `sources` sont laisses intacts — c'est la difference entre
        « redit » et « confirme », et c'est la seule raison d'etre de cette
        methode.
        """
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"UPDATE {self.TABLE_SOUVENIRS} SET vu_le = ?, "
                f"occurrences = occurrences + 1 WHERE identifiant = ?",
                (_maintenant().isoformat(timespec="seconds"), identifiant),
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
                    # Qui a decide est trace, mais celui qui rejette ou archive
                    # n'affirme pas le contenu : `sources` n'est pas touche.
                    f"{souvenir.source}{SEPARATEUR_SOURCES}{source.strip()}",
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
            # `ligne.keys()` plutot qu'un acces direct : une base d'avant la
            # migration, relue par un processus qui n'a pas encore appele
            # `_creer_tables`, n'a pas la colonne.
            valide_depuis=(ligne["valide_depuis"] if "valide_depuis" in colonnes else None),
            sources=self._sources_depuis_ligne(ligne, colonnes),
        )

    @staticmethod
    def _sources_depuis_ligne(ligne: sqlite3.Row, colonnes: Iterable[str]) -> Tuple[str, ...]:
        """Les sources distinctes d'une ligne — comptees, deduites, ou vides.

        Trois cas, et le troisieme est celui qui compte :

        1. La colonne porte une liste : elle fait foi, elle a ete tenue a jour
           a chaque confirmation.
        2. Elle est vide (ligne d'avant DEC-0104) et `source` ne contient pas le
           separateur : le souvenir n'a jamais ete confirme, donc il a
           exactement une voix. La deduction est certaine.
        3. Elle est vide et `source` contient le separateur : le souvenir A ete
           corrobore, mais par combien de voix distinctes ? Decouper la chaine
           donnerait un chiffre, pas une mesure — une source nommee « a + b »
           en vaudrait deux. On rend un tuple vide, et `nombre_de_sources`
           repond `None` : **jamais compte ici** n'est pas la meme chose que
           « une seule ».
        """
        brut = ligne["sources"] if "sources" in colonnes else None
        if brut:
            try:
                liste = json.loads(brut)
            except (TypeError, ValueError):
                logger.warning("Liste de sources illisible pour %s : traitee "
                               "comme non comptee.", ligne["identifiant"])
                return ()
            if isinstance(liste, list):
                return tuple(str(element) for element in liste)
            return ()
        source = (ligne["source"] or "").strip()
        if source and SEPARATEUR_SOURCES not in source:
            return (source,)
        return ()

    def _dechiffrer_ou_signaler(self, identifiant: str, contenu_stocke: str) -> str:
        """Dechiffre un contenu sensible, ou rend un etat lisible plutot que de
        faire echouer toute une lecture (`souvenirs()`) pour UNE ligne illisible.

        Jamais de texte en clair fabrique : l'appelant sait que le souvenir
        existe et pourquoi il ne peut pas le lire, jamais une supposition sur
        son contenu.
        """
        if self.coffre is None:
            return SANS_COFFRE
        try:
            return self.coffre.dechiffrer(contenu_stocke)
        except EchecDechiffrement as erreur:
            logger.warning(
                "Souvenir sensible %s illisible avec le coffre configure : %s",
                identifiant, erreur,
            )
            return DECHIFFREMENT_REFUSE

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
        inclure_a_venir: bool = False,
        inclure_rejetes: bool = False,
        inclure_archives: bool = False,
        sensible: Optional[bool] = None,
    ) -> List[Souvenir]:
        """Les souvenirs, filtres. Les perimes, rejetes et archives sont ecartes
        sauf demande expresse.

        Rendre un contexte temporaire perime ferait dire a ARENA une chose fausse
        avec l'assurance d'un fait. Rendre un souvenir REJETE dans la lecture
        normale annulerait le sens meme de `rejeter()` — le proprietaire a dit
        non, pas "pas encore" — c'est pour cela que les trois se demandent.

        `sensible` vaut None par defaut : les deux populations reviennent
        ensemble, comme toujours. `sensible=True` isole les souvenirs chiffres
        — la seule population qu'un `LIKE` SQL ne peut pas fouiller, puisque
        sur le disque c'est du chiffre (voir
        `core/memory/recuperation.py::sensibles_correspondants`).
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
        if sensible is not None:
            requete += " AND sensible = ?"
            arguments.append(int(sensible))
        requete += " ORDER BY importance DESC, cree_le DESC, rowid DESC LIMIT ?"
        arguments.append(limite)

        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()

        souvenirs = [self._depuis_ligne(ligne) for ligne in lignes]
        if not inclure_perimes:
            souvenirs = [s for s in souvenirs if not s.est_perime()]
        # Le miroir : un souvenir qui annonce une verite a venir n'est pas encore
        # vrai. Le rendre ferait repondre « le tarif est 5500 » des septembre
        # pour un tarif qui prend effet en octobre.
        if not inclure_a_venir:
            souvenirs = [s for s in souvenirs if not s.pas_encore_vrai()]
        return souvenirs

    def souvenirs_correspondant_a_des_mots(
        self,
        mots: Iterable[str],
        projet: Optional[str] = None,
        type: Optional[TypeSouvenir] = None,
        limite: int = 500,
    ) -> List[Souvenir]:
        """Les souvenirs dont le contenu contient au moins un des mots donnes.

        Un SECOND chemin d'acces, complementaire a `souvenirs()` (qui trie par
        importance/recence et s'arrete a `limite`) : sans lui, un souvenir
        pertinent mais ancien et peu important, au-dela de cette fenetre,
        n'etait jamais meme EXAMINE par `core/memory/recuperation.py::recuperer`
        (mission ARENA x AUDIT, corrige le 12/09/2026 — « plus de 500
        souvenirs, celui qui compte tombe hors de la fenetre »).

        Filtre en SQL (`LIKE`), jamais un Python qui chargerait toute la table
        en memoire pour la filtrer ensuite : `limite` borne ce qui revient,
        comme pour `souvenirs()`. Ce n'est pas un index (SQLite ne peut pas en
        utiliser un pour un `LIKE '%...%'` a joker des deux cotes), mais une
        « autre strategie bornee » — le cout reste un balayage SQL en C sur les
        souvenirs NON sensibles, jamais un chargement complet cote Python, et
        jamais un appel d'embeddings supplementaire (ceux-la restent bornes par
        l'appelant, `core/memory/semantique.py`).

        Les souvenirs SENSIBLES (`sensible=True`) restent exclus D'ICI : leur
        `contenu` est chiffre sur le disque (DEC-0090) et un `LIKE` sur du
        chiffre ne trouvera jamais rien. Ce n'est plus une limite de la
        recherche pour autant — `core/memory/recuperation.py::sensibles_correspondants`
        leur ouvre une TROISIEME fenetre bornee, qui les dechiffre puis filtre
        les mots cote Python. Elle n'existait pas avant le 12/09/2026 : jusque
        la, « le code du portail du chantier Fast Group est 4821 » ne ressortait
        sur AUCUN mot-cle des qu'il tombait hors de la fenetre
        importance/recence (mesure DEC-0097).

        Limite mesuree, non contournee : `LIKE` compare le texte tel qu'il est
        stocke (accents compris), alors que `mots` vient deja normalise
        (`core/memory/recuperation.py::mots_utiles`, sans accent). Un mot
        accentue dans le contenu original peut donc echapper a CE filtre
        precisement, meme s'il reste trouve par la fenetre importance/recence
        habituelle, qui normalise cote Python.
        """
        mots_valides = [mot for mot in mots if mot]
        if not mots_valides:
            return []

        clauses = " OR ".join(["contenu LIKE ? ESCAPE '\\'"] * len(mots_valides))
        requete = (
            f"SELECT * FROM {self.TABLE_SOUVENIRS} "
            f"WHERE etat = ? AND sensible = 0 AND ({clauses})"
        )
        arguments: List[Any] = [Etat.ACTIF.value]
        for mot in mots_valides:
            motif_echappe = mot.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            arguments.append(f"%{motif_echappe}%")
        if type is not None:
            requete += " AND type = ?"
            arguments.append(type.value)
        if projet is not None:
            requete += " AND projet = ?"
            arguments.append(projet)
        requete += " ORDER BY importance DESC, cree_le DESC LIMIT ?"
        arguments.append(limite)

        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(requete, arguments).fetchall()

        souvenirs = [self._depuis_ligne(ligne) for ligne in lignes]
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
