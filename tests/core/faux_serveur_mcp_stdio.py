"""Un faux serveur MCP, en stdio, pour tester `ClientMcpStdio` sans Node.

Lance en sous-processus par les tests (`[sys.executable, __file__]`), il parle
le protocole minimal que `core/mcp/stdio_transport.py` utilise :
`initialize`, `notifications/initialized`, `tools/list`, `tools/call`. Il
imite deliberement un comportement mesure sur le vrai serveur OpenTakeoff :
une notification sans `id` glissee entre deux reponses, pour verifier que le
client ne la prend jamais pour la reponse qu'il attend.
"""
import json
import sys
import time

#: Le retard de l'outil `tardif`, en secondes. Nomme pour que le test
#: qui l'utilise puisse attendre exactement ce qu'il faut, sans deviner.
RETARD_SECONDES = 1.5


def _ecrire(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main():
    for ligne in sys.stdin:
        ligne = ligne.strip()
        if not ligne:
            continue
        requete = json.loads(ligne)
        methode = requete.get("method")
        id_ = requete.get("id")

        if methode == "initialize":
            _ecrire({"jsonrpc": "2.0", "id": id_,
                     "result": {"protocolVersion": "2025-06-18",
                                "serverInfo": {"name": "faux-opentakeoff", "version": "0"}}})
        elif methode == "notifications/initialized":
            continue  # aucune reponse attendue
        elif methode == "tools/list":
            _ecrire({"jsonrpc": "2.0", "id": id_,
                     "result": {"tools": [{"name": "ping"}, {"name": "erreur"},
                                          {"name": "lent"}, {"name": "tardif"}]}})
        elif methode == "tools/call":
            nom = (requete.get("params") or {}).get("name")
            if nom == "ping":
                # Une notification glissee AVANT la reponse, comme le vrai
                # serveur en emet une apres load_plan (mesure reelle).
                _ecrire({"jsonrpc": "2.0", "method": "notifications/resources/list_changed"})
                _ecrire({"jsonrpc": "2.0", "id": id_, "result": {
                    "structuredContent": (requete.get("params") or {}).get("arguments") or {}}})
            elif nom == "erreur":
                _ecrire({"jsonrpc": "2.0", "id": id_, "result": {
                    "content": [{"type": "text", "text": "erreur applicative simulee"}],
                    "isError": True}})
            elif nom == "lent":
                time.sleep(5)
                _ecrire({"jsonrpc": "2.0", "id": id_, "result": {"structuredContent": {}}})
            elif nom == "tardif":
                # Assez lent pour depasser un petit delai, assez court pour que
                # la reponse arrive PENDANT que le test tourne encore : c'est
                # ce qui permet de verifier qu'une reponse en retard n'est pas
                # servie a l'appel suivant.
                time.sleep(RETARD_SECONDES)
                _ecrire({"jsonrpc": "2.0", "id": id_,
                         "result": {"structuredContent": {"origine": "tardif"}}})
            else:
                _ecrire({"jsonrpc": "2.0", "id": id_, "result": {
                    "content": [{"type": "text", "text": f"outil {nom} introuvable"}],
                    "isError": True}})
        else:
            _ecrire({"jsonrpc": "2.0", "id": id_, "error": {"message": f"methode inconnue : {methode}"}})


if __name__ == "__main__":
    main()
