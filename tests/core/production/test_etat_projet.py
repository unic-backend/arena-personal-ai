"""`core/production/etat_projet.py` — la forme de l'etat d'un projet Video.

Pas de logique d'execution ici : uniquement la structure et sa serialisation.
DEC-0037.
"""
from core.execution.coordination import EtatEtape, Resultat, Trace
from core.production.etat_projet import EtapeProjet, EtatProjetVideo


def test_une_etape_projet_se_serialise_avec_ses_dependances():
    etape = EtapeProjet(id="a", capacite="vision", parametres={"question": "quoi ?"},
                        depend_de=("b",), facultative=True)

    assert etape.to_dict() == {
        "id": "a", "capacite": "vision", "parametres": {"question": "quoi ?"},
        "depend_de": ["b"], "facultative": True,
    }


def test_un_etat_projet_vide_se_serialise_sans_resultat():
    etat = EtatProjetVideo(objectif="une video de chantier")

    transporte = etat.to_dict()

    assert transporte["objectif"] == "une video de chantier"
    assert transporte["graphe"] == []
    assert transporte["resultat"] is None
    assert transporte["artefact_final"] is None


def test_un_etat_projet_porte_le_resultat_de_la_coordination():
    resultat = Resultat(tache="video::x", traces=[Trace(nom="a", etat=EtatEtape.REUSSIE)],
                        aboutie=True)
    etat = EtatProjetVideo(
        objectif="x", graphe=[EtapeProjet(id="a", capacite="vision")],
        resultat=resultat, artefact_final="/tmp/rendu.mp4")

    transporte = etat.to_dict()

    assert transporte["resultat"]["aboutie"] is True
    assert transporte["resultat"]["etapes"][0]["etape"] == "a"
    assert transporte["artefact_final"] == "/tmp/rendu.mp4"
