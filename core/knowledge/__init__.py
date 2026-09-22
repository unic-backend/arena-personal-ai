"""Knowledge Vault local d'ARENA.

Le contenu vivant du vault reste dans data/knowledge_vault/ et n'entre jamais
dans Git. Le paquet expose seulement le moteur et ses contrats.
"""

from core.knowledge.vault import KnowledgeVault, LintReport, SearchHit

__all__ = ["KnowledgeVault", "LintReport", "SearchHit"]
