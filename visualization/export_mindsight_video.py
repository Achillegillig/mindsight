"""Exporter un aller-retour par dimension ou la révélation MindSight en MP4."""

import argparse
from contextlib import contextmanager
from math import cos, isfinite, pi
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from time import sleep

if __package__:
    from .mindsight_opengl import (
        DEFAULT_STRANDS, IDLE, LABELS, REVEAL_BACKGROUND, ProfileGauges, Renderer, create_window, gl,
    )
    from .portrait_soundtrack import REVEAL_HOLD, REVEAL_TAIL, SOUNDTRACK_START, find_soundtrack
else:
    from mindsight_opengl import (
        DEFAULT_STRANDS, IDLE, LABELS, REVEAL_BACKGROUND, ProfileGauges, Renderer, create_window, gl,
    )
    from portrait_soundtrack import REVEAL_HOLD, REVEAL_TAIL, SOUNDTRACK_START, find_soundtrack

from pyglet import graphics, shapes, text, window
from pyglet.math import Mat4


TURNS = (0.0, 1.0, 0.0)
REVEAL_DURATION = REVEAL_HOLD + REVEAL_TAIL


def level_at_frame(frame, ramp_frames, hold_frames):
    leg, offset = divmod(frame, ramp_frames + hold_frames)
    start = TURNS[leg]
    if offset < hold_frames or leg == len(TURNS) - 1:
        return start
    fraction = (offset - hold_frames + 1) / ramp_frames
    eased = (1.0 - cos(pi * fraction)) / 2.0
    return start + (TURNS[leg + 1] - start) * eased


class Gauge:
    def __init__(self, width, height):
        scale = min(width / 1280, height / 720)
        left = round(34 * scale)
        bottom = height - round(132 * scale)
        self.rail_x = left + 22 * scale
        self.rail_y = bottom + 24 * scale
        self.rail_width = 292 * scale
        panel_right = left + 336 * scale
        self.batch = graphics.Batch()
        layers = [graphics.Group(order=i) for i in range(4)]
        self.panel = shapes.RoundedRectangle(
            left, bottom, 336 * scale, 98 * scale, radius=13 * scale,
            color=(16, 28, 35, 245), batch=self.batch, group=layers[0],
        )
        self.rail = shapes.RoundedRectangle(
            self.rail_x, self.rail_y - 2.5 * scale, self.rail_width, 5 * scale, radius=2.5 * scale,
            color=(80, 99, 105), batch=self.batch, group=layers[1],
        )
        self.fill = shapes.Rectangle(
            self.rail_x, self.rail_y - 2.5 * scale, 0, 5 * scale,
            color=(250, 203, 127), batch=self.batch, group=layers[2],
        )
        self.knob = shapes.Circle(
            self.rail_x, self.rail_y, 6.5 * scale,
            color=(250, 203, 127), batch=self.batch, group=layers[3],
        )
        font = ["Segoe UI", "DejaVu Sans", "Arial"]
        self.name = text.Label(
            x=self.rail_x, y=bottom + 61 * scale, anchor_y="center",
            font_name=font, font_size=20 * scale, weight="bold", dpi=96,
            color=(250, 249, 244, 255), batch=self.batch, group=layers[3],
        )
        self.value = text.Label(
            x=panel_right - 22 * scale, y=bottom + 61 * scale, anchor_x="right", anchor_y="center",
            font_name=font, font_size=12 * scale, dpi=96,
            color=(250, 203, 127, 255), batch=self.batch, group=layers[3],
        )

    def draw(self, level):
        self.fill.width = self.rail_width * level
        self.knob.x = self.rail_x + self.fill.width
        label = f"{10 * level:.1f} / 10".replace(".", ",")
        if self.value.text != label:
            self.value.text = label
        self.batch.draw()

    def close(self):
        for item in (self.panel, self.rail, self.fill, self.knob, self.name, self.value):
            item.delete()


@contextmanager
def capture_frames(video, size):
    width, height = size
    surface = create_window(width, height, visible=False, vsync=False)
    try:
        framebuffer = surface.get_framebuffer_size()
        if framebuffer[0] < width or framebuffer[1] < height:
            raise RuntimeError(f"Tampon OpenGL trop petit pour {width} × {height}. Essaie --size 1280x720.")
        surface.projection = Mat4.orthogonal_projection(0, width, 0, height, -1, 1)
        gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)
        pixels = (gl.GLubyte * (width * height * 3))()
        pixel_bytes = memoryview(pixels).cast("B")

        def write_frame():
            gl.glReadBuffer(gl.GL_BACK)
            gl.glReadPixels(0, 0, width, height, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, pixels)
            video.write(pixel_bytes)

        yield write_frame
    finally:
        surface.close()


def render_frames(video, size, fps, ramp_frames, hold_frames):
    frame_count = (len(TURNS) - 1) * (ramp_frames + hold_frames) + hold_frames
    with capture_frames(video, size) as write_frame:
        gauge = Gauge(*size)
        try:
            for dimension, label in enumerate(LABELS):
                print(f"[{dimension + 1}/{len(LABELS)}] {label}", flush=True)
                gauge.name.text = label
                renderer = Renderer(DEFAULT_STRANDS)
                try:
                    levels = list(IDLE)
                    for frame in range(frame_count):
                        level = level_at_frame(frame, ramp_frames, hold_frames)
                        levels[dimension] = level
                        # La rampe est déjà lissée. Le curseur montre la valeur appliquée au GPU.
                        renderer.levels[:] = levels
                        renderer.advance(1 / fps, levels)
                        renderer.draw(*size)
                        gauge.draw(level)
                        write_frame()
                finally:
                    renderer.close()
        finally:
            gauge.close()


def render_reveal(video, size, fps, profile):
    with capture_frames(video, size) as write_frame:
        gauges = ProfileGauges(*size, profile)
        try:
            renderer = Renderer(flow=0.0)
            try:
                for frame in range(round(REVEAL_DURATION * fps)):
                    elapsed = frame / fps
                    renderer.advance_reveal(1 / fps, elapsed - REVEAL_HOLD, profile)
                    renderer.draw(*size, background=REVEAL_BACKGROUND)
                    if elapsed < REVEAL_HOLD:
                        gauges.draw(elapsed)
                    write_frame()
            finally:
                renderer.close()
        finally:
            gauges.close()


def publish_video(encoded, destination, *, overwrite):
    if os.name != "nt" and not overwrite:
        # Sous POSIX, rename remplacerait une destination créée pendant le rendu.
        destination.hardlink_to(encoded)
        return
    move = encoded.replace if overwrite else encoded.rename
    for attempt in range(20):
        try:
            move(destination)
            return
        except OSError as error:
            # Sous Windows, un fichier tout juste encodé peut rester brièvement verrouillé.
            if getattr(error, "winerror", None) not in (32, 33) or attempt == 19:
                raise
            sleep(0.25)


def soundtrack_for(args):
    if args.reveal is None or args.silent:
        return None
    if args.soundtrack is not None:
        if not args.soundtrack.is_file():
            raise FileNotFoundError(f"Piste audio introuvable. {args.soundtrack}")
        return args.soundtrack.resolve()
    return find_soundtrack()


def export(args, ffmpeg):
    destination = args.output.resolve()
    if destination.exists() and not args.overwrite:
        raise FileExistsError(f"{destination} existe déjà. Choisis un autre chemin ou ajoute --overwrite.")
    soundtrack = soundtrack_for(args)
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = args.size
    ramp_frames = round(args.ramp_seconds * args.fps)
    hold_frames = round(0.6 * args.fps)

    with tempfile.TemporaryDirectory(prefix="mindsight-video-", dir=destination.parent) as staging:
        encoded = Path(staging) / "export.mp4"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
            "-framerate", str(args.fps), "-i", "pipe:0",
        ]
        if soundtrack is not None:
            command.extend(("-ss", str(SOUNDTRACK_START), "-i", str(soundtrack), "-map", "0:v:0", "-map", "1:a:0",
                            "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-shortest"))
        command.extend((
            "-vf", "vflip,scale=out_color_matrix=bt709:out_range=tv",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709", "-colorspace", "bt709", "-color_trc", "iec61966-2-1",
            "-color_range", "tv", "-movflags", "+faststart", str(encoded),
        ))
        with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
            try:
                if args.reveal is None:
                    render_frames(encoder.stdin, args.size, args.fps, ramp_frames, hold_frames)
                else:
                    render_reveal(encoder.stdin, args.size, args.fps, tuple(score / 10 for score in args.reveal))
                encoder.stdin.close()
                if encoder.wait() != 0:
                    raise RuntimeError("FFmpeg n’a pas pu encoder la vidéo.")
            except BaseException:
                if encoder.poll() is None:
                    encoder.kill()
                encoder.wait()
                raise
        publish_video(encoded, destination, overwrite=args.overwrite)
    return destination


def video_size(value):
    try:
        width, height = map(int, value.lower().split("x"))
    except ValueError:
        width, height = 0, 0
    if not (480 <= width <= 3840 and 270 <= height <= 2160 and width % 2 == height % 2 == 0):
        raise argparse.ArgumentTypeError("Utilise deux dimensions paires entre 480x270 et 3840x2160.")
    return width, height


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("mindsight-dimensions.mp4"))
    parser.add_argument("--size", type=video_size, default=(1280, 720), help="Résolution, par défaut 1280x720.")
    parser.add_argument("--fps", type=int, default=30, help="Images par seconde, par défaut 30.")
    parser.add_argument("--ramp-seconds", type=float, default=3.0, help="Durée d’un trajet de 0 à 10, en secondes.")
    parser.add_argument("--reveal", type=float, nargs=len(LABELS), metavar="SCORE",
                        help=f"Exporter la révélation de {REVEAL_DURATION:g} s, dont {REVEAL_HOLD:g} s de cercle, "
                             "à partir de six valeurs sur 10 dans l’ordre des dimensions.")
    audio = parser.add_mutually_exclusive_group()
    audio.add_argument("--soundtrack", type=Path, help="Utiliser cette piste pour --reveal à partir de 14 min 40 s.")
    audio.add_argument("--silent", action="store_true", help="Exporter une révélation silencieuse.")
    parser.add_argument("--overwrite", action="store_true", help="Remplacer le fichier MP4 de destination.")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".mp4":
        parser.error("Le chemin de sortie doit se terminer par .mp4.")
    if not 12 <= args.fps <= 120:
        parser.error("La cadence doit être comprise entre 12 et 120 images par seconde.")
    if not isfinite(args.ramp_seconds) or not 0.25 <= args.ramp_seconds <= 60:
        parser.error("La durée d’un trajet doit être comprise entre 0,25 et 60 secondes.")
    if args.reveal is not None and any(not 0 <= score <= 10 for score in args.reveal):
        parser.error("Les six scores de révélation doivent être compris entre 0 et 10.")
    if args.reveal is None and args.soundtrack is not None:
        parser.error("--soundtrack nécessite --reveal. Les exemples par dimension sont silencieux.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        parser.error("Installe FFmpeg et rends la commande ffmpeg accessible dans le PATH.")
    try:
        destination = export(args, ffmpeg)
    except KeyboardInterrupt:
        parser.exit(130, "Export interrompu.\n")
    except (OSError, RuntimeError, ValueError, window.WindowException, gl.GLException) as error:
        parser.exit(1, f"Export MindSight : {error}\n")
    print(f"Vidéo exportée dans {destination}")


if __name__ == "__main__":
    main()
