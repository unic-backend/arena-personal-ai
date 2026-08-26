"""Mémoire de conversation : l'historique qu'ARENA relit avant de répondre.

La version qui interrogeait `/api/chat` exigeait Ollama ; elle vit maintenant
dans `tests/test_api.py`, marquée `integration`. Ce fichier teste la mémoire
elle-même, hors ligne.
"""


def test_un_echange_est_relu_dans_l_ordre(memoire):
    memoire.add_chat_message(session_id="default", role="user", content="Comment je m'appelle ?")
    memoire.add_chat_message(session_id="default", role="assistant", content="Tu t'appelles Saer.")

    historique = memoire.get_recent_history(session_id="default")

    assert [(m["role"], m["content"]) for m in historique] == [
        ("user", "Comment je m'appelle ?"),
        ("assistant", "Tu t'appelles Saer."),
    ]


def test_les_sessions_ne_se_melangent_pas(memoire):
    memoire.add_chat_message(session_id="a", role="user", content="message de A")
    memoire.add_chat_message(session_id="b", role="user", content="message de B")

    assert [m["content"] for m in memoire.get_recent_history("a")] == ["message de A"]
    assert [m["content"] for m in memoire.get_recent_history("b")] == ["message de B"]


def test_l_historique_est_borne_par_limit(memoire):
    for i in range(10):
        memoire.add_chat_message(session_id="s", role="user", content=f"message {i}")

    assert len(memoire.get_recent_history("s", limit=4)) == 4


def test_une_session_inconnue_ne_renvoie_rien(memoire):
    assert memoire.get_recent_history("session-jamais-vue") == []


def test_un_fait_est_relu_apres_ecriture(memoire):
    memoire.set_fact("user_profile", "owner", "Saer", {"role": "Propriétaire"})

    assert memoire.get_fact("owner") == "Saer"


def test_un_fait_inconnu_vaut_None_et_pas_une_valeur_plausible(memoire):
    assert memoire.get_fact("fait_qui_n_existe_pas") is None
