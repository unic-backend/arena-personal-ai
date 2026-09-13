"""Un plan dit ce qu'il a fait et **pourquoi il s'est arrêté**.

Avant le 13/09/2026, `raison_d_arret` existait — `RaisonDArret`, sept valeurs,
portée par `EtatBoucle` — mais **elle ne sortait jamais de la boucle**. Elle
finissait dans une ligne de journal applicatif, c'est-à-dire nulle part où
quelqu'un puisse la retrouver le lendemain. `plan_id` et le compte de souvenirs
n'existaient pas du tout.

Le manque était concret : quand une demande aboutissait à une réponse
incomplète, rien ne disait si le plan avait **atteint son objectif**, **épuisé
son budget de tours**, ou **manqué de temps**. Les trois se ressemblent vues de
l'extérieur, et elles appellent trois gestes différents.

Trois propriétés portent ces tests :

1. **Aucun arrêt n'échappe au journal.** `_arreter` est le passage obligé de
   tout arrêt ; une raison manquante signalerait un chemin qui le contourne.
2. **Rien n'est inventé hors contexte.** Un plan sans demande porte
   `requete = None` ; sans compteur d'outils, `appels_outils` reste `None`.
3. **Le compteur de souvenirs appartient au plan**, pas au processus.
"""
import asyncio

import pytest

from core.execution.boucle import BoucleAgentique, Budget, RaisonDArret
from core.execution.coordination import Etape
from core.observabilite.fil import nouveau_fil, souvenirs_lus, tache
from core.observabilite.plans import JournalDesPlans, PlanExecute


@pytest.fixture
def journal(tmp_path) -> JournalDesPlans:
    return JournalDesPlans(db_path=str(tmp_path / "plans.db"))


def _etape(nom="agir", rendu="ok"):
    return Etape(nom=nom, appel=lambda: rendu)


def _un_seul_tour(objectif, observations):
    return [] if observations else [_etape()]


def _toujours(objectif, observations):
    """Propose une etape a chaque tour — c'est ce qui epuise le budget de tours.

    Avec `_un_seul_tour`, le second tour rend `[]` et l'arret est `PLAN_VIDE`,
    pas `BUDGET_TOURS` : les deux sont des arrets legitimes et differents, et
    les confondre dans un test ferait passer l'un pour l'autre.
    """
    return [_etape()]


ATTEINT = lambda _r, _a: (True, "fait")          # noqa: E731
JAMAIS = lambda _r, _a: (False, "pas encore")    # noqa: E731


def executer(journal, **reste):
    boucle = BoucleAgentique(
        objectif=reste.pop("objectif", "un objectif"),
        planifier=reste.pop("planifier", _un_seul_tour),
        evaluer=reste.pop("evaluer", ATTEINT),
        journal=journal, **reste,
    )
    return asyncio.run(boucle.executer())


# --------------------------------------------------------------------------
# Aucun arrêt n'échappe au journal
# --------------------------------------------------------------------------

def test_un_plan_atteint_est_enregistre_avec_sa_raison(journal):
    etat = executer(journal)

    ligne = journal.dernieres()[0]
    assert ligne.plan_id == etat.plan_id
    assert ligne.raison_d_arret == RaisonDArret.OBJECTIF_ATTEINT.value
    assert ligne.atteint is True


@pytest.mark.parametrize("reste, attendue", [
    ({"planifier": _toujours, "evaluer": JAMAIS, "budget": Budget(tours_max=2)},
     RaisonDArret.BUDGET_TOURS),
    ({"evaluer": JAMAIS},
     RaisonDArret.PLAN_VIDE),
    ({"planifier": lambda o, obs: []},
     RaisonDArret.PLAN_VIDE),
    ({"planifier": lambda o, obs: (_ for _ in ()).throw(RuntimeError("casse"))},
     RaisonDArret.PLANIFICATION_EN_ECHEC),
    ({"planifier": lambda o, obs: [_etape(f"e{i}") for i in range(5)],
      "budget": Budget(etapes_max=2)},
     RaisonDArret.BUDGET_ETAPES),
])
def test_chaque_raison_d_arret_arrive_au_journal(journal, reste, attendue):
    """Les quatre arrêts se ressemblent vus de l'extérieur ; le journal les sépare."""
    executer(journal, **reste)

    assert journal.dernieres()[0].raison_d_arret == attendue.value


def test_deux_executions_du_meme_objectif_ont_deux_identifiants(journal):
    """C'est ce qui permet de les distinguer quand la première a échoué."""
    premier = executer(journal, objectif="le meme")
    second = executer(journal, objectif="le meme")

    assert premier.plan_id != second.plan_id
    assert len({p.plan_id for p in journal.dernieres()}) == 2


def test_l_identifiant_voyage_dans_l_etat_rendu(journal):
    etat = executer(journal)

    assert etat.to_dict()["plan_id"] == etat.plan_id


def test_sans_journal_la_boucle_tourne_quand_meme(tmp_path):
    """Un journal absent n'est pas une panne : c'est le cas d'un test."""
    boucle = BoucleAgentique(objectif="sans trace", planifier=_un_seul_tour,
                             evaluer=ATTEINT)

    etat = asyncio.run(boucle.executer())

    assert etat.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT


def test_une_ecriture_impossible_n_empeche_pas_le_plan(journal, monkeypatch):
    """Perdre la trace d'un plan est regrettable ; l'empêcher de rendre son
    résultat l'est davantage."""
    def casse(*_a, **_k):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(journal, "_connexion", casse)

    etat = executer(journal)

    assert etat.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT


# --------------------------------------------------------------------------
# Rien n'est inventé hors contexte
# --------------------------------------------------------------------------

def test_un_plan_hors_demande_ne_s_invente_pas_de_demande(journal):
    executer(journal)

    ligne = journal.dernieres()[0]
    assert ligne.requete is None
    assert ligne.type_tache is None


def test_un_plan_dans_une_demande_la_nomme(journal):
    with nouveau_fil("demande-du-matin"), tache("PLAQUISTE"):
        executer(journal)

    ligne = journal.dernieres()[0]
    assert ligne.requete == "demande-du-matin"
    assert ligne.type_tache == "PLAQUISTE"


def test_sans_compteur_d_outils_le_compte_reste_none(journal):
    """Règle 5 de la boucle. `0` ferait lire « aucun outil appelé » là où la
    vérité est « personne n'a compté »."""
    executer(journal)

    assert journal.dernieres()[0].appels_outils is None


def test_avec_un_compteur_d_outils_le_compte_est_rendu(journal):
    appels = [0]

    def une_etape_qui_appelle():
        appels[0] += 3
        return "ok"

    executer(journal,
             planifier=lambda o, obs: [] if obs else [
                 Etape(nom="outil", appel=une_etape_qui_appelle)],
             compteur_outils=lambda: appels[0])

    assert journal.dernieres()[0].appels_outils == 3


def test_une_demande_retrouve_exactement_ses_plans(journal):
    with nouveau_fil("demande-A"):
        executer(journal, objectif="plan A1")
        executer(journal, objectif="plan A2")
    with nouveau_fil("demande-B"):
        executer(journal, objectif="plan B1")

    assert len(journal.dernieres(requete_id="demande-A")) == 2
    assert len(journal.dernieres(requete_id="demande-B")) == 1
    assert len(journal.dernieres()) == 3


# --------------------------------------------------------------------------
# Le compteur de souvenirs appartient au plan
# --------------------------------------------------------------------------

def test_les_souvenirs_consultes_sont_comptes_pour_le_plan(journal):
    from core.observabilite.fil import compter_souvenirs_lus

    executer(journal, planifier=lambda o, obs: [] if obs else [
        Etape(nom="lire", appel=lambda: compter_souvenirs_lus(4) or "ok")])

    assert journal.dernieres()[0].souvenirs_consultes == 4


def test_un_plan_qui_ne_lit_rien_compte_zero(journal):
    """`0` est une mesure ici : le plan a tourné et n'a rien consulté."""
    executer(journal)

    assert journal.dernieres()[0].souvenirs_consultes == 0


def test_le_compteur_repart_a_zero_a_chaque_plan(journal):
    """Sinon « 12 souvenirs consultés » voudrait dire « depuis le démarrage »."""
    from core.observabilite.fil import compter_souvenirs_lus

    for _ in range(2):
        executer(journal, planifier=lambda o, obs: [] if obs else [
            Etape(nom="lire", appel=lambda: compter_souvenirs_lus(5) or "ok")])

    assert [p.souvenirs_consultes for p in journal.dernieres()] == [5, 5]


def test_hors_plan_le_compte_ne_s_accumule_pas():
    """Compter des lectures qui n'appartiennent à aucun plan gonflerait le suivant."""
    from core.observabilite.fil import compter_souvenirs_lus

    compter_souvenirs_lus(99)

    assert souvenirs_lus() == 0


def test_la_recuperation_reelle_alimente_le_compteur(journal, tmp_path):
    """Le chemin réel, pas un double : `recuperer()` doit compter ce qu'il rend."""
    from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
    from core.memory.recuperation import recuperer

    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    for i in range(3):
        memoire.retenir(f"Le tarif de pose du chantier {i} est {5000 + i} F/m2.",
                        TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="proprietaire")

    executer(journal, planifier=lambda o, obs: [] if obs else [
        Etape(nom="lire", appel=lambda: recuperer(memoire, "tarif de pose chantier"))])

    assert journal.dernieres()[0].souvenirs_consultes == 3


# --------------------------------------------------------------------------
# Le rapport
# --------------------------------------------------------------------------

def test_seuls_les_souvenirs_RETENUS_sont_comptes(journal, tmp_path):
    """Le test que le sabotage a réclamé (13/09/2026).

    `test_la_recuperation_reelle_alimente_le_compteur` utilisait trois souvenirs
    que le budget laissait tous passer : candidats et retenus valaient trois, et
    remplacer l'un par l'autre ne changeait rien — **24 tests restaient verts**.

    Ici le budget en écarte. Un souvenir que le budget n'a pas pris n'est pas
    parti vers l'invite : le compter ferait lire « le plan a consulté quinze
    souvenirs » quand le modèle n'en a vu que deux.
    """
    from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
    from core.memory.recuperation import recuperer

    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    for i in range(15):
        memoire.retenir(f"Le tarif de pose du chantier numero {i} est {5000 + i} F/m2.",
                        TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="proprietaire")

    # Un budget serré : plusieurs candidats, peu de retenus.
    executer(journal, planifier=lambda o, obs: [] if obs else [
        Etape(nom="lire", appel=lambda: recuperer(
            memoire, "tarif de pose chantier", budget_caracteres=150))])

    comptes = journal.dernieres()[0].souvenirs_consultes
    assert 0 < comptes < 15, (
        f"{comptes} : le compteur doit suivre les souvenirs RETENUS, pas les "
        f"candidats examinés"
    )


def test_un_plan_imbrique_ne_herite_pas_du_compte_du_parent(journal):
    """Le second test que le sabotage a réclamé.

    `test_le_compteur_repart_a_zero_a_chaque_plan` enchaînait deux plans
    **successifs** : le premier étant refermé, le second repartait de zéro même
    sans remise à zéro explicite — 24 tests restaient verts. C'est
    l'imbrication qui distingue les deux, et c'est le cas réel : un plan qui en
    déclenche un autre.
    """
    from core.observabilite.fil import compter_souvenirs_lus, plan, souvenirs_lus

    with plan("parent"):
        compter_souvenirs_lus(7)
        with plan("enfant"):
            assert souvenirs_lus() == 0, (
                "l'enfant hérite du compte du parent : « 7 souvenirs » lui "
                "serait attribué alors qu'il n'a rien lu"
            )
            compter_souvenirs_lus(2)
            assert souvenirs_lus() == 2
        assert souvenirs_lus() == 7, "le parent doit retrouver SON compte"


def test_le_rapport_repartit_les_raisons_d_arret(journal):
    executer(journal)
    executer(journal)
    executer(journal, planifier=_toujours, evaluer=JAMAIS, budget=Budget(tours_max=2))

    rapport = journal.resume()

    assert rapport["par_raison_d_arret"] == {"GOAL_REACHED": 2, "REPLAN_BUDGET": 1}
    assert rapport["atteints"] == 2
    assert rapport["total"] == 3


def test_le_rapport_dit_que_atteint_n_est_pas_un_jugement(journal):
    """« atteint » mesure l'arrêt, pas la qualité du résultat."""
    rapport = journal.resume()

    assert "pas que le resultat est bon" in rapport["note"]


def test_un_rapport_vide_ne_pretend_rien(journal):
    rapport = journal.resume()

    assert rapport["total"] == 0
    assert rapport["plans"] == []
    assert rapport["par_raison_d_arret"] == {}


def test_le_meme_plan_reecrit_ne_se_duplique_pas(journal):
    """`INSERT OR REPLACE` sur la clé : un plan est une ligne, pas deux."""
    plan = PlanExecute(plan_id="p1", objectif="x", raison_d_arret="GOAL_REACHED",
                       atteint=True, tours=1, etapes=1, secondes=0.1)
    journal.enregistrer(plan)
    journal.enregistrer(plan)

    assert len(journal.dernieres()) == 1
