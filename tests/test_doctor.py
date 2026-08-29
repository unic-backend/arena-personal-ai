"""Le diagnostic dit-il la vérité ?

Ce fichier existe à cause d'un mensonge. Jusqu'au 28/08/2026, `doctor.py`
affichait « [OK] Environnement virtuel (.venv) actif » **sans rien vérifier** :
lancé hors du venv, il disait quand même OK. Il n'avait aucun test — c'est
précisément ce qui a permis à cette ligne de survivre.

`test_le_venv_est_mesure_et_non_affirme` est le test qui porte la correction.
`test_aucun_secret_n_est_affiche` est celui qui protège le propriétaire quand il
colle son diagnostic dans une conversation.
"""
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

import doctor  # noqa: E402 — le chemin est posé juste au-dessus
from doctor import (  # noqa: E402 — le chemin est posé juste au-dessus
    ABSENT,
    EN_PANNE,
    NON_CONFIGURE,
    OK,
    Rapport,
    Verification,
    modeles_ollama,
    verifier_cle_api,
    verifier_connaissances_metier,
    verifier_dependances,
    verifier_docker,
    verifier_environnement_virtuel,
    verifier_ffmpeg,
    verifier_google,
    verifier_modele,
    verifier_ollama,
    verifier_python,
)

CLE = "une-cle-de-test-tres-longue-et-secrete"


# --- Le test qui porte la correction ------------------------------------------------

def test_le_venv_est_mesure_et_non_affirme(monkeypatch):
    """La ligne qui mentait : hors venv, elle doit dire ABSENT."""
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    assert verifier_environnement_virtuel().etat == ABSENT


def test_un_venv_actif_est_reconnu(monkeypatch):
    monkeypatch.setattr(sys, "prefix", "/projet/.venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr")

    verification = verifier_environnement_virtuel()

    assert verification.etat == OK
    assert ".venv" in verification.detail


# --- Aucun secret ne sort ------------------------------------------------------------

def test_aucun_secret_n_est_affiche():
    """Un diagnostic collé dans une conversation ne doit rien divulguer."""
    verification = verifier_cle_api(CLE)

    assert verification.etat == OK
    assert CLE not in verification.rendre()
    assert str(len(CLE)) in verification.detail


def test_une_cle_absente_est_un_defaut_de_configuration():
    verification = verifier_cle_api("   ")

    assert verification.etat == NON_CONFIGURE
    assert verification.essentiel is True
    assert "secrets.token_urlsafe" in verification.remede


# --- Une absence de réponse n'est pas une liste vide ---------------------------------

def test_ollama_muet_rend_none_pas_une_liste_vide():
    """`[]` voudrait dire « il répond et n'a aucun modèle » : autre phrase, autre remède."""
    def refuse(url):
        raise ConnectionError("injoignable")

    assert modeles_ollama(lecteur=refuse) is None


def test_ollama_qui_repond_rend_ses_modeles():
    def repond(url):
        return {"models": [{"name": "qwen3.5:9b"}, {"name": "nomic-embed-text:latest"}]}

    assert modeles_ollama(lecteur=repond) == ["qwen3.5:9b", "nomic-embed-text:latest"]


def test_sans_ollama_la_presence_d_un_modele_est_indeterminable():
    """On ne dit pas « absent » de ce qu'on n'a pas pu regarder."""
    verification = verifier_modele("Modele rapide", "qwen3.5:9b", None)

    assert verification.etat == EN_PANNE
    assert "indeterminable" in verification.detail


def test_un_modele_installe_est_reconnu_avec_ou_sans_etiquette():
    installes = ["nomic-embed-text:latest"]

    assert verifier_modele("Embeddings", "nomic-embed-text", installes).etat == OK
    assert verifier_modele("Autre", "bge-m3", installes).etat == ABSENT


def test_un_modele_absent_donne_la_commande_qui_l_installe():
    verification = verifier_modele("Modele profond", "qwen3.5:9b", ["autre:1b"])

    assert verification.etat == ABSENT
    assert verification.remede == "ollama pull qwen3.5:9b"


def test_ollama_eteint_est_une_panne_essentielle():
    verification = verifier_ollama(None)

    assert verification.etat == EN_PANNE
    assert verification.essentiel is True
    assert verification.remede == "ollama serve"


# --- Les autres mesures ---------------------------------------------------------------

def test_python_mesure_la_version_reellement_en_cours():
    verification = verifier_python()

    assert verification.etat == OK
    assert f"{sys.version_info.major}.{sys.version_info.minor}" in verification.detail


def test_un_paquet_manquant_est_nomme():
    def importer(paquet):
        if paquet == "httpx":
            raise ImportError("absent")

    verification = verifier_dependances(importateur=importer)

    assert verification.etat == ABSENT
    assert "httpx" in verification.detail
    assert verification.remede == "pip install -r requirements.txt"


@pytest.mark.parametrize("sonde,attendu", [(lambda: True, OK), (lambda: False, ABSENT)])
def test_les_outils_systeme_sont_sondes(sonde, attendu):
    assert verifier_ffmpeg(sonde=sonde).etat == attendu
    assert verifier_docker(sonde=sonde).etat == attendu


def test_docker_absent_dit_qu_arena_refuse_plutot_que_de_degrader():
    """Le remède compte moins que la conséquence : il faut qu'il la lise."""
    verification = verifier_docker(sonde=lambda: False)

    assert "REFUSE" in verification.detail


def test_google_incomplet_nomme_les_variables_manquantes():
    verification = verifier_google("Courrier", "ARENA ne lit rien",
                                   "gmail.readonly", ["GOOGLE_CLIENT_SECRET"])

    assert verification.etat == NON_CONFIGURE
    assert "GOOGLE_CLIENT_SECRET" in verification.detail
    assert "GOOGLE_CLIENT_ID" not in verification.detail


def test_google_complet_n_affiche_aucune_valeur(monkeypatch):
    """Les valeurs ne traversent meme pas la fonction : seuls les NOMS y entrent."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id-secret")
    verification = verifier_google("Agenda", "rien", "calendar.readonly", [])

    assert verification.etat == OK
    assert "id-secret" not in verification.rendre()


def test_des_dependances_absentes_rendent_google_indeterminable():
    """On ne dit pas « non configure » de ce qu'on n'a pas pu regarder."""
    verification = verifier_google("Courrier", "rien", "gmail.readonly", None)

    assert verification.etat == EN_PANNE
    assert "indeterminable" in verification.detail


def test_les_noms_des_variables_viennent_du_code_des_connecteurs(monkeypatch):
    """La ligne qui a deja derive une fois : le diagnostic reclamait GMAIL_*
    quand le projet attendait GOOGLE_*. Les deux listes ne doivent plus etre
    ecrites a deux endroits."""
    from doctor import variables_google_absentes

    for suffixe in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN"):
        monkeypatch.delenv(f"GOOGLE_{suffixe}", raising=False)
        monkeypatch.delenv(f"GMAIL_{suffixe}", raising=False)

    from core.connectors.google_oauth import manquantes

    assert variables_google_absentes() == manquantes()
    assert variables_google_absentes() == [
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]


def test_l_agenda_est_diagnostique_lui_aussi():
    from doctor import diagnostiquer

    noms = [v.nom for v in diagnostiquer().verifications]

    assert "Agenda (Calendar)" in noms
    assert "Courrier (Gmail)" in noms


def test_les_connaissances_metier_reelles_sont_lues():
    """Le fichier de prix du propriétaire, pas un double."""
    verification = verifier_connaissances_metier()

    assert verification.etat == OK
    assert "article" in verification.detail


def test_un_fichier_metier_illisible_est_une_panne(tmp_path):
    casse = tmp_path / "metier.yaml"
    casse.write_text("ceci: [n'est pas: du yaml", encoding="utf-8")

    assert verifier_connaissances_metier(casse).etat == EN_PANNE


def test_un_fichier_metier_absent_est_signale(tmp_path):
    assert verifier_connaissances_metier(tmp_path / "absent.yaml").etat == ABSENT


# --- Le verdict ------------------------------------------------------------------------

def test_un_essentiel_manquant_empeche_arena_de_repondre():
    rapport = Rapport([
        Verification("Ollama", EN_PANNE, "eteint", "ollama serve", essentiel=True),
        Verification("ffmpeg", ABSENT, "absent", "installer"),
    ])

    assert [v.nom for v in rapport.manquants_essentiels] == ["Ollama"]
    assert "NE PEUT PAS REPONDRE" in rapport.rendre()


def test_une_capacite_absente_n_empeche_pas_de_repondre():
    """ffmpeg manquant coûte la vidéo, pas la conversation."""
    rapport = Rapport([
        Verification("Ollama", OK, "en ligne", essentiel=True),
        Verification("ffmpeg", ABSENT, "absent", "installer"),
    ])

    assert rapport.manquants_essentiels == []
    assert "ARENA peut repondre." in rapport.rendre()
    assert "1 capacite(s) indisponible(s)" in rapport.rendre()


def test_chaque_defaut_porte_son_remede():
    """Nommer un problème sans dire quoi faire laisse le propriétaire devant un terminal."""
    from doctor import diagnostiquer

    sans_remede = [v.nom for v in diagnostiquer().a_regarder if not v.remede]

    assert sans_remede == [], f"defauts sans remede : {sans_remede}"


def test_un_ok_ne_porte_jamais_de_remede():
    assert verifier_python().remede == ""


def test_main_charge_le_dotenv_avant_de_diagnostiquer(monkeypatch):
    """`os.getenv()` ne lit que l'environnement du processus, jamais `.env` —
    seul `load_dotenv()` fait le pont. `doctor.py` ne passe jamais par
    `apps.backend.config` (l'autre endroit ou `.env` est charge), donc sans
    cet appel une cle correctement ecrite dans `.env` restait mesuree comme
    absente : exactement le defaut reproduit en conditions reelles, une
    USMAN_API_KEY presente dans `.env` mais que `doctor.py` disait absente."""
    appels = []
    monkeypatch.setattr(doctor, "load_dotenv", lambda dotenv_path=None: appels.append(dotenv_path))
    monkeypatch.setattr(doctor, "diagnostiquer", lambda: Rapport([]))

    doctor.main()

    assert len(appels) == 1, "main() doit charger .env avant toute mesure"
    assert appels[0] == RACINE / ".env"


def test_sans_dotenv_installe_main_ne_plante_pas(monkeypatch):
    """`dotenv` est une dependance parmi d'autres : son absence doit se lire
    dans la ligne « Dependances », jamais faire planter le diagnostic entier."""
    monkeypatch.setattr(doctor, "load_dotenv", None)
    monkeypatch.setattr(doctor, "diagnostiquer", lambda: Rapport([]))

    assert doctor.main() == 0
