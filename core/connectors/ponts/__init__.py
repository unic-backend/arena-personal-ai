"""Ponts vers des moteurs externes : code ARENA, execute par LEUR interpreteur.

Un pont n'est pas une copie. Il importe le moteur au moment de tourner, dans
son propre environnement, et rend du JSON. La frontiere reste un **processus
separe** — la regle du depot pour tout moteur externe (DEC-0027, VoiceStudio ;
`.gitignore`, Xaar Kaname).
"""
