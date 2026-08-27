"""La memoire personnelle : quatre regles, et une migration qui n'efface rien.

Le test qui compte le plus est `test_une_inference_ne_devient_pas_un_fait_toute_seule` :
c'est la facon la plus discrete de fabriquer un mensonge durable, et la
specification l'interdit nommement.
"""
from datetime import datetime, timedelta

import pytest

from core.actions.journal import MASQUE
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import (
    IMPORTANCE_PAR_DEFAUT,
    MemoirePersonnelle,
    Nature,
    Souvenir,
    TypeSouvenir,
)


@pytest.fixture
def memoire(tmp_path):
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


def _retenir(memoire, **remplacements):
    valeurs = {
        "contenu": "Le tarif de pose est 5000 FCFA le m2 developpe.",
        "type": TypeSouvenir.SEMANTIQUE,
        "nature": Nature.FAIT,
        "source": "devis UC-2026-0804-FG2",
    }
    valeurs.update(remplacements)
    return memoire.retenir(**valeurs)


# --- 1. Une supposition ne devient jamais un fait toute seule -----------------

def test_une_inference_ne_devient_pas_un_fait_toute_seule(memoire):
    souvenir = _retenir(memoire, nature=Nature.INFERENCE,
                        contenu="Il prefere sans doute les cloisons en 70 mm.")

    relu = memoire.lire(souvenir.identifiant)

    assert relu.nature is Nature.INFERENCE
    assert relu.est_une_supposition is True


def test_relire_cent_fois_une_inference_ne_la_promeut_pas(memoire):
    souvenir = _retenir(memoire, nature=Nature.INFERENCE, contenu="Sans doute 70 mm.")

    for _ in range(100):
        memoire.lire(souvenir.identifiant)
        memoire.souvenirs()

    assert memoire.lire(souvenir.identifiant).nature is Nature.INFERENCE


def test_confirmer_est_le_seul_chemin_vers_le_fait(memoire):
    souvenir = _retenir(memoire, nature=Nature.INFERENCE, contenu="Sans doute 70 mm.")

    confirme = memoire.confirmer(souvenir.identifiant, source="le proprietaire, 2026-08-27")

    assert confirme.nature is Nature.FAIT
    assert "le proprietaire" in confirme.source


def test_confirmer_sans_source_est_refuse(memoire):
    souvenir = _retenir(memoire, nature=Nature.INFERENCE)

    with pytest.raises(ValueError, match="sur la foi de rien"):
        memoire.confirmer(souvenir.identifiant, source="   ")


def test_confirmer_conserve_la_source_d_origine(memoire):
    """On doit pouvoir remonter a ce qui avait fait naitre la supposition."""
    souvenir = _retenir(memoire, nature=Nature.INFERENCE, source="deduit de 3 devis")

    confirme = memoire.confirmer(souvenir.identifiant, source="le proprietaire")

    assert "deduit de 3 devis" in confirme.source


@pytest.mark.parametrize("nature", [Nature.PREFERENCE, Nature.CONTEXTE_TEMPORAIRE])
def test_confirmer_ne_transforme_pas_les_autres_natures_en_fait(memoire, nature):
    """Une preference confirmee reste une preference : elle peut changer sans etre fausse."""
    souvenir = _retenir(memoire, nature=nature, contenu="Il aime les devis courts.")

    confirme = memoire.confirmer(souvenir.identifiant, source="le proprietaire")

    assert confirme.nature is nature


def test_confirmer_un_souvenir_inconnu_rend_none(memoire):
    assert memoire.confirmer("jamais-ecrit", source="le proprietaire") is None


def test_les_quatre_natures_de_la_specification_existent():
    assert {n.value for n in Nature} == {
        "FACT", "PREFERENCE", "INFERENCE", "TEMPORARY_CONTEXT",
    }


def test_on_peut_lire_uniquement_les_faits(memoire):
    _retenir(memoire, nature=Nature.FAIT, contenu="Tarif 5000.")
    _retenir(memoire, nature=Nature.INFERENCE, contenu="Sans doute 70 mm.")

    faits = memoire.souvenirs(nature=Nature.FAIT)

    assert [s.contenu for s in faits] == ["Tarif 5000."]


# --- 2. Rien n'entre sans source ---------------------------------------------

@pytest.mark.parametrize("source", ["", "   ", None])
def test_un_souvenir_sans_source_est_refuse(memoire, source):
    with pytest.raises(ValueError, match="sans auteur"):
        _retenir(memoire, source=source)


def test_un_souvenir_vide_est_refuse(memoire):
    with pytest.raises(ValueError, match="n'est pas un souvenir"):
        _retenir(memoire, contenu="   ")


def test_une_entite_sans_source_est_refusee(memoire):
    with pytest.raises(ValueError, match="confirmee par personne"):
        memoire.enregistrer_entite(nom="Fast Group", type="client", source="")


def test_une_relation_sans_source_est_refusee(memoire):
    with pytest.raises(ValueError, match="supposition sur un lien"):
        memoire.relier("Fast Group", "chantier", "Medina", source="")


def test_la_relation_porte_sa_propre_source(memoire):
    """Savoir que deux entites existent ne dit pas d'ou vient leur lien."""
    memoire.enregistrer_entite("Fast Group", "client", source="devis FG2")
    memoire.enregistrer_entite("Medina", "chantier", source="bon de commande")

    relation = memoire.relier("Fast Group", "chantier", "Medina", source="le proprietaire")

    assert relation.source == "le proprietaire"
    assert memoire.relations(depuis="Fast Group")[0].source == "le proprietaire"


def test_un_depot_refuse_ne_laisse_rien(memoire):
    with pytest.raises(ValueError):
        _retenir(memoire, source="")

    assert memoire.souvenirs() == []


# --- 3. Le contexte temporaire expire ----------------------------------------

def test_un_contexte_temporaire_recoit_une_echeance(memoire):
    souvenir = _retenir(memoire, nature=Nature.CONTEXTE_TEMPORAIRE,
                        contenu="Il est sur le chantier de Medina.")

    assert souvenir.expire_le is not None


def test_un_fait_n_a_pas_d_echeance(memoire):
    assert _retenir(memoire, nature=Nature.FAIT).expire_le is None


def test_un_contexte_perime_n_est_plus_rendu(memoire):
    _retenir(memoire, nature=Nature.CONTEXTE_TEMPORAIRE, duree_heures=0,
             contenu="Il est sur le chantier de Medina.")

    assert memoire.souvenirs() == []


def test_un_contexte_perime_reste_lisible_si_on_le_demande(memoire):
    """Il n'est pas efface : il n'est simplement plus presente comme vrai."""
    _retenir(memoire, nature=Nature.CONTEXTE_TEMPORAIRE, duree_heures=0, contenu="Medina.")

    assert len(memoire.souvenirs(inclure_perimes=True)) == 1


def test_un_contexte_dans_le_delai_est_rendu(memoire):
    _retenir(memoire, nature=Nature.CONTEXTE_TEMPORAIRE, duree_heures=12, contenu="Medina.")

    assert len(memoire.souvenirs()) == 1


def test_une_echeance_illisible_est_traitee_comme_perimee():
    souvenir = Souvenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, "s", expire_le="pas une date")

    assert souvenir.est_perime() is True


def test_la_duree_par_defaut_d_un_contexte_est_de_douze_heures(memoire):
    souvenir = _retenir(memoire, nature=Nature.CONTEXTE_TEMPORAIRE, contenu="Medina.")

    duree = (datetime.fromisoformat(souvenir.expire_le)
             - datetime.fromisoformat(souvenir.cree_le))

    assert duree == timedelta(hours=12)


# --- 4. L'importance se declare, elle ne s'invente pas ------------------------

def test_l_importance_par_defaut_est_le_milieu(memoire):
    """Un souvenir n'est pas important parce qu'il vient d'etre ecrit."""
    assert _retenir(memoire).importance == IMPORTANCE_PAR_DEFAUT == 0.5


@pytest.mark.parametrize("importance", [-0.1, 1.1, 2, -5])
def test_une_importance_hors_bornes_est_refusee(memoire, importance):
    with pytest.raises(ValueError, match="entre 0 et 1"):
        _retenir(memoire, importance=importance)


@pytest.mark.parametrize("importance", [0.0, 0.5, 1.0])
def test_les_bornes_sont_acceptees(memoire, importance):
    assert _retenir(memoire, importance=importance).importance == importance


def test_les_souvenirs_importants_viennent_en_premier(memoire):
    _retenir(memoire, contenu="Detail.", importance=0.1)
    _retenir(memoire, contenu="Essentiel.", importance=0.9)

    assert memoire.souvenirs()[0].contenu == "Essentiel."


# --- Les quatre memoires ------------------------------------------------------

def test_les_quatre_types_de_la_specification_existent():
    assert {t.value for t in TypeSouvenir} == {
        "EPISODIC", "SEMANTIC", "PROCEDURAL", "TASK",
    }


@pytest.mark.parametrize("type", list(TypeSouvenir))
def test_chaque_type_se_retient_et_se_relit(memoire, type):
    _retenir(memoire, type=type, contenu=f"Contenu {type.value}.")

    assert len(memoire.souvenirs(type=type)) == 1


def test_on_retrouve_un_chantier_par_son_projet(memoire):
    """« Continue le projet d'il y a quatre mois » commence ici."""
    _retenir(memoire, projet="Fast Group", contenu="18 parois de 5,40 x 2,50.")
    _retenir(memoire, projet="Medina", contenu="Plafond BA13, 40 m2.")

    assert [s.contenu for s in memoire.souvenirs(projet="Fast Group")] == [
        "18 parois de 5,40 x 2,50."
    ]


def test_les_projets_connus_sont_listables(memoire):
    _retenir(memoire, projet="Fast Group")
    _retenir(memoire, projet="Medina")
    _retenir(memoire, projet=None)

    assert memoire.projets() == ["Fast Group", "Medina"]


# --- Entites et relations ------------------------------------------------------

def test_une_entite_se_retient_et_se_relit(memoire):
    memoire.enregistrer_entite("Fast Group", "client", source="devis FG2", projet="Fast Group")

    entites = memoire.entites(projet="Fast Group")

    assert [e.nom for e in entites] == ["Fast Group"]
    assert entites[0].source == "devis FG2"


def test_reenregistrer_une_entite_met_a_jour_sa_source(memoire):
    memoire.enregistrer_entite("Fast Group", "client", source="devis FG2")
    memoire.enregistrer_entite("Fast Group", "client", source="bon de commande BC-12")

    assert memoire.entites()[0].source == "bon de commande BC-12"
    assert len(memoire.entites()) == 1


def test_deux_entites_de_meme_nom_mais_de_types_differents_coexistent(memoire):
    memoire.enregistrer_entite("Medina", "chantier", source="a")
    memoire.enregistrer_entite("Medina", "quartier", source="b")

    assert len(memoire.entites()) == 2


def test_les_relations_se_lisent_dans_les_deux_sens(memoire):
    memoire.relier("Fast Group", "chantier", "Medina", source="le proprietaire")

    assert len(memoire.relations(depuis="Fast Group")) == 1
    assert len(memoire.relations(vers="Medina")) == 1


def test_relier_deux_fois_ne_cree_pas_de_doublon(memoire):
    memoire.relier("A", "lien", "B", source="s1")
    memoire.relier("A", "lien", "B", source="s2")

    relations = memoire.relations()
    assert len(relations) == 1
    assert relations[0].source == "s2"


# --- Aucun secret -------------------------------------------------------------

def test_un_secret_dans_les_metadonnees_est_masque(memoire):
    souvenir = _retenir(memoire, metadonnees={"access_token": "ya29.SECRET"})

    assert souvenir.metadonnees["access_token"] == MASQUE


def test_aucun_secret_n_atteint_le_fichier(memoire):
    _retenir(memoire, metadonnees={"api_key": "ya29.SECRET-ABSOLU"})

    assert b"ya29.SECRET-ABSOLU" not in memoire.db_path.read_bytes()


def test_un_secret_dans_une_entite_est_masque_aussi(memoire):
    entite = memoire.enregistrer_entite("X", "client", source="s",
                                        metadonnees={"password": "abc"})

    assert entite.metadonnees["password"] == MASQUE


# --- La migration n'efface rien -----------------------------------------------

@pytest.fixture
def ancienne_memoire(tmp_path):
    """Une base contenant deja des faits ecrits par `MemoryManager`."""
    chemin = tmp_path / "partagee.db"
    ancienne = MemoryManager(db_path=str(chemin))
    ancienne.set_fact("user_profile", "owner", "Ousmane", {"role": "Proprietaire"})
    ancienne.set_fact("entreprise", "ninea", "013141677")
    ancienne.add_chat_message("default", "user", "Bonjour")
    return ancienne, chemin


def test_la_migration_importe_les_faits_existants(ancienne_memoire):
    ancienne, chemin = ancienne_memoire
    memoire = MemoirePersonnelle(db_path=str(chemin))

    importees = memoire.migrer_depuis_long_terme()

    assert importees == 2
    contenus = [s.contenu for s in memoire.souvenirs()]
    assert any("Ousmane" in c for c in contenus)
    assert any("013141677" in c for c in contenus)


def test_la_migration_n_efface_pas_l_ancienne_table(ancienne_memoire):
    """L'ancienne table reste lue et ecrite par MemoryManager : on n'y touche pas."""
    ancienne, chemin = ancienne_memoire
    MemoirePersonnelle(db_path=str(chemin)).migrer_depuis_long_terme()

    assert ancienne.get_fact("owner") == "Ousmane"
    assert ancienne.get_fact("ninea") == "013141677"
    assert len(ancienne.get_recent_history("default")) == 1


def test_les_entrees_migrees_sont_des_faits_pas_des_inferences(ancienne_memoire):
    """Le proprietaire les a posees lui-meme ; ce ne sont pas des deductions."""
    _, chemin = ancienne_memoire
    memoire = MemoirePersonnelle(db_path=str(chemin))
    memoire.migrer_depuis_long_terme()

    assert all(s.nature is Nature.FAIT for s in memoire.souvenirs())


def test_les_entrees_migrees_gardent_leur_origine(ancienne_memoire):
    _, chemin = ancienne_memoire
    memoire = MemoirePersonnelle(db_path=str(chemin))
    memoire.migrer_depuis_long_terme()

    assert all(s.source.startswith("long_term_memory.") for s in memoire.souvenirs())


def test_migrer_deux_fois_ne_duplique_rien(ancienne_memoire):
    _, chemin = ancienne_memoire
    memoire = MemoirePersonnelle(db_path=str(chemin))

    premier = memoire.migrer_depuis_long_terme()
    second = memoire.migrer_depuis_long_terme()

    assert (premier, second) == (2, 0)
    assert len(memoire.souvenirs()) == 2


def test_migrer_sans_ancienne_table_ne_leve_pas(memoire):
    assert memoire.migrer_depuis_long_terme() == 0


def test_les_metadonnees_de_l_ancienne_memoire_survivent(ancienne_memoire):
    _, chemin = ancienne_memoire
    memoire = MemoirePersonnelle(db_path=str(chemin))
    memoire.migrer_depuis_long_terme()

    proprietaire = [s for s in memoire.souvenirs() if "Ousmane" in s.contenu][0]
    assert proprietaire.metadonnees["role"] == "Proprietaire"
