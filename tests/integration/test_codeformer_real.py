"""Smoke test opt-in avec les vrais poids CodeFormer (jamais simule)."""
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from core.restoration.codeformer import ConfigurationCodeFormer, ServiceCodeFormer

pytestmark = pytest.mark.integration


async def test_codeformer_restaure_reellement_une_image(tmp_path):
    if os.getenv("RUN_CODEFORMER_SMOKE") != "1":
        pytest.skip("RUN_CODEFORMER_SMOKE=1 n'est pas active")
    configuration = ConfigurationCodeFormer.depuis_environnement(tmp_path / "restorations")
    service = ServiceCodeFormer(configuration)
    etat = service.etat()
    if not etat.disponible:
        pytest.fail(f"Smoke demande mais CodeFormer indisponible : {etat.raison}")

    tampon = io.BytesIO()
    Image.effect_noise((128, 128), 60).convert("RGB").save(tampon, format="PNG")
    resultat = await service.restaurer(tampon.getvalue(), nom_source="smoke.png")

    assert resultat.sortie.is_file()
    assert resultat.sortie.parent == Path(configuration.sorties)
    with Image.open(resultat.sortie) as rendu:
        rendu.verify()
