"""Conduire une tâche en plusieurs étapes sans perdre le fil.

Trois tests portent cette capacité.

`test_une_etape_facultative_qui_echoue_n_arrete_pas_la_tache` — c'est ce qui
permet à un calcul impossible de ne pas emporter la réponse avec lui.
`test_la_reprise_est_bornee` — retenter sans fin transforme une panne en boucle.
`test_une_etape_obligatoire_qui_echoue_arrete_et_dit_ou` — on ne rend pas un
résultat partiel en le présentant comme complet.
"""
import pytest

from core.execution.coordination import (
    Coordination,
    Etape,
    EtatEtape,
)


def etapes_simples():
    return [Etape("a", lambda: "A"), Etape("b", lambda acquis: f"B apres {acquis['a']}")]


# --- Les trois tests qui portent la capacité --------------------------------------

async def test_une_etape_facultative_qui_echoue_n_arrete_pas_la_tache():
    def tombe():
        raise ConnectionError("bac a sable absent")

    resultat = await Coordination("tache", [
        Etape("plan", lambda: "un plan"),
        Etape("calcul", tombe, facultative=True),
        Etape("synthese", lambda acquis: f"reponse sans calcul ({list(acquis)})"),
    ]).executer()

    assert resultat.aboutie is True
    assert resultat.trace_de("calcul").etat is EtatEtape.ABANDONNEE
    assert "bac a sable absent" in resultat.trace_de("calcul").raison
    assert "synthese" in resultat.resultats


async def test_la_reprise_est_bornee():
    """Retenter sans fin transforme une panne en boucle."""
    essais = {"n": 0}

    def toujours_casse():
        essais["n"] += 1
        raise TimeoutError("le service ne repond pas")

    resultat = await Coordination("tache", [
        Etape("appel", toujours_casse, essais_max=3, facultative=True),
    ]).executer()

    assert essais["n"] == 3, "exactement le nombre d'essais declare"
    assert resultat.trace_de("appel").tentatives == 3


async def test_une_etape_obligatoire_qui_echoue_arrete_et_dit_ou():
    def tombe():
        raise RuntimeError("panne")

    resultat = await Coordination("tache", [
        Etape("premiere", lambda: "ok"),
        Etape("obligatoire", tombe),
        Etape("jamais", lambda: "ne doit pas tourner"),
    ]).executer()

    assert resultat.aboutie is False
    assert resultat.arretee_a == "obligatoire"
    assert resultat.trace_de("obligatoire").etat is EtatEtape.ECHOUEE
    assert resultat.trace_de("jamais").etat is EtatEtape.NON_ATTEINTE
    assert "jamais" not in resultat.resultats


# --- Rien n'est perdu -----------------------------------------------------------------

async def test_ce_qui_a_reussi_avant_l_echec_est_garde():
    """On ne perd pas le travail deja fait parce qu'une etape est tombee."""
    resultat = await Coordination("tache", [
        Etape("plan", lambda: "un plan utile"),
        Etape("suite", lambda: 1 / 0),
    ]).executer()

    assert resultat.resultats["plan"] == "un plan utile"
    assert resultat.aboutie is False


async def test_une_etape_reussie_apres_reprise_le_dit():
    essais = {"n": 0}

    def instable():
        essais["n"] += 1
        if essais["n"] < 3:
            raise ConnectionError("coupure")
        return "enfin"

    resultat = await Coordination("tache", [
        Etape("appel", instable, essais_max=3),
    ]).executer()

    trace = resultat.trace_de("appel")
    assert trace.etat is EtatEtape.REUSSIE
    assert trace.tentatives == 3
    assert "3 tentative(s)" in resultat.rendre()


async def test_une_duree_est_relevee_pour_chaque_etape():
    resultat = await Coordination("tache", etapes_simples()).executer()

    assert all(t.secondes is not None and t.secondes >= 0 for t in resultat.traces)


# --- La vérification est une étape, pas une supposition ---------------------------------

async def test_une_etape_sans_controle_ne_se_declare_pas_verifiee():
    """Sans contrôle déclaré, « ça n'a pas levé » est tout ce qu'on peut affirmer."""
    resultat = await Coordination("tache", [Etape("a", lambda: "")]).executer()

    trace = resultat.trace_de("a")
    assert trace.etat is EtatEtape.REUSSIE
    assert trace.verifiee is None, "None n'est pas True"


async def test_une_verification_qui_echoue_fait_echouer_l_etape():
    resultat = await Coordination("tache", [
        Etape("a", lambda: "", verifier=lambda r: (bool(r), "resultat vide")),
    ]).executer()

    assert resultat.aboutie is False
    assert resultat.trace_de("a").verifiee is False
    assert "resultat vide" in resultat.trace_de("a").raison


async def test_une_verification_qui_echoue_est_retentee():
    sorties = iter(["", "", "enfin quelque chose"])

    resultat = await Coordination("tache", [
        Etape("a", lambda: next(sorties), essais_max=3,
              verifier=lambda r: (bool(r), "vide")),
    ]).executer()

    assert resultat.trace_de("a").etat is EtatEtape.REUSSIE
    assert resultat.trace_de("a").verifiee is True


# --- Les dépendances --------------------------------------------------------------------

async def test_une_etape_dont_la_dependance_n_a_rien_produit_n_est_pas_lancee():
    """On ne lance pas une etape dans le vide."""
    lancee = []

    resultat = await Coordination("tache", [
        Etape("source", lambda: 1 / 0, facultative=True),
        Etape("suite", lambda: lancee.append(1), depend_de=("source",),
              facultative=True),
    ]).executer()

    assert lancee == []
    assert "depend de source" in resultat.trace_de("suite").raison


async def test_l_acquis_est_transmis_aux_etapes_suivantes():
    resultat = await Coordination("tache", etapes_simples()).executer()

    assert resultat.resultats["b"] == "B apres A"


# --- L'état correspond à des opérations réelles -------------------------------------------

async def test_l_observateur_voit_les_etats_dans_l_ordre_reel():
    """`EN_COURS` s'affiche pendant qu'une étape tourne, pas avant."""
    vus = []

    def observer(trace):
        vus.append((trace.nom, trace.etat))

    await Coordination("tache", etapes_simples(), observateur=observer).executer()

    assert vus[0] == ("a", EtatEtape.EN_COURS)
    assert vus[1] == ("a", EtatEtape.REUSSIE)
    assert vus[2] == ("b", EtatEtape.EN_COURS)


async def test_un_observateur_casse_n_arrete_pas_la_tache():
    def observer(trace):
        raise RuntimeError("l'afficheur a plante")

    resultat = await Coordination("tache", etapes_simples(),
                                  observateur=observer).executer()

    assert resultat.aboutie is True


async def test_l_etat_transportable_porte_les_abandons():
    resultat = await Coordination("tache", [
        Etape("a", lambda: "ok"),
        Etape("b", lambda: 1 / 0, facultative=True),
    ]).executer()

    transporte = resultat.to_dict()
    assert transporte["abandonnees"] == ["b"]
    assert transporte["aboutie"] is True


def test_une_tache_sans_etape_est_refusee():
    with pytest.raises(ValueError):
        Coordination("vide", [])


def test_une_etape_qui_ne_s_execute_jamais_est_refusee():
    with pytest.raises(ValueError):
        Etape("a", lambda: None, essais_max=0)


# --- Le moteur de raisonnement tourne réellement dessus -------------------------------------

async def test_le_raisonnement_utilise_la_coordination(provider_factory, monkeypatch):
    """La preuve par l'usage : l'état des étapes sort avec la réponse."""
    from core.reasoning.reasoning_engine import ReasoningEngine

    moteur = ReasoningEngine(provider=provider_factory("Plan en prose.", "Solution."))
    resultat = await moteur.solve_complex_task("explique une idee")

    etapes = {e["etape"]: e["etat"] for e in resultat["coordination"]["etapes"]}
    assert etapes == {"plan": "DONE", "calcul": "DONE", "synthese": "DONE"}
    assert resultat["final_response"] == "Solution."


async def test_un_bac_a_sable_absent_n_emporte_pas_la_reponse(provider_factory, monkeypatch):
    """Le calcul est facultatif : la synthèse se fait quand même."""
    from core.reasoning.reasoning_engine import ReasoningEngine

    plan = "Plan.\n```python\nprint(2+2)\n```"
    moteur = ReasoningEngine(provider=provider_factory(plan, "Solution sans calcul."))
    monkeypatch.setattr(moteur.interpreter, "docker_available", False)
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)

    resultat = await moteur.solve_complex_task("resous x^2 = 4")

    etapes = {e["etape"]: e["etat"] for e in resultat["coordination"]["etapes"]}
    assert etapes["calcul"] == "SKIPPED"
    assert etapes["synthese"] == "DONE"
    assert "Erreur calcul" in resultat["calculation_result"]
    assert resultat["final_response"] == "Solution sans calcul."
