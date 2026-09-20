"""Un travail de fond survit-il à un redémarrage — et que peut-on honnêtement
en faire ensuite ?

Le manque mesuré (20/09/2026) : `FileDeTravaux` était deux dictionnaires en
mémoire. Un lot de conversion à moitié fait, un suivi de génération en cours,
disparaissaient sans laisser de trace au redémarrage d'ARENA.

Quatre tests portent l'étape :

- `test_un_travail_en_cours_au_redemarrage_devient_INTERROMPU` : jamais
  `TERMINE` (ce serait un mensonge), jamais effacé (ce serait une perte).
- `test_le_resultat_n_est_jamais_relu_du_disque` : un résultat non
  sérialisable a été écrit par `repr`. Le rendre tel quel donnerait une chaîne
  déguisée en objet, qu'un appelant traiterait comme le vrai résultat.
- `test_une_cle_deja_terminee_ne_relance_rien` : la règle d'idempotence.
- `test_un_travail_sans_descripteur_ne_se_reprend_pas` : inventer une reprise
  pour un travail qui ne sait pas se décrire serait pire que ne pas reprendre.

Aucun test n'écrit hors de `tmp_path`.
"""
import asyncio
import json

import pytest

from core.execution.travaux import EtatTravail, FileDeTravaux


@pytest.fixture
def fichier(tmp_path):
    return tmp_path / "file.json"


async def _rien():
    return "fait"


# --- Ce qui est écrit --------------------------------------------------------------

async def test_un_travail_est_ecrit_des_sa_soumission(fichier):
    """Écrit AVANT de tourner : c'est cette fenêtre qu'un arrêt brutal doit
    laisser visible."""
    file = FileDeTravaux(fichier=fichier)
    travail = file.soumettre("indexation", _rien)

    charge = json.loads(fichier.read_text(encoding="utf-8"))
    assert [t["id"] for t in charge["travaux"]] == [travail.identifiant]

    await file.attendre(travail.identifiant)
    charge = json.loads(fichier.read_text(encoding="utf-8"))
    assert charge["travaux"][0]["etat"] == "DONE"


async def test_sans_fichier_la_file_n_ecrit_rien(tmp_path):
    """Le défaut reste la mémoire pure : brancher un disque partout ferait
    écrire des fichiers à des tests qui n'en demandent pas."""
    file = FileDeTravaux()
    travail = file.soumettre("indexation", _rien)
    await file.attendre(travail.identifiant)

    assert file.fichier is None
    assert list(tmp_path.iterdir()) == []


async def test_un_echec_est_ecrit_avec_sa_raison(fichier):
    async def casse():
        raise RuntimeError("libreoffice absent")

    file = FileDeTravaux(fichier=fichier)
    travail = file.soumettre("conversion", casse)
    await file.attendre(travail.identifiant)

    relue = FileDeTravaux(fichier=fichier)
    repris = relue.lire(travail.identifiant)
    assert repris.etat is EtatTravail.ECHOUE
    assert "libreoffice absent" in repris.raison


# --- Le redémarrage -----------------------------------------------------------------

async def test_un_travail_qui_tourne_est_ecrit_EN_COURS_sur_le_disque(fichier):
    """C'est la fenêtre qu'un `kill -9` doit laisser visible.

    Sans cette écriture-là, un travail tué en plein milieu se relirait comme
    s'il n'avait jamais été soumis.
    """
    demarre = asyncio.Event()
    libere = asyncio.Event()

    async def sans_fin():
        demarre.set()
        await libere.wait()

    file = FileDeTravaux(fichier=fichier)
    travail = file.soumettre("suivi video", sans_fin)
    await demarre.wait()

    charge = json.loads(fichier.read_text(encoding="utf-8"))
    assert charge["travaux"][0]["etat"] == "RUNNING"
    assert charge["travaux"][0]["demarre_le"]

    libere.set()
    await file.attendre(travail.identifiant)


async def test_un_travail_en_cours_au_redemarrage_devient_INTERROMPU(fichier):
    """Rien ne tourne au démarrage : un `RUNNING` retrouvé est un travail mort.

    Le fichier est écrit tel qu'un `kill -9` le laisse : état `RUNNING`, pas
    de fin, pas de raison.
    """
    fichier.write_text(json.dumps({"travaux": [{
        "id": "t1", "nom": "suivi video", "etat": "RUNNING",
        "demarre_le": "2026-09-20T00:00:00+00:00",
    }]}), encoding="utf-8")

    file = FileDeTravaux(fichier=fichier)
    repris = file.lire("t1")

    assert repris.etat is EtatTravail.INTERROMPU
    assert "redemarrage" in repris.raison
    assert [t.identifiant for t in file.interrompus()] == ["t1"]


async def test_une_raison_deja_ecrite_n_est_pas_ecrasee(fichier):
    """Ce que le travail avait dit de lui-même vaut mieux qu'un message générique."""
    fichier.write_text(json.dumps({"travaux": [{
        "id": "t1", "nom": "lot", "etat": "RUNNING",
        "raison": "12 fichiers sur 40 convertis",
    }]}), encoding="utf-8")

    assert FileDeTravaux(fichier=fichier).lire("t1").raison == (
        "12 fichiers sur 40 convertis")


async def test_un_travail_en_attente_au_redemarrage_devient_INTERROMPU_aussi(fichier):
    """Soumis, jamais démarré : il n'a pas abouti non plus."""
    fichier.write_text(json.dumps({"travaux": [
        {"id": "t1", "nom": "indexation", "etat": "PENDING"}]}), encoding="utf-8")

    file = FileDeTravaux(fichier=fichier)

    assert file.lire("t1").etat is EtatTravail.INTERROMPU


async def test_un_travail_termine_reste_termine(fichier):
    fichier.write_text(json.dumps({"travaux": [
        {"id": "t1", "nom": "indexation", "etat": "DONE"}]}), encoding="utf-8")

    assert FileDeTravaux(fichier=fichier).lire("t1").etat is EtatTravail.TERMINE


async def test_le_resultat_n_est_jamais_ecrit_sur_le_disque(fichier):
    """Le journal dit CE QUI a tourné, pas ce que ça a produit.

    Deux raisons, et la seconde pèse plus : un résultat non sérialisable
    deviendrait une chaîne `repr` qu'un appelant prendrait pour le vrai objet ;
    et un résultat porte souvent le contenu du propriétaire — chemins de ses
    fichiers, extraits de ses documents. Après un redémarrage, `resultat` vaut
    `None` ; l'état, lui, reste exact.
    """
    class PasDuJson:
        pass

    async def rend_un_objet():
        return PasDuJson()

    file = FileDeTravaux(fichier=fichier)
    travail = file.soumettre("analyse", rend_un_objet)
    await file.attendre(travail.identifiant)
    assert file.lire(travail.identifiant).resultat is not None

    # Le disque ne le porte meme pas : rien a relire, rien a fuiter.
    assert "resultat" not in json.loads(fichier.read_text(encoding="utf-8"))["travaux"][0]

    relue = FileDeTravaux(fichier=fichier)
    assert relue.lire(travail.identifiant).resultat is None
    assert relue.lire(travail.identifiant).etat is EtatTravail.TERMINE


async def test_un_travail_interrompu_n_est_jamais_purge(fichier):
    """La purge borne l'historique FINI. Jeter un interrompu perdrait du travail."""
    from core.execution.travaux import TRAVAUX_TERMINES_GARDES

    travaux = [{"id": "interrompu", "nom": "lot", "etat": "RUNNING"}]
    travaux += [{"id": f"fini{i}", "nom": "x", "etat": "DONE", "fini_le": f"{i:04d}"}
                for i in range(TRAVAUX_TERMINES_GARDES + 20)]
    fichier.write_text(json.dumps({"travaux": travaux}), encoding="utf-8")

    file = FileDeTravaux(fichier=fichier)
    await file.attendre(file.soumettre("de plus", _rien).identifiant)

    assert file.lire("interrompu") is not None
    assert file.lire("interrompu").etat is EtatTravail.INTERROMPU


async def test_un_journal_illisible_repart_a_vide_sans_lever(fichier):
    fichier.write_text("{pas du json", encoding="utf-8")

    file = FileDeTravaux(fichier=fichier)

    assert file.inventaire() == []
    assert file.soumettre("indexation", _rien).identifiant


async def test_un_travail_illisible_est_ignore_sans_emporter_les_autres(fichier):
    fichier.write_text(json.dumps({"travaux": [
        {"pas_d_identifiant": True},
        {"id": "bon", "nom": "indexation", "etat": "DONE"}]}), encoding="utf-8")

    assert FileDeTravaux(fichier=fichier).lire("bon") is not None


# --- La clé d'exécution ---------------------------------------------------------------

async def test_une_cle_deja_terminee_ne_relance_rien(fichier):
    """Même job, même clé : un seul effet. C'est la règle d'idempotence."""
    appels = []

    async def compte():
        appels.append(1)
        return "fait"

    file = FileDeTravaux(fichier=fichier)
    premier = file.soumettre("conversion", compte, cle="lot:abc")
    await file.attendre(premier.identifiant)

    second = file.soumettre("conversion", compte, cle="lot:abc")

    assert second.identifiant == premier.identifiant
    assert appels == [1], "le corps ne doit avoir tourne qu'une fois"


async def test_une_cle_survit_au_redemarrage(fichier):
    """Sinon l'idempotence s'arrêterait exactement là où elle sert le plus."""
    appels = []

    async def compte():
        appels.append(1)
        return "fait"

    file = FileDeTravaux(fichier=fichier)
    await file.attendre(file.soumettre("conversion", compte, cle="lot:abc").identifiant)

    relue = FileDeTravaux(fichier=fichier)
    relue.soumettre("conversion", compte, cle="lot:abc")

    assert appels == [1]


async def test_une_cle_echouee_ne_bloque_pas_un_nouvel_essai(fichier):
    """Figer une panne passagère en refus permanent serait pire que de réessayer."""
    essais = []

    async def casse():
        essais.append(1)
        raise RuntimeError("service coupe")

    file = FileDeTravaux(fichier=fichier)
    await file.attendre(file.soumettre("conversion", casse, cle="lot:abc").identifiant)
    await file.attendre(file.soumettre("conversion", casse, cle="lot:abc").identifiant)

    assert len(essais) == 2


async def test_sans_cle_deux_soumissions_sont_deux_travaux(fichier):
    file = FileDeTravaux(fichier=fichier)
    un = file.soumettre("indexation", _rien)
    deux = file.soumettre("indexation", _rien)

    assert un.identifiant != deux.identifiant


# --- La reprise, et ce qu'elle ne promet pas ------------------------------------------

async def test_un_travail_avec_descripteur_est_repris(fichier):
    fichier.write_text(json.dumps({"travaux": [{
        "id": "t1", "nom": "suivi video", "etat": "RUNNING",
        "descripteur": {"type": "suivi", "parametres": {"job_id": "wan-42"},
                        "passer_le_travail": False},
    }]}), encoding="utf-8")
    file = FileDeTravaux(fichier=fichier)
    vus = []

    def fabrique(parametres):
        vus.append(parametres)

        async def appel():
            return f"suivi de {parametres['job_id']}"

        return appel

    repris = file.reprendre_les_interrompus({"suivi": fabrique})

    assert vus == [{"job_id": "wan-42"}]
    assert len(repris) == 1
    await file.attendre(repris[0].identifiant)
    assert file.lire(repris[0].identifiant).resultat == "suivi de wan-42"
    # L'histoire ne se reecrit pas : l'ancien reste INTERROMPU.
    assert file.lire("t1").etat is EtatTravail.INTERROMPU


async def test_un_travail_sans_descripteur_ne_se_reprend_pas(fichier):
    """Il reste visible, avec sa raison. Inventer une reprise serait pire."""
    fichier.write_text(json.dumps({"travaux": [
        {"id": "t1", "nom": "conversion en lot", "etat": "RUNNING"}]}),
        encoding="utf-8")
    file = FileDeTravaux(fichier=fichier)

    assert file.reprendre_les_interrompus({"suivi": lambda p: _rien}) == []
    assert file.lire("t1").etat is EtatTravail.INTERROMPU
    assert file.lire("t1").reprenable is False
    # Et il reste LISTE : ne pas se reprendre n'est pas disparaitre.
    assert [t.identifiant for t in file.interrompus()] == ["t1"]


async def test_un_type_sans_fabrique_reste_interrompu(fichier):
    fichier.write_text(json.dumps({"travaux": [{
        "id": "t1", "nom": "x", "etat": "RUNNING",
        "descripteur": {"type": "type_inconnu", "parametres": {}},
    }]}), encoding="utf-8")
    file = FileDeTravaux(fichier=fichier)

    assert file.reprendre_les_interrompus({"suivi": lambda p: _rien}) == []
    assert file.lire("t1").etat is EtatTravail.INTERROMPU


async def test_une_fabrique_qui_leve_n_arrete_pas_les_autres(fichier):
    fichier.write_text(json.dumps({"travaux": [
        {"id": "casse", "nom": "a", "etat": "RUNNING",
         "descripteur": {"type": "casse", "parametres": {}}},
        {"id": "bon", "nom": "b", "etat": "RUNNING",
         "descripteur": {"type": "bon", "parametres": {}}},
    ]}), encoding="utf-8")
    file = FileDeTravaux(fichier=fichier)

    def qui_leve(parametres):
        raise ValueError("descripteur incomplet")

    repris = file.reprendre_les_interrompus(
        {"casse": qui_leve, "bon": lambda p: _rien})

    assert len(repris) == 1
    assert file.lire("casse").etat is EtatTravail.INTERROMPU


async def test_la_reprise_garde_la_cle_donc_ne_double_pas_un_travail_abouti(fichier):
    """Un travail interrompu dont la clé a DÉJÀ abouti ailleurs n'est pas rejoué."""
    fichier.write_text(json.dumps({"travaux": [
        {"id": "fini", "nom": "suivi", "etat": "DONE", "cle": "wan:42"},
        {"id": "coupe", "nom": "suivi", "etat": "RUNNING", "cle": "wan:42",
         "descripteur": {"type": "suivi", "parametres": {}}},
    ]}), encoding="utf-8")
    file = FileDeTravaux(fichier=fichier)
    appels = []

    def fabrique(parametres):
        async def appel():
            appels.append(1)
        return appel

    repris = file.reprendre_les_interrompus({"suivi": fabrique})

    assert [t.identifiant for t in repris] == ["fini"]
    assert appels == []


async def test_les_six_etats_sont_ceux_demandes():
    assert {e.value for e in EtatTravail} == {
        "PENDING", "RUNNING", "DONE", "FAILED", "CANCELLED", "PAUSED"}


# --- La clé d'un lot de conversion ------------------------------------------------

async def test_un_lot_identique_porte_la_meme_cle(fichier):
    """Deux fois la même demande de conversion, un seul travail.

    Sans cette clé, un double appui sur le bouton reconvertirait des fichiers
    déjà produits — avec le coût CPU et le risque d'écrasement que ça implique.
    """
    from core.actions.resultat import succes
    from core.production.conversion.lot import cle_du_lot, convertir_lot_en_fond

    assert cle_du_lot(["a.docx", "b.docx"], "pdf") == cle_du_lot(
        ["b.docx", "a.docx"], "pdf"), "l'ordre ne change pas la demande"
    assert cle_du_lot(["a.docx"], "pdf") != cle_du_lot(["a.docx"], "png")

    conversions = []

    def convertir_un(chemin, format_cible):
        conversions.append(chemin)
        return succes("convert", chemin, "converti", preuve=f"{chemin}.{format_cible}")

    file = FileDeTravaux(fichier=fichier)
    premier = convertir_lot_en_fond(convertir_un, file, ["a.docx"], "pdf")
    await file.attendre(premier.identifiant)
    second = convertir_lot_en_fond(convertir_un, file, ["a.docx"], "pdf")

    assert second.identifiant == premier.identifiant
    assert conversions == ["a.docx"], "le lot ne doit pas etre reconverti"


async def test_un_lot_interrompu_n_est_PAS_repris_tout_seul(fichier):
    """Il a déjà écrit des fichiers : le relancer au démarrage rejouerait des
    écritures dont personne n'a vérifié l'effet.

    Il reste `INTERROMPU`, visible sur `/api/travaux`, et c'est au propriétaire
    de le redemander. C'est une décision, pas un oubli.
    """
    from core.actions.resultat import succes
    from core.production.conversion.lot import convertir_lot_en_fond

    def convertir_un(chemin, format_cible):
        return succes("convert", chemin, "converti", preuve=f"{chemin}.{format_cible}")

    file = FileDeTravaux(fichier=fichier)
    travail = convertir_lot_en_fond(convertir_un, file, ["a.docx"], "pdf")

    assert travail.descripteur == {}, "un lot ne declare pas de reprise automatique"
    await file.attendre(travail.identifiant)
