"""Parler a un serveur MCP qui ne parle QUE sur son entree/sortie standard.

`core/mcp/transport.py` sait joindre WanGP : un serveur HTTP, avec un port et
une session qui voyage dans un en-tete. OpenTakeoff (chapitre metre) est
different par construction — lu dans son propre code (`mcp/server.ts`,
`mcp/Dockerfile`) : `StdioServerTransport` uniquement, aucun mode HTTP. Le
proprietaire du depot le dit explicitement dans sa documentation : « Never
point a client config at `npm start` — npm's banner goes to stdout, which is
the MCP wire. » Le protocole EST le flux du processus.

Deux chemins existaient : etendre `ClientMcp` pour parler les deux transports
a la fois, au risque de rendre un module simple illisible, ou ecrire le second
transport a cote, sur le meme contrat de reponse. Le second a ete choisi —
`Reponse` (de `core.mcp.transport`) n'est pas duplique, il est reutilise :
c'est le meme protocole JSON-RPC, seul le tuyau change.

**Trois regles, qui sont les memes que le transport HTTP pour la meme raison :**

1. **Une panne est un etat, jamais une exception qui remonte.** `node`
   absent, le dossier du serveur absent, un processus qui se termine tout
   seul : tout devient un `Reponse` avec sa raison.

2. **La session est un processus, pas un identifiant.** Sans port ni jeton de
   session a transporter, le processus lui-meme EST la session : tant qu'il
   vit, `load_plan` puis `set_scale` puis `detect_rooms` partagent le meme
   etat. Il nait a `ouvrir()`, il meurt a `fermer()`. Un appelant qui garde le
   client au-dela de son usage garde un processus Node vivant pour rien.

3. **Une notification n'est pas une reponse.** Le serveur ecrit des messages
   sans `id` entre deux reponses (ex. `notifications/resources/list_changed`
   apres `load_plan`). Chaque appel lit jusqu'a trouver SON `id`, jamais la
   premiere ligne venue — une mesure faite sur ce serveur reel l'a confirme :
   la premiere ligne apres `load_plan` etait cette notification, pas son
   resultat.

4. **La lecture ne passe pas par `select()`.** La premiere version attendait
   sur `selectors.DefaultSelector().select()`, applique au descripteur du
   pipe `stdout` du sous-processus. Cela marche sous Linux et **echoue sous
   Windows** : `select()` n'y accepte que des sockets, jamais un pipe, d'ou
   `OSError: [WinError 10038]` a chaque appel — mesure faite le 2026-08-29
   sur la machine du proprietaire, ou OpenTakeoff etait inutilisable alors
   qu'il tournait de bout en bout sur Linux. La lecture se fait desormais
   dans un **thread bloquant** qui pousse les octets dans une `queue.Queue`,
   et l'attente est un `queue.get(timeout=...)` : le meme code sur les deux
   systemes, sans rien qui dependent du type de descripteur.
"""
import json
import logging
import os
import queue
import subprocess
import threading
import time
import uuid
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

from core.mcp.transport import VERSION_PROTOCOLE, Reponse

logger = logging.getLogger("usman.mcp.stdio")

#: Delai total accorde a un appel (poignee de main comprise si necessaire).
#: Plus genereux que le transport HTTP : ouvrir un plan PDF fait tourner un
#: moteur de geometrie, pas repondre a une requete web.
DELAI_SECONDES = 60.0

#: Delai laisse au processus pour se terminer proprement avant d'etre tue.
DELAI_ARRET_SECONDES = 5.0


class ClientMcpStdio:
    """Un client MCP minimal, en stdio : lance un processus, lui parle, l'arrete.

    S'utilise comme gestionnaire de contexte pour que le processus ne survive
    jamais a son appelant :

        with ClientMcpStdio(["node", "dist/server.js"], dossier="...") as client:
            client.appeler("load_plan", {"path": "..."})
    """

    def __init__(self, commande: List[str], dossier: str,
                 delai: float = DELAI_SECONDES,
                 environnement: Optional[Dict[str, str]] = None) -> None:
        self.commande = commande
        self.dossier = dossier
        self.delai = delai
        #: Additif, jamais requis : OpenTakeoff hérite l'environnement du
        #: parent tel quel (`environnement=None`) et n'est pas affecté. Un
        #: futur serveur qui doit voir un environnement DIFFERENT du parent
        #: (ex. un fournisseur d'embeddings force, jamais celui hérité) le
        #: fournit ici — jamais en modifiant `os.environ` du processus ARENA
        #: lui-même, ce qui affecterait tout le reste en même temps.
        self._environnement = environnement
        self._processus: Optional[subprocess.Popen] = None
        self._echec_ouverture: str = ""
        #: Octets lus par le thread lecteur, pas encore coupes en lignes.
        #: `os.read` sur le descripteur plutot que `TextIOWrapper.readline()` :
        #: un `readline()` bufferise avale plusieurs lignes d'un coup dans SON
        #: tampon a lui, invisible a l'appelant — mesure sur ce module, avec
        #: deux lignes ecrites par le faux serveur dans le meme appel systeme.
        self._tampon: bytes = b""
        #: Les morceaux lus, dans l'ordre. `None` marque la fin du flux.
        self._file: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._lecteur: Optional[threading.Thread] = None

    def __enter__(self) -> "ClientMcpStdio":
        poignee = self.ouvrir()
        if not poignee.ok:
            self._echec_ouverture = poignee.raison
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc: Optional[BaseException], tb: Optional[TracebackType]) -> None:
        self.fermer()

    # --- Cycle de vie du processus ----------------------------------------------

    def ouvrir(self) -> Reponse:
        """Lance le processus et fait la poignee de main. Rejouee : sans effet."""
        if self._processus is not None:
            return Reponse(ok=True)
        try:
            self._processus = subprocess.Popen(
                self.commande, cwd=self.dossier,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # le serveur y ecrit des avertissements sans consequence
                # Octets bruts (pas `text=True`) : la lecture passe par
                # `os.read()` sur le descripteur, jamais par le tampon interne
                # d'un `TextIOWrapper` — voir la note sur `self._tampon`.
                env=self._environnement,  # None : herite l'environnement du parent, comme avant
            )
        except (OSError, FileNotFoundError) as erreur:
            self._processus = None
            logger.info("Lancement impossible (%s dans %s) : %s",
                        self.commande, self.dossier, erreur)
            # Le systeme ne dit pas toujours CE QUI manque : Linux nomme le
            # fichier absent, Windows repond « [WinError 2] Le fichier
            # specifie est introuvable » sans le nommer. La raison porte donc
            # elle-meme la commande et le dossier — sinon le proprietaire lit
            # une panne sans savoir de quoi elle parle.
            programme = self.commande[0] if self.commande else "(commande vide)"
            return Reponse(ok=False, raison=(
                f"{type(erreur).__name__}: {erreur} "
                f"(programme {programme}, dossier {self.dossier})"))

        # Une session neuve part d'un flux neuf : ni tampon ni morceau de la
        # precedente. Le thread est `daemon` pour qu'un appelant qui oublie
        # `fermer()` n'empeche pas Python de s'arreter.
        self._tampon = b""
        self._file = queue.Queue()
        self._lecteur = threading.Thread(
            target=self._lire_sans_fin,
            args=(self._processus.stdout.fileno(), self._file),
            name="mcp-stdio-lecteur", daemon=True)
        self._lecteur.start()

        poignee = self._poster({
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "initialize",
            "params": {
                "protocolVersion": VERSION_PROTOCOLE,
                "capabilities": {},
                "clientInfo": {"name": "ARENA", "version": "1"},
            },
        })
        if not poignee.ok:
            self.fermer()
            return poignee
        self._notifier({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return poignee

    def fermer(self) -> None:
        """Arrete le processus. N'echoue jamais — un processus deja mort n'est pas une erreur."""
        processus, self._processus = self._processus, None
        if processus is None:
            return
        try:
            if processus.stdin:
                processus.stdin.close()
            processus.terminate()
            processus.wait(timeout=DELAI_ARRET_SECONDES)
        except Exception:  # noqa: BLE001 - au pire, on tue
            try:
                processus.kill()
                processus.wait(timeout=DELAI_ARRET_SECONDES)
            except Exception:  # noqa: BLE001 - le processus ne repond plus, rien de plus a faire
                pass
        # Le pipe se ferme avec le processus : `os.read` rend b"" et le thread
        # sort tout seul. On l'attend brievement, sans jamais bloquer dessus.
        lecteur, self._lecteur = self._lecteur, None
        if lecteur is not None:
            lecteur.join(timeout=DELAI_ARRET_SECONDES)

    # --- Protocole ----------------------------------------------------------------

    def outils(self) -> Reponse:
        """La liste des outils annonces par le serveur."""
        return self._poster({"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/list"})

    def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
        """Appelle un outil. Le processus doit deja etre ouvert (voir `ouvrir`)."""
        if self._processus is None:
            return Reponse(ok=False, raison=self._echec_ouverture or "session non ouverte")
        return self._poster({
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call",
            "params": {"name": nom, "arguments": arguments or {}},
        })

    # --- Bas niveau -----------------------------------------------------------------

    def _notifier(self, corps: Dict[str, Any]) -> None:
        """Envoie un message sans reponse attendue (pas d'`id`)."""
        if self._processus is None or self._processus.stdin is None:
            return
        try:
            self._processus.stdin.write((json.dumps(corps) + "\n").encode("utf-8"))
            self._processus.stdin.flush()
        except Exception as erreur:  # noqa: BLE001 - une panne est un etat
            logger.info("Notification MCP impossible : %s", erreur)

    @staticmethod
    def _lire_sans_fin(fd: int, file: "queue.Queue[Optional[bytes]]") -> None:
        """Lit le flux jusqu'a sa fin et pousse chaque morceau dans la file.

        Tourne dans son propre thread : c'est ce qui remplace le `select()`
        d'origine, impossible sur un pipe sous Windows (regle 4 du module).
        Une lecture vide, un descripteur ferme ou une erreur systeme donnent
        tous la meme chose — `None`, la fin du flux. Ce thread ne leve rien :
        personne n'est la pour le rattraper.
        """
        try:
            while True:
                morceau = os.read(fd, 65536)
                if not morceau:
                    break
                file.put(morceau)
        except (OSError, ValueError):  # descripteur ferme sous nos pieds
            pass
        finally:
            file.put(None)

    def _ligne_suivante(self, limite: float) -> Optional[bytes]:
        """Une ligne (sans le `\\n`), prise sur la file du thread lecteur.

        Rend `None` si le delai est depasse, le processus est mort, ou le
        flux s'est ferme sans plus rien envoyer.
        """
        processus = self._processus
        while b"\n" not in self._tampon:
            restant = limite - time.monotonic()
            if restant <= 0:
                return None
            try:
                morceau = self._file.get(timeout=restant)
            except queue.Empty:
                # Rien n'est arrive dans le temps restant. Si le processus est
                # mort entre-temps, inutile d'attendre le delai complet.
                if processus.poll() is not None:
                    return None
                continue
            if morceau is None:
                return None  # flux ferme
            self._tampon += morceau
        ligne, _, self._tampon = self._tampon.partition(b"\n")
        return ligne

    def _poster(self, corps: Dict[str, Any]) -> Reponse:
        """Envoie un message JSON-RPC et lit jusqu'a la reponse portant son `id`."""
        processus = self._processus
        if processus is None or processus.stdin is None or processus.stdout is None:
            return Reponse(ok=False, raison=self._echec_ouverture or "processus indisponible")
        try:
            processus.stdin.write((json.dumps(corps) + "\n").encode("utf-8"))
            processus.stdin.flush()
        except Exception as erreur:  # noqa: BLE001 - une panne est un etat
            logger.info("Appel MCP impossible (stdin) : %s", erreur)
            return Reponse(ok=False, raison=f"{type(erreur).__name__}: {erreur}")

        limite = time.monotonic() + self.delai
        while True:
            ligne = self._ligne_suivante(limite)
            if ligne is None:
                if processus.poll() is not None:
                    return Reponse(ok=False, raison=f"processus termine (code {processus.returncode})")
                return Reponse(ok=False, raison=f"delai depasse ({self.delai:g}s)")
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                charge = json.loads(ligne)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue  # une ligne qui n'est pas du JSON-RPC n'est pas notre reponse
            if charge.get("id") != corps.get("id"):
                continue  # une notification, ou la reponse d'un autre appel
            if "error" in charge:
                erreur = charge["error"] or {}
                return Reponse(ok=False, raison=str(erreur.get("message") or erreur))
            return Reponse(ok=True, resultat=charge.get("result") or {})
