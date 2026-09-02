"""Les vérifications du script d'audit VPS mesurent-elles vraiment ?

`auditer_vps.py` n'a aucune dépendance réseau ni service à simuler : chaque
sonde lit un fichier ou lance une commande, et chacune peut donc être testée
en remplaçant cette seule lecture — jamais en mockant la mesure elle-même
(`.claude/rules/verification.md` : mocker ce qu'on teste ne prouve rien).

`test_ports_ouverts_choisit_la_bonne_colonne_selon_la_commande_qui_a_repondu`
est le test qui porte le correctif du 02/09/2026 : l'index de colonne était
choisi selon `shutil.which("ss")` (la commande est-elle installée ?) plutôt
que selon la commande qui a réellement produit la sortie — un `ss` installé
mais qui échoue silencieusement (permissions, sandbox) faisait retomber sur
`netstat` tout en lisant `netstat` avec l'index de colonne de `ss`.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

import auditer_vps  # noqa: E402 — le chemin est posé juste au-dessus
from auditer_vps import (  # noqa: E402 — le chemin est posé juste au-dessus
    FAIL,
    PASS,
    WARN,
    Constat,
    _option_jail,
    _option_ssh,
    _verdict_ressource,
    main,
    verifier_ports_ouverts,
    verifier_ssh,
)

# --- _option_ssh ---------------------------------------------------------------

def test_option_ssh_lit_la_valeur_definie():
    config = "Port 2222\nPermitRootLogin no\n"
    assert _option_ssh(config, "Port", "22") == "2222"
    assert _option_ssh(config, "PermitRootLogin", "yes") == "no"


def test_option_ssh_rend_le_defaut_si_absente():
    assert _option_ssh("PasswordAuthentication yes\n", "Port", "22") == "22"


def test_verifier_ssh_signale_le_fichier_illisible(monkeypatch):
    monkeypatch.setattr(auditer_vps, "_lire", lambda chemin: None)
    constats = verifier_ssh()

    assert len(constats) == 1
    assert constats[0].verdict == WARN
    assert "sshd_config illisible" in constats[0].detail


def test_verifier_ssh_racine_ouverte_est_un_echec(monkeypatch):
    monkeypatch.setattr(
        auditer_vps, "_lire",
        lambda chemin: "PermitRootLogin yes\nPasswordAuthentication yes\nPort 22\n")
    constats = verifier_ssh()
    par_nom = {c.nom: c for c in constats}

    assert par_nom["SSH — connexion root"].verdict == FAIL
    assert par_nom["SSH — authentification par mot de passe"].verdict == FAIL
    assert par_nom["SSH — port"].verdict == WARN  # port par défaut, pas un échec


def test_verifier_ssh_configuration_durcie_passe(monkeypatch):
    monkeypatch.setattr(
        auditer_vps, "_lire",
        lambda chemin: "PermitRootLogin no\nPasswordAuthentication no\nPort 2222\n")
    constats = verifier_ssh()
    par_nom = {c.nom: c for c in constats}

    assert par_nom["SSH — connexion root"].verdict == PASS
    assert par_nom["SSH — authentification par mot de passe"].verdict == PASS
    assert par_nom["SSH — port"].verdict == PASS


# --- _option_jail : précédence fail2ban -----------------------------------------

def test_option_jail_respecte_la_precedence(tmp_path):
    """jail.local doit l'emporter sur jail.conf — dernier fichier lu gagne."""
    (tmp_path / "jail.conf").write_text("[sshd]\nport = ssh\n")
    (tmp_path / "jail.local").write_text("[sshd]\nport = 2222\n")
    (tmp_path / "jail.d").mkdir()

    assert _option_jail(tmp_path, "sshd", "port") == "2222"


def test_option_jail_rend_vide_si_option_absente(tmp_path):
    (tmp_path / "jail.conf").write_text("[sshd]\nenabled = true\n")
    (tmp_path / "jail.d").mkdir()

    assert _option_jail(tmp_path, "sshd", "port") == ""


# --- verifier_ports_ouverts : le correctif du 02/09/2026 ------------------------

def test_ports_ouverts_choisit_la_bonne_colonne_selon_la_commande_qui_a_repondu(monkeypatch):
    """`ss` est présent (shutil.which dirait vrai) mais échoue réellement : la
    sortie vient de `netstat`, et l'ancien code lisait quand même la colonne
    de `ss` — extrayant `*` (le port distant, colonne LISTEN de netstat)
    plutôt que le port 22 réellement en écoute."""
    ligne_netstat = "tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN"

    def fausse_executer(*args, delai=5.0):
        if args[0] == "ss":
            return None  # installé mais indisponible dans ce contexte
        if args[0] == "netstat":
            return ligne_netstat + "\n"
        raise AssertionError(f"commande inattendue : {args}")

    monkeypatch.setattr(auditer_vps, "_executer", fausse_executer)

    constat = verifier_ports_ouverts()

    assert "1 port(s)" in constat.detail
    assert ": 22" in constat.detail  # le vrai port en écoute, pas "*"


def test_ports_ouverts_lit_bien_la_colonne_ss_quand_ss_repond(monkeypatch):
    ligne_ss = "tcp   LISTEN  0   128   0.0.0.0:443   0.0.0.0:*"

    def fausse_executer(*args, delai=5.0):
        if args[0] == "ss":
            return ligne_ss + "\n"
        raise AssertionError("netstat ne devrait pas être appelé si ss répond")

    monkeypatch.setattr(auditer_vps, "_executer", fausse_executer)

    constat = verifier_ports_ouverts()

    assert "443" in constat.detail


def test_ports_ouverts_sans_aucun_outil(monkeypatch):
    monkeypatch.setattr(auditer_vps, "_executer", lambda *a, **k: None)

    constat = verifier_ports_ouverts()

    assert constat.verdict == WARN
    assert "ss" in constat.detail and "netstat" in constat.detail


# --- _verdict_ressource : les trois seuils --------------------------------------

def test_verdict_ressource_trois_paliers():
    assert _verdict_ressource("x", 10, "d").verdict == PASS
    assert _verdict_ressource("x", 60, "d").verdict == WARN
    assert _verdict_ressource("x", 90, "d").verdict == FAIL


# --- Constat.rendre ---------------------------------------------------------------

def test_constat_rendre_porte_la_marque_et_le_detail():
    assert Constat("Nom", PASS, "détail").rendre() == "[PASS] Nom — détail"
    assert Constat("Nom", FAIL, "détail").rendre() == "[FAIL] Nom — détail"


# --- main() : le code de sortie reflète les échecs -------------------------------

def test_main_rend_1_si_un_echec_existe(monkeypatch, capsys):
    monkeypatch.setattr(auditer_vps, "auditer", lambda: [Constat("x", FAIL, "d")])
    assert main() == 1


def test_main_rend_0_sans_echec(monkeypatch, capsys):
    monkeypatch.setattr(auditer_vps, "auditer", lambda: [Constat("x", WARN, "d"), Constat("y", PASS, "d")])
    assert main() == 0
