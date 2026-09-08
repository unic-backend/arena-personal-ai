"""La capacité `file_conversion` — un fichier fourni, converti par le meilleur
moteur réellement disponible sur cette machine.

Voir `docs/audits/file_converter_pro_audit.md` pour la mission, l'audit du
dépôt externe et ce qui a été retenu. Le connecteur (`core/connectors/
file_conversion.py`) est la seule porte d'entrée ; ce paquet ne fait que le
travail : registre des moteurs, garde de sécurité, validation réelle de la
sortie, lot en tâche de fond.
"""
