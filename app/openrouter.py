import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

HTTP_ERRORS = {
    401: "Clé OpenRouter invalide.",
    402: "Crédit OpenRouter insuffisant.",
    403: "OpenRouter a refusé la requête. Vérifie les permissions de la clé.",
    404: "Ce modèle n’est pas disponible sur OpenRouter.",
    429: "Limite OpenRouter atteinte. Réessaie dans un moment.",
}


class OpenRouterError(RuntimeError):
    pass


def generate_reply(api_key, model, system_prompt, messages, *, json_output=False, timeout=60):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        "stream": False,
        "reasoning": {"enabled": False},
        "max_tokens": 512,
    }
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    request = Request(
        CHAT_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        raise OpenRouterError(
            HTTP_ERRORS.get(error.code, f"OpenRouter a renvoyé une erreur HTTP {error.code}.")
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise OpenRouterError("OpenRouter ne répond pas. Vérifie ta connexion et réessaie.") from error
    except ValueError as error:
        raise OpenRouterError("OpenRouter a renvoyé une réponse illisible.") from error

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise OpenRouterError("OpenRouter n’a pas fourni de relance.") from error
    if not isinstance(content, str) or not content.strip():
        raise OpenRouterError("Le modèle a renvoyé une relance vide.")
    return content.strip()
