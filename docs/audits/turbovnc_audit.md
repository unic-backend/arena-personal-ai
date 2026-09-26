# Audit — TurboVNC (`TurboVNC/turbovnc`)

*Mission ARENA x TURBOVNC — reçue le 25/09/2026. Décision du propriétaire le
même jour : **ne pas intégrer** (DEC-0135). Ce document dit pourquoi, et à
quelles conditions la question se rouvrirait. Aucun code n'a été ajouté.*

## Provenance

| | |
|---|---|
| Dépôt | `https://github.com/TurboVNC/turbovnc` |
| Commit audité | `8ef3739` (21/09/2026, « Server: Assign Xi atoms to keyboard/ptr devices ») |
| Licence | GPL-2.0 (`LICENSE.txt` lu dans le clone) |
| Nature | Serveur VNC (`Xvnc`, dérivé de TightVNC) + visionneuse Java, pour afficher à distance un bureau X11 — pensé pour la 3D avec VirtualGL |

## Ce que TurboVNC est réellement (source lue, pas supposée)

- **Le serveur est Linux/Un*x uniquement.** Le tableau des prérequis du
  projet (doc/sysreq.txt, dans leur dépôt) ne donne une colonne *Host* qu'aux « Linux and
  Other Un*x Operating Systems ». Mac et Windows n'y ont qu'une colonne
  *Client* : sous Windows, TurboVNC **regarde** un bureau distant, il n'en
  sert aucun.
- **Aucune API programmable.** On lance une session par `vncserver`, un
  script Perl (`unix/vncserver.in`, première ligne `#!/usr/bin/env perl`),
  et on la regarde avec un client VNC. Rien à appeler en HTTP, rien qu'un
  connecteur ARENA pourrait interroger comme `core/connectors/case_computer.py`
  interroge Case.
- **La vue web n'est pas incluse.** `-novnc <dossier>` (`unix/vncserver.in`,
  ligne 263 ; doc/usage.txt, ancre noVNC) sert un noVNC **fourni à part**,
  et seulement si TurboVNC a été compilé avec son serveur web — sinon
  « TurboVNC was not built with the noVNC web server. Ignoring -novnc. ».

## Pourquoi il ne colle pas à ARENA aujourd'hui

1. **La machine du propriétaire est sous Windows** (`Lancer_ARENA.bat`,
   PowerShell). Le seul rôle que TurboVNC peut y tenir est celui de client —
   et ARENA n'a pas besoin d'un client VNC : le propriétaire pilote depuis la
   PWA.
2. **L'intégrer tel quel donnerait un connecteur « non configuré » pour
   toujours** : aucun serveur ne pourrait tourner là où ARENA tourne. C'est
   exactement le composant dormant que les missions du propriétaire
   interdisent.
3. **Le seul bureau Linux qu'ARENA pilote déjà est Case** (DEC-0092,
   `core/connectors/case_computer.py`), et ses agents y voient l'écran par
   `capture_ecran` (`GET /computers/{id}/screenshot`). Une vue *en direct* de
   ce bureau depuis le téléphone serait le seul usage réel de TurboVNC — mais
   il se monte **dans l'image Case**, pas dans ARENA, et la question « faut-il
   une vue en direct ? » n'a pas été posée par le besoin.
4. **Licence** : GPL-2.0. Lancer le binaire séparément ne contamine rien ; en
   copier du code dans ARENA le ferait. Aucune des deux options n'a de raison
   d'être aujourd'hui.

## Ce qui rouvrirait la question

- Le propriétaire veut **regarder en direct**, depuis son téléphone, le
  bureau Case pendant qu'un agent y travaille — alors : serveur TurboVNC +
  noVNC dans l'image Case, simple lien dans la PWA, aucun code GPL dans ARENA.
- ARENA tourne un jour sur une machine Linux (ou WSL2) avec une carte
  graphique à partager en 3D (VirtualGL) — le cas pour lequel TurboVNC existe.

Hors de ces deux cas, l'ajouter serait du code mort.
