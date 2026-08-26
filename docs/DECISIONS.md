# REGISTRE DES DÉCISIONS ARCHITECTURALES (ADR)

## DEC-0001 : Arborescence complète unifiée dès la Phase 0
- Décision : Adopter l'arborescence complète dès le premier jour.

## DEC-0002 : Local-First strict
- Décision : Moteur de réflexion Qwen 3.5:9b sur Ollama / RTX A2000, Transcription Whisper locale, FFmpeg local. Aucune dépendance obligatoire à une API cloud payante.

## DEC-0003 : Sécurité des Publications
- Décision : Par défaut, `PUBLISH=False` et `DELETE=False`. Toute tentative de publication passe en mode Simulation avec génération de brouillons.

## DEC-0004 : Sans bac à sable, l'exécution de code est refusée
- Décision (26/08/2026) : si Docker est indisponible, `SandboxInterpreterTool`
  refuse d'exécuter (`sandbox_mode: REFUSED`) au lieu de basculer sur la machine.
  Le repli reste possible derrière `ALLOW_UNSAFE_EXEC=true`, posé explicitement.
- Pourquoi : le repli silencieux annulait toute la protection. Une autorisation
  ne se devine pas — toute valeur non reconnue vaut « non ».
- Coût si c'est faux : `CoderAgent` et `ReasoningEngine` ne fonctionnent plus
  quand Docker est arrêté. C'est délibéré : mieux vaut une capacité indisponible
  qu'une capacité dangereuse.

## DEC-0005 : Licence propriétaire, tous droits réservés
- Décision (26/08/2026, propriétaire) : le code n'est réutilisable par personne
  pour l'instant. Voir `LICENSE`.
- Coût si c'est faux : aucune contribution extérieure possible. À revoir si le
  projet doit s'ouvrir.
- Réserve : une licence interdit, elle n'empêche pas. Un dépôt public reste
  lisible et copiable ; seul le passage en privé bloque réellement.
