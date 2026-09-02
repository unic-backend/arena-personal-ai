"""Un prix changé dans le fichier métier est vu sans redémarrer le serveur.

Défaut mesuré le 01/09/2026 : la grille était lue **une fois**, à la
construction de l'agent — lui-même un singleton créé à l'import de
`apps/backend/runtime.py`, donc au démarrage du serveur.

```
1 AU DEMARRAGE        -> Plaque standard BA13 = 4500
2 FICHIER             -> ecrit a 999999
3 CE QUE L AGENT VOIT -> 4500
```

Le propriétaire changeait son prix, ARENA continuait de chiffrer à l'ancien, et
rien ne le disait. C'est le pire mode d'échec de ce dépôt, et il est nommé
ailleurs dans ces mêmes fichiers : **un mauvais prix sur un document qui part
chez un client**.
"""
import yaml

from agents.plaquiste.plaquiste_agent import (
    MetierSuivi,
    PlaquisteAgent,
    _grille,
    date_du_metier,
)
from core.connectors.devis import DevisConnector

GRILLE_DE_DEPART = {"prix_materiaux": {"Plaque BA13": 4500, "Rail": 1200}}


def ecrire(chemin, donnees):
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")


class TestLaGrilleSuitLeFichier:

    def test_un_prix_change_est_vu_au_chiffrage_suivant(self, tmp_path):
        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        suivi = MetierSuivi(fichier)
        assert _grille(suivi.actuel())["Plaque BA13"] == 4500

        ecrire(fichier, {"prix_materiaux": {"Plaque BA13": 5200, "Rail": 1200}})

        assert _grille(suivi.actuel())["Plaque BA13"] == 5200

    def test_un_article_ajoute_apparait(self, tmp_path):
        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        suivi = MetierSuivi(fichier)

        ecrire(fichier, {"prix_materiaux": dict(
            GRILLE_DE_DEPART["prix_materiaux"], **{"Bande a joint": 800})})

        assert "Bande a joint" in _grille(suivi.actuel())

    def test_un_fichier_inchange_n_est_pas_relu(self, tmp_path, monkeypatch):
        """La relecture suit la date de modification, jamais une horloge."""
        import agents.plaquiste.plaquiste_agent as module

        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        suivi = MetierSuivi(fichier)

        lectures = []
        vrai = module.charger_metier
        monkeypatch.setattr(module, "charger_metier",
                            lambda c=fichier: lectures.append(1) or vrai(c))

        for _ in range(5):
            suivi.actuel()

        assert lectures == []

    def test_un_fichier_disparu_n_a_pas_la_date_zero(self, tmp_path):
        """`None` n'est pas `0` : c'est cette valeur qui décide d'une relecture."""
        fichier = tmp_path / "absent.yaml"

        assert date_du_metier(fichier) is None

    def test_un_fichier_efface_vide_la_grille_au_lieu_de_la_figer(self, tmp_path):
        """Refuser de chiffrer est plus sûr que chiffrer sur une grille fantôme."""
        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        suivi = MetierSuivi(fichier)
        assert _grille(suivi.actuel())

        fichier.unlink()

        assert _grille(suivi.actuel()) == {}


class TestLesDeuxPointsDEntreeSuivent:
    """L'agent et le connecteur chiffrent tous les deux : les deux doivent suivre."""

    def test_l_agent_suit_le_fichier(self, tmp_path, monkeypatch):
        import agents.plaquiste.plaquiste_agent as module

        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        monkeypatch.setattr(module, "FICHIER_METIER", fichier)
        agent = PlaquisteAgent(provider=None)

        ecrire(fichier, {"prix_materiaux": {"Plaque BA13": 7000}})

        assert _grille(agent.metier)["Plaque BA13"] == 7000

    def test_le_connecteur_suit_le_fichier(self, tmp_path, monkeypatch):
        import agents.plaquiste.plaquiste_agent as module

        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        monkeypatch.setattr(module, "FICHIER_METIER", fichier)
        connecteur = DevisConnector()

        ecrire(fichier, {"prix_materiaux": {"Plaque BA13": 7000}})

        assert _grille(connecteur.metier)["Plaque BA13"] == 7000

    def test_une_grille_injectee_n_est_jamais_ecrasee(self, tmp_path, monkeypatch):
        """Les tests injectent leur grille : le disque ne doit pas la remplacer."""
        import agents.plaquiste.plaquiste_agent as module

        fichier = tmp_path / "metier.yaml"
        ecrire(fichier, GRILLE_DE_DEPART)
        monkeypatch.setattr(module, "FICHIER_METIER", fichier)
        injectee = {"prix_materiaux": {"Plaque BA13": 1}}
        agent = PlaquisteAgent(provider=None, metier=injectee)

        ecrire(fichier, {"prix_materiaux": {"Plaque BA13": 7000}})

        assert _grille(agent.metier)["Plaque BA13"] == 1
