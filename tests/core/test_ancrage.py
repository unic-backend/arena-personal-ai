"""Composition déterministe et bornée du fil avant la demande actuelle."""
from core.context.ancrage import (
    DEBUT_CONTEXTE,
    DEBUT_DEMANDE,
    FIN_CONTEXTE,
    borner_tours,
    joindre_le_fil,
)


def test_la_demande_reste_intacte_et_separee_du_contexte():
    demande = "parle-moi du basket"
    recu = joindre_le_fil(
        demande,
        [{"role": "user", "content": "Parlons de football"}],
        "Ousmane",
        maximum=6,
    )

    assert recu == "\n".join((
        DEBUT_CONTEXTE,
        "Ousmane: Parlons de football",
        FIN_CONTEXTE,
        DEBUT_DEMANDE,
        demande,
    ))
    assert recu.endswith(demande)


def test_le_budget_supprime_les_tours_les_plus_anciens_sans_trou():
    tours = [
        {"role": "user", "content": "ancien-" + "a" * 80},
        {"role": "assistant", "content": "milieu-" + "b" * 80},
        {"role": "user", "content": "récent-" + "c" * 80},
    ]

    gardes = borner_tours(tours, maximum=6, budget_caracteres=195)

    assert [tour["content"].split("-")[0] for tour in gardes] == ["milieu", "récent"]
    rendu = joindre_le_fil(
        "combien", tours, "Ousmane", maximum=6, budget_caracteres=195
    )
    contexte = rendu.split(FIN_CONTEXTE)[0]
    assert len(contexte.split("\n", 1)[1]) <= 195
    assert "ancien-" not in rendu


def test_le_nombre_de_tours_est_aussi_borne():
    tours = [{"role": "user", "content": str(numero)} for numero in range(10)]

    assert [t["content"] for t in borner_tours(tours, maximum=3)] == ["7", "8", "9"]


def test_sans_fil_la_demande_passe_seule():
    assert joindre_le_fil("un titre", [], "Ousmane", maximum=6) == "un titre"
