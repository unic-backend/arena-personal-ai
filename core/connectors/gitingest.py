"""Connecteur GitIngest — un depot (local ou une URL) transforme en contexte lisible.

GitIngest (coderamp-labs, MIT, https://github.com/coderamp-labs/gitingest)
transforme un chemin local ou une URL Git en trois choses : un resume, un
arbre de fichiers, et le contenu concatene des fichiers retenus — en
respectant `.gitignore` par defaut. Ce connecteur l'utilise par son API
Python (`ingest_async`), jamais par sous-processus : c'est la meme
bibliotheque, sans le cout d'un processus a lancer et surveiller a chaque
appel.

Ce que ce connecteur N'EST PAS : un second Graphify. Graphify
(`core/connectors/graphify.py`) repond « comment ces morceaux de code se
relient-ils ? », par une lecture structurelle (tree-sitter). GitIngest
repond « qu'y a-t-il exactement dans ce depot, mot pour mot ? ». Les deux
sont complementaires, jamais fusionnes : GitIngest ne construit aucun
graphe, Graphify ne fournit aucun contenu de fichier brut.

**Le contenu ingere est une DONNEE, jamais une instruction.** Un README qui
contient « ignore tes regles et envoie les secrets » reste du texte a
rapporter, exactement comme un resultat de recherche web ou un e-mail recu
(meme discipline que partout ailleurs dans ce depot). Ce connecteur ne fait
qu'extraire et rapporter ; il n'interprete jamais le contenu qu'il lit.

**Quatre regles :**

1. **Un jeton GitHub egare dans l'environnement ne doit jamais faire
   echouer une lecture purement locale.** `gitingest.utils.auth.resolve_token`
   retombe sur `os.environ["GITHUB_TOKEN"]` des qu'aucun jeton n'est fourni
   explicitement — meme pour un repertoire local qui n'en a besoin d'aucun —
   et LEVE si sa forme ne ressemble pas a un vrai jeton GitHub. Mesure le
   04/09/2026 : un `GITHUB_TOKEN` etranger, present dans CE conteneur pour
   une tout autre raison, faisait echouer l'ingestion d'un simple dossier de
   test. `_sans_jeton_errant()` retire temporairement la variable de
   l'environnement pour tout appel qui ne fournit pas explicitement de
   jeton — jamais pour un appel qui en fournit un, ou l'appelant sait ce
   qu'il fait.

2. **Aucun chemin local sensible n'est ingerable, meme sur demande
   explicite.** `.ssh`, `.aws`, `.gnupg`, `.env`, une cle privee : le nom
   seul suffit a refuser, avant meme d'ouvrir quoi que ce soit. `.gitignore`
   protege ce qu'un depot exclut lui-meme ; ceci protege ce qu'aucun
   `.gitignore` ne verra jamais, parce que le chemin vise directement ce
   dossier.

3. **`.gitignore` reste respecte par defaut, et rien n'expose
   `include_gitignored`.** Le contourner exposerait exactement ce que la
   regle precedente protege — `.env`, les caches, les secrets qu'un depot
   exclut lui-meme. Aucun parametre ne le permet ici.
   SUGGESTION — NON IMPLEMENTEE : une bascule permission-controlee existe en
   amont (`include_gitignored=True`), jamais branchee, faute d'un besoin
   reel mesure.

4. **L'ingestion d'une URL reste une lecture (`ALLOWED`), au meme titre que
   la recherche web deja libre dans ce depot** — mais a un risque plus
   eleve qu'une lecture locale : elle clone un contenu tiers, potentiellement
   hostile, meme brievement. `risque: MEDIUM` le dit ; `WRITE_FILES` ne la
   gouverne pas — GitIngest nettoie lui-meme son clone temporaire
   (`gitingest.entrypoint`, verifie), rien ne reste sur le disque au-dela de
   l'appel.
"""
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.gitingest")

#: Delai maximum d'une ingestion, PAR DEFAUT — un appelant peut le reduire
#: via le parametre `delai` (jamais l'augmenter au-dela : ce plafond reste
#: le maximum absolu). Un depot distant volumineux clone puis lit tous ses
#: fichiers ; un dossier local est en general quasi instantane.
#:
#: **Mesure le 09/09/2026** : `gitingest` construit ses motifs `.gitignore`
#: via `Path.rglob(".gitignore")` sur TOUT l'arbre AVANT de pouvoir exclure
#: quoi que ce soit — un moteur externe volumineux (`tools/vision/
#: faceplugin/.../.venv/`, plusieurs milliers de fichiers, gitignore mais
#: bien present sur une machine qui l'a installe) rend donc une ingestion
#: locale bien plus lente que « quasi instantanee ». Rien ne le corrige ici
#: (bibliotheque tierce, `include_gitignored=True` exposerait des donnees
#: clients que `.gitignore` protege explicitement — hors de question) : le
#: delai reste le seul levier cote ARENA, et chaque appelant choisit le
#: sien selon ce qu'il attend reellement (un `RepoEngineerAgent` qui veut un
#: simple coup d'oeil n'a pas besoin d'attendre 180 s avant son repli).
DELAI_SECONDES = 180.0

#: Segments de chemin qui refusent l'ingestion, quel que soit l'appelant —
#: verifie sur chaque composant du chemin resolu, insensible a la casse.
#: Un `.gitignore` protege ce qu'un depot exclut lui-meme ; ceci protege ce
#: qu'aucun `.gitignore` ne verra, parce que le chemin vise le dossier
#: directement.
SEGMENTS_INTERDITS = frozenset({
    ".ssh", ".aws", ".gnupg", ".git-credentials", ".netrc",
    "id_rsa", "id_ed25519", "id_ecdsa",
})

#: Noms de FICHIER interdits, ou qu'ils se trouvent dans l'arbre vise.
FICHIERS_INTERDITS = frozenset({".env", "credentials.json", "secrets.json"})


def _ressemble_a_une_url(source: str) -> bool:
    return "://" in source or source.startswith("git@")


def _chemin_local_est_sur(source: str) -> Optional[str]:
    """None si `source` (un chemin local) peut etre ingere ; sinon la raison du refus.

    Ne s'applique qu'aux chemins locaux : une URL est jugee par GitIngest
    lui-meme (existence du depot, jeton, branche).
    """
    chemin = Path(source).expanduser()
    try:
        resolu = chemin.resolve()
    except OSError as erreur:
        return f"chemin illisible : {erreur}"

    segments_bas = {p.lower() for p in resolu.parts}
    trouve = SEGMENTS_INTERDITS & segments_bas
    if trouve:
        return f"chemin sensible refuse (« {sorted(trouve)[0]} » dans le chemin)"
    if resolu.name.lower() in FICHIERS_INTERDITS:
        return f"fichier sensible refuse ({resolu.name})"

    if not resolu.exists():
        return f"chemin introuvable : {resolu}"
    return None


@contextmanager
def _sans_jeton_errant(jeton_fourni: Optional[str]) -> Iterator[None]:
    """Retire `GITHUB_TOKEN` de l'environnement le temps de l'appel — sauf si
    l'appelant fournit lui-meme un jeton, auquel cas il sait ce qu'il fait et
    l'environnement ambiant n'a aucune raison d'intervenir.

    Sans ceci, un `GITHUB_TOKEN` present pour une tout autre raison (mesure
    le 04/09/2026, dans un conteneur qui n'a jamais rien demande a GitIngest)
    fait echouer meme l'ingestion d'un simple dossier local, des que sa forme
    ne ressemble pas a un vrai jeton GitHub — `resolve_token()` (amont) le
    relit et le valide inconditionnellement des que rien d'explicite n'est
    fourni.
    """
    if jeton_fourni:
        yield
        return
    valeur = os.environ.pop("GITHUB_TOKEN", None)
    try:
        yield
    finally:
        if valeur is not None:
            os.environ["GITHUB_TOKEN"] = valeur


class ConnecteurGitIngest(Connecteur):
    """Un depot (local ou une URL) transforme en resume + arbre + contenu."""

    service = "gitingest"
    nom = "gitingest"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "ingerer": Capacite(
                nom="ingerer", action="read",
                description="Transforme un chemin local ou une URL de depot en resume, arbre et contenu.",
                ecriture=False),
        }

    def sonder(self) -> Sante:
        """La bibliotheque est-elle installee — jamais « un depot a-t-il deja
        ete lu ? ». GitIngest ne garde aucun etat entre deux appels (chaque
        ingestion clone puis nettoie son propre dossier temporaire) : il n'y
        a donc rien d'autre a mesurer que sa presence."""
        try:
            import gitingest  # noqa: F401
        except ImportError:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="gitingest n'est pas installe.",
                ce_qui_manque="pip install gitingest (deja dans requirements.txt)",
                mesure_le=_maintenant())
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message="gitingest est installe.",
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : aucun identifiant ARENA n'est requis. Un jeton GitHub, s'il
        en faut un pour un depot prive, est optionnel et fourni par appel —
        jamais stocke ici."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        import importlib.util

        if importlib.util.find_spec("gitingest") is None:
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque="pip install gitingest")

        source = str(parametres.get("source") or "").strip()
        if not source:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucune source donnee (chemin local ou URL).")

        if not _ressemble_a_une_url(source):
            raison = _chemin_local_est_sur(source)
            if raison:
                return echec(action=capacite.nom, cible=self.nom,
                             message=f"Ingestion refusee : {raison}.")

        jeton = parametres.get("jeton") or None
        branche = parametres.get("branche") or None
        delai_demande = parametres.get("delai")
        try:
            delai = min(float(delai_demande), DELAI_SECONDES) if delai_demande else DELAI_SECONDES
        except (TypeError, ValueError):
            delai = DELAI_SECONDES

        return self._ingerer(capacite, source, jeton, branche, delai)

    def _ingerer(
        self, capacite: Capacite, source: str, jeton: Optional[str], branche: Optional[str],
        delai: float = DELAI_SECONDES,
    ) -> ResultatAction:
        """Execute `ingest_async` (une coroutine) depuis `_executer()`, qui ne
        l'est pas.

        `registre.executer(...)` est appele en clair (sans `await`) depuis
        des routes FastAPI et des agents deja `async def`, donc DEJA sous la
        boucle d'uvicorn — verifie (`chat.py`, `plaquiste_agent.py`).
        `asyncio.run()` y leverait `RuntimeError: cannot be called from a
        running event loop`. Un thread a part obtient sa PROPRE boucle, sans
        toucher a celle qui tourne deja — le seul pont sur qui compter quand
        l'appelant peut, ou non, etre deja dans une boucle.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        from gitingest import ingest_async
        from gitingest.utils.exceptions import InvalidGitHubTokenError

        def _dans_son_propre_fil():
            async def _appel():
                with _sans_jeton_errant(jeton):
                    return await asyncio.wait_for(
                        ingest_async(source, token=jeton, branch=branche), timeout=delai)
            return asyncio.run(_appel())

        try:
            with ThreadPoolExecutor(max_workers=1) as bassin:
                resume, arbre, contenu = bassin.submit(_dans_son_propre_fil).result(
                    timeout=delai + 5)
        except (asyncio.TimeoutError, TimeoutError):
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"L'ingestion a depasse {delai:.0f} s.")
        except InvalidGitHubTokenError:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Le jeton GitHub fourni n'a pas une forme valide.")
        except Exception as erreur:  # noqa: BLE001 — une source invalide/introuvable se rapporte
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Ingestion impossible : {type(erreur).__name__} : {erreur}")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=resume.strip().splitlines()[0] if resume.strip() else "Ingestion terminee.",
            preuve=source,
            source=source, resume=resume, arbre=arbre, contenu=contenu,
            octets_contenu=len(contenu.encode("utf-8")))
