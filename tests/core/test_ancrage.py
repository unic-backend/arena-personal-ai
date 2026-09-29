"""Ancrage déterministe des questions elliptiques."""
from core.context.ancrage import ancrer_question


def test_football_puis_donne_moi_un_nom():
    fil = [
        {"role": "user", "content": "Parle-moi du football sénégalais"},
        {"role": "assistant", "content": "Voici les dernières nouvelles."},
    ]

    assert ancrer_question("donne-moi un nom", fil) == (
        "donne-moi un nom\n\nSujet du tour précédent : football sénégalais"
    )


def test_une_question_avec_son_sujet_reste_strictement_intacte():
    question = "parle-moi du basket"
    fil = [{"role": "user", "content": "Parlons de football"}]

    assert ancrer_question(question, fil) == question


def test_liaison_et_pronom_accole_ne_sont_pas_des_sujets():
    fil = [{"role": "user", "content": "Et alors ?"}]

    assert ancrer_question("donne-moi un nom", fil) == "donne-moi un nom"
