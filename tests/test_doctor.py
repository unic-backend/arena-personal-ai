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
    verifier_tesseract,
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
    assert verifier_tesseract(sonde=sonde).etat == attendu


def test_tesseract_absent_dit_ce_qui_reste_illisible():
    verification = verifier_tesseract(sonde=lambda: False)

    assert verification.etat == ABSENT
    assert "scanne" in verification.detail
    assert verification.remede


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


class TestUnePanneNeTueJamaisLeDiagnostic:
    """Une sonde qui casse marque SA ligne, pas les vingt autres.

    Mesure du 29/08/2026, machine du proprietaire (Windows) : la sonde
    OpenTakeoff levait `OSError [WinError 10038]` — le `select()` sur un pipe,
    corrige dans `core/mcp/stdio_transport.py` — et `doctor.py` s'arretait la.
    Il perdait le GPU, Ollama, ffmpeg, la cle API : tout, a cause d'un seul
    connecteur en panne. Un diagnostic qui meurt de ce qu'il diagnostique ne
    diagnostique rien.
    """

    def test_une_sonde_qui_leve_marque_sa_ligne_et_ne_remonte_pas(self, monkeypatch):
        from core.connectors import opentakeoff

        def sonde_qui_casse(self):
            raise OSError(10038, "Une operation a ete tentee sur autre chose qu'un socket")

        monkeypatch.setattr(opentakeoff.ConnecteurOpenTakeoff, "sonder", sonde_qui_casse)

        verification = doctor.verifier_opentakeoff()

        assert verification.etat == EN_PANNE
        assert "10038" in verification.detail, (
            "la ligne ne dit pas ce qui a cassé : le propriétaire ne peut pas agir dessus")

    def test_le_rapport_complet_survit_a_cette_panne(self, monkeypatch):
        """Le vrai enjeu : les autres lignes sont toujours là."""
        from core.connectors import opentakeoff

        monkeypatch.setattr(
            opentakeoff.ConnecteurOpenTakeoff, "sonder",
            lambda self: (_ for _ in ()).throw(OSError(10038, "pas un socket")))

        verification = doctor.verifier_opentakeoff()
        rapport = Rapport([
            Verification("GPU", OK, "RTX A2000"),
            verification,
            Verification("Ollama", OK, "4 modeles"),
        ])

        assert len(rapport.verifications) == 3
        assert [v.etat for v in rapport.verifications] == [OK, EN_PANNE, OK]


class TestAucuneSondeNEmporteLeRapport:
    """La garde de `verifier_opentakeoff` ne disait rien des vingt autres.

    Mesuré le 29/08/2026 : une sonde levait `OSError [WinError 10038]` et le
    diagnostic entier mourait. La sonde a été corrigée — et une sonde corrigée
    ne protège que d'elle-même. Les autres lisent des fichiers, ouvrent des
    sous-processus et importent des modules : n'importe laquelle peut lever
    demain, et le propriétaire reperdrait ses vingt lignes utiles.

    `test_le_rapport_survit_a_n_importe_quelle_sonde_qui_leve` est le test qui
    porte la garantie : elle est celle du **rapport**, pas d'une sonde.
    """

    def test_mesurer_transforme_une_exception_en_ligne_en_panne(self):
        def sonde_qui_casse():
            raise RuntimeError("le disque a disparu")

        verification = doctor.mesurer("Une sonde", sonde_qui_casse)

        assert verification.nom == "Une sonde"
        assert verification.etat == EN_PANNE
        assert "RuntimeError" in verification.detail
        assert "le disque a disparu" in verification.detail, (
            "la ligne ne dit pas ce qui a cassé : elle n'aide personne")

    def test_mesurer_ne_touche_pas_a_une_sonde_qui_va_bien(self):
        attendue = Verification("Ollama", OK, "en ligne, 4 modele(s)")

        assert doctor.mesurer("Ollama", lambda: attendue) is attendue

    def test_le_rapport_survit_a_n_importe_quelle_sonde_qui_leve(self, monkeypatch):
        """Chaque sonde est cassée à son tour ; le rapport doit rester entier."""
        sondes = [nom for nom in dir(doctor)
                  if nom.startswith("verifier_") and nom != "verifier_modele"]
        assert len(sondes) >= 10, "l'inventaire des sondes n'a rien trouvé"

        entier = len(doctor.diagnostiquer().verifications)

        for nom in sondes:
            with monkeypatch.context() as contexte:
                contexte.setattr(
                    doctor, nom,
                    lambda *a, **k: (_ for _ in ()).throw(OSError(10038, "pas un socket")))
                rapport = doctor.diagnostiquer()

            assert len(rapport.verifications) == entier, (
                f"{nom} en panne fait disparaître des lignes du rapport")
            assert any(v.etat == EN_PANNE for v in rapport.verifications), (
                f"{nom} a levé sans qu'aucune ligne ne le signale")

    def test_ollama_injoignable_ne_tue_pas_le_rapport(self, monkeypatch):
        """`modeles_ollama` est appelé avant la liste : il était hors du filet."""
        monkeypatch.setattr(
            doctor, "modeles_ollama",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("réseau coupé")))

        rapport = doctor.diagnostiquer()

        assert rapport.verifications, "le rapport est vide"


class TestVoiceStudioEstDiagnostique:
    """Une capacité que le diagnostic ignore est invisible au propriétaire.

    Le connecteur audio est arrivé le 01/09/2026 ; `doctor.py` ne le
    connaissait pas. Et un port qui répond ne prouve rien : VoiceStudio
    démarre très bien **sans aucun moteur**, et une sonde qui s'arrêterait à
    `/system/info` l'annoncerait « OK » alors qu'il ne peut ni parler ni
    écouter.
    """

    def _lecteur(self, tts=(), asr=(), muet=False):
        def lire(url):
            if muet:
                raise OSError("connexion refusee")
            if url.endswith("/system/info"):
                return {"app_version": "0.5.1", "device": "cpu"}
            genre = url.rsplit("/", 1)[-1]
            moteurs = tts if genre == "tts" else asr
            return {"backends": [{"id": m, "available": True} for m in moteurs]}
        return lire

    def test_service_eteint_est_non_configure_avec_la_commande(self):
        v = doctor.verifier_voicestudio(self._lecteur(muet=True))
        assert v.etat is NON_CONFIGURE
        assert "uvicorn" in v.remede

    def test_un_port_qui_repond_sans_moteur_n_est_pas_OK(self):
        """Le mensonge que ce test empêche."""
        v = doctor.verifier_voicestudio(self._lecteur(tts=(), asr=()))
        assert v.etat is NON_CONFIGURE
        assert "aucun moteur" in v.detail

    def test_transcription_seule_est_signalee_comme_incomplete(self):
        v = doctor.verifier_voicestudio(self._lecteur(tts=(), asr=("faster-whisper",)))
        assert v.etat is NON_CONFIGURE
        assert "aucun moteur de voix" in v.detail

    def test_les_moteurs_reels_sont_nommes(self):
        v = doctor.verifier_voicestudio(
            self._lecteur(tts=("kittentts",), asr=("faster-whisper",)))
        assert v.etat is OK
        assert "kittentts" in v.detail and "faster-whisper" in v.detail

    def test_le_diagnostic_complet_porte_la_ligne(self):
        """Sans ça, la vérification existe mais personne ne la voit."""
        import inspect
        assert 'mesurer("Voix (VoiceStudio)"' in inspect.getsource(doctor)


class TestModeleEmbeddings:
    """Le diagnostic doit nommer le modèle qu'ARENA demande, pas un autre.

    Défaut mesuré le 01/09/2026 : la valeur par défaut était écrite deux fois
    et avait divergé. `scripts/doctor.py` vérifiait `nomic-embed-text` pendant
    que `core/memory/semantique.py` demandait `bge-m3` depuis le 27/08/2026 —
    un changement mesuré, pas un goût : le seuil sémantique de 0,45 appartient
    à bge-m3.

    Conséquence : le propriétaire installait le modèle que le diagnostic
    nommait, le diagnostic passait au vert, et la mémoire sémantique ne
    marchait toujours pas.
    """

    def test_le_diagnostic_nomme_le_modele_du_code(self):
        from core.memory.semantique import MODELE_EMBEDDINGS

        assert doctor.modele_embeddings_du_code() == MODELE_EMBEDDINGS

    def test_la_variable_d_environnement_est_respectee(self, monkeypatch):
        """Une seule source, mais toujours réglable par `.env`."""
        import importlib

        import core.memory.semantique as semantique

        monkeypatch.setenv("EMBEDDINGS_LOCAL_MODEL", "un-modele-a-lui")
        importlib.reload(semantique)
        try:
            assert doctor.modele_embeddings_du_code() == "un-modele-a-lui"
        finally:
            monkeypatch.delenv("EMBEDDINGS_LOCAL_MODEL", raising=False)
            importlib.reload(semantique)

    def test_un_modele_illisible_ne_se_devine_pas(self, monkeypatch):
        """Nommer un modèle au hasard est exactement ce qui a produit le défaut."""
        monkeypatch.setattr(doctor, "modele_embeddings_du_code", lambda: None)

        resultat = doctor.verifier_modele_embeddings(["bge-m3"])

        assert resultat.etat == doctor.ABSENT
        assert "indeterminable" in resultat.detail
