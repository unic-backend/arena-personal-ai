@echo off
REM Double-clic : lance ARENA en entier (serveur + tunnel + QR de l'adresse).
REM Le travail est dans scripts\lancer_arena.ps1 ; ce fichier n'existe que pour
REM pouvoir le lancer d'un double-clic depuis l'explorateur Windows.
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0scripts\lancer_arena.ps1"