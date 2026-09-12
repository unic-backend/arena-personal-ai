"""La recuperation : retrouver loin, sans grossir le prompt.

Deux tests portent la phase :
`test_le_projet_d_il_y_a_quatre_mois_est_retrouve` — la formulation exacte de la
specification — et `test_le_budget_n_est_jamais_depasse`, parce qu'une memoire
qui fait grossir chaque prompt finit par ne plus tenir dedans.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import (
    BUDGET_PAR_DEFAUT,
    MARQUE_SUPPOSITION,
    POIDS,
    fenetre_evoquee,
    formater,
    mots_utiles,
    normaliser,
    recuperer,
    rendre_ligne,
    taille,
)

MAINTENANT = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)


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


# --- Le test que la specification cite nommement ------------------------------

def test_le_projet_d_il_y_a_quatre_mois_est_retrouve(memoire, retenir):
    retenir("18 parois de 5,40 x 2,50 m pour le chantier Fast Group.",
            jours=120, projet="Fast Group", importance=0.8)
    retenir("Plafond BA13 de 40 m2 pose a Medina.", jours=3, projet="Medina")

    resultats = recuperer(memoire, "Continue le projet Fast Group d'il y a quatre mois",
                          maintenant=MAINTENANT)

    assert len(resultats) >= 1
    assert "Fast Group" in resultats[0].souvenir.contenu


def test_le_signal_temporel_se_declenche_pour_quatre_mois(memoire, retenir):
    ancien = retenir("Chantier Fast Group.", jours=120, projet="Fast Group")

    resultats = recuperer(memoire, "le projet d'il y a quatre mois", maintenant=MAINTENANT)

    trouve = [r for r in resultats if r.souvenir.identifiant == ancien.identifiant][0]
    assert trouve.signaux["temporel"] == 1.0


def test_un_souvenir_hors_de_la_fenetre_n_a_pas_le_bonus(memoire, retenir):
    recent = retenir("Chantier Fast Group hier.", jours=1, projet="Fast Group")

    resultats = recuperer(memoire, "Fast Group il y a quatre mois", maintenant=MAINTENANT)

    trouve = [r for r in resultats if r.souvenir.identifiant == recent.identifiant][0]
    assert trouve.signaux["temporel"] == 0.0


@pytest.mark.parametrize("expression,jours_attendus", [
    ("il y a quatre mois", 120), ("il y a 4 mois", 120),
    ("il y a deux semaines", 14), ("il y a 3 jours", 3), ("il y a un an", 365),
])
def test_les_formulations_de_temps_sont_comprises(expression, jours_attendus):
    debut, fin = fenetre_evoquee(expression, MAINTENANT)
    milieu = debut + (fin - debut) / 2

    assert abs((MAINTENANT - milieu).days - jours_attendus) <= 1


@pytest.mark.parametrize("expression", ["hier", "la semaine derniere", "le mois dernier"])
def test_les_raccourcis_de_temps_sont_compris(expression):
    assert fenetre_evoquee(expression, MAINTENANT) is not None


def test_une_question_sans_temps_n_a_pas_de_fenetre():
    assert fenetre_evoquee("quel est le tarif de pose ?", MAINTENANT) is None


def test_la_fenetre_est_large_pas_un_jour_precis():
    """Personne ne compte les jours en disant « il y a quatre mois »."""
    debut, fin = fenetre_evoquee("il y a quatre mois", MAINTENANT)

    assert (fin - debut).days > 60


# --- Le budget est une limite dure --------------------------------------------

def test_le_budget_n_est_jamais_depasse(memoire, retenir):
    for index in range(200):
        retenir(f"Chantier Fast Group, paroi numero {index}, "
                f"cloison fermee sur ses deux faces.", jours=index, projet="Fast Group")

    resultats = recuperer(memoire, "Fast Group cloison paroi", budget_caracteres=500,
                          maintenant=MAINTENANT)

    assert taille(resultats) <= 500
    assert len(resultats) > 0


@pytest.mark.parametrize("budget", [100, 300, 1000, 5000])
def test_le_budget_est_respecte_a_toutes_les_tailles(memoire, retenir, budget):
    for index in range(60):
        retenir(f"Chantier Fast Group, paroi {index}, cloison fermee deux faces.",
                jours=index, projet="Fast Group")

    assert taille(recuperer(memoire, "Fast Group cloison paroi",
                            budget_caracteres=budget, maintenant=MAINTENANT)) <= budget


def test_un_souvenir_trop_gros_n_est_pas_tronque(memoire, retenir):
    """Il n'est pas pris. Un souvenir coupe en deux ment sur ce qu'il dit."""
    retenir("Fast Group " + "cloison " * 200)

    resultats = recuperer(memoire, "Fast Group cloison", budget_caracteres=50,
                          maintenant=MAINTENANT)

    assert resultats == []


def test_les_plus_pertinents_passent_en_premier_dans_le_budget(memoire, retenir):
    """Budget calcule sur la ligne reelle : un chiffre en dur mesurerait le
    format, pas la priorite."""
    retenir("Fast Group : detail sans importance.", jours=1,
            projet="Fast Group", importance=0.1)
    essentiel = retenir("Fast Group : le tarif convenu est 5000 FCFA.", jours=1,
                        projet="Fast Group", importance=0.95)
    budget = len(rendre_ligne(essentiel)) + 1

    resultats = recuperer(memoire, "Fast Group tarif", budget_caracteres=budget,
                          maintenant=MAINTENANT)

    assert len(resultats) == 1
    assert "5000" in resultats[0].souvenir.contenu


def test_le_budget_par_defaut_est_borne():
    assert 0 < BUDGET_PAR_DEFAUT <= 4000


# --- La recence seule ne suffit pas -------------------------------------------

def test_un_souvenir_frais_sans_rapport_n_est_pas_rendu(memoire, retenir):
    """Sinon ARENA repondrait a tout avec ce qu'il vient d'apprendre."""
    retenir("Il a mange du thieboudienne ce midi.", jours=0, importance=0.9)

    assert recuperer(memoire, "quel est le tarif de pose ?", maintenant=MAINTENANT) == []


def test_une_question_sans_rapport_ne_rend_rien(memoire, retenir):
    retenir("18 parois pour Fast Group.", jours=10, projet="Fast Group")

    assert recuperer(memoire, "comment va la meteo a Dakar ?", maintenant=MAINTENANT) == []


def test_rien_de_pertinent_le_dit_au_lieu_de_bricoler(memoire, retenir):
    retenir("18 parois pour Fast Group.", jours=10)

    assert formater(recuperer(memoire, "la meteo", maintenant=MAINTENANT)) == \
        "Aucun souvenir pertinent."


def test_un_projet_demande_explicitement_suffit(memoire, retenir):
    """L'appelant qui nomme le projet a deja fait le lien."""
    retenir("Detail quelconque.", jours=5, projet="Fast Group")

    assert len(recuperer(memoire, "raconte", projet="Fast Group", maintenant=MAINTENANT)) == 1


# --- Chaque resultat dit pourquoi il est la -----------------------------------

def test_chaque_resultat_porte_ses_quatre_signaux(memoire, retenir):
    retenir("Le tarif de pose est 5000 FCFA.", jours=2, importance=0.9)

    resultat = recuperer(memoire, "tarif de pose", maintenant=MAINTENANT)[0]

    assert set(resultat.signaux) == set(POIDS)


def test_le_pourquoi_se_lit_en_une_ligne(memoire, retenir):
    retenir("Le tarif de pose est 5000 FCFA.", jours=2)

    pourquoi = recuperer(memoire, "tarif de pose", maintenant=MAINTENANT)[0].pourquoi()

    assert "score" in pourquoi and "correspondance" in pourquoi


def test_le_score_est_la_somme_ponderee_de_ses_signaux(memoire, retenir):
    retenir("Le tarif de pose est 5000 FCFA.", jours=2, importance=0.9)

    resultat = recuperer(memoire, "tarif de pose", maintenant=MAINTENANT)[0]
    attendu = sum(POIDS[nom] * valeur for nom, valeur in resultat.signaux.items())

    assert resultat.score == pytest.approx(attendu)


def test_les_poids_somment_a_un():
    assert sum(POIDS.values()) == pytest.approx(1.0)


# --- Une supposition reste marquee --------------------------------------------

def test_une_supposition_est_marquee_dans_le_prompt(memoire, retenir):
    retenir("Il prefere les montants de 70 mm.", jours=1, nature=Nature.INFERENCE)

    rendu = formater(recuperer(memoire, "montants 70 mm", maintenant=MAINTENANT))

    assert MARQUE_SUPPOSITION in rendu


def test_un_fait_n_est_pas_marque_comme_supposition(memoire, retenir):
    retenir("Le tarif de pose est 5000 FCFA.", jours=1)

    rendu = formater(recuperer(memoire, "tarif de pose", maintenant=MAINTENANT))

    assert MARQUE_SUPPOSITION not in rendu


def test_chaque_ligne_porte_sa_source(memoire, retenir):
    retenir("Le tarif de pose est 5000 FCFA.", jours=1, source="devis UC-2026-0804-FG2")

    rendu = formater(recuperer(memoire, "tarif de pose", maintenant=MAINTENANT))

    assert "UC-2026-0804-FG2" in rendu


def test_le_projet_apparait_dans_la_ligne(memoire, retenir):
    souvenir = retenir("18 parois.", projet="Fast Group")

    assert "[Fast Group]" in rendre_ligne(souvenir)


# --- Les perimes ne reviennent pas par cette porte ----------------------------

def test_un_contexte_perime_n_est_pas_recupere(memoire):
    memoire.retenir("Il est sur le chantier de Medina aujourd'hui.",
                    TypeSouvenir.EPISODIQUE, Nature.CONTEXTE_TEMPORAIRE,
                    source="il l'a dit", duree_heures=0)

    assert recuperer(memoire, "chantier Medina", maintenant=MAINTENANT) == []


def test_un_contexte_valide_est_recupere(memoire):
    memoire.retenir("Il est sur le chantier de Medina aujourd'hui.",
                    TypeSouvenir.EPISODIQUE, Nature.CONTEXTE_TEMPORAIRE,
                    source="il l'a dit", duree_heures=12)

    assert len(recuperer(memoire, "chantier Medina")) == 1


# --- Normalisation -------------------------------------------------------------

def test_les_accents_ne_separent_pas_les_mots():
    assert normaliser("Médina") == normaliser("medina") == "medina"


def test_une_question_accentuee_retrouve_un_souvenir_sans_accent(memoire, retenir):
    retenir("Chantier a Medina, plafond BA13.", jours=2)

    assert len(recuperer(memoire, "le chantier de Médina", maintenant=MAINTENANT)) == 1


def test_les_mots_vides_ne_comptent_pas():
    assert mots_utiles("le tarif de la pose") == {"tarif", "pose"}


def test_m2_est_un_mot_utile():
    """« m2 » est dans presque toutes ses phrases : le couper rendait
    « combien de m2 » aveugle a ses propres devis."""
    assert mots_utiles("il a un m2") == {"m2"}


def test_les_lettres_isolees_ne_comptent_pas():
    assert mots_utiles("l a d m") == set()


# --- Filtres -------------------------------------------------------------------

def test_le_filtre_par_type_est_applique(memoire, retenir):
    retenir("Un devis se numerote UC-AAAA-MMJJ.", type=TypeSouvenir.PROCEDURALE)
    retenir("Un devis a ete envoye a Fast Group.", type=TypeSouvenir.EPISODIQUE)

    resultats = recuperer(memoire, "devis", type=TypeSouvenir.PROCEDURALE,
                          maintenant=MAINTENANT)

    assert len(resultats) == 1
    assert resultats[0].souvenir.type is TypeSouvenir.PROCEDURALE


def test_le_filtre_par_projet_est_applique(memoire, retenir):
    retenir("Cloison posee.", projet="Fast Group")
    retenir("Cloison posee.", projet="Medina")

    resultats = recuperer(memoire, "cloison", projet="Medina", maintenant=MAINTENANT)

    assert [r.souvenir.projet for r in resultats] == ["Medina"]


# --- Au-dela de la fenetre importance/recence -----------------------------------
# Avant ce correctif (audit externe, commit f7f0478) : `recuperer()` n'examinait
# QUE les 500 souvenirs les plus importants/recents (`souvenirs(limite=500)`,
# la fenetre de `MemoirePersonnelle.souvenirs`). Un souvenir pertinent mais peu
# important et ancien, au-dela de cette fenetre, n'etait jamais meme NOTE par
# `noter()` — quel que soit son score potentiel, il ne concourait pas.

def _remplir_la_fenetre(retenir, effectif=520):
    """Occupe la fenetre importance/recence avec des souvenirs SANS RAPPORT
    avec la question posee ensuite — jamais le mot cherche."""
    for index in range(effectif):
        retenir(f"Chantier ordinaire numero {index}, cloison BA13 standard.",
               jours=0, importance=0.9)


def test_un_souvenir_hors_fenetre_mais_pertinent_est_desormais_trouve(memoire, retenir):
    _remplir_la_fenetre(retenir)
    # Hors de la fenetre par construction : peu important ET ancien, donc
    # classe bien apres les 520 remplissages par
    # `ORDER BY importance DESC, cree_le DESC`.
    retenir("Le motif GIRAFETURQUOISE identifie le chantier de reference.",
           jours=800, importance=0.02)

    resultats = recuperer(memoire, "girafeturquoise", maintenant=MAINTENANT)

    contenus = [r.souvenir.contenu for r in resultats]
    assert any("GIRAFETURQUOISE" in c for c in contenus), (
        "le souvenir pertinent, hors de la fenetre des 500, n'a pas ete trouve")


def test_un_souvenir_hors_fenetre_sans_rapport_reste_absent(memoire, retenir):
    """Le complement ne fait pas remonter n'importe quoi : sans mot commun
    avec la question, un souvenir hors fenetre reste hors de la reponse,
    exactement comme un souvenir DANS la fenetre sans rapport."""
    _remplir_la_fenetre(retenir)
    retenir("Un souvenir totalement sans rapport, invente pour ce test.",
           jours=800, importance=0.02)

    resultats = recuperer(memoire, "girafeturquoise", maintenant=MAINTENANT)

    assert resultats == []


def test_un_souvenir_hors_fenetre_mais_perime_reste_absent(memoire, retenir):
    """L'expiration reste respectee meme pour le chemin complementaire.

    `duree_heures` calcule `expire_le` par rapport a l'heure REELLE de
    creation (pas `MAINTENANT`, une date fixee pour le test) : il faut donc
    forcer directement une echeance passee, comme `retenir` (fixture
    ci-dessus) force deja `cree_le` par SQL direct."""
    _remplir_la_fenetre(retenir)
    souvenir = retenir("Le motif GIRAFETURQUOISE marque un contexte temporaire.",
                       jours=800, importance=0.02)
    with sqlite3.connect(memoire.db_path) as connexion:
        connexion.execute("UPDATE souvenirs SET expire_le = ? WHERE identifiant = ?",
                          ("2020-01-01T00:00:00+00:00", souvenir.identifiant))

    resultats = recuperer(memoire, "girafeturquoise", maintenant=MAINTENANT)

    assert resultats == []


def test_un_souvenir_hors_fenetre_reste_dans_le_budget(memoire, retenir):
    """La fusion des deux fenetres ne casse pas la garantie de budget."""
    _remplir_la_fenetre(retenir)
    retenir("Le motif GIRAFETURQUOISE identifie le chantier de reference, "
           "avec beaucoup de details superflus pour allonger ce souvenir "
           "bien au-dela de ce qu'un tout petit budget pourrait contenir.",
           jours=800, importance=0.02)

    resultats = recuperer(memoire, "girafeturquoise", budget_caracteres=30,
                          maintenant=MAINTENANT)

    assert taille(resultats) <= 30


def test_un_souvenir_sensible_hors_fenetre_reste_hors_de_portee(memoire, retenir, tmp_path):
    """Limite reelle, pas une regression : le contenu chiffre ne peut pas
    etre retrouve par un `LIKE` — documente, jamais contourne en silence."""
    from core.memory.chiffrement import Coffre

    memoire.coffre = Coffre(passphrase="phrase-de-test-suffisamment-longue")
    _remplir_la_fenetre(retenir)
    memoire.retenir(
        contenu="Le motif GIRAFETURQUOISE identifie un chantier sensible.",
        type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
        source="devis confidentiel", importance=0.02, sensible=True,
    )

    resultats = recuperer(memoire, "girafeturquoise", maintenant=MAINTENANT)

    assert resultats == [], (
        "un souvenir sensible a ete trouve par mot-cle : son contenu chiffre "
        "ne devrait jamais correspondre a un LIKE en clair")


def test_limite_reelle_un_mot_partage_par_trop_de_souvenirs_peut_encore_manquer(
    memoire, retenir,
):
    """Mesuree, pas cachee : le complement (`souvenirs_correspondant_a_des_mots`)
    est LUI AUSSI borne a `limite_lecture`. Si plus de 500 AUTRES souvenirs
    partagent le mot cherche, et sont tous plus importants ou plus recents,
    le souvenir cible peut encore rester hors de portee — la meme classe de
    limite qu'avant, juste repoussee, jamais pretendue resolue en toutes
    circonstances. Un mot RARE (les tests ci-dessus) n'a pas ce probleme ;
    un mot tres commun peut l'avoir encore."""
    for index in range(520):
        retenir(f"Chantier {index}, une phrase ordinaire.", jours=0, importance=0.9)
    retenir("Chantier tres particulier, mais peu important et ancien.",
           jours=800, importance=0.01)

    resultats = recuperer(memoire, "chantier particulier tres", maintenant=MAINTENANT)

    contenus = [r.souvenir.contenu for r in resultats]
    assert not any("peu important et ancien" in c for c in contenus), (
        "cette limite documentee n'est plus reproduite : soit elle a ete "
        "resolue (mettre a jour ce test et sa documentation), soit ce test "
        "est devenu faux pour une autre raison")


# --- Vitesse -------------------------------------------------------------------

def test_la_recuperation_reste_rapide_sur_mille_souvenirs(memoire, retenir):
    """« Memory must scale without making responses slow. » Mesure, pas suppose."""
    import time

    for index in range(1000):
        retenir(f"Chantier {index}, cloison BA13, paroi fermee deux faces.", jours=index % 400)

    debut = time.perf_counter()
    resultats = recuperer(memoire, "cloison BA13 paroi", maintenant=MAINTENANT)
    ecoule = time.perf_counter() - debut

    assert resultats != []
    assert ecoule < 0.5, f"recuperation trop lente : {ecoule:.3f} s"
