# Image du bac a sable ARENA
# Boite isolee dans laquelle le code genere par l IA est execute,
# sans acces au disque de Saer ni a Internet.

FROM python:3.11-slim

# Outils de calcul dont le ReasoningEngine a besoin
RUN pip install --no-cache-dir sympy numpy

WORKDIR /app

CMD ["python", "--version"]
