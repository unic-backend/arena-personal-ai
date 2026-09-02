"""Les actions preparees qui attendent un « oui ».

Depuis la phase 1.1, `NEEDS_CONFIRMATION` existe comme **statut**. Ce n'etait
pas encore un mecanisme : l'action etait annoncee prete, et rien ne la retenait.
Le proprietaire pouvait lire « pret a envoyer », il ne pouvait pas repondre
« envoie ».

Ce module est ce qui retient. Il tient quatre garanties, et chacune est une
chose qui ne peut pas arriver :

1. **Une action non confirmee ne s'execute pas.** L'objet en attente porte ses
   parametres mais n'a aucun moyen de se declencher : seul `confirmer()` appelle
   l'executeur. Il n'existe pas de chemin ou deposer suffise.

2. **Confirmer deux fois n'execute qu'une fois.** Le passage a `CONFIRMEE` est un
   `UPDATE ... WHERE etat = 'EN_ATTENTE'` : la seconde tentative ne change aucune
   ligne, et rend le resultat deja enregistre au lieu d'agir a nouveau.

3. **Une confirmation perimee ne part pas.** Un « envoie » clique trois jours
   plus tard porte sur un contexte qui n'existe plus. Au-dela du delai, l'action
   passe `EXPIREE` et refuse d'etre confirmee.

4. **Aucun secret n'est mis en attente.** Un parametre dont le nom annonce un
   identifiant fait **refuser le depot**, avec son motif. Les identifiants
   viennent de la configuration du connecteur, jamais de l'appelant — donc les
   perdre en route ne casse rien, et les ecrire sur le disque casserait tout.

5. **Une suggestion non validee ne survit pas.** Refusee ou perimee, l'action
   perd son contenu : le corps du message, le destinataire, l'objet sont
   effaces de la base. Demande du proprietaire le 02/09/2026 — « il peut
   suggerer des reponses, mais si je valide pas il supprime sa suggestion ».

   Mesure faite avant ce correctif : un brouillon refuse gardait son corps
   entier dans `data/database/memory.db`, indefiniment. Un message que le
   proprietaire a explicitement refuse d'envoyer n'a aucune raison de rester
   ecrit quelque part.

   Ce qui reste : QUE quelque chose a ete propose vers QUI, quand, et que ce
   fut refuse. La trace, jamais le texte. C'est ce qui permet a une seconde
   confirmation de rester sans effet (garantie 2) — une ligne supprimee
   repondrait « action inconnue » au lieu de « deja annulee ».
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
from typing import Any, Callable, Dict, List, Optional

from core.actions.journal import FRAGMENTS_SECRETS, masquer
from core.actions.resultat import ResultatAction, echec, non_implemente

logger = logging.getLogger("usman.actions.attente")

#: Ce qui execute reellement l'action une fois confirmee. Injecte pour que ce
#: module n'importe pas le registre des connecteurs — qui importe deja les
#: actions, et le cycle serait immediat.
Executeur = Callable[..., ResultatAction]

# Une confirmation vaut pour la journee ou elle a ete demandee. Au-dela, le
# contexte a change : le client a rappele, le devis a ete revu, le chantier est
# fini. Reglable a la construction.
DELAI_PAR_DEFAUT_HEURES = 24


class EtatAttente(str, Enum):
    """Le cycle de vie d'une action preparee."""

    EN_ATTENTE = "PENDING"
    CONFIRMEE = "CONFIRMED"
    ANNULEE = "CANCELLED"
    EXPIREE = "EXPIRED"


#: Les deux fins SANS accord du proprietaire : il a refuse, ou il n'a pas
#: repondu. Dans les deux cas la suggestion perd son contenu (garantie 5).
#: `CONFIRMEE` n'y est pas : ce qui est parti sur son ordre reste tracable.
ETATS_SANS_VALIDATION = frozenset({EtatAttente.ANNULEE, EtatAttente.EXPIREE})


def _maintenant() -> datetime:
    """Isole pour que les tests fixent l'heure."""
    return datetime.now(timezone.utc)


def parametre_secret(parametres: Dict[str, Any]) -> Optional[str]:
    """Le nom du premier parametre qui annonce un secret, ou None.

    Cherche en profondeur : un jeton cache dans un sous-dictionnaire est un
    jeton quand meme.
    """
    def _chercher(valeur: Any) -> Optional[str]:
        if isinstance(valeur, dict):
            for nom, interne in valeur.items():
                if any(f in str(nom).lower() for f in FRAGMENTS_SECRETS):
                    return str(nom)
                trouve = _chercher(interne)
                if trouve:
                    return trouve
        elif isinstance(valeur, (list, tuple)):
            for element in valeur:
                trouve = _chercher(element)
                if trouve:
                    return trouve
        return None

    return _chercher(parametres or {})


@dataclass(frozen=True)
class ActionEnAttente:
    """Ce qui est montre avant de demander « j'envoie ? ».

    Les quatre premiers champs sont exactement ce que la specification demande
    d'afficher : ACTION, CIBLE, RISQUE, RESULTAT ATTENDU.

    Attributes:
        action: ce qui sera fait, en clair (« Publie une video sur TikTok »).
        cible: sur quoi, ou vers qui.
        risque: LOW, MEDIUM ou HIGH, tel que la politique le porte.
        resultat_attendu: ce qui aura change si l'action part.
        connecteur: le connecteur qui executera.
        capacite: la capacite appelee.
        compte: le compte concerne, s'il y en a un.
        parametres: les arguments, sans aucun secret.
        etat: ou en est l'action.
        resultat_final: le statut rendu apres execution, ou None.
    """

    action: str
    cible: str
    risque: str
    resultat_attendu: str
    connecteur: str
    capacite: str
    compte: Optional[str] = None
    parametres: Dict[str, Any] = field(default_factory=dict)
    etat: EtatAttente = EtatAttente.EN_ATTENTE
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    cree_le: str = ""
    expire_le: str = ""
    resultat_final: Optional[str] = None

    def est_perimee(self, maintenant: Optional[datetime] = None) -> bool:
        """Vrai si le delai est passe. Une date illisible est traitee comme perimee."""
        if not self.expire_le:
            return False
        try:
            limite = datetime.fromisoformat(self.expire_le)
        except ValueError:
            logger.warning("Date d'expiration illisible (%s) : action traitee comme perimee.",
                           self.expire_le)
            return True
        return (maintenant or _maintenant()) >= limite

    def to_dict(self) -> Dict[str, Any]:
        """Ce que l'interface affiche avant la confirmation."""
        return {
            "id": self.identifiant,
            "action": self.action,
            "cible": self.cible,
            "risque": self.risque,
            "resultat_attendu": self.resultat_attendu,
            "connecteur": self.connecteur,
            "capacite": self.capacite,
            "compte": self.compte,
            "parametres": self.parametres,
            "etat": self.etat.value,
            "cree_le": self.cree_le,
            "expire_le": self.expire_le,
            "resultat_final": self.resultat_final,
        }

    def resume(self) -> str:
        """Les quatre lignes a lire avant de repondre."""
        return (
            f"ACTION           : {self.action}\n"
            f"CIBLE            : {self.cible}\n"
            f"RISQUE           : {self.risque}\n"
            f"RESULTAT ATTENDU : {self.resultat_attendu}"
        )


class FileDAttente:
    """Depose, montre, puis execute ou abandonne les actions preparees."""

    TABLE = "actions_en_attente"

    def __init__(
        self,
        db_path: str = "data/database/memory.db",
        executeur: Optional[Executeur] = None,
        delai_heures: int = DELAI_PAR_DEFAUT_HEURES,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.executeur = executeur
        self.delai_heures = delai_heures
        self._creer_table()

    def _connexion(self) -> sqlite3.Connection:
        connexion = sqlite3.connect(self.db_path)
        connexion.row_factory = sqlite3.Row
        return connexion

    def _creer_table(self) -> None:
        with closing(self._connexion()) as connexion:
            connexion.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    identifiant      TEXT PRIMARY KEY,
                    action           TEXT NOT NULL,
                    cible            TEXT NOT NULL,
                    risque           TEXT NOT NULL,
                    resultat_attendu TEXT NOT NULL,
                    connecteur       TEXT NOT NULL,
                    capacite         TEXT NOT NULL,
                    compte           TEXT,
                    parametres       TEXT NOT NULL,
                    etat             TEXT NOT NULL,
                    cree_le          TEXT NOT NULL,
                    expire_le        TEXT NOT NULL,
                    resultat_final   TEXT
                )
            """)
            connexion.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_etat "
                f"ON {self.TABLE} (etat, cree_le DESC)"
            )
            connexion.commit()

    # --- Depot ----------------------------------------------------------------

    def deposer(
        self,
        action: str,
        cible: str,
        risque: str,
        resultat_attendu: str,
        connecteur: str,
        capacite: str,
        compte: Optional[str] = None,
        parametres: Optional[Dict[str, Any]] = None,
    ) -> ActionEnAttente:
        """Met une action en attente. **Elle ne s'execute pas.**

        Raises:
            ValueError: si un parametre porte un nom de secret. Les identifiants
                viennent de la configuration du connecteur, pas de l'appelant :
                en mettre un ici serait l'ecrire sur le disque pour rien.
        """
        parametres = dict(parametres or {})
        secret = parametre_secret(parametres)
        if secret:
            raise ValueError(
                f"Le parametre « {secret} » porte un nom de secret : une action en "
                f"attente n'en transporte jamais. Les identifiants viennent de la "
                f"configuration du connecteur."
            )

        debut = _maintenant()
        en_attente = ActionEnAttente(
            action=action, cible=cible, risque=risque,
            resultat_attendu=resultat_attendu, connecteur=connecteur,
            capacite=capacite, compte=compte,
            # Deuxieme filet : le refus ci-dessus couvre les noms connus, le
            # masquage couvre ce qui aurait ete ajoute apres coup.
            parametres=masquer(parametres),
            cree_le=debut.isoformat(timespec="seconds"),
            expire_le=(debut + timedelta(hours=self.delai_heures)).isoformat(timespec="seconds"),
        )

        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"INSERT INTO {self.TABLE} (identifiant, action, cible, risque, "
                f"resultat_attendu, connecteur, capacite, compte, parametres, etat, "
                f"cree_le, expire_le, resultat_final) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    en_attente.identifiant, en_attente.action, en_attente.cible,
                    en_attente.risque, en_attente.resultat_attendu, en_attente.connecteur,
                    en_attente.capacite, en_attente.compte,
                    json.dumps(en_attente.parametres, ensure_ascii=False),
                    en_attente.etat.value, en_attente.cree_le, en_attente.expire_le, None,
                ),
            )
            connexion.commit()
        logger.info("Action en attente %s : %s -> %s", en_attente.identifiant, action, cible)
        return en_attente

    # --- Lecture --------------------------------------------------------------

    @staticmethod
    def _depuis_ligne(ligne: sqlite3.Row) -> ActionEnAttente:
        return ActionEnAttente(
            identifiant=ligne["identifiant"], action=ligne["action"], cible=ligne["cible"],
            risque=ligne["risque"], resultat_attendu=ligne["resultat_attendu"],
            connecteur=ligne["connecteur"], capacite=ligne["capacite"], compte=ligne["compte"],
            parametres=json.loads(ligne["parametres"]), etat=EtatAttente(ligne["etat"]),
            cree_le=ligne["cree_le"], expire_le=ligne["expire_le"],
            resultat_final=ligne["resultat_final"],
        )

    def lire(self, identifiant: str) -> Optional[ActionEnAttente]:
        """Relit une action. L'etat rendu tient compte du delai ecoule."""
        with closing(self._connexion()) as connexion:
            ligne = connexion.execute(
                f"SELECT * FROM {self.TABLE} WHERE identifiant = ?", (identifiant,)
            ).fetchone()
        if ligne is None:
            return None

        action = self._depuis_ligne(ligne)
        if action.etat is EtatAttente.EN_ATTENTE and action.est_perimee():
            self._changer_etat(identifiant, EtatAttente.EXPIREE)
            return self.lire(identifiant)
        return action

    def en_attente(self, limite: int = 50) -> List[ActionEnAttente]:
        """Les actions qui attendent encore un « oui », les plus recentes d'abord.

        Une action perimee n'y figure pas : elle est marquee `EXPIREE` au passage,
        parce qu'une liste d'attente qui montre des actions mortes fait cliquer
        sur des actions mortes.
        """
        with closing(self._connexion()) as connexion:
            lignes = connexion.execute(
                f"SELECT * FROM {self.TABLE} WHERE etat = ? ORDER BY cree_le DESC, rowid DESC "
                f"LIMIT ?", (EtatAttente.EN_ATTENTE.value, limite),
            ).fetchall()

        vivantes: List[ActionEnAttente] = []
        for ligne in lignes:
            action = self._depuis_ligne(ligne)
            if action.est_perimee():
                self._changer_etat(action.identifiant, EtatAttente.EXPIREE)
            else:
                vivantes.append(action)
        return vivantes

    # --- Transitions ----------------------------------------------------------

    def _changer_etat(
        self, identifiant: str, etat: EtatAttente, resultat_final: Optional[str] = None
    ) -> bool:
        """Passe l'action a `etat`, **seulement si elle attend encore**.

        Rend False si aucune ligne n'a change : c'est ce qui rend une double
        confirmation inoffensive.

        Vers un etat NON VALIDE (`ANNULEE`, `EXPIREE`), le contenu part avec :
        garantie 5. Un seul endroit change l'etat, donc un seul endroit efface —
        aucun chemin ne peut abandonner une action en gardant son brouillon.
        """
        efface = etat in ETATS_SANS_VALIDATION
        with closing(self._connexion()) as connexion:
            curseur = connexion.execute(
                f"UPDATE {self.TABLE} SET etat = ?, resultat_final = ?"
                + (", parametres = ?" if efface else "")
                + " WHERE identifiant = ? AND etat = ?",
                ((etat.value, resultat_final, "{}", identifiant, EtatAttente.EN_ATTENTE.value)
                 if efface else
                 (etat.value, resultat_final, identifiant, EtatAttente.EN_ATTENTE.value)),
            )
            connexion.commit()
            return curseur.rowcount == 1

    def annuler(self, identifiant: str) -> bool:
        """Abandonne l'action. Rend False si elle n'attendait plus."""
        return self._changer_etat(identifiant, EtatAttente.ANNULEE)

    def confirmer(self, identifiant: str) -> ResultatAction:
        """Le « oui ». C'est le seul chemin qui execute quoi que ce soit.

        Returns:
            Le `ResultatAction` de l'execution, ou un refus explique : action
            inconnue, deja traitee, perimee, ou executeur absent.
        """
        action = self.lire(identifiant)
        if action is None:
            return non_implemente(
                action="confirmer", cible=identifiant,
                message=f"Aucune action en attente sous l'identifiant « {identifiant} ».",
            )

        if action.etat is EtatAttente.EXPIREE:
            return echec(
                action.capacite, action.cible,
                f"Confirmation trop tardive : cette action a expire le {action.expire_le}. "
                f"Rien n'a ete envoye. Refais la demande si elle est toujours d'actualite.",
            )

        if action.etat is not EtatAttente.EN_ATTENTE:
            return echec(
                action.capacite, action.cible,
                f"Cette action est deja {action.etat.value}"
                + (f" (resultat : {action.resultat_final})." if action.resultat_final
                   else ". Rien n'a ete refait."),
            )

        # Le verrou. Si une autre confirmation est passee entre la lecture et
        # ici, cet UPDATE ne change aucune ligne et on ne rejoue pas l'action.
        if not self._changer_etat(identifiant, EtatAttente.CONFIRMEE):
            deja = self.lire(identifiant)
            return echec(
                action.capacite, action.cible,
                f"Cette action vient d'etre traitee ailleurs "
                f"(resultat : {deja.resultat_final if deja else 'inconnu'}). Rien n'a ete refait.",
            )

        if self.executeur is None:
            resultat = non_implemente(
                action.capacite, action.cible,
                "Aucun executeur n'est branche sur la file d'attente : rien n'a ete envoye.",
            )
        else:
            try:
                resultat = self.executeur(
                    action.connecteur, action.capacite,
                    compte=action.compte, **action.parametres,
                )
            except Exception as erreur:
                logger.error("Execution de %s en echec : %s", identifiant, erreur)
                resultat = echec(action.capacite, action.cible,
                                 f"Erreur pendant l'execution : {erreur}")

        if not isinstance(resultat, ResultatAction):
            resultat = echec(action.capacite, action.cible,
                             "L'executeur n'a pas rendu de resultat exploitable.")

        self._enregistrer_resultat(identifiant, resultat.statut.value)
        return resultat

    def _enregistrer_resultat(self, identifiant: str, statut: str) -> None:
        """Note ce que l'execution a donne, sans toucher a l'etat."""
        with closing(self._connexion()) as connexion:
            connexion.execute(
                f"UPDATE {self.TABLE} SET resultat_final = ? WHERE identifiant = ?",
                (statut, identifiant),
            )
            connexion.commit()
