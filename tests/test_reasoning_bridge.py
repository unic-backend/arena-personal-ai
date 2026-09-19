"""Tests du pont entre le chat et le moteur de raisonnement.

Deux categories :

- **Fonctions pures** (`profondeur_pour`, `note_de_calcul`, `note_de_critique`) :
  aucun appel modele, aucun service, tests instantanes.
- **`resoudre_profondement`** : avec un FAUX moteur injecte. Aucun appel
  reseau, aucun Ollama, aucun bac a sable.
"""

from apps.backend.reasoning_bridge import (
    note_de_calcul,
    note_de_critique,
    profondeur_pour,
    resoudre_profondement,
)

# --- profondeur_pour ---------------------------------------------------------


class TestProfondeurPour:
    def test_un_mot_de_verification_demande_approfondie(self):
        assert profondeur_pour("vérifie ce calcul") == "approfondie"
        assert profondeur_pour("Relis ma réponse") == "approfondie"
        assert profondeur_pour("corrige cette erreur") == "approfondie"
        assert profondeur_pour("Es-tu sûr de ça ?") == "approfondie"

    def test_une_demande_courte_ordinaire_reste_standard(self):
        assert profondeur_pour("combien font 12 % de 340") == "standard"
        assert profondeur_pour("résous x^2 - 5x + 6 = 0") == "standard"

    def test_une_demande_longue_passe_approfondie(self):
        longue = "explique-moi " + "vraiment " * 30 + "ce point précis"
        assert len(longue) > 200
        assert profondeur_pour(longue) == "approfondie"

    def test_chaine_vide_reste_standard(self):
        assert profondeur_pour("") == "standard"
        assert profondeur_pour(None) == "standard"


# --- note_de_calcul ----------------------------------------------------------


class TestNoteDeCalcul:
    def test_calcul_reussi_ne_produit_aucune_note(self):
        assert note_de_calcul("") == ""
        assert note_de_calcul("42") == ""

    def test_calcul_refuse_produit_un_avertissement(self):
        note = note_de_calcul("Erreur calcul : bac a sable indisponible")
        assert "⚠️" in note
        assert "bac a sable indisponible" in note
        assert "aucun calcul" in note


# --- note_de_critique --------------------------------------------------------


class TestNoteDeCritique:
    def test_pas_de_critique_aucune_note(self):
        assert note_de_critique(None) == ""
        assert note_de_critique({}) == ""

    def test_critique_ok_aucune_note(self):
        assert note_de_critique({"ok": True, "raison": "parfait"}) == ""

    def test_critique_sans_verdict_aucune_note(self):
        # ok=None : le moteur a abandonne la critique, rien a dire a l'utilisateur.
        assert note_de_critique({"ok": None, "raison": "illisible"}) == ""

    def test_critique_ko_produit_un_avertissement(self):
        note = note_de_critique({"ok": False, "raison": "il manque les cas limites"})
        assert "🔍" in note
        assert "il manque les cas limites" in note

    def test_critique_ko_avec_confiance_affiche_le_score(self):
        note = note_de_critique({"ok": False, "raison": "inexact", "confiance": 0.35})
        assert "0.35" in note
        assert "inexact" in note

    def test_critique_ko_sans_raison_reste_lisible(self):
        note = note_de_critique({"ok": False})
        assert "sans raison donnee" in note


# --- resoudre_profondement : avec un faux moteur -----------------------------


class _FauxMoteur:
    """Moteur factice : enregistre l'appel, rend un resultat predefini."""

    def __init__(self, resultat: dict):
        self.resultat = resultat
        self.appels: list = []

    async def solve_complex_task(self, prompt: str, profondeur: str = "standard",
                                 contexte: str = ""):
        self.appels.append({"prompt": prompt, "profondeur": profondeur,
                            "contexte": contexte})
        resultat = dict(self.resultat)
        resultat["profondeur"] = profondeur
        return resultat


async def test_resoudre_profondement_passe_la_profondeur_choisie():
    moteur = _FauxMoteur({
        "status": "success",
        "plan": "plan en prose",
        "calculation_result": "",
        "final_response": "Réponse finale.",
        "critique": None,
    })

    res = await resoudre_profondement("résous cette équation", moteur=moteur)

    assert len(moteur.appels) == 1
    assert moteur.appels[0]["profondeur"] == "standard"
    assert res["profondeur"] == "standard"
    assert res["response"] == "Réponse finale."
    assert res["agent"] == "ReasoningEngine"
    assert "critique" not in res


async def test_resoudre_profondement_propage_la_critique_ko():
    moteur = _FauxMoteur({
        "status": "success",
        "plan": "plan",
        "calculation_result": "",
        "final_response": "Solution incomplète.",
        "critique": {"ok": False, "raison": "il manque les cas limites",
                     "confiance": 0.4},
    })

    res = await resoudre_profondement("vérifie ma réponse", moteur=moteur)

    assert moteur.appels[0]["profondeur"] == "approfondie"
    assert res["profondeur"] == "approfondie"
    # Le verdict voyage dans le champ JSON, pas dans le texte : c'est la
    # PWA (et tout autre client) qui decide comment l'afficher.
    assert res["critique"]["ok"] is False
    assert res["critique"]["raison"] == "il manque les cas limites"
    # Le texte de la reponse ne porte PAS la note de critique ? pas de
    # doublon avec le badge cote interface.
    assert "cas limites" not in res["response"]


async def test_resoudre_profondement_ajoute_la_note_de_calcul():
    moteur = _FauxMoteur({
        "status": "success",
        "plan": "plan",
        "calculation_result": "Erreur calcul : bac a sable absent",
        "final_response": "Voici la réponse.",
    })

    res = await resoudre_profondement("combien font 2+2", moteur=moteur)

    assert "⚠️" in res["response"]
    assert "bac a sable absent" in res["response"]


async def test_resoudre_profondement_preserve_les_cles_historiques():
    moteur = _FauxMoteur({
        "status": "error",
        "plan": "plan",
        "calculation_result": "",
        "final_response": "Réponse.",
    })

    res = await resoudre_profondement("test", moteur=moteur)

    for cle in ("status", "agent", "plan", "calcul", "response"):
        assert cle in res, f"cle historique manquante : {cle}"

    assert res["status"] == "error"
    assert res["calcul"] == ""


# --- Le fil de conversation atteint le moteur (19/09/2026) --------------------
#
# Jusqu'ici le moteur ne recevait que la derniere phrase : « verifie ton
# calcul » arrivait sans le calcul, et il repondait a cote sans pouvoir faire
# autrement.

def _moteur_muet():
    return _FauxMoteur({
        "status": "success", "plan": "", "calculation_result": "",
        "final_response": "Reponse.", "critique": None,
    })


async def test_le_contexte_est_transmis_au_moteur():
    moteur = _moteur_muet()

    await resoudre_profondement("verifie ton calcul", moteur=moteur,
                                contexte="Ousmane: 12 % de 340 ?\nUsman: 40,8")

    assert "40,8" in moteur.appels[0]["contexte"]


async def test_sans_contexte_le_moteur_en_recoit_un_vide():
    """Le comportement d'avant ce parametre, a l'identique."""
    moteur = _moteur_muet()

    await resoudre_profondement("resous cette equation", moteur=moteur)

    assert moteur.appels[0]["contexte"] == ""


async def test_le_contexte_ne_devient_jamais_la_question():
    moteur = _moteur_muet()

    await resoudre_profondement("verifie", moteur=moteur, contexte="x" * 500)

    assert moteur.appels[0]["prompt"] == "verifie"


async def test_un_fil_long_ne_fait_pas_basculer_en_mode_approfondie():
    """Le mode approfondie coute deux appels de modele de plus. Le declencher
    parce que la CONVERSATION depasse 200 caracteres le rendrait systematique
    au neuvieme message, sans que la question ait gagne en difficulte."""
    moteur = _moteur_muet()

    await resoudre_profondement("combien font 12 % de 340 ?", moteur=moteur,
                                contexte="bla " * 500)

    assert moteur.appels[0]["profondeur"] == "standard"
