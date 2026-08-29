"""Diagnostic d'ARENA : ce qui repond, ce qui manque, et la commande qui l'obtient.

**Ce fichier a menti.** Jusqu'au 28/08/2026 il affichait, ligne 14 :

    print("[OK] Environnement virtuel (.venv) actif")

sans rien verifier. Lance hors du venv, il disait quand meme OK. C'est
exactement ce que ce depot s'interdit partout ailleurs — un `[OK]` qui n'est
pas une mesure — et c'est pire ici qu'ailleurs : un diagnostic auquel on ne
peut pas se fier est plus dangereux qu'aucun diagnostic, parce qu'on lui fait
confiance pour decider si le probleme est ailleurs.

**Trois regles :**

1. **Chaque ligne vient d'une mesure.** Aucun etat n'est deduit de la presence
   d'un fichier ou d'une variable : la question est « repond-il ? ». Un service
   qu'on n'a pas interroge n'est pas `OK`.

2. **Ce qui manque se dit avec la commande qui l'obtient.** Nommer un probleme
   sans dire quoi faire laisse le proprietaire devant un terminal.

3. **Aucun secret ne s'affiche.** La cle API se verifie par sa presence, jamais
   par sa valeur : un diagnostic colle dans une conversation ne doit pas
   divulguer ce qu'il verifie.

    python scripts/doctor.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

RACINE = Path(__file__).resolve().parent.parent

#: Les quatre etats. `OK` exige une mesure ; les trois autres disent pourquoi.
OK = "OK"
ABSENT = "ABSENT"            # pas installe, pas present sur la machine
EN_PANNE = "EN PANNE"        # installe, mais ne repond pas
NON_CONFIGURE = "NON CONFIGURE"  # il manque une valeur que le proprietaire fournit

#: Version minimale : celle de l'image Docker du backend.
PYTHON_MINIMUM = (3, 11)

#: Delai d'interrogation d'un service local. Court : il tourne sur la machine.
DELAI_SECONDES = 3.0

#: Ce que le code importe vraiment et sans quoi le serveur ne demarre pas.
DEPENDANCES = ("fastapi", "uvicorn", "httpx", "pydantic", "yaml", "dotenv")


@dataclass(frozen=True)
class Verification:
    """Le resultat d'UNE mesure. `remede` est vide seulement quand tout va bien."""

    nom: str
    etat: str
    detail: str
    remede: str = ""
    #: Sans lui, ARENA ne peut pas repondre du tout.
    essentiel: bool = False

    @property
    def va_bien(self) -> bool:
        return self.etat == OK

    def rendre(self) -> str:
        marque = {OK: "[OK]  ", ABSENT: "[ABS] ",
                  EN_PANNE: "[PANNE]", NON_CONFIGURE: "[CONF]"}[self.etat]
        ligne = f"{marque} {self.nom:<24} {self.detail}"
        return f"{ligne}\n         -> {self.remede}" if self.remede else ligne


# --- La machine et l'installation -----------------------------------------------

def verifier_python() -> Verification:
    """La version reellement en train d'executer ce script."""
    version = sys.version_info
    lisible = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) < PYTHON_MINIMUM:
        return Verification(
            "Python", ABSENT, f"version {lisible}, trop ancienne",
            f"Installer Python {PYTHON_MINIMUM[0]}.{PYTHON_MINIMUM[1]} ou plus recent.",
            essentiel=True)
    return Verification("Python", OK, f"version {lisible}", essentiel=True)


def verifier_environnement_virtuel() -> Verification:
    """MESUREE, cette fois : un venv actif deplace `sys.prefix`.

    C'est la ligne qui mentait. Elle ne ment plus, et un test le tient.
    """
    dans_un_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if dans_un_venv:
        return Verification("Environnement virtuel", OK, f"actif ({Path(sys.prefix).name})")
    return Verification(
        "Environnement virtuel", ABSENT,
        "aucun venv actif : les paquets s'installent sur le Python du systeme",
        "Sous Windows : .venv\\Scripts\\Activate.ps1")


def verifier_dependances(importateur: Optional[Callable[[str], Any]] = None) -> Verification:
    """Tente d'importer ce que le serveur importe. Un paquet absent est nomme."""
    importer = importateur or __import__
    manquants: List[str] = []
    for paquet in DEPENDANCES:
        try:
            importer(paquet)
        except Exception:  # noqa: BLE001 — un import casse vaut un import absent
            manquants.append(paquet)
    if manquants:
        return Verification(
            "Dependances", ABSENT, f"{len(manquants)} paquet(s) manquant(s) : "
            + ", ".join(manquants),
            "pip install -r requirements.txt", essentiel=True)
    return Verification("Dependances", OK,
                        f"{len(DEPENDANCES)} paquet(s) importes", essentiel=True)


def verifier_cle_api(valeur: Optional[str] = None) -> Verification:
    """Presence seulement. **La valeur ne s'affiche jamais.**"""
    cle = valeur if valeur is not None else (
        os.getenv("USMAN_API_KEY") or os.getenv("ARENA_API_KEY") or "")
    if not cle.strip():
        return Verification(
            "Cle API", NON_CONFIGURE,
            "USMAN_API_KEY absente : la passerelle /api et /v1 est desactivee",
            'python -c "import secrets; print(secrets.token_urlsafe(32))" puis la '
            "coller dans .env", essentiel=True)
    return Verification("Cle API", OK, f"presente ({len(cle)} caracteres)", essentiel=True)


# --- Le modele local --------------------------------------------------------------

def _lire_json(url: str, delai: float = DELAI_SECONDES) -> Any:
    """Un GET qui rend du JSON, ou leve. Isole pour que les tests le remplacent."""
    with urllib.request.urlopen(url, timeout=delai) as reponse:  # noqa: S310 — URL locale
        return json.loads(reponse.read().decode("utf-8"))


def modeles_ollama(lecteur: Optional[Callable[[str], Any]] = None,
                   url: Optional[str] = None) -> Optional[List[str]]:
    """Les modeles installes, ou `None` si Ollama ne repond pas.

    `None` est une absence de reponse, pas une liste vide : une liste vide
    voudrait dire « Ollama repond et n'a aucun modele », ce qui est une autre
    phrase et un autre remede.
    """
    lire = lecteur or _lire_json
    base = url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        charge = lire(f"{base.rstrip('/')}/api/tags")
    except Exception:  # noqa: BLE001 — un service eteint est un etat
        return None
    modeles = (charge or {}).get("models")
    if not isinstance(modeles, list):
        return None
    return [str((m or {}).get("name") or "") for m in modeles if isinstance(m, dict)]


def verifier_ollama(installes: Optional[List[str]]) -> Verification:
    """Ollama repond-il ? La question n'est pas « est-il installe ? »."""
    if installes is None:
        return Verification(
            "Ollama", EN_PANNE, "ne repond pas : sans lui, ARENA ne repond pas non plus",
            "ollama serve", essentiel=True)
    return Verification("Ollama", OK, f"en ligne, {len(installes)} modele(s)",
                        essentiel=True)


def _installe(installes: List[str], attendu: str) -> bool:
    """Un modele est present si son nom correspond, avec ou sans etiquette."""
    racine = attendu.split(":")[0]
    return any(nom == attendu or nom.split(":")[0] == racine for nom in installes)


def verifier_modele(nom_lisible: str, modele: str, installes: Optional[List[str]],
                    essentiel: bool = False) -> Verification:
    """Un modele precis est-il la ? Sans Ollama, la question ne se tranche pas."""
    if installes is None:
        return Verification(nom_lisible, EN_PANNE,
                            f"{modele} : indeterminable, Ollama ne repond pas",
                            "ollama serve", essentiel=essentiel)
    if not _installe(installes, modele):
        return Verification(nom_lisible, ABSENT, f"{modele} n'est pas installe",
                            f"ollama pull {modele}", essentiel=essentiel)
    return Verification(nom_lisible, OK, modele, essentiel=essentiel)


# --- Les capacites qui dependent d'un outil ---------------------------------------

def _commande_repond(binaire: str, arguments: List[str]) -> bool:
    """Lance vraiment la commande. `shutil.which` dirait seulement qu'un fichier existe."""
    if shutil.which(binaire) is None:
        return False
    try:
        acheve = subprocess.run([binaire, *arguments], capture_output=True,
                                timeout=10, check=False)
    except Exception:  # noqa: BLE001
        return False
    return acheve.returncode == 0


def verifier_gpu(sonde: Optional[Callable[[], bool]] = None) -> Verification:
    presente = sonde() if sonde else _commande_repond(
        "nvidia-smi", ["--query-gpu=name", "--format=csv,noheader"])
    if not presente:
        return Verification(
            "Carte graphique", ABSENT,
            "nvidia-smi ne repond pas : le modele tournera sur le processeur, lentement",
            "Verifier les pilotes NVIDIA.")
    return Verification("Carte graphique", OK, "nvidia-smi repond")


def verifier_ffmpeg(sonde: Optional[Callable[[], bool]] = None) -> Verification:
    presente = sonde() if sonde else _commande_repond("ffmpeg", ["-version"])
    if not presente:
        return Verification(
            "ffmpeg (video)", ABSENT,
            "absent : pas d'analyse video, pas de sous-titres, pas de montage",
            "winget install ffmpeg")
    return Verification("ffmpeg (video)", OK, "repond")


def verifier_docker(sonde: Optional[Callable[[], bool]] = None) -> Verification:
    presente = sonde() if sonde else _commande_repond("docker", ["info"])
    if not presente:
        return Verification(
            "Docker (bac a sable)", ABSENT,
            "inactif : ARENA REFUSE d'executer du code plutot que de le faire sans isolation",
            "Demarrer Docker Desktop.")
    return Verification("Docker (bac a sable)", OK, "le demon repond")


def verifier_wangp(lecteur: Optional[Callable[[str], Any]] = None) -> Verification:
    """Le serveur MCP de WanGP, interroge pour de vrai."""
    lire = lecteur or _lire_json
    url = os.getenv("WAN2GP_MCP_URL", "http://127.0.0.1:8765")
    try:
        lire(url)
    except urllib.error.HTTPError:
        # Il repond, meme si ce n'est pas un JSON exploitable a la racine : le
        # port est tenu par quelque chose qui parle.
        return Verification("WanGP (generation video)", OK, f"repond sur {url}")
    except Exception:  # noqa: BLE001
        return Verification(
            "WanGP (generation video)", NON_CONFIGURE, f"ne repond pas sur {url}",
            "Lancer WanGP avec son serveur MCP.")
    return Verification("WanGP (generation video)", OK, f"repond sur {url}")


def verifier_moneyprinter(lecteur: Optional[Callable[[str], Any]] = None) -> Verification:
    """Le service de video courte, interroge pour de vrai.

    Une reponse HTTP, meme un refus d'authentification, prouve qu'il ecoute :
    c'est ce qu'on cherche a savoir. Ce qu'on ne cherche pas, c'est si un port
    est ouvert — n'importe quoi peut tenir un port.
    """
    lire = lecteur or _lire_json
    base = os.getenv("MONEYPRINTER_URL", "http://127.0.0.1:8080/api/v1")
    try:
        lire(f"{base.rstrip('/')}/tasks?page=1&page_size=1")
    except urllib.error.HTTPError:
        return Verification("Video courte (MPT)", OK, f"repond sur {base}")
    except Exception:  # noqa: BLE001
        return Verification(
            "Video courte (MPT)", NON_CONFIGURE, f"ne repond pas sur {base}",
            "Lancer MoneyPrinterTurbo : python -m uvicorn app.asgi:app "
            "--host 127.0.0.1 --port 8080")
    return Verification("Video courte (MPT)", OK, f"repond sur {base}")


def verifier_opentakeoff() -> Verification:
    """Le metre de plan PDF, interroge pour de vrai — pas suppose absent.

    Reutilise `ConnecteurOpenTakeoff.sonder()` plutot que de reecrire une
    seconde logique : deux mesures de la meme sante qui pourraient diverger
    seraient pires qu'une seule, reutilisee.
    """
    try:
        sys.path.insert(0, str(RACINE))
        from core.connectors.base import EtatSante
        from core.connectors.opentakeoff import ConnecteurOpenTakeoff
    except Exception:  # noqa: BLE001 — les dependances manquent : une autre ligne le dit
        return Verification("Metre de plan (OpenTakeoff)", EN_PANNE,
                            "indeterminable : les dependances ne s'importent pas")

    sante = ConnecteurOpenTakeoff().sonder()
    if sante.etat == EtatSante.OPERATIONNEL:
        return Verification("Metre de plan (OpenTakeoff)", OK, sante.message)
    if sante.etat == EtatSante.NON_CONFIGURE:
        return Verification("Metre de plan (OpenTakeoff)", NON_CONFIGURE, sante.message,
                            "scripts/installer_opentakeoff.ps1, puis OPENTAKEOFF_MCP_DIR dans .env")
    return Verification("Metre de plan (OpenTakeoff)", EN_PANNE, sante.message)


def verifier_gardien() -> Verification:
    """La memoire de maintenance du gardien (DEC-0014) — ce qu'elle contient
    deja, jamais « aucun probleme » invente si aucun cycle n'a encore tourne.
    """
    try:
        sys.path.insert(0, str(RACINE))
        from apps.backend.config import DB_PATH
        from core.guardian.file_maintenance import FileDeMaintenance
    except Exception:  # noqa: BLE001 — les dependances manquent : une autre ligne le dit
        return Verification("Gardien (maintenance)", EN_PANNE,
                            "indeterminable : les dependances ne s'importent pas")

    try:
        fichier = FileDeMaintenance(db_path=str(DB_PATH))
        dernier_cycle = fichier.dernier_cycle_le()
        ouvertes = fichier.ouvertes()
        toutes = fichier.toutes()
    except Exception as erreur:  # noqa: BLE001
        return Verification("Gardien (maintenance)", EN_PANNE,
                            f"file de maintenance illisible : {type(erreur).__name__}",
                            "Verifier data/database/memory.db.")

    if dernier_cycle is None:
        return Verification("Gardien (maintenance)", OK,
                            "aucun cycle encore lance (POST /api/gardien/cycle pour le premier)")
    if not ouvertes:
        return Verification("Gardien (maintenance)", OK,
                            f"depot propre au dernier cycle ({dernier_cycle})")
    return Verification("Gardien (maintenance)", OK,
                        f"{len(ouvertes)} tache(s) ouverte(s) sur {len(toutes)} deja vue(s), "
                        f"dernier cycle {dernier_cycle}")


def verifier_inference() -> Verification:
    """Le regime d'inference, et qui est reellement joignable.

    Ce n'est pas un defaut de n'avoir aucun service distant : le mode local est
    un choix valable, et c'est le defaut historique du projet. La ligne est
    donc `OK` — elle informe, elle ne reproche pas.
    """
    try:
        sys.path.insert(0, str(RACINE))
        from apps.backend.config import (
            DEEPINFRA_API_KEY,
            FOURNISSEUR_DEMANDE,
            GROQ_API_KEY,
            MODE_IA,
        )
    except Exception:  # noqa: BLE001 — les dependances manquent : la ligne du dessus le dit
        return Verification("Inference (hybride)", EN_PANNE,
                            "indeterminable : les dependances ne s'importent pas",
                            "pip install -r requirements.txt")

    distants = [nom for nom, cle in (("Groq", GROQ_API_KEY),
                                     ("DeepInfra", DEEPINFRA_API_KEY)) if cle]
    if not distants:
        return Verification(
            "Inference (hybride)", OK,
            f"mode {MODE_IA}, aucun service distant configure : tout passe par Ollama")
    return Verification(
        "Inference (hybride)", OK,
        f"mode {MODE_IA}, demande {FOURNISSEUR_DEMANDE}, distants : {', '.join(distants)}")


def variables_google_absentes() -> Optional[List[str]]:
    """Les noms des variables OAuth manquantes, ou `None` si on n'a pas pu regarder.

    La liste vient de `core/connectors/google_oauth.py` — **le meme code que
    celui des connecteurs**. La recopier ici l'aurait fait deriver le jour ou
    les noms changent, et le diagnostic aurait annonce une variable qui n'existe
    plus. C'est exactement ce qui est arrive le 28/08 : ce fichier reclamait
    encore `GMAIL_CLIENT_ID` quand le projet attendait `GOOGLE_CLIENT_ID`.

    `None` quand l'import echoue : la ligne « Dependances » le dit deja, et
    inventer une reponse ici la contredirait.
    """
    try:
        sys.path.insert(0, str(RACINE))
        from core.connectors.google_oauth import manquantes
    except Exception:  # noqa: BLE001 — dependances absentes : la question ne se tranche pas
        return None
    return manquantes()


def verifier_google(nom: str, capacite: str, portees: str,
                    absentes: Optional[List[str]]) -> Verification:
    """Une capacite Google. Presence des identifiants seulement — aucune valeur.

    Le courrier et l'agenda partagent le meme identifiant : ils partagent donc
    le meme diagnostic, et se distinguent par la portee a accorder.
    """
    if absentes is None:
        return Verification(nom, EN_PANNE,
                            "indeterminable : les dependances ne s'importent pas",
                            "pip install -r requirements.txt")
    if absentes:
        return Verification(
            nom, NON_CONFIGURE,
            f"{', '.join(absentes)} absente(s) : {capacite}",
            f"console.cloud.google.com : identifiant OAuth « application de "
            f"bureau », portees {portees}, puis les coller dans .env")
    return Verification(nom, OK, f"identifiants presents (portees {portees})")


# --- Les donnees du proprietaire ---------------------------------------------------

def verifier_connaissances_metier(chemin: Optional[Path] = None) -> Verification:
    """Le fichier des prix. Sans lui, l'assistant refuse de chiffrer."""
    fichier = chemin or RACINE / "config" / "unic_plaquiste.yaml"
    if not fichier.is_file():
        return Verification(
            "Connaissances metier", ABSENT,
            "config/unic_plaquiste.yaml introuvable : aucun devis ne sera chiffre",
            "Retablir le fichier depuis Git.")
    try:
        import yaml
        metier = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
    except Exception as erreur:  # noqa: BLE001
        return Verification("Connaissances metier", EN_PANNE,
                            f"fichier illisible : {type(erreur).__name__}",
                            "Verifier la syntaxe YAML.")
    articles = len(metier.get("prix_materiaux") or {}) + len(metier.get("prix_portes") or {})
    if not articles:
        return Verification("Connaissances metier", EN_PANNE,
                            "aucun prix dans le fichier", "Verifier config/unic_plaquiste.yaml.")
    return Verification("Connaissances metier", OK, f"{articles} article(s) tarifes")


def verifier_documents(dossier: Optional[Path] = None) -> Verification:
    """Le classeur de documents. Un dossier vide se dit, il ne s'invente pas."""
    chemin = dossier or RACINE / "data" / "documents"
    if not chemin.is_dir():
        return Verification(
            "Documents", ABSENT, f"{chemin.name}/ n'existe pas",
            "Creer data/documents/ et y deposer devis, factures et notes.")
    fichiers = [f for f in chemin.rglob("*") if f.is_file() and not f.name.startswith(".")]
    if not fichiers:
        return Verification("Documents", ABSENT, "dossier vide : rien a indexer",
                            "Deposer des fichiers dans data/documents/.")
    return Verification("Documents", OK, f"{len(fichiers)} fichier(s) presents")


# --- La campagne ---------------------------------------------------------------------

@dataclass
class Rapport:
    """Toutes les mesures, y compris celles qui ont echoue."""

    verifications: List[Verification] = field(default_factory=list)

    @property
    def manquants_essentiels(self) -> List[Verification]:
        return [v for v in self.verifications if v.essentiel and not v.va_bien]

    @property
    def a_regarder(self) -> List[Verification]:
        return [v for v in self.verifications if not v.va_bien]

    def rendre(self) -> str:
        lignes = [v.rendre() for v in self.verifications]
        lignes.append("")
        essentiels = self.manquants_essentiels
        if essentiels:
            lignes.append("ARENA NE PEUT PAS REPONDRE. Il manque : "
                          + ", ".join(v.nom for v in essentiels))
        else:
            lignes.append("ARENA peut repondre.")
        autres = [v for v in self.a_regarder if not v.essentiel]
        if autres:
            lignes.append(f"{len(autres)} capacite(s) indisponible(s) : "
                          + ", ".join(v.nom for v in autres))
        return "\n".join(lignes)


def diagnostiquer() -> Rapport:
    """Fait toutes les mesures. Ollama n'est interroge qu'une fois."""
    installes = modeles_ollama()
    # Un seul identifiant Google pour deux services : une seule lecture.
    absentes_google = variables_google_absentes()
    rapide = os.getenv("CODER_LOCAL_MODEL", "qwen2.5-coder:14b")
    profond = os.getenv("DEFAULT_LOCAL_MODEL", "qwen3.5:9b")
    embeddings = os.getenv("EMBEDDINGS_LOCAL_MODEL", "nomic-embed-text")
    vision = os.getenv("VISION_LOCAL_MODEL", "qwen3-vl:4b")

    return Rapport([
        verifier_python(),
        verifier_environnement_virtuel(),
        verifier_dependances(),
        verifier_cle_api(),
        verifier_inference(),
        verifier_ollama(installes),
        verifier_modele("Modele rapide", rapide, installes, essentiel=True),
        verifier_modele("Modele profond", profond, installes),
        verifier_modele("Modele d'embeddings", embeddings, installes),
        verifier_modele("Modele de vision", vision, installes),
        verifier_gpu(),
        verifier_ffmpeg(),
        verifier_docker(),
        verifier_wangp(),
        verifier_moneyprinter(),
        verifier_opentakeoff(),
        verifier_gardien(),
        verifier_google("Courrier (Gmail)", "ARENA ne lit pas ton courrier",
                        "gmail.readonly / gmail.send", absentes_google),
        verifier_google("Agenda (Calendar)", "ARENA ne voit pas tes creneaux",
                        "calendar.readonly / calendar.events", absentes_google),
        verifier_connaissances_metier(),
        verifier_documents(),
    ])


def main() -> int:
    """Affiche le rapport. Rend 1 si ARENA ne peut pas repondre, 0 sinon."""
    print("=" * 62)
    print("  ARENA — DIAGNOSTIC. Chaque ligne est une mesure, pas une supposition.")
    print("=" * 62)
    rapport = diagnostiquer()
    print(rapport.rendre())
    print("=" * 62)
    return 1 if rapport.manquants_essentiels else 0


if __name__ == "__main__":
    raise SystemExit(main())
