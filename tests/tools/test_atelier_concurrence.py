"""Deux tâches, le même fichier, en même temps — mission ARENA x TRANS4MERS
§11/§12/§20/§46/§51.

**Ce que ces tests prouvent, avec de vrais threads, pas une simulation.**
`Atelier` est partagé par construction (`apps/backend/runtime.py` n'en crée
qu'un) : deux requêtes concurrentes qui demandent toutes deux à Dioumtoukay
de modifier le même fichier doivent produire un résultat cohérent — jamais
un mélange des deux écritures, jamais une correction perdue en silence.

Un `threading.Barrier` force le pire entrelacement possible (les deux
threads démarrent au même instant, pas "l'un après l'autre par chance") :
sans lui, une race de ce genre peut passer au vert neuf fois sur dix sans
rien prouver.
"""
import threading
from pathlib import Path

from tools.atelier import verrous
from tools.atelier.atelier import Atelier


def _sur_deux_threads(cible, n=2):
    barriere = threading.Barrier(n)
    resultats = [None] * n

    def _lance(i):
        barriere.wait()  # les deux ne partent qu'ensemble : la vraie course
        resultats[i] = cible(i)

    threads = [threading.Thread(target=_lance, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return resultats


class TestEcritureConcurrente:
    """Deux `ecrire()` simultanés sur le MÊME fichier ne doivent jamais
    produire un contenu mélangé — l'un des deux gagne, entier."""

    def test_le_contenu_final_est_integralement_l_un_des_deux_jamais_un_melange(
            self, tmp_path):
        atelier = Atelier(racine=tmp_path)
        contenu_a = "A" * 200_000 + "\n"
        contenu_b = "B" * 200_000 + "\n"

        _sur_deux_threads(
            lambda i: atelier.ecrire("cible.txt", contenu_a if i == 0 else contenu_b))

        final = (tmp_path / "cible.txt").read_text(encoding="utf-8")
        assert final in (contenu_a, contenu_b), (
            "le fichier final doit etre integralement A ou integralement B, "
            "jamais un melange des deux ecritures concurrentes")


class TestRemplacementConcurrent:
    """La vraie garantie anti-TOCTOU (§11/§12/§46) sous concurrence reelle :
    la seconde tache ne doit JAMAIS ecraser silencieusement le travail de la
    premiere sur le meme passage."""

    def test_une_seule_des_deux_reussit_sur_le_meme_passage_l_autre_echoue_proprement(
            self, tmp_path):
        (tmp_path / "config.py").write_text("DEBUG = False\n", encoding="utf-8")
        atelier = Atelier(racine=tmp_path)

        resultats = _sur_deux_threads(
            lambda i: atelier.remplacer("config.py", "DEBUG = False",
                                        f"DEBUG = True  # tache-{i}"))

        reussites = [r for r in resultats if r.ok]
        echecs = [r for r in resultats if not r.ok]
        # Verrouillees, les deux tentatives s'executent l'une APRES l'autre :
        # la seconde relit un fichier qui ne contient plus "DEBUG = False"
        # (la premiere l'a deja remplace) et echoue proprement — "introuvable"
        # — au lieu d'ecraser la premiere correction en silence. SANS le
        # verrou, les deux pourraient toutes deux lire "DEBUG = False" avant
        # que l'une n'ecrive, et la seconde ecraserait la premiere : ok=True,
        # ok=True, et une seule des deux corrections survivrait — un mensonge
        # silencieux (le rapport dirait deux succes pour un seul effet reel).
        assert len(reussites) == 1, (
            f"exactement une des deux doit reussir, "
            f"{len(reussites)} ont reussi : {resultats}")
        assert len(echecs) == 1
        assert "introuvable" in echecs[0].message.lower()

        final = (tmp_path / "config.py").read_text(encoding="utf-8")
        assert final.count("DEBUG = True") == 1, (
            "le fichier final doit porter EXACTEMENT une correction, "
            "jamais deux collees ni aucune perdue"
        )


class TestLeSabotageProuveLeManque:
    """Retire le verrou : la meme course redevient dangereuse."""

    def test_sans_verrou_les_deux_remplacements_peuvent_tous_deux_reussir(
            self, tmp_path, monkeypatch):
        """Prouve que le verrou est ce qui protege, pas une coincidence :
        en le neutralisant (le contexte ne fait plus rien), on force
        artificiellement les deux threads a lire AVANT que l'un n'ecrive —
        exactement le defaut que `verrous.pour` corrige."""
        import contextlib

        (tmp_path / "config.py").write_text("DEBUG = False\n", encoding="utf-8")
        atelier = Atelier(racine=tmp_path)

        lu_par_les_deux = threading.Barrier(2)
        original_read = Path.read_text

        def _lecture_synchronisee(self, *a, **k):
            resultat = original_read(self, *a, **k)
            if self.name == "config.py":
                lu_par_les_deux.wait(timeout=5)  # force les DEUX a lire avant d'ecrire
            return resultat

        monkeypatch.setattr(verrous, "pour", lambda chemin: contextlib.nullcontext())
        monkeypatch.setattr(Path, "read_text", _lecture_synchronisee)

        resultats = _sur_deux_threads(
            lambda i: atelier.remplacer("config.py", "DEBUG = False",
                                        f"DEBUG = True  # tache-{i}"))

        reussites = [r for r in resultats if r.ok]
        assert len(reussites) == 2, (
            "sans le verrou, force a l'entrelacement le pire possible, les "
            "DEUX remplacements lisent 'DEBUG = False' et reussissent tous "
            "les deux — c'est exactement le defaut que verrous.pour corrige "
            "dans le test precedent"
        )
