"""Joue cinq conversations fictives sur un serveur MindSight déjà lancé."""

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCENARIOS = {
    "réponses courtes": ("Un galet", "Gris", "Lisse", "Une rivière", "Je ne sais pas"),
    "ressenti nommé": (
        "Un galet au fond d’une rivière. Le courant me calme.",
        "Je pense au bruit de l’eau.", "Ça me rappelle mon enfance.",
        "J’éprouve de la nostalgie.", "Je préfère rester sur cette image.",
    ),
    "description seule": (
        "Une pierre carrée.", "Elle est noire.", "Elle tient dans la main.",
        "Je la vois sur une table.", "Je ne lui imagine pas d’histoire.",
    ),
    "refus et corrections": (
        "Une pierre blanche.", "En fait, elle est noire.",
        "Je préfère passer cette question.", "Elle est dans ma poche.",
        "Je ne ressens rien de particulier.",
    ),
    "image inattendue": (
        "Un caillou creux, avec une toute petite porte.",
        "Je ne sais pas ce qu’il y a derrière.", "Je la laisse fermée.",
        "La porte est bleue.", "Je préfère décider plus tard.",
    ),
}


def request(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    query = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(query, timeout=75) as response:
        return json.load(response)


def run(base_url):
    opening = request(f"{base_url}/api/conversation/opening")
    for scenario, answers in SCENARIOS.items():
        history = [opening]
        for turn, answer in enumerate(answers, start=1):
            question = history[-1]["content"]
            history.append({"role": "user", "content": answer})
            result = request(f"{base_url}/api/conversation/turn", {"messages": history})
            print(json.dumps({
                "scenario": scenario, "turn": turn, "question": question,
                "answer": answer, **result,
            }, ensure_ascii=False), flush=True)
            history.append({"role": "assistant", "content": result["reply"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        run(args.url.rstrip("/"))
    except HTTPError as error:
        detail = json.load(error).get("detail", error.reason)
        parser.exit(1, f"Le serveur a renvoyé HTTP {error.code} : {detail}\n")
    except (URLError, TimeoutError) as error:
        parser.exit(1, f"Connexion à MindSight impossible : {error}\n")
