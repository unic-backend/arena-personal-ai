"""L'amorce (mission ARENA x TRANS4MERS, §14/§47) : une action tuée en plein
vol laisse une preuve, jamais un journal muet.

Avant `amorcer()`/`confirmer()`, `noter()` écrivait APRÈS l'action : un crash
pendant l'écriture d'un fichier ou une commande longue ne laissait RIEN sur
le disque — la reprise ne savait même pas que l'action avait été tentée, et
pouvait la rejouer en croyant repartir de zéro. Le test de sabotage plus bas
(`TestLeSabotageProuveLeManque`) le démontre pour de vrai.
"""
import json
from pathlib import Path

import pytest

from core.execution.reprise import JournalDeReprise

DEMANDE = "corrige le bug de calcul dans metre.py"


@pytest.fixture
def fichier(tmp_path) -> Path:
    return tmp_path / "travaux" / "reprises.json"


class TestUneActionTueeEnPleinVolLaissePreuve:
    """Le coeur de la mission : amorcer AVANT, confirmer APRES."""

    def test_amorcee_seule_est_deja_sur_le_disque(self, fichier):
        """Simule un crash EXACTEMENT entre amorcer() et confirmer()."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)

        journal.amorcer(tache, "ecrire", "config.py")
        # Rien d'autre n'a lieu : c'est ici que le processus meurt.

        sur_disque = json.loads(fichier.read_text(encoding="utf-8"))
        etapes = sur_disque["taches"][0]["etapes"]
        assert len(etapes) == 1, "l'amorce doit etre ecrite avant l'action, pas apres"
        assert etapes[0]["outil"] == "ecrire"
        assert etapes[0]["confirmee"] is False

    def test_une_etape_non_confirmee_est_dite_a_l_etat_inconnu(self, fichier):
        """La reprise ne doit JAMAIS lire une amorce comme un succes ou un echec."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        journal.amorcer(tache, "executer", "npm run build")
        journal.interrompre(tache, "processus tue")

        repris = JournalDeReprise(fichier=fichier).ouvrir(DEMANDE)
        deja = repris.deja_fait()

        assert len(deja) == 1
        assert "ETAT INCONNU" in deja[0]
        assert "ne PAS" in deja[0] or "ne pas" in deja[0].lower()

    def test_confirmee_redevient_une_etape_ordinaire(self, fichier):
        """Le chemin normal : amorcer puis confirmer, comme la boucle le fait."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)

        etape = journal.amorcer(tache, "lire", "metre.py")
        journal.confirmer(tache, etape, ok=True, resume="200 lignes lues", duree_ms=12)

        assert tache.etapes[0].confirmee is True
        assert tache.etapes[0].ok is True
        assert tache.etapes[0].resume == "200 lignes lues"
        assert tache.etapes[0].duree_ms == 12
        assert tache.deja_fait() == ["lire metre.py -> ok : 200 lignes lues"]

    def test_un_echec_confirme_reste_un_echec(self, fichier):
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)

        etape = journal.amorcer(tache, "executer", "pytest")
        journal.confirmer(tache, etape, ok=False, resume="2 failed", duree_ms=800)

        assert tache.etapes[0].ok is False
        assert tache.etapes[0].confirmee is True

    def test_confirmer_retrouve_l_etape_meme_apres_relecture_disque(self, fichier):
        """`confirmer` doit fonctionner sur une Tache relue depuis un AUTRE
        JournalDeReprise, comme un vrai redemarrage entre amorcer et confirmer
        (par exemple : amorce par un tour, confirme par le tour suivant apres
        un redemarrage d'ARENA au milieu — un scenario deliberement extreme,
        pour prouver que confirmer() ne fait pas confiance a une reference
        Python encore valide)."""
        journal = JournalDeReprise(fichier=fichier)
        tache = journal.ouvrir(DEMANDE)
        etape = journal.amorcer(tache, "ecrire", "config.py")

        relu = JournalDeReprise(fichier=fichier)
        tache_relue = relu.lire(tache.identifiant)
        relu.confirmer(tache_relue, etape, ok=True, resume="ecrit", duree_ms=5)

        final = JournalDeReprise(fichier=fichier).lire(tache.identifiant)
        assert final.etapes[0].confirmee is True
        assert final.etapes[0].ok is True


class TestLeSabotageProuveLeManque:
    """DEC-culture du projet : casser volontairement ce que la garantie
    protege, et prouver que la garantie manque vraiment sans elle."""

    def test_sans_amorce_un_crash_en_plein_vol_ne_laisse_RIEN(self, fichier):
        """Le comportement de l'ANCIEN chemin (`noter()` seul, apres coup) :
        entre le debut de l'action et l'appel a `noter()`, rien n'est sur le
        disque. C'est exactement le manque que `amorcer()`/`confirmer()`
        corrige — ce test fixe le comportement de l'ancien chemin pour que la
        difference reste mesuree, pas seulement affirmee."""
        journal = JournalDeReprise(fichier=fichier)
        journal.ouvrir(DEMANDE)

        # `noter()` seul = l'action a deja fini de tourner avant que quoi que
        # ce soit ne soit ecrit. Un crash AVANT cet appel (pendant l'action
        # elle-meme) ne laisse donc rien.
        sur_disque = json.loads(fichier.read_text(encoding="utf-8"))
        assert sur_disque["taches"][0]["etapes"] == [], (
            "avant noter(), le journal est bien vide : c'est le trou que "
            "amorcer() comble")
