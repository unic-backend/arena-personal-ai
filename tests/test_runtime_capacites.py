"""Le cablage reel du registre de capacites (VOLET « espaces separes », phase 3).

`tests/core/test_capacites.py` verifie le mecanisme avec des doubles ; celui-ci
verifie que `apps/backend/runtime.py` — le seul endroit ou les agents et le
registre existent ensemble — l'a effectivement rempli avec les CINQ vrais
agents deja construits, pas des doublons ni un sous-ensemble oublie.
"""
from apps.backend.runtime import (
    capacites,
    coder_agent,
    fresh_agent,
    plaquiste_agent,
    video_agent,
)


def test_les_cinq_espaces_route_par_l_orchestrateur_sont_enregistres():
    """Les memes identifiants que `INTENTION_PAR_ESPACE` cote orchestrateur."""
    assert sorted(capacites.espaces()) == ["code", "documents", "plaquiste", "video", "web"]


def test_chaque_espace_pointe_vers_l_agent_reellement_utilise_ailleurs():
    """Pas un agent recree pour l'occasion : le meme objet que `dispatch_request` appelle."""
    assert capacites._capacites["code"] is coder_agent
    assert capacites._capacites["plaquiste"] is plaquiste_agent
    assert capacites._capacites["video"] is video_agent
    assert capacites._capacites["web"] is fresh_agent


async def test_l_espace_documents_est_appelable_avec_le_meme_contrat():
    """L'adaptateur autour de LightRAGTool.query() doit rendre {status, agent, response}."""
    resultat = await capacites.demander("documents", "question de test")

    assert resultat["status"] == "success"
    assert "response" in resultat
