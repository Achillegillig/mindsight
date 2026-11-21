"""Synthèse et transcription vocales Azure via l’API REST."""

import json
import re
from socket import gaierror
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.etree.ElementTree import Element, SubElement, tostring

DEFAULT_VOICE = "fr-FR-Soleil:MAI-Voice-2.1-Flash"
DEFAULT_STYLE = "softvoice"
MAI_TRANSCRIPTION_MODEL = "MAI-Transcribe-2"


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
    audio = _request_speech(request, region)
    if not audio:
        raise SpeechError("Azure Speech a renvoyé un audio vide.")
    return audio


def transcribe(api_key, region, audio):
    if not re.fullmatch(r"[a-z][a-z0-9]{1,39}", region):
        raise SpeechError("Région Azure Speech invalide.")
    request = Request(
        f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/"
        "cognitiveservices/v1?language=fr-FR&format=simple",
        data=audio,
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        },
    )
    result = _transcription_result(request, region, timeout=15)
    if isinstance(result, dict):
        status = result.get("RecognitionStatus")
        text = result.get("DisplayText")
        if status == "Success" and isinstance(text, str):
            return text.strip()
        if status in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout"):
            return ""
    raise SpeechError("Azure Speech n’a pas pu transcrire cet enregistrement.")


def mai_transcription_url(endpoint):
    if not re.fullmatch(
        r"https://[a-z0-9][a-z0-9-]*\.(?:cognitiveservices\.azure\.com|api\.cognitive\.microsoft\.com)/?",
        endpoint,
        flags=re.IGNORECASE | re.ASCII,
    ):
        raise ValueError(
            "AZURE_SPEECH_ENDPOINT doit contenir l’URL HTTPS Azure Speech sans chemin "
            "(par exemple https://eastus.api.cognitive.microsoft.com)."
        )
    return endpoint.rstrip("/") + "/speechtotext/transcriptions:transcribe?api-version=2025-10-15"


def transcribe_with_mai(api_key, region, url, audio):
    boundary = f"mindsight-{uuid4().hex}"
    definition = json.dumps({
        "locales": ["fr"],
        "enhancedMode": {"enabled": True, "model": MAI_TRANSCRIPTION_MODEL},
    }).encode("utf-8")
    body = b"".join((
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="audio"; filename="dictation.wav"\r\n',
        b"Content-Type: audio/wav\r\n\r\n",
        audio,
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="definition"\r\n\r\n',
        definition,
        f"\r\n--{boundary}--\r\n".encode(),
    ))
    request = Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    })
    request.add_unredirected_header("Ocp-Apim-Subscription-Key", api_key)
    result = _transcription_result(request, region, timeout=30)
    combined = result.get("combinedPhrases") if isinstance(result, dict) else None
    if not isinstance(combined, list):
        raise SpeechError("Réponse de transcription Azure invalide.")
    parts = []
    for phrase in combined:
        if not isinstance(phrase, dict) or not isinstance(phrase.get("text"), str):
            raise SpeechError("Réponse de transcription Azure invalide.")
        parts.append(phrase["text"].strip())
    return " ".join(filter(None, parts))


def _transcription_result(request, region, *, timeout):
    try:
        return json.loads(_request_speech(request, region, timeout=timeout))
    except ValueError as error:
        raise SpeechError("Réponse de transcription Azure invalide.") from error


def _request_speech(request, region, *, timeout=8):
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise SpeechError(f"Azure Speech a renvoyé HTTP {response.status}.")
            return response.read()
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

