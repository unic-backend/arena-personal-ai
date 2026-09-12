"""La recuperation semantique : retrouver ce qui est dit autrement.

Deux tests portent la phase. `test_le_souvenir_sans_mot_commun_remonte_par_le_sens`
est la raison d'exister du module — le lexical seul rate « combien de panneaux »
quand le souvenir dit « plaques BA13 ». Et
`test_sans_embeddings_le_mode_reste_lexical_et_le_dit` est la regle du depot :
une capacite absente se rapporte, elle ne se simule pas.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import recuperer
from core.memory.semantique import (
    ETAT_REPONSE_INVALIDE,
    ETAT_SERVEUR_ABSENT,
    MODE_LEXICAL,
    MODE_SEMANTIQUE,
    SEUIL_SEMANTIQUE,
    IndexSemantique,
    cosinus,
    mesurer,
    recuperer_semantique,
)

MAINTENANT = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

QUESTION = "Combien de panneaux ai-je pris pour ce chantier ?"
PROCHE = "234 plaques BA13 commandees pour Fast Group."
ETRANGER = "Rendez-vous chez le dentiste mardi."

#: Vecteurs de test, en quatre dimensions. La question et le souvenir proche
#: pointent presque dans la meme direction ; l'etranger est orthogonal.
VECTEURS = {
    QUESTION: [0.0, 0.90, 0.10, 0.0],
    PROCHE: [0.0, 0.95, 0.05, 0.0],
    ETRANGER: [0.0, 0.0, 0.0, 1.0],
}
AUTRE = [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def memoire(tmp_path):
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


@pytest.fixture
def retenir(memoire):
    """Retient un souvenir et lui donne l'age demande."""
    def _retenir(contenu, jours=0, **remplacements):
        valeurs = {
            "type": TypeSouvenir.EPISODIQUE, "nature": Nature.FAIT,
            "source": "devis UC-2026-0804-FG2",
        }
        valeurs.update(remplacements)
        souvenir = memoire.retenir(contenu=contenu, **valeurs)
        date = (MAINTENANT - timedelta(days=jours)).isoformat(timespec="seconds")
        with sqlite3.connect(memoire.db_path) as connexion:
            connexion.execute("UPDATE souvenirs SET cree_le = ? WHERE identifiant = ?",
                              (date, souvenir.identifiant))
        return memoire.lire(souvenir.identifiant)
    return _retenir


def fournisseur_de_test(textes):
    """Un fournisseur qui rend des vecteurs connus, sans serveur ni reseau."""
    async def _fournir(demandes):
        textes.extend(demandes)
        return [VECTEURS.get(texte, AUTRE) for texte in demandes]
    return _fournir


def index_de_test():
    return IndexSemantique(fournisseur=fournisseur_de_test([]))


# --- Le test qui justifie la phase ---------------------------------------------

async def test_le_souvenir_sans_mot_commun_remonte_par_le_sens(memoire, retenir):
    retenir(PROCHE, jours=40, importance=0.7)
    retenir(ETRANGER, jours=1)

    lexical = recuperer(memoire, QUESTION, maintenant=MAINTENANT)
    assert lexical == [], "le lexical doit rater ce souvenir, sinon le test ne prouve rien"

    trouve = await recuperer_semantique(
        memoire, QUESTION, index=index_de_test(), maintenant=MAINTENANT)

    assert trouve.mode == MODE_SEMANTIQUE
    contenus = [resultat.souvenir.contenu for resultat in trouve.resultats]
    assert PROCHE in contenus


async def test_un_souvenir_etranger_ne_remonte_pas(memoire, retenir):
    retenir(ETRANGER, jours=0, importance=0.9)

    trouve = await recuperer_semantique(
        memoire, QUESTION, index=index_de_test(), maintenant=MAINTENANT)

    assert [resultat.souvenir.contenu for resultat in trouve.resultats] == []


async def test_une_proximite_au_niveau_du_bruit_ne_fait_pas_remonter(memoire, retenir):
    """0,40 est le niveau mesure des souvenirs sans rapport avec bge-m3.

    Sous le seuil, un souvenir muet reste ou il est, meme tres important et tout
    frais. Ce test garde le seuil : le baisser fait echouer ici, pas en production.
    """
    bruit = "Facture electricite de juillet."
    retenir(bruit, jours=0, importance=0.9)

    vecteurs = {QUESTION: [0.0, 0.90, 0.10, 0.0], bruit: [0.0, 0.40, 0.0, 0.90]}

    async def fournir(demandes):
        return [vecteurs.get(texte, AUTRE) for texte in demandes]

    proximite = cosinus(vecteurs[QUESTION], vecteurs[bruit])
    assert 0.39 < proximite < SEUIL_SEMANTIQUE, "le cas doit tomber juste sous le seuil"

    trouve = await recuperer_semantique(
        memoire, QUESTION, index=IndexSemantique(fournisseur=fournir), maintenant=MAINTENANT)

    assert trouve.resultats == []


# --- La capacite se mesure ------------------------------------------------------

async def test_sans_embeddings_le_mode_reste_lexical_et_le_dit(memoire, retenir):
    retenir("18 parois pour le chantier Fast Group.", jours=10, projet="Fast Group")

    async def rien(_demandes):
        return []

    trouve = await recuperer_semantique(
        memoire, "Continue le chantier Fast Group",
        index=IndexSemantique(fournisseur=rien), maintenant=MAINTENANT)

    assert trouve.mode == MODE_LEXICAL
    assert trouve.etat.disponible is False
    assert trouve.etat.etat == ETAT_SERVEUR_ABSENT
    attendu = recuperer(memoire, "Continue le chantier Fast Group", maintenant=MAINTENANT)
    assert trouve.resultats == attendu


async def test_un_vecteur_trop_court_n_est_pas_une_capacite():
    async def minuscule(demandes):
        return [[0.5] for _ in demandes]

    etat = await mesurer(minuscule)

    assert etat.disponible is False
    assert etat.etat == ETAT_REPONSE_INVALIDE
    assert etat.dimension is None


async def test_mesurer_rapporte_la_dimension_obtenue():
    etat = await mesurer(fournisseur_de_test([]))

    assert etat.disponible is True
    assert etat.dimension == 4


# --- Le budget et le cache ------------------------------------------------------

async def test_le_budget_n_est_jamais_depasse(memoire, retenir):
    for _ in range(5):
        retenir(PROCHE, jours=5, importance=0.6)

    trouve = await recuperer_semantique(
        memoire, QUESTION, index=index_de_test(), budget_caracteres=120,
        maintenant=MAINTENANT)

    from core.memory.recuperation import taille
    assert taille(trouve.resultats) <= 120
    assert trouve.resultats, "un budget serre garde le meilleur, il ne rend pas vide"


async def test_le_cache_ne_redemande_pas_un_texte_connu():
    demandes = []
    index = IndexSemantique(fournisseur=fournisseur_de_test(demandes))

    await index.vecteurs([QUESTION, PROCHE])
    await index.vecteurs([QUESTION, PROCHE])

    assert index.appels == 1
    assert demandes.count(PROCHE) == 1


def test_deux_vecteurs_de_dimensions_differentes_ne_se_comparent_pas():
    assert cosinus([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


# --- Au-dela de la fenetre importance/recence -----------------------------------
# Meme defaut que cote lexical (audit externe, commit f7f0478) : `candidats =
# memoire.souvenirs(limite=limite_lecture)` ne vectorisait QUE la fenetre
# importance/recence — un souvenir hors de cette fenetre n'etait jamais meme
# soumis a Ollama, quel que soit le sens qu'il aurait pu partager avec la
# question.

async def test_un_souvenir_hors_fenetre_est_desormais_vectorise_et_trouve(memoire, retenir):
    for index in range(520):
        retenir(f"Chantier ordinaire numero {index}, sans lien avec la question.",
               jours=0, importance=0.9)
    # Hors fenetre par construction (peu important, ancien) — MAIS partage un
    # mot DISTINCTIF avec la question (aucun autre souvenir ne le porte), donc
    # le filtre SQL complementaire (`souvenirs_correspondant_a_des_mots`) le
    # retrouve et le soumet a la vectorisation, meme sans entree dans
    # VECTEURS (-> AUTRE, orthogonal a QUESTION : seule la correspondance
    # lexicale le fait remonter ici, pas le sens — ce test verifie qu'il est
    # EXAMINE, pas qu'il gagne par le sens).
    #
    # Un mot COMMUN aux 520 souvenirs de remplissage (comme "chantier") ne
    # suffirait pas : le filtre complementaire est LUI AUSSI borne
    # (`limite_lecture`), et 520 correspondances sur un mot banal
    # rempliraient a nouveau cette fenetre avant le souvenir cible — limite
    # reelle et mesuree, documentee dans `souvenirs_correspondant_a_des_mots`,
    # pas contournee ici par un mot qui la masquerait.
    retenir("Ce souvenir GIRAFETURQUOISE reclame une attention particuliere.",
           jours=800, importance=0.02)

    trouve = await recuperer_semantique(
        memoire, "girafeturquoise particuliere",
        index=index_de_test(), maintenant=MAINTENANT)

    contenus = [resultat.souvenir.contenu for resultat in trouve.resultats]
    assert any("GIRAFETURQUOISE" in c for c in contenus), (
        "le souvenir hors fenetre, mais lexicalement lie a la question, "
        "n'a jamais ete vectorise ni retrouve")
    assert cosinus([], []) == 0.0
