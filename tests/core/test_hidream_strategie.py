"""`core/production/hidream_strategie.py` — mission ARENA x HIDREAM-I1
(DEC-0085).

Le coeur de la mission §33 : une classification A/B/C/D/E qui vient d'un
CALCUL verifiable, jamais d'une estimation a l'oeil. Chaque test construit
un materiel EXPLICITE — jamais une vraie carte, cette suite tourne sans GPU
— et verifie que le seuil documente produit bien la decision attendue.
"""
from core.production.hidream_strategie import (
    PROFILS,
    StrategieHiDream,
    decider_strategie,
)
from core.production.materiel import EtatDisque, EtatGpu, EtatRam

DISQUE_LARGE = EtatDisque(chemin="/data", libre_mo=500 * 1024, mesure_le="x")
DISQUE_ETROIT = EtatDisque(chemin="/data", libre_mo=10 * 1024, mesure_le="x")


class TestMaterielReelDuProprietaire:
    """RTX A2000 12 Go + 32 Go RAM — le materiel MESURE de ce projet (voir
    docs/audits/hidream_i1_audit.md). Aucune des trois variantes ne doit
    tenir localement : la RAM systeme (32 Go) est deja plus petite que les
    ~63 Go que chaque variante charge."""

    GPU = EtatGpu(nom="NVIDIA RTX A2000", vram_totale_mo=12288, vram_libre_mo=11500, mesure_le="x")
    RAM = EtatRam(totale_mo=32768, disponible_mo=28000, mesure_le="x")

    def test_aucune_variante_ne_tient_localement_sans_worker_distant(self):
        for nom in ("full", "dev", "fast"):
            decision = decider_strategie(PROFILS[nom], self.GPU, self.RAM, DISQUE_LARGE)
            assert decision.strategie is StrategieHiDream.UNSUPPORTED, (
                f"{nom} : {decision.strategie.value} — {decision.raison}")
            assert decision.raison  # jamais un label seul

    def test_un_worker_distant_configure_devient_le_recours(self):
        decision = decider_strategie(
            PROFILS["fast"], self.GPU, self.RAM, DISQUE_LARGE, worker_distant_configure=True)
        assert decision.strategie is StrategieHiDream.REMOTE_REQUIRED
        assert "distant" in decision.raison


class TestLocalFull:
    def test_une_carte_assez_grande_choisit_local_full(self):
        gpu = EtatGpu(nom="H100", vram_totale_mo=80 * 1024, vram_libre_mo=75 * 1024, mesure_le="x")
        ram = EtatRam(totale_mo=64 * 1024, disponible_mo=50 * 1024, mesure_le="x")

        decision = decider_strategie(PROFILS["fast"], gpu, ram, DISQUE_LARGE)

        assert decision.strategie is StrategieHiDream.LOCAL_FULL
        assert "H100" in decision.raison

    def test_juste_en_dessous_du_seuil_bf16_ne_choisit_pas_local_full(self):
        """La marge de securite (85 %) est appliquee, pas seulement la VRAM
        totale — une carte tout juste suffisante « sur le papier » ne doit
        pas etre retenue sans marge."""
        profil = PROFILS["fast"]
        vram_pile_juste_mo = int(profil.vram_go_bf16 * 1024)
        gpu = EtatGpu(nom="Carte limite", vram_totale_mo=vram_pile_juste_mo,
                     vram_libre_mo=vram_pile_juste_mo, mesure_le="x")
        ram = EtatRam(totale_mo=128 * 1024, disponible_mo=100 * 1024, mesure_le="x")

        decision = decider_strategie(profil, gpu, ram, DISQUE_LARGE)

        assert decision.strategie is not StrategieHiDream.LOCAL_FULL


class TestLocalOffload:
    def test_grosse_ram_petite_vram_choisit_offload(self):
        """VRAM insuffisante meme quantifiee, mais assez de RAM pour porter
        les poids decharges : la seule strategie qui tient."""
        gpu = EtatGpu(nom="RTX A2000", vram_totale_mo=12288, vram_libre_mo=11500, mesure_le="x")
        ram = EtatRam(totale_mo=96 * 1024, disponible_mo=80 * 1024, mesure_le="x")

        decision = decider_strategie(PROFILS["fast"], gpu, ram, DISQUE_LARGE)

        assert decision.strategie is StrategieHiDream.LOCAL_OFFLOAD
        assert "offload" in decision.raison.lower()


class TestDisque:
    def test_disque_insuffisant_refuse_avant_tout_calcul_vram(self):
        gpu = EtatGpu(nom="H100", vram_totale_mo=80 * 1024, vram_libre_mo=75 * 1024, mesure_le="x")
        ram = EtatRam(totale_mo=128 * 1024, disponible_mo=100 * 1024, mesure_le="x")

        decision = decider_strategie(PROFILS["fast"], gpu, ram, DISQUE_ETROIT)

        assert decision.strategie is StrategieHiDream.UNSUPPORTED
        assert "disque" in decision.raison.lower()

    def test_disque_non_mesurable_est_unsupported(self):
        gpu = EtatGpu(nom="H100", vram_totale_mo=80 * 1024, vram_libre_mo=75 * 1024, mesure_le="x")
        ram = EtatRam(totale_mo=128 * 1024, disponible_mo=100 * 1024, mesure_le="x")

        decision = decider_strategie(PROFILS["fast"], gpu, ram, None)

        assert decision.strategie is StrategieHiDream.UNSUPPORTED
        assert "disque" in decision.raison.lower()


class TestMaterielAbsent:
    def test_aucun_gpu_visible_et_aucun_worker_distant_est_unsupported(self):
        ram = EtatRam(totale_mo=128 * 1024, disponible_mo=100 * 1024, mesure_le="x")
        decision = decider_strategie(PROFILS["fast"], None, ram, DISQUE_LARGE)

        assert decision.strategie is StrategieHiDream.UNSUPPORTED
        assert "aucune carte nvidia" in decision.raison.lower()

    def test_ram_non_mesurable_est_unsupported(self):
        gpu = EtatGpu(nom="H100", vram_totale_mo=80 * 1024, vram_libre_mo=75 * 1024, mesure_le="x")
        decision = decider_strategie(PROFILS["fast"], gpu, None, DISQUE_LARGE)

        assert decision.strategie is StrategieHiDream.UNSUPPORTED
        assert "ram" in decision.raison.lower()


class TestProfils:
    def test_les_trois_variantes_publiees_ont_un_profil(self):
        assert set(PROFILS) == {"full", "dev", "fast"}

    def test_le_diviseur_de_quantification_est_documente_pas_optimiste(self):
        """3.5, pas 4 : VAE et normalisations restent en precision plus
        haute (voir le docstring du module)."""
        profil = PROFILS["full"]
        assert profil.vram_go_quantifie_estime < profil.vram_go_bf16 / 3
