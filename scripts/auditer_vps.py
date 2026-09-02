"""Ce que la machine qui héberge ARENA néglige côté système — mesuré, pas lu.

    python scripts/auditer_vps.py

Port du script bash `vps-audit` (Israel Abebe Kokiso, licence MIT,
https://github.com/nuver-labs/vps-audit) dans les conventions de ce dépôt :
Python plutôt que Bash, commentaires en français, un `Constat` par
vérification (même forme que `auditer_surface_publique.py`) plutôt que des
impressions colorées. Les vérifications elles-mêmes — quoi regarder, quels
seuils — viennent de l'original ; la façon de les mener et de les rapporter
est celle de ce dépôt. Attribution conservée : la licence MIT l'exige.

**Ce script audite la machine, pas ARENA.** `auditer_surface_publique.py`
mesure ce qu'un visiteur d'Internet peut atteindre dans l'application ;
celui-ci mesure la configuration du système d'exploitation qui la fait
tourner — SSH, pare-feu, mots de passe, mises à jour. Sur un poste de
développement (pas de `ufw`, pas de `/etc/ssh/sshd_config` accessible), la
plupart des lignes rendront `WARN` faute d'outil à interroger — c'est une
mesure honnête de cette machine-ci, pas un défaut du script. Sur le VPS de
production, les mêmes lignes deviennent le vrai diagnostic.

**Trois règles, comme le reste du dépôt :**

1. Chaque `Constat` vient d'une commande ou d'un fichier réellement lu — un
   outil absent rend `WARN` avec sa raison, jamais un `PASS` supposé.
2. Ce qui échoue se dit avec la commande ou le fichier qui le corrige.
3. Lecture seule de bout en bout : aucune vérification ici n'écrit sur le
   disque, à l'exception du rapport final que l'appelant choisit de garder.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

#: Les trois verdicts d'une vérification de sécurité — jamais un simple OK/KO,
#: `WARN` existe pour ce qui n'est ni sûr ni dangereux dans l'immédiat.
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# Seuils repris de l'original (vps-audit v0.2.0).
SEUIL_RESSOURCE_WARN = 50   # % d'usage disque/mémoire/CPU
SEUIL_RESSOURCE_FAIL = 80
SEUIL_SERVICES_WARN = 20
SEUIL_SERVICES_FAIL = 40
SEUIL_LOGINS_WARN = 10
SEUIL_LOGINS_FAIL = 50
SEUIL_PORTS_WARN = 10
SEUIL_PORTS_FAIL = 20
LONGUEUR_MDP_MIN = 12


@dataclass
class Constat:
    """Le résultat d'UNE vérification — jamais une supposition."""

    nom: str
    verdict: str
    detail: str

    def rendre(self) -> str:
        marque = {PASS: "[PASS]", WARN: "[WARN]", FAIL: "[FAIL]"}[self.verdict]
        return f"{marque} {self.nom} — {self.detail}"


def _executer(*args: str, delai: float = 5.0) -> Optional[str]:
    """Lance vraiment la commande et renvoie sa sortie, jamais une chaîne vide
    qui se lirait comme une réponse : `None` si l'outil est absent ou échoue."""
    if shutil.which(args[0]) is None:
        return None
    try:
        resultat = subprocess.run(args, capture_output=True, text=True,
                                   timeout=delai, check=False)
    except Exception:  # noqa: BLE001 — une sonde qui plante n'est pas une mesure
        return None
    return resultat.stdout


def _lire(chemin: Path) -> Optional[str]:
    try:
        return chemin.read_text(errors="replace")
    except OSError:
        return None


# --- Configuration SSH -------------------------------------------------------

def _option_ssh(config: str, option: str, defaut: str) -> str:
    for ligne in config.splitlines():
        m = re.match(rf"^\s*{option}\s+(\S+)", ligne, re.IGNORECASE)
        if m:
            return m.group(1)
    return defaut


def verifier_ssh() -> List[Constat]:
    config = _lire(Path("/etc/ssh/sshd_config"))
    if config is None:
        return [Constat("Configuration SSH", WARN,
                         "/etc/ssh/sshd_config illisible depuis cette machine — "
                         "à vérifier directement sur le VPS")]

    constats = []
    root_login = _option_ssh(config, "PermitRootLogin", "prohibit-password")
    constats.append(Constat(
        "SSH — connexion root", PASS if root_login == "no" else FAIL,
        "désactivée" if root_login == "no" else
        f"autorisée ({root_login}) — mettre `PermitRootLogin no` dans sshd_config"))

    mdp = _option_ssh(config, "PasswordAuthentication", "yes")
    constats.append(Constat(
        "SSH — authentification par mot de passe", PASS if mdp == "no" else FAIL,
        "désactivée, clés uniquement" if mdp == "no" else
        "activée — préférer l'authentification par clé seule"))

    port = _option_ssh(config, "Port", "22")
    if port == "22":
        constats.append(Constat("SSH — port", WARN,
                                 "port par défaut (22) — un port non standard réduit les tentatives automatisées"))
    else:
        constats.append(Constat("SSH — port", PASS, f"port non standard ({port})"))
    return constats


# --- Pare-feu -----------------------------------------------------------------

def verifier_pare_feu() -> Constat:
    if shutil.which("ufw"):
        sortie = _executer("ufw", "status") or ""
        actif = "active" in sortie.lower()
        return Constat("Pare-feu (ufw)", PASS if actif else FAIL,
                        "actif" if actif else "installé mais inactif — `ufw enable`")
    if shutil.which("firewall-cmd"):
        sortie = _executer("firewall-cmd", "--state") or ""
        actif = "running" in sortie.lower()
        return Constat("Pare-feu (firewalld)", PASS if actif else FAIL,
                        "actif" if actif else "installé mais inactif")
    if shutil.which("nft"):
        sortie = _executer("nft", "list", "ruleset") or ""
        actif = "table" in sortie
        return Constat("Pare-feu (nftables)", PASS if actif else FAIL,
                        "des règles existent" if actif else "aucune règle trouvée")
    if shutil.which("iptables"):
        sortie = _executer("iptables", "-L", "-n") or ""
        actif = "Chain INPUT" in sortie
        return Constat("Pare-feu (iptables)", PASS if actif else FAIL,
                        "des règles existent" if actif else "aucune règle trouvée")
    return Constat("Pare-feu", WARN, "aucun outil reconnu (ufw/firewalld/nftables/iptables) sur cette machine")


# --- Mises à jour automatiques -------------------------------------------------

def verifier_maj_automatiques() -> Constat:
    sortie = _executer("dpkg", "-l")
    if sortie is None:
        return Constat("Mises à jour automatiques", WARN, "dpkg absent — machine non Debian/Ubuntu ?")
    installe = "unattended-upgrades" in sortie
    return Constat("Mises à jour automatiques", PASS if installe else FAIL,
                    "unattended-upgrades installé" if installe else
                    "non configurées — `apt install unattended-upgrades`")


# --- Fail2ban / CrowdSec -------------------------------------------------------

def _service_actif(nom: str) -> bool:
    sortie = _executer("systemctl", "is-active", nom)
    return bool(sortie) and sortie.strip() == "active"


def verifier_prevention_intrusion() -> Constat:
    dpkg = _executer("dpkg", "-l") or ""
    installe = "fail2ban" in dpkg or "crowdsec" in dpkg
    actif = ("fail2ban" in dpkg and _service_actif("fail2ban")) or \
            ("crowdsec" in dpkg and _service_actif("crowdsec"))
    if not installe:
        return Constat("Prévention d'intrusion", FAIL,
                        "ni fail2ban ni crowdsec installé")
    if not actif:
        return Constat("Prévention d'intrusion", WARN,
                        "installé mais pas démarré")
    return Constat("Prévention d'intrusion", PASS, "fail2ban ou crowdsec actif")


def _option_jail(dossier: Path, section: str, option: str) -> str:
    """Reprend la précédence de fail2ban : jail.conf, jail.d/*.conf, jail.local,
    jail.d/*.local — le dernier fichier lu qui définit l'option gagne."""
    fichiers = [dossier / "jail.conf", *sorted((dossier / "jail.d").glob("*.conf")),
                dossier / "jail.local", *sorted((dossier / "jail.d").glob("*.local"))]
    resultat = ""
    section_re = re.compile(rf"^\s*\[{re.escape(section)}\]\s*$")
    option_re = re.compile(rf"^\s*{re.escape(option)}\s*=\s*(.+?)\s*$")
    for fichier in fichiers:
        contenu = _lire(fichier)
        if contenu is None:
            continue
        dans_section = False
        for ligne in contenu.splitlines():
            if re.match(r"^\s*\[", ligne):
                dans_section = bool(section_re.match(ligne))
                continue
            if dans_section:
                m = option_re.match(ligne)
                if m:
                    resultat = m.group(1)
    return resultat


def verifier_alignement_port_fail2ban() -> Optional[Constat]:
    """Le jail [sshd] herite `port = ssh` (22) de jail.conf. Si sshd ecoute sur
    un autre port, la regle de pare-feu generee vise toujours 22 : chaque
    bannissement est un no-op silencieux, alors que fail2ban continue de dire
    qu'il bannit. Verification propre a ce fork (pas dans vps-audit d'origine)."""
    if shutil.which("fail2ban-client") is None:
        return None
    dossier = Path("/etc/fail2ban")
    if not dossier.is_dir():
        return None

    sortie_sshd = _executer("sshd", "-T") or ""
    port_effectif = None
    for ligne in sortie_sshd.splitlines():
        if ligne.startswith("port "):
            port_effectif = ligne.split()[1]
            break
    if port_effectif is None:
        config = _lire(Path("/etc/ssh/sshd_config")) or ""
        port_effectif = _option_ssh(config, "Port", "22")
    if not port_effectif.isdigit():
        return Constat("Fail2ban — alignement du port", WARN,
                        "port SSH effectif indéterminable — à vérifier à la main")

    active = _option_jail(dossier, "sshd", "enabled")
    port_jail = _option_jail(dossier, "sshd", "port") or "ssh"
    banaction = _option_jail(dossier, "sshd", "banaction") or _option_jail(dossier, "DEFAULT", "banaction")

    if active != "true":
        return Constat("Fail2ban — alignement du port", WARN,
                        "le jail [sshd] n'est pas activé — les tentatives SSH ne sont pas bloquées")
    if "allports" in banaction:
        return Constat("Fail2ban — alignement du port", PASS,
                        f"banaction={banaction} bloque tous les ports, SSH ({port_effectif}) est couvert")
    if port_jail in ("ssh", port_effectif, "0:65535"):
        return Constat("Fail2ban — alignement du port", PASS,
                        f"le jail [sshd] couvre le port SSH actif ({port_effectif})")
    return Constat("Fail2ban — alignement du port", FAIL,
                    f"le jail bloque le port '{port_jail}' mais SSH écoute sur {port_effectif} — "
                    f"chaque bannissement est silencieusement inefficace")


# --- Connexions échouées -------------------------------------------------------

def verifier_connexions_echouees() -> Constat:
    auth_log = Path("/var/log/auth.log")
    contenu = _lire(auth_log)
    if contenu is not None:
        nombre = contenu.count("Failed password")
    else:
        sortie = _executer("journalctl", "-u", "ssh", "--since", "24 hours ago")
        if sortie is None:
            return Constat("Connexions échouées", WARN,
                            "ni /var/log/auth.log ni journalctl disponibles — hypothèse impossible")
        nombre = sortie.count("Failed password")

    if nombre < SEUIL_LOGINS_WARN:
        return Constat("Connexions échouées", PASS, f"{nombre} tentative(s) échouée(s) — dans la norme")
    if nombre < SEUIL_LOGINS_FAIL:
        return Constat("Connexions échouées", WARN, f"{nombre} tentative(s) échouée(s) — surveiller")
    return Constat("Connexions échouées", FAIL, f"{nombre} tentative(s) échouée(s) — possible attaque en cours")


# --- Mises à jour système ------------------------------------------------------

def verifier_maj_systeme() -> Constat:
    sortie = _executer("apt-get", "-s", "upgrade")
    if sortie is None:
        return Constat("Mises à jour système", WARN, "apt-get absent — machine non Debian/Ubuntu ?")
    m = re.search(r"^(\d+)\s+upgraded", sortie, re.MULTILINE)
    nombre = int(m.group(1)) if m else 0
    return Constat("Mises à jour système", PASS if nombre == 0 else FAIL,
                    "à jour" if nombre == 0 else f"{nombre} mise(s) à jour disponible(s)")


# --- Services et ports ----------------------------------------------------------

def verifier_services() -> Constat:
    sortie = _executer("systemctl", "list-units", "--type=service", "--state=running")
    if sortie is None:
        return Constat("Services actifs", WARN, "systemctl indisponible")
    nombre = sum(1 for ligne in sortie.splitlines() if "loaded active running" in ligne)
    if nombre < SEUIL_SERVICES_WARN:
        return Constat("Services actifs", PASS, f"{nombre} service(s) — surface d'attaque réduite")
    if nombre < SEUIL_SERVICES_FAIL:
        return Constat("Services actifs", WARN, f"{nombre} service(s) — envisager d'en réduire le nombre")
    return Constat("Services actifs", FAIL, f"{nombre} service(s) — surface d'attaque élevée")


def verifier_ports_ouverts() -> Constat:
    # L'index de la colonne adresse locale diffère entre les deux commandes
    # (`ss -tuln` : colonne 4, `netstat -tuln` : colonne 3) — il faut le
    # choisir selon la commande qui a VRAIMENT produit `sortie`, jamais selon
    # la simple présence de `ss` sur la machine (qui peut être installé sans
    # être la commande utilisée, si `ss` a échoué et qu'on est retombé sur
    # `netstat`).
    sortie = _executer("ss", "-tuln")
    index_adresse = 4
    if sortie is None:
        sortie = _executer("netstat", "-tuln")
        index_adresse = 3
    if sortie is None:
        return Constat("Ports ouverts", WARN, "ni `ss` ni `netstat` disponibles")

    ports = set()
    for ligne in sortie.splitlines():
        if "LISTEN" not in ligne:
            continue
        champs = ligne.split()
        adresse = champs[index_adresse] if len(champs) > index_adresse else ""
        if ":" in adresse:
            ports.add(adresse.rsplit(":", 1)[-1])

    nombre = len(ports)
    liste = ",".join(sorted(ports, key=lambda p: (len(p), p)))
    if nombre < SEUIL_PORTS_WARN:
        return Constat("Ports ouverts", PASS, f"{nombre} port(s) en écoute : {liste}")
    if nombre < SEUIL_PORTS_FAIL:
        return Constat("Ports ouverts", WARN, f"{nombre} port(s) en écoute, à vérifier : {liste}")
    return Constat("Ports ouverts", FAIL, f"{nombre} port(s) en écoute — exposition élevée : {liste}")


# --- Ressources ------------------------------------------------------------------

def _verdict_ressource(nom: str, pourcentage: float, detail: str) -> Constat:
    if pourcentage < SEUIL_RESSOURCE_WARN:
        return Constat(nom, PASS, detail)
    if pourcentage < SEUIL_RESSOURCE_FAIL:
        return Constat(nom, WARN, detail)
    return Constat(nom, FAIL, detail)


def verifier_disque() -> Constat:
    try:
        total, utilise, libre = shutil.disk_usage("/")
    except OSError:
        return Constat("Espace disque", WARN, "racine illisible")
    pourcentage = utilise / total * 100
    detail = (f"{pourcentage:.0f}% utilisé "
              f"({utilise // (1024**3)} Go sur {total // (1024**3)} Go, "
              f"{libre // (1024**3)} Go libres)")
    return _verdict_ressource("Espace disque", pourcentage, detail)


def verifier_memoire() -> Constat:
    meminfo = _lire(Path("/proc/meminfo"))
    if meminfo is None:
        return Constat("Mémoire", WARN, "/proc/meminfo illisible (pas Linux ?)")
    valeurs = dict(re.findall(r"^(\w+):\s+(\d+)\s+kB", meminfo, re.MULTILINE))
    if "MemTotal" not in valeurs or "MemAvailable" not in valeurs:
        return Constat("Mémoire", WARN, "champs attendus absents de /proc/meminfo")
    total = int(valeurs["MemTotal"])
    dispo = int(valeurs["MemAvailable"])
    pourcentage = (total - dispo) / total * 100
    detail = f"{pourcentage:.0f}% utilisée ({(total - dispo) // 1024} Mo sur {total // 1024} Mo)"
    return _verdict_ressource("Mémoire", pourcentage, detail)


def verifier_cpu() -> Constat:
    try:
        charge_1min = Path("/proc/loadavg").read_text().split()[0]
    except OSError:
        return Constat("Charge CPU", WARN, "/proc/loadavg illisible (pas Linux ?)")
    import os
    coeurs = os.cpu_count() or 1
    pourcentage = float(charge_1min) / coeurs * 100
    detail = f"charge moyenne (1 min) {charge_1min} sur {coeurs} cœur(s) ({pourcentage:.0f}%)"
    return _verdict_ressource("Charge CPU", pourcentage, detail)


# --- Sudo et mots de passe --------------------------------------------------------

def verifier_journalisation_sudo() -> Constat:
    sudoers = _lire(Path("/etc/sudoers"))
    if sudoers is None:
        return Constat("Journalisation sudo", WARN, "/etc/sudoers illisible depuis cette machine")
    journalise = bool(re.search(r"^\s*Defaults.*logfile", sudoers, re.MULTILINE))
    return Constat("Journalisation sudo", PASS if journalise else FAIL,
                    "les commandes sudo sont journalisées" if journalise else
                    "aucune journalisation — ajouter `Defaults logfile=/var/log/sudo.log`")


def verifier_politique_mdp() -> Constat:
    conf = _lire(Path("/etc/security/pwquality.conf"))
    if conf is None:
        return Constat("Politique de mots de passe", FAIL,
                        "/etc/security/pwquality.conf absent — aucune politique configurée")
    m = re.findall(r"^\s*minlen\s*=\s*(\d+)", conf, re.MULTILINE)
    if not m:
        return Constat("Politique de mots de passe", FAIL, "minlen non défini dans pwquality.conf")
    minlen = int(m[-1])  # la dernière définition non commentée l'emporte
    return Constat("Politique de mots de passe", PASS if minlen >= LONGUEUR_MDP_MIN else FAIL,
                    f"minlen={minlen}" + ("" if minlen >= LONGUEUR_MDP_MIN
                                          else f" — recommandé ≥ {LONGUEUR_MDP_MIN}"))


# --- Fichiers SUID -----------------------------------------------------------------

_CHEMINS_SUID_COURANTS = re.compile(r"^(/usr)?/s?bin/|^/usr/lib|^/usr/libexec")
_BINAIRES_SUID_CONNUS = re.compile(r"/(ping|sudo|mount|umount|su|passwd|chsh|newgrp|gpasswd|chfn)$")


def verifier_fichiers_suid() -> Constat:
    sortie = _executer("find", "/", "-xdev", "-type", "f", "-perm", "-4000", delai=30.0)
    if sortie is None:
        return Constat("Fichiers SUID", WARN, "`find` indisponible ou trop lent sur cette machine")
    suspects = [ligne for ligne in sortie.splitlines()
                if not _CHEMINS_SUID_COURANTS.match(ligne) and not _BINAIRES_SUID_CONNUS.search(ligne)]
    if not suspects:
        return Constat("Fichiers SUID", PASS, "aucun fichier SUID hors des emplacements standards")
    return Constat("Fichiers SUID", WARN,
                    f"{len(suspects)} fichier(s) hors des emplacements standards — à vérifier : "
                    + ", ".join(suspects[:5]) + (", ..." if len(suspects) > 5 else ""))


# ------------------------------------------------------------------------------

def auditer() -> List[Constat]:
    """Toutes les vérifications, dans l'ordre de l'original."""
    constats: List[Constat] = []
    constats.extend(verifier_ssh())
    constats.append(verifier_pare_feu())
    constats.append(verifier_maj_automatiques())
    constats.append(verifier_prevention_intrusion())
    alignement = verifier_alignement_port_fail2ban()
    if alignement is not None:
        constats.append(alignement)
    constats.append(verifier_connexions_echouees())
    constats.append(verifier_maj_systeme())
    constats.append(verifier_services())
    constats.append(verifier_ports_ouverts())
    constats.append(verifier_disque())
    constats.append(verifier_memoire())
    constats.append(verifier_cpu())
    constats.append(verifier_journalisation_sudo())
    constats.append(verifier_politique_mdp())
    constats.append(verifier_fichiers_suid())
    return constats


def main() -> int:
    constats = auditer()
    print("=" * 70)
    print("  ARENA — audit du VPS. Chaque ligne vient d'une mesure réelle.")
    print("=" * 70)
    for c in constats:
        print(c.rendre())

    echecs = [c for c in constats if c.verdict == FAIL]
    avertissements = [c for c in constats if c.verdict == WARN]
    print("=" * 70)
    print(f"{len(echecs)} échec(s), {len(avertissements)} avertissement(s), "
          f"{len(constats) - len(echecs) - len(avertissements)} conforme(s).")
    print("=" * 70)
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
