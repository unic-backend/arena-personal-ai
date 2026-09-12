"""Chiffrement au repos pour un souvenir marque sensible.

Mission ARENA x AI MEMORY VAULT (11/09/2026, DEC-0090). Le module amont
(`ai-encryption-tool/ai`, `frontend/src/cryptoVault.js`, audit complet dans
`docs/audits/ai_memory_vault_audit.md`) chiffre cote navigateur avec l'API Web
Crypto : AES-256-GCM, cle derivee par PBKDF2-HMAC-SHA256 (310 000 iterations),
sel de 16 octets et nonce de 12 octets tires au hasard a CHAQUE chiffrement.
Ce sont de bons choix, verifies ligne a ligne dans leur code (jamais une
cryptographie maison) — repris ICI en Python (`cryptography`, la bibliotheque
deja utilisee ailleurs dans ce depot, jamais une implementation ecrite a la
main), avec deux ecarts deliberes :

1. **310 000 -> 600 000 iterations.** La marge contre une attaque hors
   ligne vaut le cout. Ce paragraphe a longtemps ajoute « la derivation ne
   tourne jamais sur un chemin chaud » — c'etait faux, et c'est ce qui a
   cause un vrai defaut : chaque enveloppe portant son propre sel, relire
   500 souvenirs sensibles repayait 500 derivations, soit 2 min 14 mesurees
   le 12/09/2026. Depuis, la cle est derivee une fois par sel et gardee
   (`CLES_GARDEES`), et le sel est partage par lot d'ecritures
   (`MESSAGES_PAR_SEL`) — la forme ordinaire d'un conteneur chiffre. Le
   nonce, lui, reste tire au hasard a chaque message : c'est la seule
   unicite qu'AES-GCM exige.
2. **Local-first par construction, pas par option.** Il n'existe aucun mode
   ou la phrase de passe quitte la machine — pas de navigateur, pas de
   Supabase, pas de synchronisation. `Coffre.depuis_environnement()` lit
   `USMAN_MEMORY_VAULT_PASSPHRASE`, jamais un fichier commis, jamais un
   parametre de prompt.

**Trois regles :**

1. **Sans coffre configure, un souvenir sensible est refuse, jamais ecrit en
   clair sous couvert de securite.** `core/memory/personnelle.py::retenir`
   applique cette regle ; ce module ne fait qu'exposer l'etat (`disponible`).
2. **Un echec de dechiffrement est un etat, jamais une exception qui
   remonte jusqu'a l'appelant du prompt.** Mauvaise cle, texte chiffre modifie
   d'un seul octet, JSON corrompu : `EchecDechiffrement`, toujours le meme
   type, jamais un `KeyError`/`ValueError` different selon la cause — une
   defense qui distingue "mauvaise cle" de "corrompu" cote appelant ouvre la
   porte a une attaque par oracle.
3. **La phrase de passe n'est jamais journalisee, jamais renvoyee.** Elle vit
   dans `self._passphrase`, utilisee une fois par `_deriver_cle`, jamais
   serialisee par `to_dict`/`__repr__` (le dataclass par defaut l'aurait fait :
   `Coffre` n'en est pas un).
"""
from __future__ import annotations

import base64
import json
import logging
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("usman.memoire.chiffrement")

#: Variable d'environnement portant la phrase de passe du coffre. Jamais un
#: fichier commis, jamais une valeur par defaut : son absence doit se voir.
VARIABLE_PASSPHRASE = "USMAN_MEMORY_VAULT_PASSPHRASE"

#: Voir le docstring du module : 600 000, au-dessus des 310 000 verifies chez
#: AI Memory Vault, parce que la derivation ne tourne jamais sur un chemin chaud.
ITERATIONS_PBKDF2 = 600_000

#: Combien de cles derivees restent en memoire. Une derivation coute 275 ms
#: (mesure du 12/09/2026, 600 000 iterations) : sans ce cache, relire deux
#: fois le meme souvenir sensible la repayait deux fois.
CLES_GARDEES = 256

#: Au-dela de ce nombre de messages, l'instance renouvelle son sel — donc sa
#: cle. AES-GCM exige un nonce unique PAR CLE : avec un nonce de 96 bits tire
#: au hasard, la borne d'anniversaire reste astronomique bien au-dela de ce
#: plafond, et renouveler regulierement garde cette marge intacte meme sur un
#: coffre qui vivrait des annees.
MESSAGES_PAR_SEL = 65_536

#: Nom du fichier ou le sel d'ecriture est conserve, a cote de la base de
#: souvenirs. Il vit ICI et non chez ses deux appelants (`apps/backend/runtime.py`
#: et `core/mcp/memory_server.py`) parce que ces deux PROCESSUS doivent lire le
#: MEME fichier : deux constantes qui divergent, et chacun rederive pour rien.
NOM_FICHIER_SEL = "vault_salt"

TAILLE_SEL = 16   # octets — tire au hasard, partage par lot d'ecritures (MESSAGES_PAR_SEL)
TAILLE_NONCE = 12  # octets — la taille recommandee pour AES-GCM, jamais reutilisee
TAILLE_CLE = 32    # octets — AES-256

#: Version de l'enveloppe serialisee. Un futur changement d'algorithme ou de
#: parametres se distingue par ce champ, jamais par une supposition sur la
#: longueur des octets.
VERSION_ENVELOPPE = 1


class EchecDechiffrement(Exception):
    """Le dechiffrement a echoue — mauvaise cle, texte altere, ou JSON illisible.

    Un seul type pour les trois causes, deliberement : distinguer "la cle est
    fausse" de "le texte a ete modifie" cote appelant donnerait a un attaquant
    un oracle pour deviner la phrase de passe octet par octet.
    """


@dataclass
class _Enveloppe:
    ciphertext: bytes
    nonce: bytes
    sel: bytes
    version: int = VERSION_ENVELOPPE

    def serialiser(self) -> str:
        return json.dumps({
            "v": self.version,
            "ct": base64.b64encode(self.ciphertext).decode("ascii"),
            "iv": base64.b64encode(self.nonce).decode("ascii"),
            "sel": base64.b64encode(self.sel).decode("ascii"),
        })

    @staticmethod
    def depuis(texte: str) -> "_Enveloppe":
        try:
            donnees = json.loads(texte)
            return _Enveloppe(
                ciphertext=base64.b64decode(donnees["ct"]),
                nonce=base64.b64decode(donnees["iv"]),
                sel=base64.b64decode(donnees["sel"]),
                version=int(donnees.get("v", VERSION_ENVELOPPE)),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as erreur:
            raise EchecDechiffrement(
                "Enveloppe chiffree illisible (JSON attendu, forme inattendue)."
            ) from erreur


class Coffre:
    """Chiffre et dechiffre un contenu, avec une phrase de passe fixe.

    Une instance de `Coffre` porte UNE phrase de passe : un souvenir chiffre
    par un coffre ne se dechiffre que par un coffre construit avec la meme
    phrase. Le sel est lu dans l'enveloppe au dechiffrement, donc un souvenir
    ecrit par une instance precedente — y compris avant le partage de sel par
    lot du 12/09/2026 — reste lisible.
    """

    def __init__(
        self, passphrase: str, chemin_sel: "str | Path | None" = None
    ) -> None:
        """chemin_sel: fichier ou le sel d'ecriture est conserve entre deux
        PROCESSUS. Sans lui, chaque nouveau coffre tire son propre sel, donc
        chaque demarrage du serveur repaie une derivation pour relire les
        souvenirs ecrits par le precedent (mesure DEC-0097 : 500 souvenirs
        sensibles ecrits au fil de 100 sessions coutaient 26,7 s a la premiere
        question). Un sel n'est PAS un secret — il existe pour qu'une table
        pre-calculee ne serve pas deux coffres a la fois — mais le fichier est
        ecrit en 0600 par principe de moindre privilege.
        """
        if not (passphrase or "").strip():
            raise ValueError("Un coffre sans phrase de passe ne protege rien.")
        self._passphrase = passphrase
        self._chemin_sel = Path(chemin_sel) if chemin_sel else None
        #: Cles deja derivees, par sel. Mesure du 12/09/2026 : lire 500
        #: souvenirs sensibles prenait 2 min 14 — 275 ms de PBKDF2 par
        #: souvenir, parce que chaque enveloppe portait son propre sel.
        self._cles: "OrderedDict[bytes, bytes]" = OrderedDict()
        #: Le sel de cette instance, tire une seule fois et reutilise pour
        #: les ecritures suivantes (voir `MESSAGES_PAR_SEL`). Le NONCE, lui,
        #: reste tire au hasard a chaque message : c'est lui que GCM exige
        #: unique, et c'etait deja le cas avant ce changement.
        self._sel_courant: bytes | None = None
        self._messages_sous_ce_sel = 0

    def __repr__(self) -> str:  # jamais la phrase de passe dans un log/traceback
        return "Coffre(passphrase=<masque>)"

    @classmethod
    def depuis_environnement(
        cls,
        variable: str = VARIABLE_PASSPHRASE,
        chemin_sel: "str | Path | None" = None,
    ) -> "Coffre | None":
        """Construit un coffre depuis l'environnement, ou rend None si absent.

        None est un etat normal : la memoire fonctionne sans coffre pour tout
        souvenir non sensible (mission §11, local-first). Ce n'est que
        `retenir(..., sensible=True)` qui a besoin qu'il existe.
        """
        valeur = os.environ.get(variable)
        if not (valeur or "").strip():
            return None
        return cls(valeur, chemin_sel=chemin_sel)

    def _deriver_cle(self, sel: bytes) -> bytes:
        """La cle pour ce sel, derivee une fois puis gardee en memoire.

        Le cache ne change RIEN au format ni a la robustesse : la meme
        phrase et le meme sel donnent la meme cle, par definition de PBKDF2.
        Il change seulement le nombre de fois qu'on paie les 600 000
        iterations pour le meme sel.
        """
        connue = self._cles.get(sel)
        if connue is not None:
            self._cles.move_to_end(sel)
            return connue
        cle = self._deriver_vraiment(sel)
        self._cles[sel] = cle
        self._cles.move_to_end(sel)
        while len(self._cles) > CLES_GARDEES:
            self._cles.popitem(last=False)
        return cle

    def _sel_pour_ecrire(self) -> bytes:
        """Le sel des ecritures de cette instance, renouvele par lots.

        Avant le 12/09/2026, chaque message tirait son propre sel : deux
        souvenirs sensibles ne partageaient jamais une cle, donc les relire
        coutait une derivation CHACUN. Un sel par lot est la pratique
        habituelle d'un conteneur chiffre (un sel d'en-tete, puis un nonce
        par message) et laisse le format d'enveloppe inchange — les
        souvenirs deja ecrits restent lisibles tels quels.
        """
        if self._sel_courant is None:
            self._sel_courant = self._sel_conserve() or self._nouveau_sel()
        elif self._messages_sous_ce_sel >= MESSAGES_PAR_SEL:
            self._sel_courant = self._nouveau_sel()
        self._messages_sous_ce_sel += 1
        return self._sel_courant

    def _sel_conserve(self) -> "bytes | None":
        """Le sel du fichier, quand il existe et fait la bonne taille.

        Un fichier illisible ou tronque n'est PAS une raison de refuser
        d'ecrire : on en tire un neuf et on le remplace. Rien n'est perdu —
        chaque enveloppe porte son propre sel, donc les souvenirs deja ecrits
        restent lisibles quoi qu'il arrive a ce fichier.
        """
        if self._chemin_sel is None or not self._chemin_sel.exists():
            return None
        try:
            sel = self._chemin_sel.read_bytes()
        except OSError as erreur:
            logger.warning("Sel conserve illisible (%s) : un sel neuf est tire.", erreur)
            return None
        if len(sel) != TAILLE_SEL:
            logger.warning(
                "Sel conserve de taille inattendue (%d octets au lieu de %d) : "
                "un sel neuf est tire.", len(sel), TAILLE_SEL,
            )
            return None
        return sel

    def _nouveau_sel(self) -> bytes:
        """Un sel neuf, conserve pour les prochains processus si un chemin existe."""
        sel = os.urandom(TAILLE_SEL)
        self._messages_sous_ce_sel = 0
        if self._chemin_sel is not None:
            try:
                self._chemin_sel.parent.mkdir(parents=True, exist_ok=True)
                self._chemin_sel.write_bytes(sel)
                os.chmod(self._chemin_sel, 0o600)
            except OSError as erreur:
                # Ne pas conserver le sel coute des derivations, jamais un
                # souvenir : l'ecriture continue avec le sel en memoire.
                logger.warning(
                    "Sel non conserve dans %s (%s) : les prochains processus "
                    "repaieront une derivation.", self._chemin_sel, erreur,
                )
        return sel

    def _deriver_vraiment(self, sel: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=TAILLE_CLE,
            salt=sel,
            iterations=ITERATIONS_PBKDF2,
        )
        return kdf.derive(self._passphrase.encode("utf-8"))

    def chiffrer(self, clair: str) -> str:
        """Chiffre `clair`, rend une enveloppe serialisee (texte, stockable telle quelle)."""
        sel = self._sel_pour_ecrire()
        # Le nonce, lui, est TOUJOURS neuf : c'est l'exigence d'AES-GCM, et
        # la seule des deux qui ne se partage jamais.
        nonce = os.urandom(TAILLE_NONCE)
        cle = self._deriver_cle(sel)
        ciphertext = AESGCM(cle).encrypt(nonce, clair.encode("utf-8"), None)
        return _Enveloppe(ciphertext=ciphertext, nonce=nonce, sel=sel).serialiser()

    def dechiffrer(self, enveloppe_serialisee: str) -> str:
        """Dechiffre une enveloppe produite par `chiffrer`.

        Raises:
            EchecDechiffrement: mauvaise phrase de passe, texte chiffre altere
                (le tag d'authentification GCM ne correspond plus), ou
                enveloppe illisible. Jamais un texte en clair plausible mais
                faux : GCM authentifie, il ne "dechiffre a moitie" pas.
        """
        enveloppe = _Enveloppe.depuis(enveloppe_serialisee)
        cle = self._deriver_cle(enveloppe.sel)
        try:
            clair = AESGCM(cle).decrypt(enveloppe.nonce, enveloppe.ciphertext, None)
        except InvalidTag as erreur:
            raise EchecDechiffrement(
                "Dechiffrement refuse : mauvaise phrase de passe, ou texte chiffre modifie."
            ) from erreur
        return clair.decode("utf-8")
