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
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.atelier import verrous

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

#: Quelle part du plafond va à la **fin** de la sortie. Ne garder que le début
#: était un vrai défaut, et c'est celui qui coûtait le plus cher ici : `pytest`
#: écrit son verdict — « 3 failed » et le nom des tests tombés — sur ses toutes
#: dernières lignes. Une suite bavarde remplissait les 20 000 caractères avec
#: des points, et la seule information qui comptait disparaissait dans la coupe.
#: Dioumtoukay concluait alors « les tests passent » sur une sortie amputée.
PART_DE_LA_FIN = 0.6


@dataclass
class Resultat:
    """Ce qu'une action a vraiment donné.

    Attributes:
        ok: l'action a fait ce qu'on lui demandait.
        message: en clair, pour le propriétaire.
        sortie: ce que la commande a écrit, tel quel.
        erreur: ce qu'elle a écrit sur la sortie d'erreur, tel quel.
        code: le code de sortie. `None` quand aucune commande n'a tourné.
        donnees: structure typée, quand l'action en produit une
            (`metadonnees()`) — vide pour toutes les autres actions.
    """

    ok: bool
    message: str
    sortie: str = ""
    erreur: str = ""
    code: Optional[int] = None
    donnees: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        corps = {"ok": self.ok, "message": self.message, "sortie": self.sortie,
                "erreur": self.erreur, "code": self.code}
        if self.donnees:
            corps["donnees"] = self.donnees
        return corps


def _couper(texte: str) -> str:
    """Coupe une sortie trop longue en gardant **le début et la fin**.

    Le milieu est ce qu'on peut perdre ; la fin, non. Un `pytest` rend son
    verdict sur ses dernières lignes, un `git log` son commit le plus ancien,
    une compilation son résumé d'erreurs. Ne garder que le début revenait à
    couper systématiquement la réponse à la question posée.
    """
    texte = texte or ""
    if len(texte) <= SORTIE_MAX:
        return texte
    fin = int(SORTIE_MAX * PART_DE_LA_FIN)
    debut = SORTIE_MAX - fin
    manque = len(texte) - SORTIE_MAX
    return (texte[:debut]
            + f"\n[... coupé, {manque} caractères au milieu ...]\n"
            + texte[-fin:])


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
        """Écrit un fichier. Crée les dossiers manquants.

        Sérialisée par chemin (`verrous.pour`) : deux tâches qui écrivent le
        même fichier en même temps (mission ARENA x TRANS4MERS §20) attendent
        leur tour au lieu d'entrelacer leurs octets — jamais refusées, jamais
        bloquées plus longtemps qu'une écriture disque réelle.
        """
        p = self._chemin(chemin)
        with verrous.pour(p):
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(contenu, encoding="utf-8")
            except Exception as erreur:  # noqa: BLE001
                r = Resultat(False, f"Ecriture impossible ({type(erreur).__name__}) : {p}")
            else:
                r = Resultat(True, f"{p} ecrit ({len(contenu)} caracteres).")
        self._noter("ecrire", str(p), r)
        return r

    def remplacer(self, chemin: str, ancien: str, nouveau: str) -> Resultat:
        """Remplace un passage précis d'un fichier, sans toucher au reste.

        **C'est la correction la plus importante de cette version.** Avant, la
        seule façon de modifier un fichier était `ecrire`, qui remplace TOUT :
        pour changer une ligne dans un fichier de six cents, le modèle devait
        les réécrire toutes de mémoire. Un modèle local de 14 milliards de
        paramètres ne restitue pas six cents lignes sans en abîmer une — et
        l'abîmée passait pour une correction.

        Deux refus, et ce ne sont pas des garde-fous mais des mesures :

        - **le passage est introuvable** : le modèle a cité de mémoire un texte
          qui n'est pas dans le fichier. Écrire quand même mettrait la
          correction au mauvais endroit ;
        - **le passage apparaît plusieurs fois** : rien ne dit lequel il visait.
          En choisir un serait deviner, et le rapport annoncerait une réussite.

        Dans les deux cas, l'échec dit **ce qu'il faut faire** : relire le
        fichier, ou citer un passage plus long.
        """
        p = self._chemin(chemin)
        # Le verrou entoure LECTURE + ECRITURE ensemble : c'est ce qui rend la
        # verification « le passage apparait exactement une fois » fiable
        # meme sous concurrence reelle (mission §11/§12/§20/§46). Sans lui,
        # deux taches pourraient toutes deux lire la version AVANT la
        # modification de l'autre, trouver chacune le passage une fois, et la
        # seconde ecriture ecraserait silencieusement la premiere (une
        # « lost update » classique) — avec le verrou, la seconde tache relit
        # forcement le contenu DEJA modifie par la premiere, donc echoue
        # proprement (« introuvable ») au lieu d'ecraser son travail.
        with verrous.pour(p):
            try:
                contenu = p.read_text(encoding="utf-8")
            except Exception as erreur:  # noqa: BLE001
                r = Resultat(False, f"Lecture impossible ({type(erreur).__name__}) : {p}")
                self._noter("remplacer", str(p), r)
                return r

            vus = contenu.count(ancien)
            if not ancien:
                r = Resultat(False, "Aucun passage a remplacer n'a ete donne.")
            elif vus == 0:
                r = Resultat(False, f"Passage introuvable dans {p} : relis le fichier, "
                                    "le texte cite n'y est pas tel quel.")
            elif vus > 1:
                r = Resultat(False, f"Passage present {vus} fois dans {p} : cite un "
                                    "extrait plus long, qui n'apparaisse qu'une fois.")
            else:
                try:
                    p.write_text(contenu.replace(ancien, nouveau, 1), encoding="utf-8")
                except Exception as erreur:  # noqa: BLE001
                    r = Resultat(False, f"Ecriture impossible ({type(erreur).__name__}) : {p}")
                else:
                    r = Resultat(True, f"{p} modifie ({len(ancien)} caracteres remplaces "
                                       f"par {len(nouveau)}).")
        self._noter("remplacer", str(p), r)
        return r

    def chercher(self, motif: str, chemin: str = ".", limite: int = 100) -> Resultat:
        """Cherche un texte dans les fichiers, et rend les lignes trouvées.

        Sans ça, corriger un bug commence par deviner dans quel fichier il est.
        `grep` fait le travail quand il existe ; sinon la recherche se fait ici
        même, parce qu'une machine sans `grep` ne doit pas rendre Dioumtoukay
        aveugle.

        La recherche est **littérale**, pas une expression régulière : un nom de
        fonction contient des points et des parenthèses, et les traiter comme
        des motifs ferait trouver n'importe quoi.
        """
        p = self._chemin(chemin)
        if not motif:
            r = Resultat(False, "Aucun texte a chercher n'a ete donne.")
            self._noter("chercher", str(p), r)
            return r

        lignes = self._chercher_avec_grep(motif, p, limite)
        if lignes is None:
            lignes = self._chercher_ici_meme(motif, p, limite)

        if lignes is None:
            r = Resultat(False, f"Recherche impossible dans {p}.")
        elif not lignes:
            # Zero resultat est une reponse, pas un echec : « ce mot n'est nulle
            # part » est exactement ce qu'il fallait savoir.
            r = Resultat(True, f"« {motif} » : aucune ligne dans {p}.")
        else:
            atteinte = " (limite atteinte)" if len(lignes) >= limite else ""
            r = Resultat(True, f"« {motif} » : {len(lignes)} ligne(s){atteinte}.",
                         sortie=_couper("\n".join(lignes)))
        self._noter("chercher", f"{motif} dans {p}", r)
        return r

    @staticmethod
    def _chercher_avec_grep(motif: str, ou: Path, limite: int) -> Optional[List[str]]:
        """Les lignes trouvées par `grep`, ou `None` s'il n'a pas pu répondre."""
        try:
            fini = subprocess.run(  # noqa: S603 — c'est le but du module
                ["grep", "-rnF", "--", motif, str(ou)],
                capture_output=True, text=True, timeout=30, check=False)
        except Exception:  # noqa: BLE001 — absent, trop lent : on cherchera ici
            return None
        # `grep` rend 1 quand il n'a rien trouve : ce n'est pas une panne.
        if fini.returncode not in (0, 1):
            return None
        return [ligne for ligne in fini.stdout.splitlines() if ligne][:limite]

    @staticmethod
    def _chercher_ici_meme(motif: str, ou: Path, limite: int) -> Optional[List[str]]:
        """Le repli, quand `grep` manque. Les binaires sont sautés en silence."""
        fichiers = [ou] if ou.is_file() else sorted(ou.rglob("*"))
        trouvees: List[str] = []
        for fichier in fichiers:
            if not fichier.is_file():
                continue
            try:
                contenu = fichier.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for numero, ligne in enumerate(contenu.splitlines(), start=1):
                if motif in ligne:
                    trouvees.append(f"{fichier}:{numero}:{ligne}")
                    if len(trouvees) >= limite:
                        return trouvees
        return trouvees

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
        # Source ET destination, dans un ordre stable (`verrous.pour_plusieurs`)
        # : deux deplacements concurrents qui touchent les memes deux chemins
        # dans des sens opposes ne peuvent pas se bloquer l'un l'autre.
        with verrous.pour_plusieurs([a, b]):
            try:
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(a), str(b))
            except Exception as erreur:  # noqa: BLE001
                r = Resultat(False, f"Deplacement impossible ({type(erreur).__name__}) : {a} -> {b}")
            else:
                r = Resultat(True, f"{a} deplace vers {b}.")
        self._noter("deplacer", f"{a} -> {b}", r)
        return r

    def copier(self, source: str, destination: str) -> Resultat:
        """Copie un fichier. La source reste en place, contrairement a `deplacer`.

        DEC-0038 comme le reste de ce module : aucune garde ici. Une
        capacite qui a besoin de confirmer avant de copier (`file_
        organization`, mission « AI File Sorter ») la demande a son propre
        niveau, avant d'appeler cette methode — jamais dedans.
        """
        a, b = self._chemin(source), self._chemin(destination)
        with verrous.pour_plusieurs([a, b]):
            try:
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(a), str(b))
            except Exception as erreur:  # noqa: BLE001
                r = Resultat(False, f"Copie impossible ({type(erreur).__name__}) : {a} -> {b}")
            else:
                r = Resultat(True, f"{a} copie vers {b}.")
        self._noter("copier", f"{a} -> {b}", r)
        return r

    def supprimer(self, chemin: str) -> Resultat:
        """Supprime un fichier (jamais un dossier — `deplacer`/`copier`
        suffisent pour ranger ; supprimer un dossier entier n'a jamais ete
        demande et resterait a construire deliberement s'il l'etait).

        Meme absence de garde que le reste du module. Un appelant qui veut
        une suppression protegee (confirmation, corbeille) la construit
        au-dessus — c'est exactement ce que fait le connecteur `file_
        organization`.
        """
        p = self._chemin(chemin)
        with verrous.pour(p):
            try:
                if p.is_dir():
                    raise IsADirectoryError(f"{p} est un dossier, pas un fichier")
                p.unlink()
            except Exception as erreur:  # noqa: BLE001
                r = Resultat(False, f"Suppression impossible ({type(erreur).__name__}) : {p}")
            else:
                r = Resultat(True, f"{p} supprime.")
        self._noter("supprimer", str(p), r)
        return r

    def creer_dossier(self, chemin: str) -> Resultat:
        """Cree un dossier, avec ses parents manquants. Idempotent."""
        p = self._chemin(chemin)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Creation de dossier impossible ({type(erreur).__name__}) : {p}")
        else:
            r = Resultat(True, f"{p} cree (ou deja present).")
        self._noter("creer_dossier", str(p), r)
        return r

    def supprimer_dossier_vide(self, chemin: str) -> Resultat:
        """Retire un dossier — SEULEMENT s'il est deja vide.

        Deliberement etroit, a la difference de `supprimer()` (qui refuse
        tout dossier) : c'est l'inverse exact de `creer_dossier()`, utile a
        `core/production/organisation/application.py` pour annuler une
        creation de dossier sans jamais risquer d'emporter un contenu que
        le plan n'a pas cree lui-meme. Un dossier non-vide reste refuse.
        """
        p = self._chemin(chemin)
        try:
            p.rmdir()  # leve OSError si non vide ou absent -- jamais recursif
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Suppression de dossier impossible ({type(erreur).__name__}) : {p}")
        else:
            r = Resultat(True, f"{p} supprime (etait vide).")
        self._noter("supprimer_dossier_vide", str(p), r)
        return r

    def metadonnees(self, chemin: str, hachage: bool = False) -> Resultat:
        """Taille, dates, type — et un SHA-256 si `hachage` (couteux sur un
        gros fichier, jamais calcule par defaut).

        Rendues dans `sortie` comme un texte lisible (meme convention que
        `lister`) ET dans `Resultat` via un dictionnaire accessible par
        l'appelant Python — `to_dict()` les transporte telles quelles.
        """
        p = self._chemin(chemin)
        try:
            stat = p.stat()
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Metadonnees illisibles ({type(erreur).__name__}) : {p}")
            self._noter("metadonnees", str(p), r)
            return r

        from datetime import datetime, timezone
        donnees: Dict[str, Any] = {
            "taille_octets": stat.st_size,
            "modifie_le": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "type": "dossier" if p.is_dir() else "fichier",
            "extension": p.suffix.lstrip(".").lower() if p.is_file() else "",
        }
        if hachage and p.is_file():
            import hashlib
            sha = hashlib.sha256()
            with open(p, "rb") as f:
                for bloc in iter(lambda: f.read(1 << 20), b""):
                    sha.update(bloc)
            donnees["sha256"] = sha.hexdigest()

        r = Resultat(True, f"{p} : {donnees['taille_octets']} octets, "
                           f"modifie le {donnees['modifie_le']}.",
                     sortie="\n".join(f"{cle}: {valeur}" for cle, valeur in donnees.items()),
                     donnees=donnees)
        self._noter("metadonnees", str(p), r)
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

        **Le groupe de processus entier est arrete au timeout, pas seulement
        celui-ci.** `subprocess.run(..., timeout=...)` ne tue que le processus
        de tete : un `pytest`/`npm`/script qui a lance ses propres enfants les
        laisse orphelins et actifs alors que `executer` a deja rapporte
        « arretee ». Concept verifie dans le code source de mini-SWE-agent
        (`environments/local.py::_run`, qui documente exactement ce defaut et
        tue le groupe entier) — repris ici avec le style deja en place
        (Popen + `communicate`, jamais `shell=True`).
        """
        if not commande:
            return Resultat(False, "Aucune commande donnee.")
        ou = self._chemin(dossier) if dossier else self.racine
        try:
            processus = subprocess.Popen(  # noqa: S603 — c'est le but du module
                commande, cwd=str(ou), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=(os.name == "posix"))
        except FileNotFoundError:
            r = Resultat(False, f"Commande introuvable : {commande[0]}")
        except Exception as erreur:  # noqa: BLE001
            r = Resultat(False, f"Commande impossible ({type(erreur).__name__}).")
        else:
            try:
                sortie, erreur_std = processus.communicate(timeout=delai)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(processus.pid, signal.SIGKILL)
                else:
                    processus.kill()
                sortie, erreur_std = processus.communicate()
                r = Resultat(False, f"Commande arretee apres {delai:.0f}s : {' '.join(commande)}",
                             sortie=_couper(sortie), erreur=_couper(erreur_std))
            else:
                r = Resultat(
                    ok=processus.returncode == 0,
                    message=(f"{' '.join(commande)} -> code {processus.returncode}"),
                    sortie=_couper(sortie), erreur=_couper(erreur_std),
                    code=processus.returncode)
        self._noter("executer", " ".join(commande), r)
        return r

    # --- Git -------------------------------------------------------------------------

    def git(self, *arguments: str, dossier: Optional[str] = None) -> Resultat:
        """Une commande git, dans le dépôt demandé.

        Rien n'est interdit ici — `push` compris. DEC-0038 : c'est ce qu'il a
        demandé, et le journal dit ce qui est parti.
        """
        return self.executer(["git", *arguments], dossier=dossier)

    def isoler(self, nom: str, base: str = "HEAD", dossier: Optional[str] = None) -> Resultat:
        """Crée un worktree git isolé pour un travail risqué ou parallèle,
        sans jamais toucher l'arbre de travail principal.

        Mission ARENA x TRANS4MERS §18/§52. Concept vérifié dans le code
        source de Trans4mers (MIT, `abhayzangir1/trans4mer`, commit `d0940a9`,
        `core/trans4mers-engine/src/git_workspace.rs::ensure_git_workspace` —
        `.gitignore` protégeant les worktrees isolés de tout commit
        accidentel). Rien copié : `git worktree` est ici invoqué en shell nu
        via `self.git()`, comme le reste de ce module — c'est du `git`
        ordinaire, pas une bibliothèque `git2` embarquée.

        **Une capacité de plus, pas une restriction.** DEC-0038 reste entier :
        Dioumtoukay peut toujours modifier l'arbre principal directement s'il
        le choisit. `isoler()` lui donne juste un endroit où travailler SANS
        y toucher, quand la tâche s'y prête (branche à soi, tâches
        parallèles) — jamais un chemin obligatoire.

        Returns:
            En cas de succès, `donnees["chemin"]` porte le chemin absolu du
            nouveau worktree — c'est ce chemin qu'il faut passer en `DOSSIER:`
            aux actions suivantes pour travailler réellement dedans.
        """
        if not nom or any(c in nom for c in ("/", "\\", "..")):
            return Resultat(False, "NOM de worktree invalide : un seul segment, "
                                   "sans '/' ni '..'.")
        ou = self._chemin(dossier) if dossier else self.racine
        self._proteger_worktrees_du_commit(ou)
        chemin_worktree = ou / ".worktrees" / nom
        resultat = self.git("worktree", "add", "-b", nom, str(chemin_worktree), base,
                            dossier=dossier)
        if resultat.ok:
            resultat.donnees["chemin"] = str(chemin_worktree)
            resultat.message = f"Worktree isole cree : {chemin_worktree} (branche {nom})."
            resultat.sortie = str(chemin_worktree)
        return resultat

    def nettoyer_worktree(self, nom: str, dossier: Optional[str] = None) -> Resultat:
        """Retire un worktree isolé créé par `isoler()`.

        **N'écrase jamais un travail non commité par défaut** — mission §19,
        « never destroy user work » : `git worktree remove` refuse tout seul
        s'il reste des modifications non commitées dans le worktree, et cet
        échec est rapporté tel quel, jamais contourné par un `--force`
        ajouté ici. Un appelant qui veut vraiment forcer le fait lui-même via
        `atelier.git("worktree", "remove", chemin, "--force")` — un geste
        explicite, jamais un défaut silencieux.
        """
        if not nom or any(c in nom for c in ("/", "\\", "..")):
            return Resultat(False, "NOM de worktree invalide : un seul segment, "
                                   "sans '/' ni '..'.")
        ou = self._chemin(dossier) if dossier else self.racine
        chemin_worktree = ou / ".worktrees" / nom
        return self.git("worktree", "remove", str(chemin_worktree), dossier=dossier)

    @staticmethod
    def _proteger_worktrees_du_commit(racine: Path) -> None:
        """S'assure que `.worktrees/` est ignoré par git dans ce dépôt.

        Sans ça, un `git add -A` ultérieur dans l'arbre principal pourrait
        aspirer le contenu entier d'un worktree isolé — le contraire exact
        de l'isolation recherchée. Idée vérifiée dans Trans4mers
        (`git_workspace.rs::ensure_gitignore`) ; n'ajoute la ligne que si le
        fichier existe déjà et ne la porte pas encore — ne crée jamais de
        `.gitignore` dans un dépôt qui n'en a pas choisi d'avoir un.
        """
        gitignore = racine / ".gitignore"
        ligne = ".worktrees/"
        try:
            if not gitignore.is_file():
                return
            contenu = gitignore.read_text(encoding="utf-8")
            if ligne not in contenu.splitlines():
                with verrous.pour(gitignore):
                    contenu = gitignore.read_text(encoding="utf-8")
                    if ligne not in contenu.splitlines():
                        separateur = "" if contenu.endswith("\n") or not contenu else "\n"
                        gitignore.write_text(
                            contenu + separateur + f"{ligne}\n", encoding="utf-8")
        except OSError as erreur:  # noqa: BLE001 — une protection qui echoue ne bloque pas isoler()
            logger.warning(".gitignore non mis a jour pour .worktrees/ (%s).", erreur)
