#!/bin/sh
# Point d'entree du conteneur ARENA — VOLET « ARENA en ligne », phase 3.2.
#
# Mesure du 30/08/2026 : `USER arena` (phase 3.1) casse au premier demarrage
# des que `data/` est monte en volume (`deploy/docker-compose.yml`), avec
# exactement cette trace :
#
#   PermissionError: [Errno 13] Permission denied: '/app/data/rag'
#
# Un volume monte depuis l'hote arrive avec les permissions de l'hote — le
# plus souvent root:root — et les recouvre entierement : rien dans l'image ne
# peut les changer a l'avance, parce que le contenu de l'image a cet endroit
# n'existe plus une fois le volume monte.
#
# Ce script tourne donc AVANT `USER arena` (le conteneur demarre root le
# temps de ces deux lignes, jamais plus), donne `data/` et `media/` a
# l'utilisateur `arena`, puis lui passe la main avec `gosu` — qui ne revient
# jamais en root ensuite, contrairement a `sudo`.
set -e

chown -R arena:arena /app/data /app/media

exec gosu arena "$@"
