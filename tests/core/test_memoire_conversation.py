"""Ce qui se dit dans une conversation doit se retrouver après.

Ce fichier existe à cause du défaut mesuré le 02/09/2026 : « il oublie ce
qu'on s'est dit ». La cause n'était ni un réglage ni une taille :

- `pwa_gateway` **lisait** la mémoire longue à chaque message ;
- il n'y **écrivait rien** ;
- un seul endroit du projet entier appelait `retenir()` — l'agent devis, après
  avoir mesuré un plan PDF.

Il lisait une mémoire que la conversation ne remplissait jamais.

`test_ce_qu_il_dit_se_retrouve_bien_plus_tard` est le test qui porte la
correction. `test_ce_qu_arena_repond_n_est_jamais_un_fait` est celui qui
protège ce que la correction ne doit pas abîmer : ARENA n'atteste rien, et
retenir sa propre réponse comme une vérité établie serait la façon la plus
discrète de fabriquer un mensonge durable.
"""
import pytest

from core.memory.conversation import (
    IMPORTANCE_BANAL,
    IMPORTANCE_REGLE,
    LONGUEUR_MAX,
    classer,
    retenir_l_echange,
)
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import recuperer

SOURCE = "conversation du 02/09/2026"


@pytest.fixture
def memoire(tmp_path):
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


# --- Le test qui porte la correction ---------------------------------------------

def test_ce_qu_il_dit_se_retrouve_bien_plus_tard(memoire):
    """Le défaut réparé : dit un jour, retrouvé un autre."""
    retenir_l_echange(memoire, "mon tarif de pose est 5000 F/m2 tout compris",
                      "Note.", source=SOURCE)

    resultats = recuperer(memoire, "c'est combien ma pose au m2 ?")

    assert resultats, "ce qu'il a dit n'est retrouvé par rien"
    assert "5000 F/m2" in resultats[0].souvenir.contenu


def test_sans_le_branchement_la_memoire_reste_vide(memoire):
    """L'état d'avant, pour que la mesure reste lisible."""
    assert recuperer(memoire, "tarif de pose") == []


# --- Ce que la correction ne doit pas abîmer ---------------------------------------

def test_ce_qu_arena_repond_n_est_jamais_un_fait(memoire):
    """ARENA produit du texte ; il n'atteste rien.

    Retenir sa réponse comme `FAIT` ferait, du premier chiffre approximatif,
    un souvenir définitif que plus rien ne viendrait contredire.
    """
    ecrits = retenir_l_echange(memoire, "et pour 40 m2 ?",
                               "Ça ferait environ 200 000 F.", source=SOURCE)

    reponses = [s for s in ecrits if s.metadonnees.get("role") == "usman"]
    assert reponses, "la réponse n'a pas été retenue du tout"
    for souvenir in reponses:
        assert souvenir.nature is Nature.INFERENCE
        assert souvenir.nature is not Nature.FAIT


def test_sa_phrase_est_retenue_telle_quelle(memoire):
    """Résumer, c'est interpréter — et une interprétation fausse retenue pour
    toujours est pire qu'un oubli."""
    phrase = "le chantier de Diamniadio fait 240 m2 en cloisons doubles"

    ecrits = retenir_l_echange(memoire, phrase, "Noté.", source=SOURCE)

    assert ecrits[0].contenu == phrase


def test_ce_qu_il_dit_passe_devant_ce_qu_arena_repond(memoire):
    """La recherche pondère l'importance : l'ordre doit servir le propriétaire."""
    ecrits = retenir_l_echange(memoire, "mon tarif de pose est 5000 F/m2",
                               "D'accord, 5000 F/m2.", source=SOURCE)

    sien = next(s for s in ecrits if s.metadonnees.get("role") == "proprietaire")
    arena = next(s for s in ecrits if s.metadonnees.get("role") == "usman")
    assert sien.importance > arena.importance


# --- « Tout garder », sans que la mémoire devienne un tas ---------------------------

class TestToutEstGardeMaisPese:
    """Choix du propriétaire, 02/09/2026 : tout garder.

    On lui a dit qu'une mémoire pleine de bavardage retrouve moins bien ; il a
    maintenu. Alors on garde tout — et on pèse, ce qui rend son choix tenable :
    la recherche pondère l'importance (20 % dans `recuperation.py`).
    """

    def test_meme_une_salutation_est_gardee(self, memoire):
        ecrits = retenir_l_echange(memoire, "bonjour", "Bonjour Ousmane.", source=SOURCE)

        assert len(ecrits) == 2, "rien ne doit être jeté"

    def test_mais_elle_ne_passe_jamais_devant_un_tarif(self, memoire):
        retenir_l_echange(memoire, "bonjour", "Bonjour.", source=SOURCE)
        retenir_l_echange(memoire, "mon tarif de pose est 5000 F/m2", "Noté.", source=SOURCE)

        resultats = recuperer(memoire, "tarif pose m2")

        assert "5000" in resultats[0].souvenir.contenu

    @pytest.mark.parametrize("phrase,type_attendu,nature_attendue", [
        ("mon tarif de pose est 5000 F/m2", TypeSouvenir.SEMANTIQUE, Nature.FAIT),
        ("je ne fais jamais d'electricite", TypeSouvenir.SEMANTIQUE, Nature.FAIT),
        ("je veux des devis valables 15 jours", TypeSouvenir.SEMANTIQUE, Nature.PREFERENCE),
        ("rappelle-moi d'appeler Fast Group demain", TypeSouvenir.TACHE, Nature.FAIT),
        ("le chantier fait 240 m2", TypeSouvenir.EPISODIQUE, Nature.FAIT),
    ])
    def test_chaque_phrase_est_classee_pour_ce_qu_elle_est(
            self, phrase, type_attendu, nature_attendue):
        type_, nature, _ = classer(phrase)

        assert type_ is type_attendu
        assert nature is nature_attendue

    def test_une_regle_pese_plus_qu_une_salutation(self):
        _, _, regle = classer("mon tarif est 5000 F/m2")
        _, _, banal = classer("ok")

        assert regle == IMPORTANCE_REGLE
        assert banal == IMPORTANCE_BANAL
        assert regle > banal

    def test_le_classement_ne_demande_aucun_modele(self, monkeypatch):
        """La mémoire doit se remplir même Ollama éteint — c'est justement
        quand il l'est que le propriétaire perd le plus."""
        import core.memory.conversation as module

        assert not hasattr(module, "provider"), "ce module ne doit dépendre d'aucun modèle"
        assert classer("mon tarif est 5000 F/m2")[2] == IMPORTANCE_REGLE


# --- Ce qui ne doit jamais casser la conversation -----------------------------------

class TestUneMemoireQuiCasseNEmportePasLaReponse:
    def test_sans_memoire_rien_n_est_ecrit_et_rien_ne_leve(self):
        assert retenir_l_echange(None, "une phrase", "une reponse", source=SOURCE) == []

    def test_une_memoire_en_panne_ne_leve_pas(self):
        class MemoireCassee:
            def retenir(self, **kw):
                raise RuntimeError("disque plein")

        assert retenir_l_echange(MemoireCassee(), "q", "r", source=SOURCE) == []

    def test_un_message_vide_n_ecrit_rien(self, memoire):
        assert retenir_l_echange(memoire, "", "", source=SOURCE) == []

    def test_un_message_tres_long_est_coupe_et_le_dit(self, memoire):
        """Une coupe muette se lit comme une phrase qu'il aurait terminée ainsi."""
        ecrits = retenir_l_echange(memoire, "a" * (LONGUEUR_MAX + 500), "ok", source=SOURCE)

        assert len(ecrits[0].contenu) < LONGUEUR_MAX + 100
        assert "tronque" in ecrits[0].contenu


def test_la_source_accompagne_toujours_le_souvenir(memoire):
    """« Un souvenir sans source est une affirmation sans auteur. »"""
    ecrits = retenir_l_echange(memoire, "mon tarif est 5000", "ok", source=SOURCE)

    assert all(s.source == SOURCE for s in ecrits)


def test_le_chat_ecrit_vraiment_dans_la_memoire_longue():
    """Le branchement lui-même : sans cet appel, tout le reste est décoratif."""
    import inspect

    from apps.backend.routers import pwa_gateway

    source = inspect.getsource(pwa_gateway)
    assert "retenir_l_echange(" in source, (
        "la passerelle n'écrit pas dans la mémoire longue : le défaut est revenu")

