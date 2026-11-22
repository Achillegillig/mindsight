"""Repères musicaux communs au portrait en direct et à l’export."""

from pathlib import Path


VIDEO_DIRECTORY = Path(__file__).resolve().parents[1] / "videos"
SOUNDTRACK_START = 14 * 60 + 40
SOUNDTRACK_DROP = 15 * 60 + 10
REVEAL_HOLD = SOUNDTRACK_DROP - SOUNDTRACK_START
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}


def find_soundtrack():
    folders = (
        VIDEO_DIRECTORY / "soundtrack",
        VIDEO_DIRECTORY.parent / "soundtrack",
        VIDEO_DIRECTORY / "soundrack",
        VIDEO_DIRECTORY.parent,
    )
    for folder in folders:
        if not folder.is_dir():
            continue
        tracks = [track for track in folder.iterdir() if track.is_file() and track.suffix.lower() in AUDIO_EXTENSIONS]
        if len(tracks) > 1:
            raise ValueError(f"Plusieurs pistes dans {folder}. Choisis le fichier avec --soundtrack.")
        if tracks:
            return tracks[0].resolve()
    raise FileNotFoundError("Place la piste à la racine du projet ou dans videos/soundtrack.")
