"""Les mains de Dioumtoukay : lire, écrire, lister, exécuter, git.

Nommé par le propriétaire le 02/09/2026. Ce module est ce qui lui permet
d'entrer dans ses fichiers, son terminal et son dépôt — demande explicite, et
**DEC-0038** enregistre qu'il a levé DEC-0014 en connaissance de cause après
qu'on lui ait présenté ce que ça coûte.

**Donc : pas de garde-fou ici.** Aucune confirmation, aucun chemin interdit,
aucune commande refusée. Ce n'est pas un oubli, c'est sa décision, et la
reprendre en douce dans le code reviendrait à décider à sa place.

**Ce qui est tenu, et qui n'est pas une limite :**

1. **Tout laisse une trace.** Chaque action passe par `JournalDesActions`. Ce
   n'est pas une autorisation à demander, c'est un compte-rendu à lire : un
   agent qui agit sans trace ne peut pas être corrigé quand il se trompe, et
   c'est le propriétaire qui doit pouvoir dire ce qui s'est passé chez lui.

2. **Un échec se rapporte, il ne se déguise pas.** `docker run` rendait un code
   de sortie non nul SANS lever, et l'échec passait pour autre chose
   (`tools/docker_local.py`, mesure du 01/09/2026). Ici le code de sortie, la
   sortie standard et l'erreur sont rendus tels quels — jamais résumés, jamais
   remplacés par une phrase rassurante.

3. **Rien n'est simulé.** Une commande qui n'a pas tourné rend son erreur, pas
   un résultat plausible.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.atelier")

#: Au-delà, une commande est considérée comme bloquée. Réglable par l'appelant :
#: `pytest` sur ce dépôt prend plus d'une minute, un `git status` moins d'une
#: seconde. Un plafond unique serait faux pour l'un des deux.
DELAI_PAR_DEFAUT = 120.0

#: Ce qu'on rend d'une sortie très longue. Le reste est coupé, et la coupe est
#: **annoncée** : une sortie tronquée en silence se lit comme une sortie
#: complète, et c'est ainsi qu'on conclut faux sur un test qui a échoué plus
#: bas.
SORTIE_MAX = 20_000


@dataclass
class Resultat:
    """Ce qu'une action a vraiment donné.

    Attributes:
        ok: l'action a fait ce qu'on lui demandait.
        message: en clair, pour le propriétaire.
        sortie: ce que la commande a écrit, tel quel.
        erreur: ce qu'elle a écrit sur la sortie d'erreur, tel quel.
        code: le code de sortie. `None` quand aucune commande n'a tourné.
    """

    ok: bool
    message: str
    sortie: str = ""
    erreur: str = ""
    code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "message": self.message, "sortie": self.sortie,
                "erreur": self.erreur, "code": self.code}


def _couper(texte: str) -> str:
    """Coupe une sortie trop longue, et le dit."""
    texte = texte or ""
    if len(texte) <= SORTIE_MAX:
        return texte
    return texte[:SORTIE_MAX] + f"\n[... coupé, {len(texte) - SORTIE_MAX} caractères de plus]"


class Atelier:
    """Les mains. Un journal, aucun garde-fou — DEC-0038."""

    def __init__(self, racine: Optional[Path] = None, journal: Any = None) -> None:
        # `racine` sert de point de départ aux chemins relatifs, **pas** de
        # prison : un chemin absolu ailleurs est suivi. C'est ce qu'il a
        # demandé — « entrer dans mes fichiers du pc ».
        self.racine = Path(racine) if racine else Path.cwd()
        self.journal = journal

    # --- Trace ------------------------------------------------------------------

    def _noter(self, action: str, cible: str, resultat: Resultat) -> None:
        """Écrit ce qui vient d'être fait. Ne lève jamais : un journal en panne
        ne doit pas empêcher le travail, il doit se plaindre."""
        if self.journal is None:
            return
        try:
            from core.actions.journal import ActionEnregistree

            self.journal.enregistrer(ActionEnregistree(
                outil="dioumtoukay", action=action, cible=cible,
                resultat="SUCCESS" if resultat.ok else "FAILED",
                niveau_permission="AUTORISE_DEC-0038",
                erreurs=None if resultat.ok else (resultat.message or "")[:500],
                preuve=str(resultat.code) if resultat.code is not None else None))
        except Exception as erreur:  # noqa: BLE001
            logger.warning("Action non journalisee (%s sur %s) : %s", action, cible, erreur)

    def _chemin(self, chemin: str) -> Path:
        """Le chemin demandé, relatif à la racine s'il n'est pas absolu."""
        p = Path(chemin).expanduser()
        return p if p.is_absolute() else (self.racine / p)

    # --- Fichiers ----------------------------------------------------------------

    def lire(self, chemin: str) -> Resultat:
        """Le contenu d'un fichier, tel quel."""
        p = self._chemin(chemin)
        try:
            contenu = p.read_text(encoding="utf-8", errors="replace")
        except Exception as erreur:  # noqa: BLE001 — l'echec se nomme
            r = Resultat(False, f"Lecture impossible ({type(erreur).__name__}) : {p}")
        else:
            r = Resultat(True, f"{p} lu ({len(contenu)} caracteres).", sortie=_couper(contenu))
        self._noter("lire", str(p), r)
        return r

    def ecrire(self, chemin: str, contenu: str) -> Resultat:
        """Écrit un fichier. Crée les dossiers manquants."""
        p = self._chemin(chemin)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contenu, encoding="utf-8")
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Ecriture impossible ({type(erreur).__name__}) : {p}")
        else:
            r = Resultat(True, f"{p} ecrit ({len(contenu)} caracteres).")
        self._noter("ecrire", str(p), r)
        return r

    def lister(self, chemin: str = ".") -> Resultat:
        """Ce que contient un dossier."""
        p = self._chemin(chemin)
        try:
            entrees = sorted(
                f"{'d' if e.is_dir() else 'f'}  {e.name}" for e in p.iterdir())
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Dossier illisible ({type(erreur).__name__}) : {p}")
        else:
            r = Resultat(True, f"{p} : {len(entrees)} entree(s).",
                         sortie=_couper("\n".join(entrees)))
        self._noter("lister", str(p), r)
        return r

    def deplacer(self, source: str, destination: str) -> Resultat:
        """Déplace ou renomme. C'est ce qui range un dossier."""
        a, b = self._chemin(source), self._chemin(destination)
        try:
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(a), str(b))
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Deplacement impossible ({type(erreur).__name__}) : {a} -> {b}")
        else:
            r = Resultat(True, f"{a} deplace vers {b}.")
        self._noter("deplacer", f"{a} -> {b}", r)
        return r

    # --- Terminal ------------------------------------------------------------------

    def executer(self, commande: List[str], delai: float = DELAI_PAR_DEFAUT,
                 dossier: Optional[str] = None) -> Resultat:
        """Lance une commande et rend ce qu'elle a vraiment donné.

        La commande est une **liste** — `["git", "status"]`, jamais
        `"git status"` passé au shell. Ce n'est pas une restriction de ce qu'il
        peut lancer : c'est ce qui empêche un nom de fichier contenant une
        espace ou un `;` de devenir deux commandes par accident.

        Le code de sortie est rendu tel quel. Un code non nul est un echec
        **rapporte**, pas une exception avalee : c'est le defaut mesure le
        01/09/2026 dans `tools/docker_local.py`.
        """
        if not commande:
            return Resultat(False, "Aucune commande donnee.")
        ou = self._chemin(dossier) if dossier else self.racine
        try:
            fini = subprocess.run(  # noqa: S603 — c'est le but du module
                commande, cwd=str(ou), capture_output=True, text=True,
                timeout=delai, check=False)
        except FileNotFoundError:
            r = Resultat(False, f"Commande introuvable : {commande[0]}")
        except subprocess.TimeoutExpired:
            r = Resultat(False, f"Commande arretee apres {delai:.0f}s : {' '.join(commande)}")
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Commande impossible ({type(erreur).__name__}).")
        else:
            r = Resultat(
                ok=fini.returncode == 0,
                message=(f"{' '.join(commande)} -> code {fini.returncode}"),
                sortie=_couper(fini.stdout), erreur=_couper(fini.stderr),
                code=fini.returncode)
        self._noter("executer", " ".join(commande), r)
        return r

    # --- Git -------------------------------------------------------------------------

    def git(self, *arguments: str, dossier: Optional[str] = None) -> Resultat:
        """Une commande git, dans le dépôt demandé.

        Rien n'est interdit ici — `push` compris. DEC-0038 : c'est ce qu'il a
        demandé, et le journal dit ce qui est parti.
        """
        return self.executer(["git", *arguments], dossier=dossier)
