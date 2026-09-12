"""Ce que le cloud coute, compte a la requete, et le plafond qui y met fin.

Le cloud est a l'usage : un agent qui boucle ne fait pas planter ARENA, il
**facture**. Ce module compte ce qui part, estime ce que ca coute quand un tarif
est connu, et dit quand il faut redescendre sur Ollama.

**Cinq regles :**

1. **Un plafond atteint ne casse rien.** Il fait retomber ARENA sur sa machine.
   Refuser de repondre serait le pire des deux mondes : plus de cloud, et plus
   d'assistant non plus.

2. **Un cout inconnu reste inconnu.** Sans tarif configure, `cout_estime` vaut
   `None`, jamais `0.0` — un zero se lirait « gratuit » et laisserait le
   compteur ouvert.

3. **Le journal ne contient pas ses phrases.** On enregistre le fournisseur, le
   modele, le classement, la latence et les jetons. **Pas le prompt.** Un
   compteur d'usage n'est pas un enregistreur de conversations.

4. **La journee est celle de sa machine**, pas une fenetre glissante : « 200
   requetes par jour » doit vouloir dire ce qu'il croit.

5. **Zero veut dire « pas de plafond »**, et c'est un choix qui doit etre ecrit,
   jamais un defaut qu'on subit.
"""
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.modeles.usage")

#: Combien d'appels sont gardes en memoire quand aucune base n'est fournie.
#: Au-dela, les plus anciens partent : ce compteur ne doit pas peser plus que
#: ce qu'il compte.
#:
#: **Ce plafond n'est PAS le plafond du jour.** Mesure du 12/09/2026 (audit
#: f7f0478, etape 10) : avec `db_path=None`, `requetes_aujourdhui` et
#: `cout_aujourdhui` ne lisent QUE cette liste bornee — un proprietaire qui
#: configure `AI_MAX_CLOUD_REQUESTS_PER_DAY` au-dela de 500 verrait ses
#: premiers appels du jour expulses avant que le plafond ne soit jamais
#: atteint, le rouvrant sans fin. C'est exactement pour cela que
#: `CompteurUsage(db_path=...)` existe : des qu'une base est fournie, le
#: compte du jour se lit dans SQLite, jamais dans cette liste tronquee.
APPELS_GARDES = 500

#: Le nom de la table SQLite, dans la meme base que le reste d'ARENA
#: (memoire, gouvernance, gardien...) — DEC-0005, SQLite est deja le choix du
#: projet pour tout etat qui doit survivre un redemarrage.
TABLE_USAGE = "usage_cloud_appels"

#: Combien de jours d'historique la base garde. Le compte du jour ne regarde
#: jamais plus loin qu'aujourd'hui ; cette marge n'est que pour couvrir un
#: fuseau horaire mal aligne au moment de la purge, jamais pour du reporting
#: long terme (qui n'est pas ce que ce module promet — regle 3 du docstring).
JOURS_CONSERVES = 3

#: Tarifs connus, en dollars par million de jetons. **Vide par defaut** : un
#: tarif que personne n'a saisi ne s'invente pas, et le cout reste `None`.
#: Le proprietaire les remplit quand il veut voir des montants.
TARIFS: Dict[str, Dict[str, float]] = {}


#: Ce que vaut le plafond par requete, une fois confronte a la realite des
#: tarifs. Trois etats, jamais deux : un controle qu'on ne peut pas calculer
#: n'est pas un controle « qui passe ».
CONTROLE_DESACTIVE = "DESACTIVE"
CONTROLE_NON_VERIFIABLE = "NON_VERIFIABLE"
CONTROLE_MESURE_APRES_COUP = "MESURE_APRES_COUP"


def _aujourdhui() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass(frozen=True)
class Appel:
    """Un appel distant, tel qu'il sera compte. **Sans le texte de la demande.**"""

    fournisseur: str
    modele: str
    jour: str = field(default_factory=_aujourdhui)
    horodatage: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(
        timespec="seconds"))
    classement: str = ""
    jetons_entree: Optional[int] = None
    jetons_sortie: Optional[int] = None
    secondes: Optional[float] = None
    repli: bool = False
    succes: bool = True

    @property
    def cout_estime(self) -> Optional[float]:
        """Le cout, si et seulement si un tarif est configure pour ce modele.

        `None` n'est pas `0.0`. Un zero se lirait « gratuit ».
        """
        tarif = TARIFS.get(self.modele)
        if not tarif or self.jetons_entree is None or self.jetons_sortie is None:
            return None
        return (self.jetons_entree * tarif.get("entree", 0.0)
                + self.jetons_sortie * tarif.get("sortie", 0.0)) / 1_000_000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fournisseur": self.fournisseur, "modele": self.modele,
            "horodatage": self.horodatage, "classement": self.classement,
            "jetons_entree": self.jetons_entree, "jetons_sortie": self.jetons_sortie,
            "secondes": self.secondes, "repli": self.repli, "succes": self.succes,
            "cout_estime": self.cout_estime,
        }


@dataclass(frozen=True)
class Verdict:
    """Le cloud a-t-il encore le droit de servir aujourd'hui, et pourquoi."""

    autorise: bool
    raison: str


class CompteurUsage:
    """Compte ce qui part vers le cloud, et dit quand il faut s'arreter.

    Sans `db_path` : purement en memoire, comme avant — pour les tests et les
    usages ephemeres. Avec `db_path` : le compte du jour vit dans SQLite
    (meme base que le reste d'ARENA, DEC-0005), et **survit a un
    redemarrage** — mesure du 12/09/2026 (audit f7f0478, etape 10) : sans
    cela, un redemarrage remettait le plafond du jour a zero, autorisant a
    nouveau un budget deja epuise juste avant l'arret.
    """

    def __init__(self, requetes_par_jour: int = 200,
                 budget_journalier: float = 1.0,
                 db_path: Optional[str] = None,
                 cout_max_par_requete: float = 0.0) -> None:
        self.requetes_par_jour = max(0, requetes_par_jour)
        self.budget_journalier = max(0.0, budget_journalier)
        #: Plafond par requete, tel que le proprietaire l'a regle
        #: (`AI_MAX_COST_PER_REQUEST`). Mesure du 12/09/2026 : ce reglage
        #: existait dans `config.py` ET dans `.env.example` — donc lisible
        #: comme une protection active — sans etre lu par une seule ligne de
        #: code. Il est desormais porte ici, mais SANS pretendre bloquer :
        #: le cout d'une requete depend des jetons de SORTIE, inconnus avant
        #: la reponse, et `TARIFS` est vide par defaut donc souvent
        #: incalculable meme apres. `etat_controle_par_requete()` dit lequel
        #: des trois cas s'applique, au lieu de laisser supposer le bon.
        self.cout_max_par_requete = max(0.0, cout_max_par_requete)
        self.db_path = db_path
        #: Cache en memoire — pour le mode sans base, et pour ne rien
        #: changer au comportement deja teste. Quand `db_path` est fourni,
        #: le compte du jour ne lit **jamais** cette liste (elle est bornee,
        #: voir `APPELS_GARDES`) : il lit la base.
        self.appels: List[Appel] = []
        #: Appels distants PARTIS mais pas encore comptes. Mesure du
        #: 12/09/2026, en diagnostic de l'etape 10 : avec un plafond de 3 et
        #: dix requetes lancees en parallele, LES DIX partaient au cloud — le
        #: plafond etait verifie avant l'appel et compte seulement apres la
        #: reponse, donc chaque requete concurrente voyait un compteur encore
        #: a zero. Une place se reserve maintenant au moment de la decision.
        self._en_vol = 0
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._creer_table()

    # --- Base --------------------------------------------------------------------

    def _connexion(self) -> sqlite3.Connection:
        connexion = sqlite3.connect(self.db_path)
        connexion.row_factory = sqlite3.Row
        return connexion

    def _creer_table(self) -> None:
        with closing(self._connexion()) as connexion:
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_USAGE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fournisseur TEXT NOT NULL,
                    modele TEXT NOT NULL,
                    jour TEXT NOT NULL,
                    horodatage TEXT NOT NULL,
                    classement TEXT NOT NULL,
                    jetons_entree INTEGER,
                    jetons_sortie INTEGER,
                    secondes REAL,
                    repli INTEGER NOT NULL,
                    succes INTEGER NOT NULL
                )
            """)
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_USAGE}_jour "
                f"ON {TABLE_USAGE} (jour)")
            connexion.commit()

    def _purger_avant(self, connexion: sqlite3.Connection, aujourdhui: str) -> None:
        """Retire les jours trop anciens pour compter — jamais aujourd'hui."""
        limite = (datetime.fromisoformat(aujourdhui).date()
                  - timedelta(days=JOURS_CONSERVES)).isoformat()
        connexion.execute(f"DELETE FROM {TABLE_USAGE} WHERE jour < ?", (limite,))

    @staticmethod
    def _depuis_ligne(ligne: sqlite3.Row) -> Appel:
        return Appel(
            fournisseur=ligne["fournisseur"], modele=ligne["modele"],
            jour=ligne["jour"], horodatage=ligne["horodatage"],
            classement=ligne["classement"],
            jetons_entree=ligne["jetons_entree"], jetons_sortie=ligne["jetons_sortie"],
            secondes=ligne["secondes"], repli=bool(ligne["repli"]),
            succes=bool(ligne["succes"]),
        )

    # --- Compter ---------------------------------------------------------------

    def enregistrer(self, appel: Appel) -> Appel:
        """Range un appel. Le journal ne grossit pas sans fin."""
        self.appels.append(appel)
        surplus = len(self.appels) - APPELS_GARDES
        if surplus > 0:
            del self.appels[:surplus]
        if self.db_path:
            with closing(self._connexion()) as connexion:
                connexion.execute(
                    f"""INSERT INTO {TABLE_USAGE}
                        (fournisseur, modele, jour, horodatage, classement,
                         jetons_entree, jetons_sortie, secondes, repli, succes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (appel.fournisseur, appel.modele, appel.jour, appel.horodatage,
                     appel.classement, appel.jetons_entree, appel.jetons_sortie,
                     appel.secondes, int(appel.repli), int(appel.succes)))
                self._purger_avant(connexion, appel.jour)
                connexion.commit()
        return appel

    def du_jour(self, jour: Optional[str] = None) -> List[Appel]:
        """Les appels d'une journee — celle de sa machine, pas 24 h glissantes.

        Avec une base : lit SQLite, pas le cache borne — c'est ce qui rend le
        compte exact au-dela de `APPELS_GARDES` appels dans la meme journee.
        """
        reference = jour or _aujourdhui()
        if self.db_path:
            with closing(self._connexion()) as connexion:
                lignes = connexion.execute(
                    f"SELECT * FROM {TABLE_USAGE} WHERE jour = ?", (reference,)
                ).fetchall()
            return [self._depuis_ligne(ligne) for ligne in lignes]
        return [appel for appel in self.appels if appel.jour == reference]

    @property
    def requetes_aujourdhui(self) -> int:
        return len(self.du_jour())

    @property
    def cout_aujourdhui(self) -> Optional[float]:
        """Le total du jour, ou `None` si aucun appel n'a de tarif connu."""
        connus = [appel.cout_estime for appel in self.du_jour()
                  if appel.cout_estime is not None]
        return sum(connus) if connus else None

    @property
    def appels_en_vol(self) -> int:
        """Combien d'appels distants sont partis sans etre encore comptes."""
        return self._en_vol

    def reserver_une_place(self) -> None:
        """Prend une place dans le quota du jour AVANT l'appel.

        Synchrone et sans `await` : entre la lecture du verdict et cette
        reservation, aucune autre tache ne peut se glisser (asyncio ne
        preempte que sur un `await`). C'est ce qui fait tenir le plafond
        sous concurrence.
        """
        self._en_vol += 1

    def liberer_une_place(self) -> None:
        """Rend la place a la fin de la requete — l'appel reellement parti a
        ete compte entre-temps par `enregistrer()`, ou n'a jamais eu lieu."""
        self._en_vol = max(0, self._en_vol - 1)

    def etat_controle_par_requete(self) -> str:
        """Le plafond par requete est-il applicable, et comment ?

        - `DESACTIVE` : regle a zero, choix explicite du proprietaire.
        - `NON_VERIFIABLE` : un plafond est regle, mais aucun tarif n'est
          configure (`TARIFS` vide) — le cout d'une requete ne peut donc
          pas etre calcule, ni avant ni apres. Dire « respecte » ici serait
          un mensonge ; dire `0 $` en serait un pire.
        - `MESURE_APRES_COUP` : des tarifs existent, le depassement est
          constate sur la reponse rendue. Jamais « empeche » : les jetons de
          sortie n'existent pas avant que le modele ait repondu.
        """
        if not self.cout_max_par_requete:
            return CONTROLE_DESACTIVE
        return CONTROLE_MESURE_APRES_COUP if TARIFS else CONTROLE_NON_VERIFIABLE

    def depassements_par_requete(self, jour: Optional[str] = None) -> int:
        """Combien d'appels du jour ont coute plus que le plafond par requete.

        Compte seulement ce qui est CALCULABLE : un appel sans tarif connu
        n'est ni un depassement ni un respect, il est inconnu.
        """
        if not self.cout_max_par_requete:
            return 0
        return sum(1 for appel in self.du_jour(jour)
                   if appel.cout_estime is not None
                   and appel.cout_estime > self.cout_max_par_requete)

    # --- Decider ----------------------------------------------------------------

    def verdict(self) -> Verdict:
        """Le cloud peut-il encore servir ? Un plafond atteint fait retomber sur Ollama."""
        # Les appels en vol comptent : sinon dix requetes simultanees
        # passeraient toutes un plafond de trois (mesure du 12/09/2026).
        prevu = self.requetes_aujourdhui + self._en_vol
        if self.requetes_par_jour and prevu >= self.requetes_par_jour:
            return Verdict(False, (f"plafond atteint : {prevu} "
                                   f"requete(s) cloud aujourd'hui"))
        depense = self.cout_aujourdhui
        if self.budget_journalier and depense is not None and depense >= self.budget_journalier:
            return Verdict(False, (f"budget atteint : {depense:.4f} $ depenses "
                                   f"aujourd'hui"))
        return Verdict(True, "dans les clous")

    def resume(self) -> Dict[str, Any]:
        """Ce que l'interface peut montrer. Aucune phrase du proprietaire ici."""
        verdict = self.verdict()
        return {
            "requetes_aujourdhui": self.requetes_aujourdhui,
            "plafond_requetes": self.requetes_par_jour or None,
            # `None` quand aucun tarif n'est configure : on ne montre pas un
            # montant qu'on n'a pas calcule.
            "cout_aujourdhui": self.cout_aujourdhui,
            "budget_journalier": self.budget_journalier or None,
            "cout_max_par_requete": self.cout_max_par_requete or None,
            # Ce que ce plafond vaut REELLEMENT aujourd'hui, pas ce qu'il
            # laisse croire : sans tarif configure, il est `NON_VERIFIABLE`.
            "controle_cout_par_requete": self.etat_controle_par_requete(),
            "depassements_par_requete_aujourdhui": self.depassements_par_requete(),
            "cloud_autorise": verdict.autorise,
            "raison": verdict.raison,
        }
