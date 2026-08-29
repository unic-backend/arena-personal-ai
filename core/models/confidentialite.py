"""Ce qui a le droit de sortir de sa machine, et ce qui n'en sort jamais.

ARENA a longtemps eu une reponse simple : **rien ne sort** (DEC-0002). Le
proprietaire a ouvert le cloud le 2026-08-28 pour la vitesse (DEC-0009), ce qui
transforme cette reponse simple en une question posee **a chaque phrase**.

Ce module est la reponse. Il classe un texte avant qu'il ne parte, et c'est la
seule chose qui se tient entre son mot de passe et un serveur qui n'est pas le
sien.

**Cinq regles :**

1. **Le doute penche vers sa machine.** Une phrase qu'on ne sait pas classer est
   `PRIVE`, jamais `PUBLIC` : ARENA est son assistant personnel, pas un moteur
   de recherche. Ce qu'il dit lui appartient jusqu'a preuve du contraire.

2. **`TRES_SENSIBLE` ne sort jamais.** Aucune politique, aucun reglage, aucune
   demande explicite ne le fait sortir. Un mot de passe envoye une fois est
   envoye pour toujours.

3. **Le nom compte autant que la forme.** On reconnait un secret a ce qui
   l'annonce (« mot de passe : »), pas seulement a son allure — reconnaitre un
   jeton a sa tete rate ceux qui n'y ressemblent pas, et ce sont ceux-la qui
   partent.

4. **La piece jointe classe la demande.** Une question anodine posee sur un
   document de client n'est pas anodine : le contexte monte le niveau, il ne le
   descend jamais.

5. **Le classement se dit.** Chaque decision porte ce qui l'a declenchee, pour
   qu'elle soit verifiable au lieu d'etre crue.
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from core.actions.journal import FRAGMENTS_SECRETS


class Confidentialite(str, Enum):
    """Les quatre niveaux, du plus ouvert au plus ferme."""

    PUBLIC = "PUBLIC"                    # connaissance generale, code, definitions
    PRIVE = "PRIVE"                      # ses gouts, ses projets — a lui, sans etre secret
    SENSIBLE = "SENSIBLE"                # clients, montants, courrier, documents
    TRES_SENSIBLE = "TRES_SENSIBLE"      # mots de passe, cles, jetons


#: L'ordre est la definition de « plus ferme ». Il sert au choix du fournisseur.
ORDRE = [Confidentialite.PUBLIC, Confidentialite.PRIVE,
         Confidentialite.SENSIBLE, Confidentialite.TRES_SENSIBLE]


def rang(niveau: Confidentialite) -> int:
    """La position d'un niveau. 0 est le plus ouvert."""
    return ORDRE.index(niveau)


#: Ce qui ANNONCE un secret. Reprend les fragments deja utilises par le journal
#: des actions (`core/actions/journal.py`) : une seule liste, un seul endroit ou
#: se tromper. Les formulations francaises courantes s'y ajoutent.
ANNONCES_DE_SECRET = tuple(FRAGMENTS_SECRETS) + (
    "mot de passe", "identifiant de connexion", "cle privee", "clé privée",
    "cle d'api", "clé d'api", "cle secrete", "clé secrète", "code pin",
    "numero de carte", "numéro de carte", "cvv", "iban",
)

#: Ce qui RESSEMBLE a un secret. Complement, jamais substitut : ces motifs
#: attrapent ce qui n'a pas ete annonce.
FORMES_DE_SECRET = (
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),          # cles de fournisseurs
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),                      # Groq
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),                      # GitHub
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"),                    # Google
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}"),
)

#: Ce qui touche a ses affaires : clients, argent, courrier, documents.
AFFAIRES = (
    "devis", "facture", "client", "chantier", "montant", "acompte", "reglement",
    "règlement", "paiement", "ninea", "rccm", "contrat", "marche", "marché",
    "appel d'offre", "appel d offre", "mail de", "courriel", "e-mail de",
    "mon courrier", "ma boite mail", "ma boîte mail", "releve", "relevé",
    "banque", "bancaire", "salaire", "benefice", "bénéfice", "chiffre d'affaires",
    "fournisseur", "commande", "bon de livraison",
)

#: Ce qui est a lui sans etre confidentiel : ses gouts, ses habitudes.
PERSONNEL = (
    "je prefere", "je préfère", "mon habitude", "mes notes", "mon projet",
    "rappelle-moi", "rappelle moi", "mon planning", "mon agenda", "ma journee",
    "ma journée", "chez moi", "ma famille", "mon telephone", "mon téléphone",
)

#: Ce qui ne parle que du monde. La liste est courte **exprès** : elle ne sert
#: qu'a faire redescendre au niveau PUBLIC ce qui n'a manifestement rien de
#: personnel. Dans le doute, on n'y touche pas.
CONNAISSANCE_GENERALE = (
    "qui est", "qu'est-ce que", "qu est ce que", "c'est quoi", "definition",
    "définition", "explique-moi", "explique moi", "combien font", "traduis",
    "capitale d", "histoire de", "comment fonctionne", "difference entre",
    "différence entre", "en python", "en javascript", "regex", "algorithme",
    "quelle est la", "quel est le", "qui a invente", "qui a inventé",
    "que veut dire", "pourquoi le", "pourquoi la", "comment dit-on",
)


@dataclass(frozen=True)
class Classement:
    """Le niveau retenu, et ce qui l'a declenche."""

    niveau: Confidentialite
    motifs: List[str] = field(default_factory=list)

    @property
    def sortie_interdite(self) -> bool:
        """Vrai quand rien ne peut faire sortir ce texte de sa machine."""
        return self.niveau is Confidentialite.TRES_SENSIBLE

    def pourquoi(self) -> str:
        """Une phrase lisible. Un classement qu'on ne peut pas verifier se croit."""
        if not self.motifs:
            return f"{self.niveau.value} — rien de particulier releve"
        return f"{self.niveau.value} — {', '.join(self.motifs)}"

    def to_dict(self) -> Dict[str, Any]:
        return {"niveau": self.niveau.value, "motifs": list(self.motifs)}


def _contient(texte: str, fragments: Sequence[str]) -> List[str]:
    """Les fragments reellement presents, pour que le motif soit nommable."""
    return [fragment for fragment in fragments if fragment in texte]


def classer(texte: str, contexte: Optional[Sequence[str]] = None) -> Classement:
    """Classe un texte, et dit pourquoi.

    Args:
        texte: la demande du proprietaire.
        contexte: ce qui partira AVEC elle — souvenirs retenus, contenu d'une
            piece jointe. Le contexte ne fait que **monter** le niveau : une
            question anodine posee sur un document de client ne l'est pas.

    Returns:
        Le classement. Sans rien de reconnaissable, `PRIVE` — pas `PUBLIC` :
        ARENA est son assistant, ce qu'il lui dit lui appartient.
    """
    entier = " ".join([texte or ""] + [str(morceau) for morceau in (contexte or [])])
    minuscule = entier.lower()
    motifs: List[str] = []

    # 1. Ce qui ne sort jamais. Teste en premier : rien ne doit pouvoir le
    #    faire redescendre.
    annonces = _contient(minuscule, ANNONCES_DE_SECRET)
    formes = [motif.pattern for motif in FORMES_DE_SECRET if motif.search(entier)]
    if annonces or formes:
        if annonces:
            motifs.append(f"secret annonce ({annonces[0]})")
        if formes:
            motifs.append("valeur en forme de secret")
        return Classement(Confidentialite.TRES_SENSIBLE, motifs)

    # 2. Ses affaires : clients, argent, courrier.
    affaires = _contient(minuscule, AFFAIRES)
    if affaires:
        motifs.append(f"ses affaires ({affaires[0]})")
        return Classement(Confidentialite.SENSIBLE, motifs)

    # 3. Un contexte joint est du sien : il ne descend jamais sous SENSIBLE.
    if contexte:
        return Classement(Confidentialite.SENSIBLE,
                          ["un contenu personnel accompagne la demande"])

    # 4. Ce qui ne parle que du monde.
    if _contient(minuscule, CONNAISSANCE_GENERALE) and not _contient(minuscule, PERSONNEL):
        return Classement(Confidentialite.PUBLIC, ["connaissance generale"])

    # 5. Le reste est a lui. C'est le defaut, et il penche vers sa machine.
    personnel = _contient(minuscule, PERSONNEL)
    if personnel:
        return Classement(Confidentialite.PRIVE, [f"personnel ({personnel[0]})"])
    return Classement(Confidentialite.PRIVE, [])


# --- Ce que la politique autorise ----------------------------------------------

@dataclass(frozen=True)
class AutorisationCloud:
    """Le cloud a-t-il le droit de voir ce texte, et pourquoi."""

    autorise: bool
    raison: str


#: Ce que chaque regime autorise a sortir. La table est ecrite plutot que
#: calculee : une regle de confidentialite doit se lire, pas se deduire.
#:
#: `TRES_SENSIBLE` n'y figure nulle part, et ce n'est pas un oubli.
NIVEAUX_SORTANTS = {
    "LOCAL_ONLY": (),
    "HYBRIDE": (Confidentialite.PUBLIC, Confidentialite.PRIVE),
    "CLOUD_PREFERRED": (Confidentialite.PUBLIC, Confidentialite.PRIVE,
                        Confidentialite.SENSIBLE),
}


def cloud_autorise(classement: Classement, mode: str) -> AutorisationCloud:
    """Dit si ce texte peut partir vers un service distant, et pourquoi.

    Args:
        classement: ce que `classer()` a retenu.
        mode: `LOCAL_ONLY`, `HYBRIDE` ou `CLOUD_PREFERRED`.

    Returns:
        L'autorisation, avec sa raison. Un mode inconnu **refuse** : devant un
        reglage qu'on ne comprend pas, la machine du proprietaire est la seule
        reponse sure.
    """
    if classement.niveau is Confidentialite.TRES_SENSIBLE:
        return AutorisationCloud(
            False, "un secret ne sort jamais, quel que soit le reglage")

    sortants = NIVEAUX_SORTANTS.get(mode)
    if sortants is None:
        return AutorisationCloud(False, f"mode inconnu ({mode}) : local par securite")
    if not sortants:
        return AutorisationCloud(False, "mode local seul")
    if classement.niveau in sortants:
        return AutorisationCloud(True, f"{classement.niveau.value} autorise en {mode}")
    return AutorisationCloud(
        False, f"{classement.niveau.value} reste sur sa machine en {mode}")
