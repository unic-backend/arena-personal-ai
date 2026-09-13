"""La memoire se contredit — et elle le dit, sans jamais trancher.

Ce que ces tests tiennent, dans l'ordre ou une erreur couterait cher :

1. **Rien n'est arbitre.** La tentation naturelle, en trouvant deux tarifs, est
   de garder le plus recent. Ce serait choisir un prix a la place du
   proprietaire, et un mauvais prix choisi par ARENA est indiscernable du bon
   tant qu'une facture n'arrive pas. Plusieurs tests ne verifient que cela.
2. **Aucun faux conflit.** Un detecteur qui crie a chaque journee de chantier
   serait desactive en une semaine, et la vraie contradiction passerait avec.
3. **La portee est dite a chaque appel.** « 0 contradiction » sans elle se lit
   « la memoire est coherente », ce qui n'a pas ete mesure.
"""
import pytest

from core.memory.chiffrement import Coffre
from core.memory.contradiction import (
    PORTEE,
    SUJET_MINIMUM,
    TYPES_COMPARABLES,
    contradictions,
    nombres,
    rapport,
)
from core.memory.personnelle import Etat, MemoirePersonnelle, Nature, TypeSouvenir


@pytest.fixture
def memoire(tmp_path):
    """Une memoire vide, sur disque, comme en service."""
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


def retenir(memoire, contenu, type=TypeSouvenir.SEMANTIQUE, nature=Nature.FAIT,
            projet=None, **reste):
    """Raccourci : la source est obligatoire partout, elle ne varie pas ici."""
    return memoire.retenir(contenu, type, nature, source="proprietaire",
                           projet=projet, **reste)


# --------------------------------------------------------------------------
# Ce qui EST une contradiction
# --------------------------------------------------------------------------

def test_deux_tarifs_differents_pour_le_meme_poste_se_voient(memoire):
    """Le cas qui a motive le module : deux prix, cote a cote, tous deux actifs."""
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le tarif de pose est 5500 F/m2.")

    trouvees = contradictions(memoire)

    assert len(trouvees) == 1
    assert set(trouvees[0].valeurs[0]) != set(trouvees[0].valeurs[1])
    assert "tarif" in trouvees[0].sujet


def test_la_raison_ne_nomme_que_ce_qui_differe(memoire):
    """« 5500 contre 5000 », pas « 5500, 2 contre 5000, 2 ».

    Le `2` vient de `m2` et il est present des deux cotes : le citer ferait
    chercher au proprietaire un changement dans un nombre qui n'a pas bouge.
    """
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le tarif de pose est 5500 F/m2.")

    raison = contradictions(memoire)[0].raison

    assert "5000" in raison and "5500" in raison
    assert "5500, 2" not in raison and "5000, 2" not in raison


def test_une_decision_peut_en_contredire_une_autre(memoire):
    """`DECISION` est l'un des trois types comparables, et c'est voulu :
    deux decisions incompatibles sur le meme sujet est exactement ce qu'il
    faut remonter avant d'en appliquer une."""
    retenir(memoire, "Le delai de paiement accorde a Fast Group est 30 jours.",
            type=TypeSouvenir.DECISION)
    retenir(memoire, "Le delai de paiement accorde a Fast Group est 45 jours.",
            type=TypeSouvenir.DECISION)

    assert len(contradictions(memoire)) == 1


def test_une_inference_qui_contredit_un_fait_est_remontee(memoire):
    """Le cas le plus utile : ARENA a deduit un chiffre que le proprietaire
    dement. Les deux natures voyagent dans le rapport pour qu'il le voie."""
    retenir(memoire, "La surface du chantier Medina est 240 m2.", nature=Nature.FAIT)
    retenir(memoire, "La surface du chantier Medina est 260 m2.", nature=Nature.INFERENCE)

    trouvee = contradictions(memoire)[0]
    natures = {trouvee.a.nature, trouvee.b.nature}

    assert natures == {Nature.FAIT, Nature.INFERENCE}


# --------------------------------------------------------------------------
# Ce qui n'en est PAS — chaque exclusion vaut un test
# --------------------------------------------------------------------------

def test_deux_journees_de_chantier_ne_se_contredisent_pas(memoire):
    """L'exclusion qui empeche le detecteur d'etre desactive en une semaine.

    « Le 4 aout, 18 parois » et « le 5 aout, 20 parois » partagent leur sujet
    et different par leurs nombres : ce sont deux journees, pas un conflit.
    """
    retenir(memoire, "Le 4 aout, 18 parois posees.", type=TypeSouvenir.EPISODIQUE)
    retenir(memoire, "Le 5 aout, 20 parois posees.", type=TypeSouvenir.EPISODIQUE)

    assert contradictions(memoire) == []


def test_deux_projets_differents_ne_se_comparent_jamais(memoire):
    """Deux tarifs pour deux chantiers sont deux tarifs."""
    retenir(memoire, "Le tarif de pose est 5000 F/m2.", projet="Medina")
    retenir(memoire, "Le tarif de pose est 6000 F/m2.", projet="Ngor")

    assert contradictions(memoire) == []


def test_un_contexte_temporaire_ne_contredit_rien(memoire):
    """Il est defini comme « vrai maintenant, faux bientot » : deux valeurs
    successives sont son fonctionnement normal, pas une incoherence."""
    retenir(memoire, "Il reste 12 sacs d'enduit.", nature=Nature.CONTEXTE_TEMPORAIRE)
    retenir(memoire, "Il reste 8 sacs d'enduit.", nature=Nature.CONTEXTE_TEMPORAIRE)

    assert contradictions(memoire) == []


def test_un_souvenir_rejete_ne_contredit_plus_rien(memoire):
    """Le proprietaire a deja dit non : le conflit est tranche, pas ouvert."""
    faux = retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le tarif de pose est 5500 F/m2.")
    memoire.rejeter(faux.identifiant, source="proprietaire")

    assert contradictions(memoire) == []


def test_un_souvenir_archive_ne_contredit_plus_rien(memoire):
    ancien = retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le tarif de pose est 5500 F/m2.")
    memoire.archiver(ancien.identifiant, source="proprietaire")

    assert contradictions(memoire) == []
    assert memoire.lire(ancien.identifiant).etat is Etat.ARCHIVE, (
        "archiver n'efface pas : le souvenir reste lisible pour l'audit"
    )


def test_un_seul_mot_partage_ne_fait_pas_un_sujet(memoire):
    """A `SUJET_MINIMUM = 1`, le tarif du gypse contredirait celui de la
    main-d'oeuvre au seul motif que les deux phrases disent « tarif »."""
    assert SUJET_MINIMUM >= 2
    retenir(memoire, "Le tarif gypse est 3000.")
    retenir(memoire, "Un echafaudage monte en 2 heures.")

    assert contradictions(memoire) == []


def test_le_meme_nombre_ecrit_autrement_n_est_pas_un_conflit(memoire):
    """« 5 000 » et « 5000 » sont le meme nombre. Sans la normalisation, une
    phrase se contredirait avec sa propre reecriture."""
    retenir(memoire, "Le tarif de pose est 5 000 F/m2.")
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")

    assert contradictions(memoire) == []


def test_un_souvenir_sans_nombre_ne_contredit_rien(memoire):
    """La portee est numerique et elle est tenue : deux phrases sans chiffre
    ne produisent pas de verdict, meme si elles s'opposent au sens."""
    retenir(memoire, "On travaille avec Fast Group.")
    retenir(memoire, "On ne travaille plus avec Fast Group.")

    assert contradictions(memoire) == [], (
        "La negation n'est PAS detectee, et PORTEE le declare : "
        "un test qui pretendrait le contraire ferait croire a une garantie."
    )


def test_un_souvenir_ne_se_contredit_jamais_lui_meme(memoire):
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")

    assert contradictions(memoire) == []


def test_un_souvenir_sensible_illisible_est_ignore(tmp_path):
    """Comparer un message d'echec de dechiffrement fabriquerait un conflit
    avec le coffre, pas avec un souvenir."""
    chemin = str(tmp_path / "memoire.db")
    memoire = MemoirePersonnelle(
        db_path=chemin, coffre=Coffre("phrase-de-test-vraiment-longue",
                                      chemin_sel=tmp_path / "vault_salt"))
    retenir(memoire, "Le tarif de pose est 5000 F/m2.", sensible=True)
    retenir(memoire, "Le tarif de pose est 5500 F/m2.")

    # Meme base, coffre qui ne sait pas lire ce qui a ete ecrit.
    aveugle = MemoirePersonnelle(
        db_path=chemin, coffre=Coffre("une-tout-autre-phrase-bien-longue",
                                      chemin_sel=tmp_path / "autre_sel"))

    assert contradictions(aveugle) == []


# --------------------------------------------------------------------------
# Rien n'est arbitre — la garantie centrale
# --------------------------------------------------------------------------

def test_aucun_des_deux_n_est_designe_comme_le_bon(memoire):
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le tarif de pose est 5500 F/m2.")

    rendu = contradictions(memoire)[0].to_dict()

    assert rendu["resolue_par"] is None
    assert len(rendu["souvenirs"]) == 2
    # Les deux sont rendus ENTIERS : source, nature et date sont ce qui permet
    # au proprietaire de trancher.
    for souvenir in rendu["souvenirs"]:
        assert souvenir["source"] and souvenir["nature"] and souvenir["cree_le"]


def test_detecter_ne_modifie_rien_dans_la_memoire(memoire):
    """Le test qui tiendrait si quelqu'un ajoutait « et on garde le plus
    recent » : apres detection, les deux souvenirs sont inchanges."""
    a = retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    b = retenir(memoire, "Le tarif de pose est 5500 F/m2.")
    avant = (memoire.lire(a.identifiant).to_dict(), memoire.lire(b.identifiant).to_dict())

    contradictions(memoire)
    rapport(memoire)

    apres = (memoire.lire(a.identifiant).to_dict(), memoire.lire(b.identifiant).to_dict())
    assert apres == avant
    assert len(memoire.souvenirs()) == 2


def test_le_module_n_expose_aucun_resolveur():
    """Structurel, et il vaut son cout : la fonction de confort « resoudre »
    est ce qu'on ajoute six mois plus tard, en croyant rendre service."""
    import core.memory.contradiction as module

    publiques = {nom for nom in dir(module) if not nom.startswith("_")}
    interdits = {"resoudre", "arbitrer", "trancher", "choisir", "garder_le_plus_recent"}

    assert publiques & interdits == set()


# --------------------------------------------------------------------------
# La portee accompagne toujours le resultat
# --------------------------------------------------------------------------

def test_le_rapport_porte_sa_portee_meme_a_zero(memoire):
    """« 0 contradiction » sans la portee se lit « la memoire est coherente »."""
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")

    rendu = rapport(memoire)

    assert rendu["total"] == 0
    assert rendu["portee"] == PORTEE
    assert "negation" in rendu["portee"].lower()
    assert "coherente" in rendu["note"]


def test_le_rapport_compte_ce_qu_il_a_reellement_examine(memoire):
    """Un rapport qui compte les souvenirs ecartes ferait croire a une
    couverture qu'il n'a pas."""
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le 4 aout, 18 parois posees.", type=TypeSouvenir.EPISODIQUE)

    assert rapport(memoire)["souvenirs_examines"] == 1


def test_les_types_comparables_sont_ceux_qui_affirment_une_generalite():
    """Le contrat, ecrit : ni episode, ni tache, ni erreur."""
    assert TYPES_COMPARABLES == frozenset({
        TypeSouvenir.SEMANTIQUE, TypeSouvenir.PROCEDURALE, TypeSouvenir.DECISION,
    })


# --------------------------------------------------------------------------
# La normalisation des nombres
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texte, attendu", [
    ("5000", ("5000",)),
    ("5 000", ("5000",)),
    ("5.000", ("5000",)),
    ("5,50", ("5.5",)),
    ("007", ("7",)),
    ("0", ("0",)),
    ("aucun chiffre ici", ()),
    ("UC-2026-0812", ("2026", "812")),
])
def test_la_normalisation_des_nombres(texte, attendu):
    assert nombres(texte) == attendu
