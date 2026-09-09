"""La capacité `file_organization` — inspecter, planifier, valider, appliquer,
annuler : le classement de fichiers, jamais un deuxième moteur de fichiers.

Mission « AI File Sorter » (09/09/2026) — voir `docs/audits/
ai_file_sorter_audit.md`. Toute mutation réelle passe par
`tools/atelier/atelier.py` (DEC-0038, déjà la seule main d'ARENA sur le
filesystem) : ce paquet ne fait que décider QUOI faire et le VALIDER avant
de le faire — jamais comment toucher un fichier, Atelier le sait déjà.
"""
