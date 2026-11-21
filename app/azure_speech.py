"""Synthèse vocale Azure via l’API REST."""

import re
from socket import gaierror
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, tostring

DEFAULT_VOICE = "fr-FR-Soleil:MAI-Voice-2.1-Flash"
DEFAULT_STYLE = "softvoice"


class SpeechError(RuntimeError):
    pass


def synthesize(api_key, region, voice, text, *, style=None):
    if not re.fullmatch(r"[a-z][a-z0-9]{1,39}", region):
        raise SpeechError("Région Azure Speech invalide.")

    document = Element("speak", {
        "version": "1.0",
        "xmlns": "http://www.w3.org/2001/10/synthesis",
        "xml:lang": "fr-FR",
    })
    voice_element = SubElement(document, "voice", {"name": voice})
    if style:
        document.set("xmlns:mstts", "http://www.w3.org/2001/mstts")
        SubElement(voice_element, "mstts:express-as", {"style": style}).text = text
    else:
        voice_element.text = text
    audio_format = (
        "audio-24khz-160kbitrate-mono-mp3"
        if ":MAI-Voice-" in voice
        else "audio-24khz-48kbitrate-mono-mp3"
    )
    request = Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=tostring(document, encoding="utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": audio_format,
            "User-Agent": "MindSight",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                raise SpeechError(f"Azure Speech a renvoyé HTTP {response.status}.")
            audio = response.read()
    except HTTPError as error:
        if error.code in (401, 403):
            raise SpeechError(
                f"Azure Speech a refusé la clé ou l’accès dans la région {region} (HTTP {error.code})."
            ) from error
        raise SpeechError(f"Azure Speech a renvoyé HTTP {error.code}.") from error
    except OSError as error:
        reason = error.reason if isinstance(error, URLError) else error
        if isinstance(reason, gaierror):
            raise SpeechError(f"Résolution DNS impossible pour le service Azure Speech ({region}).") from error
        if isinstance(reason, TimeoutError):
            raise SpeechError("Azure Speech n’a pas répondu à temps.") from error
        raise SpeechError("Connexion à Azure Speech impossible.") from error

    if not audio:
        raise SpeechError("Azure Speech a renvoyé un audio vide.")
    return audio
