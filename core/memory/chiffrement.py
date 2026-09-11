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

1. **310 000 -> 600 000 iterations.** La derivation de cle ne tourne jamais
   sur un chemin chaud (un souvenir sensible s'ecrit et se lit rarement, pas a
   chaque message) : le cout supplementaire est negligeable, la marge contre
   une attaque hors ligne ne l'est pas.
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
from dataclasses import dataclass

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

TAILLE_SEL = 16   # octets — un sel par chiffrement, jamais partage entre deux souvenirs
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
    phrase (le sel differe a chaque appel, la phrase non).
    """

    def __init__(self, passphrase: str) -> None:
        if not (passphrase or "").strip():
            raise ValueError("Un coffre sans phrase de passe ne protege rien.")
        self._passphrase = passphrase

    def __repr__(self) -> str:  # jamais la phrase de passe dans un log/traceback
        return "Coffre(passphrase=<masque>)"

    @classmethod
    def depuis_environnement(cls, variable: str = VARIABLE_PASSPHRASE) -> "Coffre | None":
        """Construit un coffre depuis l'environnement, ou rend None si absent.

        None est un etat normal : la memoire fonctionne sans coffre pour tout
        souvenir non sensible (mission §11, local-first). Ce n'est que
        `retenir(..., sensible=True)` qui a besoin qu'il existe.
        """
        valeur = os.environ.get(variable)
        if not (valeur or "").strip():
            return None
        return cls(valeur)

    def _deriver_cle(self, sel: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=TAILLE_CLE,
            salt=sel,
            iterations=ITERATIONS_PBKDF2,
        )
        return kdf.derive(self._passphrase.encode("utf-8"))

    def chiffrer(self, clair: str) -> str:
        """Chiffre `clair`, rend une enveloppe serialisee (texte, stockable telle quelle)."""
        sel = os.urandom(TAILLE_SEL)
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
