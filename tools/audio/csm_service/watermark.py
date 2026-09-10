"""Reappliquer le filigrane de Sesame apres une generation Transformers-native.

**Pourquoi ce fichier existe** : `transformers.CsmForConditionalGeneration`
(>= 4.52.1) ne filigrane pas l'audio qu'il produit — verifie directement le
10/09/2026 dans `modeling_csm.py` et `generation_csm.py` du depot
`huggingface/transformers` (branche `main`) : aucune occurrence de
« watermark » ni « silentcipher ». Le runtime ORIGINAL de Sesame
(`SesameAILabs/csm`, `generator.py::Generator.generate`) l'appliquait a
chaque appel, sans exception. Choisir l'implementation Transformers-native
pour ses qualites (mission §8 — maintenue, dependances stables) sans ce
fichier aurait donc **silencieusement retire un filigrane que le depot
d'origine garantit toujours** — exactement ce que la mission interdit
(§12).

**Ce qui est repris, et sous quelle autorite.** La clef publique
`CSM_1B_GH_WATERMARK` est celle que Sesame **publie elle-meme** dans son
propre `watermarking.py` (Apache-2.0), specifiquement pour identifier l'audio
comme produit par CSM-1B — le README du depot le dit explicitement : « If
using CSM 1B in another application, use your own private key [...] »
implique en creux que la clef PUBLIQUE reste correcte pour CSM-1B lui-meme.
C'est exactement notre cas : ce service ne fait tourner rien d'autre que
CSM-1B. Le mecanisme (encoder a 44.1 kHz via `silentcipher`, puis rechantillonner
au debit d'origine) est celui du meme fichier, adapte ici a quelques lignes —
jamais copie tel quel, et attribue dans `NOTICE.md`.
"""
from __future__ import annotations

from typing import List

import torch
import torchaudio

try:
    import silentcipher
except ImportError:  # pragma: no cover — absent tant que l'environnement isole
    # n'est pas installe ; le service le signale via /health plutot que de
    # planter a l'import (meme discipline que le reste d'ARENA : une capacite
    # absente se rapporte, elle ne fait jamais planter le processus).
    silentcipher = None  # type: ignore[assignment]

#: Publiee par Sesame elle-meme pour CSM-1B (SesameAILabs/csm, watermarking.py,
#: commit `daed31e`) — voir la docstring de ce module pour pourquoi elle
#: s'applique ici sans modification.
CSM_1B_GH_WATERMARK: List[int] = [212, 211, 146, 56, 201]

_MODELE_FILIGRANE = None


def disponible() -> bool:
    """`silentcipher` est-il installe dans cet environnement ?"""
    return silentcipher is not None


def _modele(device: str):
    global _MODELE_FILIGRANE
    if _MODELE_FILIGRANE is None:
        _MODELE_FILIGRANE = silentcipher.get_model(model_type="44.1k", device=device)
    return _MODELE_FILIGRANE


@torch.inference_mode()
def appliquer(audio: torch.Tensor, sample_rate: int, device: str) -> tuple[torch.Tensor, int]:
    """Filigrane `audio` (mono, `sample_rate`) avec la clef publique de CSM-1B.

    Raises:
        RuntimeError: `silentcipher` n'est pas installe — jamais un filigrane
            silencieusement saute.
    """
    if not disponible():
        raise RuntimeError(
            "silentcipher n'est pas installe : impossible de filigraner. "
            "Voir tools/audio/csm_service/requirements.txt.")
    modele = _modele(device)
    audio_44k = torchaudio.functional.resample(audio, orig_freq=sample_rate, new_freq=44100)
    encode, _ = modele.encode_wav(audio_44k, 44100, CSM_1B_GH_WATERMARK, calc_sdr=False, message_sdr=36)
    sortie_debit = min(44100, sample_rate)
    encode = torchaudio.functional.resample(encode, orig_freq=44100, new_freq=sortie_debit)
    return encode, sortie_debit
