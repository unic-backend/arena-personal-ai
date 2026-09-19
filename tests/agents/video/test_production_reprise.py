"""Un projet vidéo interrompu reprend là où il s'est arrêté — et ne refait rien.

Le manque que ces tests couvrent (mesuré le 19/09/2026) : un projet vidéo
tournait entièrement en mémoire. Un serveur redémarré au milieu d'une
production laissait **zéro trace** : personne ne pouvait dire ce qui avait
abouti, et la seule issue était de tout relancer — y compris les étapes qui
avaient déjà produit leur fichier.

Trois tests portent l'étape :

- `test_une_etape_deja_aboutie_n_est_pas_rejouee` : c'est toute la valeur de
  la reprise. Si elle échoue, reprendre coûte aussi cher que recommencer.
- `test_une_etape_dont_l_artefact_a_disparu_est_refaite` : l'inverse, et il
  compte autant — sauter une étape dont le fichier n'est plus là rendrait un
  projet qui se déclare fini sans rien livrer.
- `test_reprendre_rejoue_le_graphe_ecrit_jamais_un_nouveau_plan` : redemander
  un plan au modèle donnerait d'autres identifiants d'étape, et le travail
  déjà fait serait refait sous d'autres noms.

Aucun test n'appelle Ollama ni le réseau : chaque collaborateur est un double.
"""
import pytest

from agents.video.production_agent import VideoProductionAgent
from core.production.journal_projet import EtatJob, JournalProjets

PLAN = ('[{"id": "vue", "capacite": "vision", "parametres": {"reference": 0}},'
        ' {"id": "assemblage", "capacite": "montage",'
        '  "parametres": {"references": [0]}, "depend_de": ["vue"]}]')


class ModeleDouble:
    def __init__(self, reponses=None, disponible=True):
        self._reponses = list(reponses or [PLAN])
        self._disponible = disponible
        self.prompts = []

    async def is_available(self) -> bool:
        return self._disponible

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        return self._reponses[0] if len(self._reponses) == 1 else self._reponses.pop(0)


class VisionDouble:
    def __init__(self, erreur=None):
        self.appels = []
        self._erreur = erreur

    async def generate(self, prompt, images=None, **kw):
        self.appels.append(images)
        if self._erreur is not None:
            raise self._erreur
        return "Un mur de plaques."


class MontageDouble:
    """Écrit un VRAI fichier : l'artefact d'une étape n'est jamais supposé."""

    def __init__(self, sortie=None, erreur=None, preuve_brute=None):
        self.appels = []
        self._sortie = sortie
        self._erreur = erreur
        #: Une `preuve` qui n'est PAS un chemin — la forme que rend Drift
        #: (un compte d'operations, `core/connectors/drift.py::_preuve`).
        self._preuve_brute = preuve_brute

    async def run(self, demande, context=None):
        self.appels.append(demande)
        if self._erreur is not None:
            raise self._erreur
        if self._preuve_brute is not None:
            return {"status": "success", "response": "monte",
                    "preuve": self._preuve_brute}
        if self._sortie is None:
            return {"status": "success", "response": "monte"}
        return {"status": "success", "response": "monte", "preuve": str(self._sortie)}


@pytest.fixture
def reference(tmp_path):
    fichier = tmp_path / "chantier.jpg"
    fichier.write_bytes(b"\xff\xd8\xff\xe0donnees-image-factices")
    return str(fichier)


@pytest.fixture
def rendu(tmp_path):
    fichier = tmp_path / "final.mp4"
    fichier.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return fichier


def _agent(journal, vision=None, montage=None, modele=None):
    return VideoProductionAgent(
        provider=modele or ModeleDouble(), provider_vision=vision or VisionDouble(),
        montage_agent=montage or MontageDouble(), journal=journal)


# --- Ce que l'exécution écrit ---------------------------------------------------------

async def test_un_projet_ecrit_son_etat_durable_et_rend_son_job_id(tmp_path, reference,
                                                                   rendu):
    journal = JournalProjets(tmp_path / "journal.json")
    agent = _agent(journal, montage=MontageDouble(sortie=rendu))

    resultat = await agent.run("fabrique une video", context={"references": [reference]})

    assert resultat["job_id"]
    job = journal.lire(resultat["job_id"])
    assert job.etat is EtatJob.REUSSI
    assert [e.step_id for e in job.etapes] == ["vue", "assemblage"]
    assert job.etape("assemblage").artefact == str(rendu)
    # La preuve est mesurée, pas annoncée.
    assert job.etape("assemblage").preuve["secondes"] is not None


async def test_chaque_etape_porte_sa_preuve_et_son_nombre_d_essais(tmp_path, reference,
                                                                   rendu):
    journal = JournalProjets(tmp_path / "journal.json")
    agent = _agent(journal, montage=MontageDouble(sortie=rendu))

    resultat = await agent.run("fabrique une video", context={"references": [reference]})

    for etape in journal.lire(resultat["job_id"]).etapes:
        assert etape.etat is EtatJob.REUSSI
        assert etape.essais >= 1
        assert "secondes" in etape.preuve


async def test_une_etape_obligatoire_en_echec_laisse_le_job_FAILED(tmp_path, reference):
    journal = JournalProjets(tmp_path / "journal.json")
    agent = _agent(journal, vision=VisionDouble(erreur=RuntimeError("modele absent")))

    resultat = await agent.run("fabrique une video", context={"references": [reference]})

    job = journal.lire(resultat["job_id"])
    assert job.etat is EtatJob.ECHOUE
    assert job.etape("vue").etat is EtatJob.ECHOUE
    assert "modele absent" in job.etape("vue").erreur
    # Et l'échec n'est pas maquillé en succès côté réponse.
    assert resultat["status"] == "warning"


async def test_sans_journal_le_comportement_est_exactement_celui_d_avant(tmp_path,
                                                                         reference,
                                                                         rendu):
    """Le journal est un ajout, jamais une condition de fonctionnement."""
    agent = VideoProductionAgent(
        provider=ModeleDouble(), provider_vision=VisionDouble(),
        montage_agent=MontageDouble(sortie=rendu))

    resultat = await agent.run("fabrique une video", context={"references": [reference]})

    assert resultat["status"] == "success"
    assert "job_id" not in resultat


# --- La reprise ------------------------------------------------------------------------

async def test_une_etape_deja_aboutie_n_est_pas_rejouee(tmp_path, reference, rendu):
    """Le cœur de la reprise : ce qui tient encore ne retourne pas sur la carte
    graphique. Sans ça, reprendre coûte aussi cher que recommencer."""
    chemin = tmp_path / "journal.json"
    montage_casse = MontageDouble(erreur=RuntimeError("ffmpeg absent"))
    vision = VisionDouble()
    resultat = await _agent(JournalProjets(chemin), vision=vision,
                            montage=montage_casse).run(
        "fabrique une video", context={"references": [reference]})
    job_id = resultat["job_id"]
    assert vision.appels, "la vision doit avoir tourne au premier passage"

    # Le serveur redemarre : nouveau journal, nouveaux collaborateurs.
    journal = JournalProjets(chemin)
    journal.suspendre(job_id, "coupure")
    vision_2 = VisionDouble()
    montage_2 = MontageDouble(sortie=rendu)
    reprise = await _agent(journal, vision=vision_2, montage=montage_2).reprendre(job_id)

    assert vision_2.appels == [], "l'etape deja aboutie ne doit PAS etre rejouee"
    assert montage_2.appels, "l'etape qui avait echoue doit, elle, etre refaite"
    assert reprise["status"] == "success"
    assert journal.lire(job_id).etat is EtatJob.REUSSI
    assert journal.lire(job_id).etape("vue").preuve.get("reutilise") is True


async def test_une_etape_dont_l_artefact_a_disparu_est_refaite(tmp_path, reference,
                                                               rendu):
    """Statut « réussi », fichier effacé : l'étape est à refaire.

    Se fier au statut seul rendrait un projet qui se déclare fini sans rien
    livrer.
    """
    chemin = tmp_path / "journal.json"
    resultat = await _agent(JournalProjets(chemin),
                            montage=MontageDouble(sortie=rendu)).run(
        "fabrique une video", context={"references": [reference]})
    job_id = resultat["job_id"]

    rendu.unlink()
    journal = JournalProjets(chemin)
    journal.suspendre(job_id, "coupure")
    montage_2 = MontageDouble(sortie=rendu)
    await _agent(journal, montage=montage_2).reprendre(job_id)

    assert montage_2.appels, "l'artefact a disparu : l'etape doit etre refaite"


async def test_un_fichier_annonce_mais_jamais_ecrit_n_est_pas_un_artefact(
        tmp_path, reference):
    """Le montage rend `preuve: /chemin/final.mp4` — et n'écrit rien.

    Retenir ce chemin ferait croire à une livraison, et rendrait l'étape
    réutilisable : une reprise la sauterait, et le projet se déclarerait fini
    sans qu'aucun fichier n'existe.
    """
    chemin = tmp_path / "journal.json"
    journal = JournalProjets(chemin)
    montage = MontageDouble(sortie=tmp_path / "jamais_ecrit.mp4")

    resultat = await _agent(journal, montage=montage).run(
        "fabrique une video", context={"references": [reference]})

    etape = journal.lire(resultat["job_id"]).etape("assemblage")
    assert etape.artefact is None
    assert etape.reutilisable is False
    assert "absent du disque" in etape.erreur


async def test_une_preuve_qui_n_est_pas_un_chemin_n_est_pas_lue_comme_un_fichier(
        tmp_path, reference):
    """Toutes les `preuve` ne sont pas des chemins.

    Celle de Drift est un compte d'opérations. La lire comme un chemin la
    ferait enregistrer « artefact annoncé absent du disque » — une fausse
    alerte qui rendrait l'étape non réutilisable à jamais, et ferait rejouer à
    chaque reprise une étape parfaitement réussie.
    """
    chemin = tmp_path / "journal.json"
    journal = JournalProjets(chemin)

    resultat = await _agent(journal, montage=MontageDouble(preuve_brute=3)).run(
        "fabrique une video", context={"references": [reference]})

    etape = journal.lire(resultat["job_id"]).etape("assemblage")
    assert etape.artefact is None
    assert etape.artefact_attendu is False
    assert etape.erreur == ""
    assert etape.reutilisable is True


async def test_reprendre_rejoue_le_graphe_ecrit_jamais_un_nouveau_plan(tmp_path,
                                                                       reference,
                                                                       rendu):
    """Redemander un plan au modèle donnerait d'autres identifiants d'étape."""
    chemin = tmp_path / "journal.json"
    await _agent(JournalProjets(chemin),
                 montage=MontageDouble(erreur=RuntimeError("casse"))).run(
        "fabrique une video", context={"references": [reference]})
    journal = JournalProjets(chemin)
    job_id = next(iter(journal.reprenables())).job_id

    modele = ModeleDouble(['[{"id": "AUTRE", "capacite": "vision"}]'])
    await _agent(journal, modele=modele, montage=MontageDouble(sortie=rendu)
                 ).reprendre(job_id)

    assert modele.prompts == [], "aucun plan ne doit etre redemande au modele"
    assert [e.step_id for e in journal.lire(job_id).etapes] == ["vue", "assemblage"]


async def test_un_projet_tue_en_plein_travail_est_repris_sans_rejouer_en_aveugle(
        tmp_path, reference, rendu):
    """Le cas réel : le processus meurt PENDANT une étape.

    Cette étape n'est ni réussie ni échouée — on ne sait pas ce qu'elle a fait.
    Elle est nommée dans la réponse plutôt que comptée réussie.
    """
    chemin = tmp_path / "journal.json"
    journal = JournalProjets(chemin)
    job = journal.ouvrir("fabrique une video",
                         graphe=[{"id": "vue", "capacite": "vision",
                                  "parametres": {"reference": 0}},
                                 {"id": "assemblage", "capacite": "montage",
                                  "parametres": {"references": [0]},
                                  "depend_de": ["vue"]}],
                         references=[reference])
    journal.declarer_etapes(job.job_id, [
        {"step_id": "vue", "capacite": "vision"},
        {"step_id": "assemblage", "capacite": "montage"}])
    journal.demarrer_etape(job.job_id, "vue")  # le processus meurt ici

    relu = JournalProjets(chemin)
    assert relu.lire(job.job_id).a_verifier() == ["vue"]

    reprise = await _agent(relu, montage=MontageDouble(sortie=rendu)
                           ).reprendre(job.job_id)

    assert "a verifier avant de relancer" in reprise["response"]
    assert "vue" in reprise["response"]


async def test_reprendre_un_projet_inconnu_le_dit(tmp_path):
    agent = _agent(JournalProjets(tmp_path / "journal.json"))

    resultat = await agent.reprendre("job-fantome")

    assert resultat["status"] == "error"
    assert "inconnu" in resultat["response"]


async def test_reprendre_un_projet_annule_est_refuse(tmp_path, reference):
    chemin = tmp_path / "journal.json"
    resultat = await _agent(JournalProjets(chemin),
                            montage=MontageDouble(erreur=RuntimeError("casse"))).run(
        "fabrique une video", context={"references": [reference]})
    journal = JournalProjets(chemin)
    journal.annuler(resultat["job_id"], "annule par le proprietaire")

    reprise = await _agent(journal).reprendre(resultat["job_id"])

    assert reprise["status"] == "error"
    assert "annule" in reprise["response"]


async def test_reprendre_un_projet_deja_fini_ne_relance_rien(tmp_path, reference,
                                                             rendu):
    chemin = tmp_path / "journal.json"
    resultat = await _agent(JournalProjets(chemin),
                            montage=MontageDouble(sortie=rendu)).run(
        "fabrique une video", context={"references": [reference]})

    journal = JournalProjets(chemin)
    montage_2 = MontageDouble(sortie=rendu)
    reprise = await _agent(journal, montage=montage_2).reprendre(resultat["job_id"])

    assert montage_2.appels == []
    assert reprise["status"] == "warning"
    assert "rien a reprendre" in reprise["response"]
