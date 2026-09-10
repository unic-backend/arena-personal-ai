"""`core/production/materiel.py` — mission ARENA x HIDREAM-I1 (DEC-0085).

Mesures reelles, jamais devinees : sur CETTE machine (aucune carte NVIDIA),
`mesurer_gpu()` doit honnetement rendre `None`, jamais un chiffre invente.
RAM et disque sont mesures pour de vrai (psutil/`shutil.disk_usage` sont
reellement appeles), avec des sondes de `nvidia-smi` simulees pour couvrir
les cas qu'aucune machine de developpement ne peut fournir.
"""
import subprocess
from pathlib import Path

from core.production import materiel


class TestMesurerGpu:
    def test_sans_nvidia_smi_rend_none(self, monkeypatch):
        """Vrai sur cette machine de developpement : pas de carte NVIDIA
        visible. `mesurer_gpu()` doit le dire honnetement, jamais deviner."""
        assert materiel.mesurer_gpu() is None

    def test_nvidia_smi_absent_du_path_ne_leve_pas(self, monkeypatch):
        def _leve(*a, **k):
            raise FileNotFoundError("nvidia-smi introuvable")
        monkeypatch.setattr(subprocess, "run", _leve)
        assert materiel.mesurer_gpu() is None

    def test_nvidia_smi_qui_gele_ne_bloque_pas(self, monkeypatch):
        def _timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5.0)
        monkeypatch.setattr(subprocess, "run", _timeout)
        assert materiel.mesurer_gpu() is None

    def test_reponse_reelle_de_nvidia_smi_est_bien_lue(self, monkeypatch):
        """La forme exacte que `nvidia-smi --query-gpu=... --format=csv,
        noheader,nounits` rend reellement (mesuree sur une machine qui en a
        une) : `Nom, total, libre`."""
        class FauxResultat:
            returncode = 0
            stdout = "NVIDIA RTX A2000, 12288, 11453\n"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: FauxResultat())

        gpu = materiel.mesurer_gpu()

        assert gpu is not None
        assert gpu.nom == "NVIDIA RTX A2000"
        assert gpu.vram_totale_mo == 12288
        assert gpu.vram_libre_mo == 11453
        assert gpu.mesure_le

    def test_code_de_retour_non_nul_rend_none(self, monkeypatch):
        class FauxResultat:
            returncode = 1
            stdout = ""
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: FauxResultat())
        assert materiel.mesurer_gpu() is None

    def test_sortie_illisible_rend_none_jamais_une_exception(self, monkeypatch):
        class FauxResultat:
            returncode = 0
            stdout = "quelque chose d'inattendu"
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: FauxResultat())
        assert materiel.mesurer_gpu() is None


class TestMesurerRam:
    def test_mesure_reelle_sur_cette_machine(self):
        """`psutil` est reellement appele — pas de simulation ici."""
        ram = materiel.mesurer_ram()

        assert ram is not None
        assert ram.totale_mo > 0
        assert 0 <= ram.disponible_mo <= ram.totale_mo
        assert ram.mesure_le

    def test_psutil_absent_rend_none_jamais_une_exception(self, monkeypatch):
        import builtins
        reel_import = builtins.__import__

        def _import_sans_psutil(nom, *args, **kwargs):
            if nom == "psutil":
                raise ImportError("psutil non installe")
            return reel_import(nom, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _import_sans_psutil)
        assert materiel.mesurer_ram() is None


class TestMesurerDisque:
    def test_mesure_reelle_sur_un_dossier_existant(self, tmp_path):
        disque = materiel.mesurer_disque(tmp_path)

        assert disque is not None
        assert disque.libre_mo > 0
        assert disque.chemin == str(tmp_path)

    def test_chemin_pas_encore_cree_mesure_son_parent_existant(self, tmp_path):
        futur = tmp_path / "pas-encore-cree" / "encore-un-niveau"
        disque = materiel.mesurer_disque(futur)

        assert disque is not None
        assert disque.libre_mo > 0

    def test_chemin_profondement_absent_remonte_jusqu_a_un_parent_existant(self):
        """Aucun des dossiers intermediaires n'existe : la mesure remonte
        jusqu'a `/`, qui existe toujours sur ce systeme — jamais une
        exception, jamais une boucle infinie."""
        chemin_impossible = Path("/n-existe-vraiment-nulle-part-12345/encore/plus/profond")
        disque = materiel.mesurer_disque(chemin_impossible)
        assert disque is not None

    def test_aucun_parent_existant_rend_none_jamais_une_boucle(self, monkeypatch):
        """Mesure defensive pure : meme si `Path.exists()` ne rendait jamais
        vrai (systeme de fichiers hostile/simule), la remontee doit
        s'arreter et rendre `None`, jamais tourner indefiniment."""
        monkeypatch.setattr(Path, "exists", lambda self: False)
        disque = materiel.mesurer_disque(Path("/quelque/chose"))
        assert disque is None
