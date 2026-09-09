"""La capacité `pdf` — fusionner, scinder, réordonner, supprimer/extraire
des pages, pivoter, extraire texte/images, lire et écrire un manifeste
PDFx (`Hyacinthe... non — AlexandrosGounis/pdfx`, MIT).

Mission « PDFx » (09/09/2026) — voir `docs/audits/pdfx_audit.md`. Un seul
moteur, `pypdf` — déjà une dépendance ARENA (lecture, `tools/documents/
reader.py`) — étendu à l'écriture. Jamais un deuxième moteur PDF : pas de
PyMuPDF, pas de pdf-lib, pas d'Electron dans le cœur d'ARENA.
"""
