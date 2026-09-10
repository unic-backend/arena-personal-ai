"""HiDream-I1 : generation d'image haute qualite, worker isole.

Mission ARENA x HIDREAM-I1 (DEC-0085). Le contrat HTTP est le meme style que
`core/connectors/moneyprinter.py` : `GET /health`, `POST /generate`,
`GET /jobs/{id}`, `POST /jobs/{id}/cancel`.

**Ce qui distingue ce connecteur des autres generateurs video/image
d'ARENA** : un controle materiel REEL avant tout envoi — c'est le sujet
des deux premiers tests, ceux qui portent l'integration.

Aucun test n'appelle le worker : la couche reseau est injectee.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.hidream import (
    GENERATIONS_PAR_MINUTE,
    HiDreamConnector,
    instantane_de,
)

#: Un materiel genereux — largement de quoi tenir HiDream-I1-Full en bf16
#: sans offload (mission §33 : verifiable independamment de la vraie carte).
MATERIEL_GENEREUX = {
    "gpu": {"nom": "H100", "vram_totale_mo": 80 * 1024, "vram_libre_mo": 75 * 1024, "mesure_le": "x"},
    "ram": {"totale_mo": 64 * 1024, "disponible_mo": 50 * 1024, "mesure_le": "x"},
    "disque": {"chemin": "/data", "libre_mo": 200 * 1024, "mesure_le": "x"},
}

#: Le materiel REEL du proprietaire (RTX A2000 12 Go, 32 Go RAM) — voir
#: docs/audits/hidream_i1_audit.md, Local Acceptance Decision : aucune
#: strategie locale ne tient, meme quantifiee/offload.
MATERIEL_RTX_A2000 = {
    "gpu": {"nom": "NVIDIA RTX A2000", "vram_totale_mo": 12288, "vram_libre_mo": 11500, "mesure_le": "x"},
    "ram": {"totale_mo": 32768, "disponible_mo": 28000, "mesure_le": "x"},
    "disque": {"chemin": "/data", "libre_mo": 200 * 1024, "mesure_le": "x"},
}

SANTE_GENEREUSE = {"variantes_disponibles": ["fast"], "materiel": MATERIEL_GENEREUX}
SANTE_A2000 = {"variantes_disponibles": [], "materiel": MATERIEL_RTX_A2000}

EN_COURS = {"job_id": "j1", "state": "generating"}
TERMINEE = {"job_id": "j1", "state": "completed", "seed": 42,
           "images": ["/sorties/hidream-j1.png"]}
ECHOUEE = {"job_id": "j1", "state": "failed", "error": "VRAM insuffisante pendant la generation."}


def faux_get(reponses, journal=None):
    def _appeler(chemin, parametres, jeton):
        if journal is not None:
            journal.append(("GET", chemin, dict(parametres), jeton))
        for cle, valeur in reponses.items():
            if chemin.startswith(cle):
                if isinstance(valeur, Exception):
                    raise valeur
                return valeur
        raise AssertionError(f"chemin non prevu : {chemin}")
    return _appeler


def faux_post(reponse=None, journal=None):
    def _appeler(chemin, charge, jeton):
        if journal is not None:
            journal.append(("POST", chemin, dict(charge), jeton))
        if isinstance(reponse, Exception):
            raise reponse
        return reponse if reponse is not None else {"job_id": "j1", "state": "queued"}
    return _appeler


@pytest.fixture
def connecteur():
    return HiDreamConnector(
        appel=faux_get({"jobs/j1": EN_COURS, "health": SANTE_GENEREUSE}),
        appel_generation=faux_post(), jeton="")


# --- Les deux tests qui portent l'integration ----------------------------------

def test_une_generation_ne_part_jamais_sans_confirmation(connecteur):
    """Elle occupe la carte graphique plusieurs minutes : c'est lui qui decide."""
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer("generer", prompt="un chat")

    assert resultat.statut is Statut.A_CONFIRMER
    assert not resultat.a_eu_lieu
    assert journal == [], "aucune generation ne doit avoir demarre"


def test_le_materiel_insuffisant_refuse_avant_tout_envoi():
    """Le coeur de la mission (§5-6, §16) : un materiel qui ne tient pas la
    variante ne doit JAMAIS atteindre le worker — jamais un OOM decouvert
    en route. Materiel du RTX A2000 reel du proprietaire."""
    journal = []
    connecteur = HiDreamConnector(
        appel=faux_get({"health": SANTE_A2000}),
        appel_generation=faux_post(journal=journal), jeton="")

    resultat = connecteur.executer_confirmee("generer", prompt="un chat", variante="fast")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert not resultat.a_eu_lieu
    assert journal == [], "le worker n'aurait jamais du recevoir la requete"
    assert "materiel insuffisant" in resultat.message.lower()


# --- Ce qui part au worker quand le materiel tient --------------------------------

def test_la_generation_confirmee_envoie_le_prompt_et_les_parametres(connecteur):
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer_confirmee(
        "generer", prompt="un chat cyberpunk", variante="fast", width=1024, height=1024, seed=7)

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "j1"
    _, chemin, charge, _ = journal[0]
    assert chemin == "generate"
    assert charge["prompt"] == "un chat cyberpunk"
    assert charge["variante"] == "fast"
    assert charge["width"] == 1024
    assert charge["height"] == 1024
    assert charge["seed"] == 7
    assert charge["strategie"]  # la decision materiel voyage avec la requete


def test_une_generation_sans_prompt_ne_part_pas(connecteur):
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer_confirmee("generer", prompt="   ")

    assert resultat.statut is Statut.ECHEC
    assert journal == []


def test_une_variante_inconnue_ne_part_pas(connecteur):
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer_confirmee("generer", prompt="un chat", variante="ultra")

    assert resultat.statut is Statut.ECHEC
    assert journal == []


def test_une_generation_sans_identifiant_rendu_n_est_pas_prouvee(connecteur):
    connecteur._appel_generation = faux_post({"state": "queued"})

    resultat = connecteur.executer_confirmee("generer", prompt="un chat")

    assert resultat.statut is Statut.ECHEC
    assert "sans rendre d'identifiant" in resultat.message


def test_le_jeton_part_dans_l_entete_et_pas_dans_le_resultat():
    journal = []
    connecteur = HiDreamConnector(
        appel=faux_get({"health": SANTE_GENEREUSE}, journal),
        appel_generation=faux_post(journal=journal), jeton="jeton-secret")

    resultat = connecteur.executer_confirmee("generer", prompt="un chat")

    assert any(entree[-1] == "jeton-secret" for entree in journal)
    assert "jeton-secret" not in str(resultat.to_dict())


# --- Etat traduit dans la forme que le suivi WanGP sait deja lire -----------------

def test_l_etat_est_traduit_dans_la_forme_que_le_suivi_sait_lire():
    instantane = instantane_de(TERMINEE)

    assert instantane["done"] is True
    assert instantane["result"]["success"] is True
    assert instantane["result"]["generated_files"] == ["/sorties/hidream-j1.png"]
    assert instantane["result"]["seed"] == 42


def test_le_suivi_deja_ecrit_lit_reellement_cet_instantane(tmp_path):
    """La preuve par l'usage : `suivi_video` (ecrit pour WanGP) n'a pas ete
    touche pour accueillir HiDream. Un VRAI fichier PNG — la relecture
    ajoutee dans `_etat` (mission §14) exige qu'il existe reellement."""
    import asyncio

    from PIL import Image

    from core.connectors.suivi_video import suivre_generation

    chemin = tmp_path / "hidream-j1.png"
    Image.new("RGB", (1024, 1024)).save(chemin)
    terminee = {**TERMINEE, "images": [str(chemin)]}

    connecteur = HiDreamConnector(
        appel=faux_get({"jobs/j1": terminee, "health": SANTE_GENEREUSE}),
        appel_generation=faux_post(), jeton="")

    suivi = asyncio.run(suivre_generation(connecteur, "j1", intervalle=0))

    assert suivi.reussi is True
    assert suivi.fichiers == [str(chemin)]


def test_une_tache_echouee_porte_sa_raison():
    instantane = instantane_de(ECHOUEE)

    assert instantane["done"] is True
    assert instantane["result"]["success"] is False
    assert "VRAM insuffisante" in instantane["result"]["errors"][0]


def test_une_tache_terminee_sans_image_n_est_pas_une_reussite():
    instantane = instantane_de({"job_id": "j1", "state": "completed", "images": []})

    assert instantane["done"] is True
    assert instantane["result"]["success"] is False


def test_etat_travail_rouvre_le_fichier_avant_de_confirmer_le_succes(tmp_path):
    """Mission §14, le coeur de la garantie : le worker peut se tromper (ou
    mentir) — `etat_travail` ne confirme jamais un succes sans avoir
    lui-meme rouvert le fichier annonce."""
    connecteur = HiDreamConnector(
        appel=faux_get({
            "jobs/j1": {**TERMINEE, "images": [str(tmp_path / "n-existe-pas.png")]},
            "health": SANTE_GENEREUSE,
        }),
        appel_generation=faux_post(), jeton="")

    resultat = connecteur.executer("etat_travail", job_id="j1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is False
    assert donnees["result"]["generated_files"] == []
    assert donnees["result"]["validations"][0]["valide"] is False


def test_etat_travail_confirme_un_vrai_fichier_et_ecrit_sa_provenance(tmp_path):
    from PIL import Image

    from core.production.artefact_image import lire_provenance

    chemin = tmp_path / "hidream-vrai.png"
    Image.new("RGB", (1024, 1024)).save(chemin)
    connecteur = HiDreamConnector(
        appel=faux_get({
            "jobs/j1": {**TERMINEE, "images": [str(chemin)], "variante": "fast",
                       "prompt": "un chat"},
            "health": SANTE_GENEREUSE,
        }),
        appel_generation=faux_post(), jeton="")

    resultat = connecteur.executer("etat_travail", job_id="j1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is True
    assert donnees["result"]["validations"][0]["valide"] is True

    provenance = lire_provenance(chemin)
    assert provenance is not None
    assert provenance["modele"] == "HiDream-I1"
    assert provenance["modele_version"] == "fast"
    assert provenance["prompt"] == "un chat"


# --- Service eteint --------------------------------------------------------------

def test_le_service_eteint_donne_la_commande_de_lancement():
    connecteur = HiDreamConnector(
        appel=faux_get({"health": ConnectionError("refuse")}),
        appel_generation=faux_post(), jeton="")

    sante = connecteur.sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "serveur_hidream.py" in sante.ce_qui_manque
    assert "HIDREAM_WORKER_URL" in sante.ce_qui_manque


def test_sans_worker_aucune_image_n_est_promise():
    connecteur = HiDreamConnector(
        appel=faux_get({"health": ConnectionError("refuse")}),
        appel_generation=faux_post(), jeton="")

    resultat = connecteur.executer_confirmee("generer", prompt="un chat")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert not resultat.a_eu_lieu


def test_l_etat_sans_identifiant_ne_regarde_rien(connecteur):
    resultat = connecteur.executer("etat_travail", job_id="  ")

    assert resultat.statut is Statut.ECHEC
    assert "Aucun identifiant" in resultat.message


# --- Capacites declarees -----------------------------------------------------------

def test_les_capacites_declarees(connecteur):
    capacites = connecteur.capacites()

    assert set(capacites) == {"capacites", "generer", "etat_travail", "annuler_travail"}
    assert [nom for nom, c in capacites.items() if c.ecriture] == ["generer", "annuler_travail"]
    assert capacites["generer"].quota_par_minute == GENERATIONS_PAR_MINUTE


def test_le_service_declare_est_image_generation(connecteur):
    assert connecteur.service == "image_generation"


def test_la_regle_exige_bien_une_confirmation():
    """La protection est dans un fichier de configuration : un test la
    mesure, sinon elle se fait retirer sans que rien ne tombe."""
    from pathlib import Path

    import yaml
    racine = Path(__file__).resolve().parents[2]
    regles = yaml.safe_load(
        (racine / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))

    assert regles["services"]["image_generation"]["generate"]["decision"] == "CONFIRMATION"
    assert regles["services"]["image_generation"]["cancel"]["decision"] == "ALLOWED"


@pytest.mark.parametrize("interdite", ["supprimer", "delete", "pipeline"])
def test_capacite_hors_liste_n_existe_pas(connecteur, interdite):
    assert connecteur.executer(interdite).statut is Statut.NON_IMPLEMENTE
