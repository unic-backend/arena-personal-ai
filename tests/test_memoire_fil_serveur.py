"""Le fil que le telephone a coupe est relu dans le journal du serveur.

Defaut mesure le 19/09/2026, apres « il oublie ce qu'on s'est dit » :

- `chatStore.ts` coupe l'historique a `.slice(-8)` a ses trois points d'appel ;
- `pwa_gateway._prompt_conversation` ne lisait que ce `history`-la ;
- le serveur, lui, ecrit **chaque** tour dans `short_term_memory` sous
  `session_id = conversation_id`, et ne l'avait jamais relu sur ce chemin.

Au neuvieme message, le premier etait invisible — a un `SELECT` de distance.
"""
from core.memory.conversation import (
    BUDGET_TOURS_ANTERIEURS,
    tours_anterieurs,
)


class JournalDouble:
    """Un `MemoryManager` scripte. Aucune base n'est ouverte ici."""

    def __init__(self, lignes=None, leve=False):
        self.lignes = lignes or []
        self.leve = leve
        self.appels = []

    def get_recent_history(self, session_id, limit=10):
        self.appels.append((session_id, limit))
        if self.leve:
            raise RuntimeError("base verrouillee")
        return self.lignes[-limit:]


def tour(role, contenu):
    return {"role": role, "content": contenu}


# --- Ce que le telephone a coupe ---------------------------------------------

def test_les_tours_hors_fenetre_du_telephone_reviennent():
    journal = JournalDouble([
        tour("user", "Le chantier de Medina fait 340 m2"),
        tour("assistant", "Note."),
        tour("user", "Et ensuite ?"),
    ])

    anciens = tours_anterieurs(journal, "conv-1", [tour("user", "Et ensuite ?")])

    contenus = [t["content"] for t in anciens]
    assert "Le chantier de Medina fait 340 m2" in contenus, (
        "le tour que le telephone n'a pas renvoye n'est pas relu : "
        "c'est exactement l'oubli qu'on corrige")


def test_un_tour_deja_envoye_n_est_pas_relu_deux_fois():
    deja = tour("user", "Et ensuite ?")
    journal = JournalDouble([tour("user", "Plus tot"), deja])

    anciens = tours_anterieurs(journal, "conv-1", [deja])

    assert [t["content"] for t in anciens] == ["Plus tot"]


def test_les_espaces_ne_font_pas_un_tour_different():
    journal = JournalDouble([tour("user", "Et   ensuite ?")])

    anciens = tours_anterieurs(journal, "conv-1", [tour("user", "Et ensuite ?")])

    assert anciens == []


def test_le_message_du_tour_en_cours_ne_revient_pas_comme_un_ancien():
    """Le chemin PWA ecrit la question dans le journal AVANT de construire
    l'invite. Sans ce retrait, elle apparaitrait deux fois : une fois comme
    rappel, une fois comme question du jour."""
    journal = JournalDouble([tour("user", "Combien pour 18 parois ?")])

    anciens = tours_anterieurs(journal, "conv-1", [],
                               message_actuel="Combien pour 18 parois ?")

    assert anciens == []


def test_l_ordre_va_du_plus_ancien_au_plus_recent():
    journal = JournalDouble([
        tour("user", "un"), tour("user", "deux"), tour("user", "trois"),
    ])

    anciens = tours_anterieurs(journal, "conv-1", [])

    assert [t["content"] for t in anciens] == ["un", "deux", "trois"]


# --- Le budget est une limite dure -------------------------------------------

def test_le_budget_borne_ce_qui_remonte():
    journal = JournalDouble([tour("user", "x" * 200) for _ in range(50)])

    anciens = tours_anterieurs(journal, "conv-1", [], budget_caracteres=1000)

    total = sum(len(t["content"]) for t in anciens)
    assert total <= 1000, f"budget depasse : {total} caracteres"
    assert anciens, "le budget a tout refuse alors qu'il tenait plusieurs tours"


def test_le_budget_garde_les_plus_recents_des_anciens():
    journal = JournalDouble([
        tour("user", "a" * 100), tour("user", "b" * 100), tour("user", "c" * 100),
    ])

    anciens = tours_anterieurs(journal, "conv-1", [], budget_caracteres=210)

    assert [t["content"][0] for t in anciens] == ["b", "c"], (
        "le budget a garde les plus vieux : le fil rendu ne touche pas "
        "le tour en cours")


def test_un_tour_trop_long_arrete_le_rappel_sans_le_trouer():
    """On ne saute pas par-dessus un tour trop long pour en prendre un plus
    court derriere : un fil troue se lit comme un fil continu, et le modele
    en deduit des enchainements qui n'ont jamais eu lieu."""
    journal = JournalDouble([
        tour("user", "court d'avant"),
        tour("user", "L" * 500),
        tour("user", "court d'apres"),
    ])

    anciens = tours_anterieurs(journal, "conv-1", [], budget_caracteres=300)

    assert [t["content"] for t in anciens] == ["court d'apres"]


def test_le_budget_par_defaut_est_celui_du_module():
    journal = JournalDouble([tour("user", "x" * 100) for _ in range(200)])

    anciens = tours_anterieurs(journal, "conv-1", [])

    total = sum(len(t["content"]) for t in anciens)
    assert total <= BUDGET_TOURS_ANTERIEURS


# --- La memoire ne bloque jamais la reponse ----------------------------------

def test_un_journal_illisible_rend_une_liste_vide():
    anciens = tours_anterieurs(JournalDouble(leve=True), "conv-1", [])
    assert anciens == []


def test_sans_journal_rien_n_est_lu():
    assert tours_anterieurs(None, "conv-1", []) == []


def test_sans_session_rien_n_est_lu():
    journal = JournalDouble([tour("user", "quelque chose")])
    assert tours_anterieurs(journal, None, []) == []
    assert journal.appels == [], "une session absente a quand meme ete lue"


def test_un_tour_vide_n_encombre_pas_le_rappel():
    journal = JournalDouble([tour("assistant", "   "), tour("user", "reel")])

    anciens = tours_anterieurs(journal, "conv-1", [])

    assert [t["content"] for t in anciens] == ["reel"]
