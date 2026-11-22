"""Portrait génératif MindSight. Depuis la racine du projet :

    python -m visualization.mindsight_opengl --demo
    python -m visualization.mindsight_opengl
    python -m app.main --osc

La dépendance graphique de ce module est pyglet 2.1. Le mode direct reçoit
le pont OSC MindSight. D lance la démo, L reprend le direct, 0–6 isolent
les traits, ↑ et ↓ règlent leur intensité, 7 et 8 testent leurs interactions,
Espace fige et F agrandit.
"""

import argparse
import ctypes as c
from math import exp, isfinite, pi
from pathlib import Path
import re
import socket
import subprocess
import sys

import pyglet

pyglet.options["shadow_window"] = False
from pyglet import gl  # noqa: E402
from pyglet.window import key  # noqa: E402
from pythonosc.dispatcher import Dispatcher  # noqa: E402

if __package__:
    from .mcp_to_osc import DEFAULT_OSC_PORT, PORTRAIT_MAPPING_PATH, load_mapping
    from .touchdesigner_osc_callbacks import ALIASES, TRAITS as OSC_PROFILE
else:
    from mcp_to_osc import DEFAULT_OSC_PORT, PORTRAIT_MAPPING_PATH, load_mapping
    from touchdesigner_osc_callbacks import ALIASES, TRAITS as OSC_PROFILE


TRAITS = ("analytique", "enthousiasme", "angoisse", "creativite", "reveur", "extraversion")
LABELS = ("Analytique", "Enthousiaste", "Torturée", "Créative", "Rêveuse", "Extraversion")
BACKGROUND = ((210, 215, 223), (232, 209, 144), (253, 202, 64))
RESPONSE_SECONDS = (0.62, 0.28, 0.38, 0.72, 1.0, 0.58)
IDLE = (0.0,) * len(TRAITS)
SAMPLES = 96
DEFAULT_STRANDS = 256
STEP = 1 / 60
REVEAL_MORPH = 3.2
PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIRECTORY = PROJECT_ROOT / "videos"
DEMO = (
    ("Repos", IDLE),
    *((label, tuple(float(i == j) for i in range(6))) for j, label in enumerate(LABELS)),
    ("Ordre et impulsion", (0.96, 0.91, 0.12, 0.32, 0.18, 0.43)),
    ("Fractures et ramifications", (0.78, 0.42, 0.95, 0.93, 0.25, 0.15)),
    ("Poussée dans la brume", (0.32, 0.94, 0.45, 0.76, 0.95, 0.72)),
)


def background_rgb(extraversion):
    """Interpole en sRGB affiché les trois états TouchDesigner 0, 5 et 10."""
    segment = 2 * min(1.0, max(0.0, extraversion))
    index = min(int(segment), 1)
    fraction = segment - index
    return tuple((a + (b - a) * fraction) / 255 for a, b in zip(BACKGROUND[index], BACKGROUND[index + 1]))


def normalized(value, scale):
    if type(value) in (int, float) and isfinite(value):
        return min(1.0, max(0.0, value / scale))
    return None


class OscInput:
    def __init__(self, port):
        self.values = list(IDLE)
        self.session_id = None
        self.reveal_levels = None
        self.dispatcher = Dispatcher(strict_timing=False)
        self.scales = {}
        self.indices = {name: i for i, name in enumerate(TRAITS)}
        channels = load_mapping(PORTRAIT_MAPPING_PATH)
        for channel in channels:
            name = ALIASES.get(channel["dimension"], channel["dimension"])
            if name in self.indices:
                scale = channel.get("scale", 1.0)
                self.scales[name] = scale
                self.values[self.indices[name]] = channel.get("idle") or 0.0
                self.dispatcher.map(channel["address"], self.trait, name, scale)
        addresses = {channel["address"] for channel in channels}
        aliases = {**{name: name for name in TRAITS}, **ALIASES}
        for alias, name in aliases.items():
            address = f"/trait/{alias}"
            if name in self.scales and address not in addresses:
                self.dispatcher.map(address, self.trait, name, self.scales[name])
        self.dispatcher.map("/profil", self.profile)
        self.dispatcher.map("/portrait/session", self.announce)
        self.dispatcher.map("/portrait/reveal", self.reveal)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if sys.platform == "win32":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(("127.0.0.1", port))
            self.socket.setblocking(False)
        except OSError:
            self.close()
            raise

    def trait(self, address, channel, *args):
        name, scale = channel
        if len(args) == 1:
            value = normalized(args[0], scale)
            if value is not None:
                self.values[self.indices[name]] = value

    def profile(self, address, *args):
        if len(args) != len(OSC_PROFILE):
            return
        names = [ALIASES.get(name, name) for name in OSC_PROFILE]
        values = [normalized(value, self.scales.get(name, 10.0)) for name, value in zip(names, args)]
        if None not in values:
            for name, value in zip(names, values):
                if name in self.indices:
                    self.values[self.indices[name]] = value

    def announce(self, address, session_id=None, *extra):
        if not extra and isinstance(session_id, str) and re.fullmatch(r"[0-9a-f]{32}", session_id):
            if session_id != self.session_id:
                self.session_id = session_id
                self.reveal_levels = None

    def reveal(self, address, session_id=None, *scores):
        if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id) or len(scores) % 2:
            return
        by_name = {}
        for name, value in zip(scores[::2], scores[1::2]):
            level = normalized(value, 10.0)
            if not isinstance(name, str) or level is None:
                return
            by_name[ALIASES.get(name, name)] = level
        if not all(name in by_name for name in TRAITS):
            return
        self.announce(address, session_id)
        if self.reveal_levels is None:
            self.reveal_levels = tuple(by_name[name] for name in TRAITS)

    def poll(self):
        for _ in range(128):
            try:
                packet, peer = self.socket.recvfrom(65535)
            except BlockingIOError:
                break
            self.dispatcher.call_handlers_for_packet(packet, peer)

    def close(self):
        self.socket.close()


GLSL_SHARED = f"""
const int SAMPLES = {SAMPLES};
const float PI = {pi};
const float TAU = 2.0 * PI;
uniform int strands;
uniform vec4 traits; // analytique, enthousiasme, angoisse, créativité
uniform float dream;

float hash(uint v) {{
    v ^= v >> 16u; v *= 0x7feb352du;
    v ^= v >> 15u; v *= 0x846ca68bu;
    v ^= v >> 16u;
    return float(v & 0x00ffffffu) / 16777216.0;
}}

int layerOf(int strand) {{
    return strand < strands / 4 ? 0 : (strand < 3 * strands / 4 ? 1 : 2);
}}

float residualGrain(uint id, uint lane) {{
    float loose = 1.0 - step(0.085, hash(lane + 6u));
    float scattered = step(0.58, hash(lane + 8u)) * (1.0 - smoothstep(0.25, 0.45, hash(id + 3649u)));
    return max(loose, scattered);
}}
"""

SIMULATION = "#version 330 core\n" + GLSL_SHARED + """
layout(location = 0) in vec4 positionAge;
layout(location = 1) in vec4 velocitySpark;
layout(location = 2) in vec4 previousStress;
out vec4 nextPositionAge;
out vec4 nextVelocitySpark;
out vec4 nextPreviousStress;
uniform float dt;
uniform float phase;
uniform float seconds;
uniform float portraitFlow;
uniform int initialize;

float pulse(float u, float cycle, float width) {
    float center = mix(-1.44, 1.44, cycle);
    float x = (u - center) / width;
    return exp(-x * x) * pow(sin(PI * cycle), 2.0);
}

float crease(float offset, float width) {
    return max(0.0, 1.0 - abs(offset) / width);
}

void main() {
    int strand = gl_VertexID / SAMPLES;
    uint lane = uint(strand) * 19u;
    uint id = uint(gl_VertexID);
    float u = 2.0 * float(gl_VertexID % SAMPLES) / float(SAMPLES - 1) - 1.0;
    float angle = TAU * hash(lane + 9u);
    float band = float(layerOf(strand));
    float plane = (band - 1.0) * 2.40 + 0.85 * (hash(lane + 13u) - 0.5);
    float radius = pow(hash(lane + 2u), 1.55);
    vec3 grain = vec3(hash(id * 5u + 1u), hash(id * 5u + 2u), hash(id * 5u + 3u)) - 0.5;
    float width = (0.47 + 0.49 * cos(2.4 * u + 0.4 * sin(0.23 * phase)));
    float twist = angle + 1.82 * u + 0.36 * sin(0.41 * phase + 2.0 * u);
    float wake = sin(3.6 * u - 0.56 * phase + 0.34 * band);
    vec3 target = vec3(
        (4.80 - 0.22 * band) * u + 0.22 * cos(twist) * width + 0.14 * wake,
        0.96 * sin(2.84 * u - 0.36 * band + 0.34 * sin(0.31 * phase))
            - 0.46 * u + 0.52 * (band - 1.0) + 1.50 * radius * width * cos(twist)
            + 0.33 * sin(6.6 * u - 0.39 * phase + angle),
        plane + 0.75 * sin(3.68 * u + 0.32 * phase) + 1.55 * radius * width * sin(twist)
    );
    float loose = 1.0 - step(0.085, hash(lane + 6u));
    target += loose * (grain * vec3(1.55, 2.85, 1.75) + vec3(0.0, 0.59 * cos(angle), 0.0));

    // Les puits analytiques partagent un axe incliné et des rayons quantifiés.
    float theta = PI * (1.0 + u) + 0.09 * sin(0.23 * phase);
    theta += floor(8.0 * hash(lane + 7u)) * TAU / 8.0;
    float ring = 0.68 + 0.62 * floor(6.0 * hash(lane + 3u));
    ring += 0.10 * sin(0.43 * phase + theta * 3.0 + band);
    vec3 concentric = vec3(ring * cos(theta), 0.60 * ring * sin(theta),
                           plane + 0.53 * ring * sin(theta));
    float spoke = floor(12.0 * hash(lane + 12u)) * TAU / 12.0 + 0.09 * sin(0.23 * phase);
    float radial = mix(0.35, 3.76, (u + 1.0) * 0.5);
    vec3 segment = vec3(radial * cos(spoke), 0.60 * radial * sin(spoke),
                        plane + 0.53 * radial * sin(spoke));
    vec3 ordered = hash(lane + 15u) < 0.23 ? segment : concentric;
    ordered.y += 0.16 * ordered.x + 0.20 * (band - 1.0);
    float structure = traits.x * (0.88 + 0.11 * hash(lane + 16u));
    target = mix(target, ordered, structure);

    // Une même impulsion ouvre le courant et pousse ses particules vers le haut.
    float cycle = fract(seconds / 6.8);
    float wave = pulse(u, cycle, 0.34) + 0.57 * pulse(-u, fract(cycle + 0.50), 0.45);
    vec3 outward = normalize(vec3(target.x * 0.60, target.y + 0.25, target.z - plane + 0.20) + 0.001);
    target += traits.y * (wave * (1.86 * outward + vec3(0.0, 1.06, 0.18))
        + 0.16 * vec3(cos(theta + phase), sin(theta + phase), wake));

    // Des jonctions alternées prolongent le courant, y compris sur les anneaux.
    float fork = floor(5.0 * hash(lane + 4u));
    float junction = -0.46 + 0.21 * fork + 0.13 * sin(0.34 * phase + fork);
    float direction = fork < 2.0 ? -1.0 : 1.0;
    float growth = smoothstep(junction, junction + 0.68, direction * u)
        * (1.0 - 0.22 * smoothstep(0.63, 1.0, direction * u));
    float opening = 0.58 + 0.42 * sin(0.55 * phase + fork * 2.4);
    float divergence = (hash(lane + 5u) < 0.18 ? 0.12 : 1.0) * growth * opening;
    float arm = fork - 1.85 + 0.50 * cos(5.0 * u + fork + 0.38 * phase);
    target += traits.w * divergence * vec3((0.51 + 0.68 * cos(3.4 * u)) * direction,
                                           1.74 * arm, 1.31 * cos(fork * 2.2 + 2.4 * u));

    // Des pentes linéaires forment les plis, et le cisaillement ouvre leur pointe.
    float offset = 0.085 * (hash(lane + 1u) - 0.5);
    float cut = -0.49 + 0.16 * sin(0.23 * phase + 0.56 * band) + offset;
    float otherCut = 0.51 + 0.16 * sin(0.19 * phase + 1.53 - 0.56 * band) - offset;
    float du = u - cut;
    float dv = u - otherCut;
    float firstFold = crease(du, 0.31);
    float secondFold = crease(dv, 0.27);
    float shoulder = crease(du + 0.15, 0.11) - 0.76 * crease(dv - 0.13, 0.10);
    float stress = max(firstFold, secondFold);
    float fold = firstFold - 0.88 * secondFold;
    float split = sign(du) * firstFold - 0.81 * sign(dv) * secondFold;
    target += traits.z * vec3(0.24 * split + 0.21 * fold,
                              0.34 * split + 0.92 * fold - 0.49 * shoulder,
                             -0.50 * split + 0.38 * fold + 0.44 * shoulder);

    // Le même support devient une nappe plus ample, avec un grain qui dérive.
    target += (0.017 + 0.10 * dream * loose) * grain;
    target.y += dream * 0.42 * sin(2.6 * u + angle + 0.31 * phase);
    target.z += dream * 0.56 * sin(2.1 * u - angle + 0.19 * phase);
    if (dream > 0.0) {
        // Des grains libres dérivent autour des fibres à une vitesse différente.
        float driftPhase = TAU * hash(id + 1837u) + 0.24 * phase + 2.1 * u;
        vec3 drift = grain * vec3(1.35, 2.65, 2.35)
            + vec3(0.12 * cos(driftPhase), 0.34 * sin(driftPhase), 0.29 * cos(driftPhase + u));
        target += dream * residualGrain(id, lane) * drift;
    }
    if (portraitFlow < 1.0) {
        float orbit = PI * (1.0 + u) + angle + 0.10 * phase;
        float ringRadius = 2.48 + 0.15 * (hash(lane + 14u) - 0.5)
            + 0.034 * sin(3.0 * orbit + 0.24 * phase + angle);
        vec3 circle = vec3(ringRadius * cos(orbit), ringRadius * sin(orbit),
                           0.42 * (band - 1.0) + 0.20 * sin(orbit + angle));
        target = mix(circle + 0.045 * grain, target, portraitFlow);
    }

    float life = mix(11.0, 26.0, hash(lane + 18u));
    float age = initialize != 0 ? life * hash(id + 1198u) : mod(positionAge.w + dt, life);
    vec3 position = initialize != 0 ? target : positionAge.xyz;
    vec3 velocity = initialize != 0 ? vec3(0.0) : velocitySpark.xyz;
    float spring = mix(10.0 + 3.0 * traits.y, 5.7, dream);
    velocity += (target - position) * (spring * dt);
    velocity *= exp(-dt * mix(4.6, 5.4, dream));
    float spark = traits.y * wave * (0.62 + 0.38 * sin(12.0 * seconds + 70.0 * hash(id + 7u)));
    nextPositionAge = vec4(position + velocity * dt, age);
    nextVelocitySpark = vec4(velocity, spark);
    nextPreviousStress = vec4(position, clamp(stress, 0.0, 1.0));
    gl_Position = vec4(0.0);
}
"""

GLSL_VIEW = """
uniform vec2 viewport;
uniform float yaw;
uniform float pitch;
uniform float portraitFlow;
vec4 project(vec3 p) {
    p.xz = mat2(cos(yaw), -sin(yaw), sin(yaw), cos(yaw)) * p.xz;
    p.yz = mat2(cos(pitch), -sin(pitch), sin(pitch), cos(pitch)) * p.yz;
    float depth = 12.9 - p.z;
    float aspect = viewport.x / viewport.y;
    float excursion = max(traits.x, 0.77 * traits.w + 0.23 * traits.y);
    // Les branches et les poussées peuvent s'étendre jusque dans les bords du cadre.
    float extension = max(traits.y, traits.w);
    float combined = min(traits.y, traits.w);
    float framing = 1.0 + 0.36 * extension * extension + 0.61 * combined * combined;
    float axis = mix(2.86, mix(2.86, 2.53, excursion) / framing, portraitFlow) * min(1.0, aspect / 1.20);
    return vec4(p.x * axis / aspect, p.y * axis, depth - 0.25, depth);
}
float atmosphere(float depth) {
    return 1.0 - smoothstep(8.8, mix(17.7, 16.0, dream), depth) * (0.49 + 0.46 * dream);
}
vec3 fiberColor(float shade, float layer) {
    vec3 turquoise = vec3(0.012, 0.143, 0.157);
    vec3 indigo = vec3(0.018, 0.031, 0.105);
    vec3 copper = vec3(0.48, 0.14, 0.061);
    vec3 color = mix(turquoise, indigo, shade * 0.73 + 0.14 * layer);
    return mix(color, copper, smoothstep(0.69, 0.89, shade));
}
"""

FULLSCREEN = """#version 330 core
out vec2 uv;
void main() {
    vec2 corner = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    uv = corner;
    gl_Position = vec4(2.0 * corner - 1.0, 0.0, 1.0);
}
"""

DISPLAY = """#version 330 core
in vec2 uv;
out vec4 pixel;
uniform sampler2D plate;
vec3 srgb(vec3 c) {
    c = max(c, vec3(0.0));
    return mix(12.92 * c, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
void main() { pixel = vec4(srgb(texture(plate, uv).rgb), 1.0); }
"""

POINT_VERTEX = "#version 330 core\n" + GLSL_SHARED + GLSL_VIEW + """
layout(location = 0) in vec4 positionAge;
layout(location = 1) in vec4 velocitySpark;
layout(location = 2) in vec4 previousStress;
uniform int haze;
out Particle {
    vec4 pigment;
    vec2 motion;
    float spark;
    float blur;
    float diameter;
} particle;

void main() {
    uint id = uint(gl_VertexID);
    bool secondaryVeil = id % 17u != 0u;
    float diffusion = smoothstep(0.05, 0.85, dream);
    if (haze != 0 && secondaryVeil && (diffusion <= 0.0 || id % 23u != 3u)) {
        particle.diameter = 0.0;
        gl_Position = vec4(0.0);
        return;
    }
    uint lane = uint(gl_VertexID / SAMPLES) * 19u;
    gl_Position = project(positionAge.xyz);
    float depth = gl_Position.w;
    float scale = clamp(viewport.y / 780.0, 0.48, 1.7);
    float seed = hash(id + 529u);
    float variety = hash(lane + 11u);
    float layer = float(layerOf(gl_VertexID / SAMPLES));
    float life = mix(11.0, 26.0, hash(lane + 18u));
    float presence = smoothstep(0.0, 1.4, positionAge.w)
        * (1.0 - smoothstep(life - 1.4, life, positionAge.w));
    float air = atmosphere(depth);
    particle.blur = dream * smoothstep(9.8, 15.8, depth);
    particle.motion = vec2(0.0);
    particle.spark = 0.0;

    if (haze != 0) {
        float depthVeil = smoothstep(8.7, 16.2, depth);
        vec3 mist = mix(vec3(0.12, 0.31, 0.36), vec3(0.55, 0.77, 0.82), dream * depthVeil * 0.84);
        mist = mix(mist, vec3(0.71, 0.43, 0.31), smoothstep(0.68, 0.97, variety) * 0.65);
        vec3 diffuseMist = mix(vec3(0.19, 0.38, 0.49), vec3(0.47, 0.68, 0.77), depthVeil);
        mist = mix(mist, diffuseMist, 0.84 * dream);
        float opacity = secondaryVeil ? 0.080 * diffusion : 0.030 + 0.090 * dream;
        float spread = secondaryVeil ? 20.0 + 53.0 * dream : 22.0 + 103.0 * dream;
        particle.pigment = vec4(mist, presence * opacity * (0.69 + 0.31 * variety));
        particle.diameter = clamp(spread * (0.50 + seed) * scale * 13.0 / depth, 2.0, 148.0);
        return;
    }

    vec3 ink = fiberColor(variety, layer);
    particle.spark = velocitySpark.w * smoothstep(0.60, 0.96, seed);
    float glint = smoothstep(0.92, 1.0, seed);
    ink = mix(ink, vec3(0.86, 0.93, 0.91), glint * 0.92);
    float point = (1.34 + 1.77 * seed * seed + 3.3 * glint + 8.2 * particle.spark) * scale * 12.3 / depth;
    float opacity = air * presence * (0.29 + 0.64 * seed) * (1.0 - 0.41 * particle.blur);
    if (dream > 0.0) {
        float dispersed = dream * residualGrain(id, lane);
        ink = mix(ink, vec3(0.25, 0.48, 0.58), 0.56 * dispersed);
        opacity *= 1.0 - 0.29 * dispersed;
        point *= 1.0 + 0.78 * dispersed;
    }
    particle.pigment = vec4(ink, opacity);
    particle.diameter = max(1.0, point * (1.0 + 1.3 * particle.blur));
    if (particle.spark > 0.02) {
        vec4 tail = project(previousStress.xyz - velocitySpark.xyz * 0.18);
        vec2 travel = (gl_Position.xy / gl_Position.w - tail.xy / tail.w) * viewport;
        particle.motion = vec2(travel.x, -travel.y) / max(length(travel), 0.001);
    }
}
"""

POINT_GEOMETRY = """#version 330 core
layout(points) in;
layout(triangle_strip, max_vertices = 4) out;
in Particle {
    vec4 pigment;
    vec2 motion;
    float spark;
    float blur;
    float diameter;
} particle[];
uniform vec2 viewport;
out vec2 coordinate;
out vec4 pigment;
out vec2 motion;
out float spark;
out float blur;

void main() {
    if (particle[0].diameter <= 0.0 || particle[0].pigment.a <= 0.001) return;
    for (int i = 0; i < 4; ++i) {
        vec2 corner = vec2((i & 1) == 0 ? -1.0 : 1.0, (i & 2) == 0 ? -1.0 : 1.0);
        gl_Position = gl_in[0].gl_Position;
        gl_Position.xy += corner * particle[0].diameter / viewport * gl_Position.w;
        coordinate = vec2(corner.x, -corner.y);
        pigment = particle[0].pigment;
        motion = particle[0].motion;
        spark = particle[0].spark;
        blur = particle[0].blur;
        EmitVertex();
    }
    EndPrimitive();
}
"""

POINT_FRAGMENT = """#version 330 core
in vec2 coordinate;
in vec4 pigment;
in vec2 motion;
in float spark;
in float blur;
uniform int haze;
uniform float dream;
out vec4 pixel;
void main() {
    vec2 p = coordinate;
    float r2 = dot(p, p);
    if (r2 >= 1.0) discard;
    if (haze != 0) {
        pixel = vec4(pigment.rgb, pigment.a * exp(-mix(4.7, 3.45, dream) * r2) * (1.0 - r2));
        return;
    }
    float along = dot(p, motion);
    float across = dot(p, vec2(-motion.y, motion.x));
    float streak = exp(-14.0 * across * across - 1.25 * (along + 0.28) * (along + 0.28));
    float edge = 1.0 - smoothstep(0.37, 1.0, r2);
    float grain = exp(-mix(3.0, 2.5, blur) * r2);
    vec3 color = mix(pigment.rgb, vec3(1.0, 0.67, 0.32), min(1.0, 2.4 * spark));
    pixel = vec4(color, pigment.a * edge * max(grain, 1.45 * spark * streak));
}
"""

FILAMENT_VERTEX = "#version 330 core\n" + GLSL_SHARED + GLSL_VIEW + """
layout(location = 0) in vec4 positionAge;
layout(location = 1) in vec4 velocitySpark;
layout(location = 2) in vec4 previousStress;
out Node {
    vec4 pigment;
    float width;
    flat int strand;
} node;
void main() {
    node.strand = gl_VertexID / SAMPLES;
    uint lane = uint(node.strand) * 19u;
    gl_Position = project(positionAge.xyz);
    float depth = gl_Position.w;
    float variety = hash(lane + 11u);
    float layer = float(layerOf(node.strand));
    float thread = hash(lane + 8u);
    float filament = (1.0 - step(0.58, thread)) * step(0.085, hash(lane + 6u));
    float accent = 1.0 - step(0.15, thread);
    float u = float(gl_VertexID % SAMPLES) / float(SAMPLES - 1);
    float edge = smoothstep(0.0, 0.14, u) * (1.0 - smoothstep(0.86, 1.0, u));
    float tension = traits.z * (0.40 + 0.60 * previousStress.w);
    float air = atmosphere(depth);
    float alpha = filament * edge * (0.28 + 0.21 * accent + 0.17 * traits.x + 0.08 * traits.w);
    alpha *= 1.0 + 0.29 * tension;
    vec3 pigment = fiberColor(variety, layer) * (1.0 - 0.42 * tension);
    node.pigment = vec4(pigment, alpha * air * (1.0 - 0.17 * dream) * (0.50 + 0.50 * edge));
    node.width = (0.76 + filament * (0.28 + 0.54 * accent + 0.48 * velocitySpark.w))
        * clamp(viewport.y / 780.0, 0.52, 2.0) * 12.5 / depth;
}
"""

FILAMENT_GEOMETRY = """#version 330 core
layout(lines) in;
layout(triangle_strip, max_vertices = 4) out;
in Node {
    vec4 pigment;
    float width;
    flat int strand;
} node[];
out vec4 pigment;
out float edge;
uniform vec2 viewport;

void vertex(int index, vec2 normal, float side) {
    vec4 position = gl_in[index].gl_Position;
    gl_Position = position;
    gl_Position.xy += side * normal * node[index].width * 2.0 / viewport * position.w;
    edge = side;
    pigment = node[index].pigment;
    EmitVertex();
}

void main() {
    // Deux sommets consécutifs de la même fibre restent reliés, même si elle s'étire.
    if (node[0].strand != node[1].strand || node[0].pigment.a + node[1].pigment.a < 0.007) return;
    vec2 a = gl_in[0].gl_Position.xy / gl_in[0].gl_Position.w;
    vec2 b = gl_in[1].gl_Position.xy / gl_in[1].gl_Position.w;
    vec2 delta = (b - a) * viewport;
    vec2 normal = vec2(-delta.y, delta.x) / max(length(delta), 0.0001);
    vertex(0, normal, -1.0);
    vertex(0, normal, 1.0);
    vertex(1, normal, -1.0);
    vertex(1, normal, 1.0);
    EndPrimitive();
}
"""

FILAMENT_FRAGMENT = """#version 330 core
in vec4 pigment;
in float edge;
out vec4 pixel;
void main() { pixel = vec4(pigment.rgb, pigment.a * (1.0 - smoothstep(0.26, 1.0, abs(edge)))); }
"""


class Program:
    def __init__(self, vertex, fragment=None, *, geometry=None, feedback=()):
        self.handle = gl.glCreateProgram()
        self.locations = {}
        try:
            for kind, source in ((gl.GL_VERTEX_SHADER, vertex),
                                 (gl.GL_GEOMETRY_SHADER, geometry),
                                 (gl.GL_FRAGMENT_SHADER, fragment)):
                if source is not None:
                    shader = gl.glCreateShader(kind)
                    try:
                        raw = c.create_string_buffer(source.encode("utf-8"))
                        pointer = c.cast(raw, c.POINTER(gl.GLchar))
                        gl.glShaderSource(shader, 1, c.byref(pointer), None)
                        gl.glCompileShader(shader)
                        self.check(shader, gl.GL_COMPILE_STATUS, gl.glGetShaderiv, gl.glGetShaderInfoLog)
                        gl.glAttachShader(self.handle, shader)
                    finally:
                        gl.glDeleteShader(shader)
            if feedback:
                strings = [c.create_string_buffer(name.encode("ascii")) for name in feedback]
                pointers = (c.POINTER(gl.GLchar) * len(strings))(
                    *(c.cast(raw, c.POINTER(gl.GLchar)) for raw in strings)
                )
                gl.glTransformFeedbackVaryings(self.handle, len(strings), pointers, gl.GL_INTERLEAVED_ATTRIBS)
            gl.glLinkProgram(self.handle)
            self.check(self.handle, gl.GL_LINK_STATUS, gl.glGetProgramiv, gl.glGetProgramInfoLog)
        except Exception:
            self.close()
            raise

    @staticmethod
    def check(handle, parameter, get_status, get_log):
        status = gl.GLint()
        get_status(handle, parameter, c.byref(status))
        if not status.value:
            length = gl.GLint()
            get_status(handle, gl.GL_INFO_LOG_LENGTH, c.byref(length))
            log = c.create_string_buffer(max(1, length.value))
            get_log(handle, len(log), None, log)
            raise RuntimeError(log.value.decode("utf-8", errors="replace"))

    def use(self):
        gl.glUseProgram(self.handle)

    def set(self, name, *values):
        if name not in self.locations:
            self.locations[name] = gl.glGetUniformLocation(self.handle, name.encode("ascii"))
        location = self.locations[name]
        if len(values) == 1 and isinstance(values[0], int):
            gl.glUniform1i(location, values[0])
        else:
            (gl.glUniform1f, gl.glUniform2f, gl.glUniform3f, gl.glUniform4f)[len(values) - 1](location, *values)

    def close(self):
        gl.glDeleteProgram(self.handle)


def linear_channel(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


class Renderer:
    """État GPU ping-pong et composition linéaire dans le contexte courant."""

    def __init__(self, strands=DEFAULT_STRANDS, levels=IDLE, *, flow=1.0):
        self.strands = strands
        self.levels = list(levels)
        self.flow = flow
        self.seconds = 0.0
        self.phase = 0.0
        self.accumulator = 0.0
        self.current = 0
        self.size = (0, 0)
        self.simulation = Program(SIMULATION, feedback=("nextPositionAge", "nextVelocitySpark", "nextPreviousStress"))
        self.points = Program(POINT_VERTEX, POINT_FRAGMENT, geometry=POINT_GEOMETRY)
        self.filaments = Program(FILAMENT_VERTEX, FILAMENT_FRAGMENT, geometry=FILAMENT_GEOMETRY)
        self.display = Program(FULLSCREEN, DISPLAY)

        self.vaos = (gl.GLuint * 3)()
        self.buffers = (gl.GLuint * 2)()
        self.framebuffer = gl.GLuint()
        self.plate = gl.GLuint()
        gl.glGenVertexArrays(len(self.vaos), self.vaos)
        gl.glGenBuffers(len(self.buffers), self.buffers)
        gl.glGenFramebuffers(1, c.byref(self.framebuffer))
        gl.glGenTextures(1, c.byref(self.plate))
        stride = 12 * c.sizeof(gl.GLfloat)
        for vao, buffer in zip(self.vaos, self.buffers):
            gl.glBindVertexArray(vao)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, strands * SAMPLES * stride, None, gl.GL_DYNAMIC_COPY)
            for index in range(3):
                gl.glEnableVertexAttribArray(index)
                gl.glVertexAttribPointer(index, 4, gl.GL_FLOAT, gl.GL_FALSE, stride, c.c_void_p(index * stride // 3))
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.plate)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glDisable(gl.GL_DEPTH_TEST)
        gl.glDisable(gl.GL_FRAMEBUFFER_SRGB)
        gl.glDisable(gl.GL_DITHER)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        self.simulate(0.0, initialize=True)

    def simulate(self, dt, *, initialize=False):
        destination = 1 - self.current
        program = self.simulation
        program.use()
        program.set("strands", self.strands)
        program.set("traits", *self.levels[:4])
        program.set("dream", float(self.levels[4]))
        program.set("dt", dt)
        program.set("phase", self.phase)
        program.set("seconds", self.seconds)
        program.set("portraitFlow", float(self.flow))
        program.set("initialize", int(initialize))
        gl.glBindVertexArray(self.vaos[self.current])
        gl.glBindBufferBase(gl.GL_TRANSFORM_FEEDBACK_BUFFER, 0, self.buffers[destination])
        gl.glEnable(gl.GL_RASTERIZER_DISCARD)
        gl.glBeginTransformFeedback(gl.GL_POINTS)
        gl.glDrawArrays(gl.GL_POINTS, 0, self.strands * SAMPLES)
        gl.glEndTransformFeedback()
        gl.glDisable(gl.GL_RASTERIZER_DISCARD)
        gl.glBindBufferBase(gl.GL_TRANSFORM_FEEDBACK_BUFFER, 0, 0)
        self.current = destination

    def reset_circle(self):
        self.levels[:] = IDLE
        self.accumulator = self.seconds = self.phase = self.flow = 0.0
        self.simulate(0.0, initialize=True)

    def advance_reveal(self, dt, elapsed, profile):
        progress = min(1.0, max(0.0, elapsed / REVEAL_MORPH))
        self.flow = progress * progress * (3.0 - 2.0 * progress)
        self.advance(dt, profile if progress > 0.0 else IDLE)

    def advance(self, elapsed, target):
        self.accumulator += min(max(0.0, elapsed), 0.12)
        while self.accumulator + 1e-12 >= STEP:
            self.accumulator -= STEP
            for i, response in enumerate(RESPONSE_SECONDS):
                self.levels[i] += (target[i] - self.levels[i]) * (1.0 - exp(-STEP / response))
            self.seconds += STEP
            self.phase += STEP * (1.0 + 1.65 * self.levels[1]) * (1.0 - 0.69 * self.levels[4])
            self.simulate(STEP)

    def resize(self, width, height):
        if (width, height) == self.size:
            return
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.plate)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA16F, width, height, 0, gl.GL_RGBA, gl.GL_HALF_FLOAT, None)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.framebuffer)
        gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, self.plate, 0)
        if gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) != gl.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("Le tampon OpenGL de composition linéaire est incomplet.")
        self.size = (width, height)

    def draw(self, width, height, *, yaw=0.14, pitch=0.18):
        if width <= 0 or height <= 0:
            return
        # Lier l’unité de texture explicitement, y compris après un redimensionnement.
        gl.glActiveTexture(gl.GL_TEXTURE0)
        self.resize(width, height)
        gl.glViewport(0, 0, width, height)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.framebuffer)
        background = background_rgb(self.levels[5])
        gl.glClearColor(*(linear_channel(channel) for channel in background), 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        gl.glBindVertexArray(self.vaos[self.current])
        gl.glEnable(gl.GL_BLEND)

        for program in (self.points, self.filaments):
            program.use()
            program.set("strands", self.strands)
            program.set("portraitFlow", float(self.flow))
            program.set("viewport", float(width), float(height))
            program.set("yaw", yaw)
            program.set("pitch", pitch)
            program.set("dream", float(self.levels[4]))
            program.set("traits", *self.levels[:4])

        cuts = (0, self.strands // 4, 3 * self.strands // 4, self.strands)
        for start, end in zip(cuts, cuts[1:]):
            first, count = start * SAMPLES, (end - start) * SAMPLES
            self.points.use()
            self.points.set("haze", 1)
            gl.glDrawArrays(gl.GL_POINTS, first, count)
            self.filaments.use()
            gl.glDrawArrays(gl.GL_LINE_STRIP, first, count)
            self.points.use()
            self.points.set("haze", 0)
            gl.glDrawArrays(gl.GL_POINTS, first, count)

        gl.glDisable(gl.GL_BLEND)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.plate)
        gl.glBindVertexArray(self.vaos[2])
        self.display.use()
        self.display.set("plate", 0)
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 3)

    def close(self):
        gl.glUseProgram(0)
        for program in (self.simulation, self.points, self.filaments, self.display):
            program.close()
        gl.glDeleteVertexArrays(len(self.vaos), self.vaos)
        gl.glDeleteBuffers(len(self.buffers), self.buffers)
        gl.glDeleteFramebuffers(1, c.byref(self.framebuffer))
        gl.glDeleteTextures(1, c.byref(self.plate))


def create_window(width, height, *, visible=True, vsync=True):
    config = gl.Config(major_version=3, minor_version=3, forward_compatible=True,
                       double_buffer=True, red_size=8, green_size=8, blue_size=8, depth_size=0)
    return pyglet.window.Window(width, height, caption="MindSight", resizable=True,
                                config=config, visible=visible, vsync=vsync)


class Portrait:
    def __init__(self, window, renderer, port, *, mode, fixed):
        self.window = window
        self.renderer = renderer
        self.port = port
        self.osc = None
        self.mode = mode
        self.live_mode = "reveal" if mode == "reveal" else "live"
        self.reveal_session = self.reveal_profile = None
        self.exported_sessions = set()
        self.exports = []
        self.fixed = list(fixed)
        self.selected = None
        self.mode_seconds = 0.0
        self.paused = False
        self.caption = None
        if mode in ("live", "reveal"):
            self.osc = OscInput(port)
        window.push_handlers(on_draw=self.on_draw, on_key_press=self.on_key_press)

    def on_draw(self):
        self.renderer.draw(*self.window.get_framebuffer_size())

    def title_and_target(self):
        if self.mode == "reveal":
            title = "Révélation" if self.reveal_profile is not None else "En attente du profil"
            return title, self.reveal_profile or IDLE
        if self.mode == "live":
            return f"OSC · {self.port}", self.osc.values
        if self.mode == "demo":
            return DEMO[int(self.mode_seconds / 9.0) % len(DEMO)]
        if self.mode == "combinations":
            return DEMO[7 + int(self.mode_seconds / 9.0) % 3]
        if self.mode == "rapid":
            levels = (DEMO[8][1], IDLE, DEMO[9][1], DEMO[7][1])
            return "Variations rapides", levels[int(self.mode_seconds / 0.63) % len(levels)]
        if self.selected is not None:
            return f"{LABELS[self.selected]} · {10 * self.fixed[self.selected]:g}/10", self.fixed
        return "Réglage manuel", self.fixed

    def sync_reveal(self):
        session, profile = self.osc.session_id, self.osc.reveal_levels
        if self.mode == "reveal" and (session, profile) != (self.reveal_session, self.reveal_profile):
            if session != self.reveal_session:
                self.renderer.reset_circle()
            self.reveal_session, self.reveal_profile = session, profile
            self.mode_seconds = 0.0
        self.exports = [process for process in self.exports if process.poll() is None]
        if profile is None or session in self.exported_sessions:
            return
        self.exported_sessions.add(session)
        destination = VIDEO_DIRECTORY / f"mindsight-portrait-{session}.mp4"
        if destination.exists():
            return
        process_group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                         if sys.platform == "win32" else {"start_new_session": True})
        try:
            process = subprocess.Popen([
                sys.executable, "-X", "utf8", "-m", "visualization.export_mindsight_video", str(destination),
                "--reveal", *(str(level * 10.0) for level in profile),
            ], cwd=PROJECT_ROOT, **process_group)
        except OSError as error:
            print(f"Impossible de lancer l’export du portrait. {error}", file=sys.stderr, flush=True)
        else:
            self.exports.append(process)

    def update(self, dt):
        if self.osc is not None:
            self.osc.poll()
            if self.live_mode == "reveal":
                self.sync_reveal()
        if not self.paused:
            self.mode_seconds += dt
        description, target = self.title_and_target()
        caption = f"MindSight | {description}" + (" · Pause" if self.paused else "")
        if caption != self.caption:
            self.window.set_caption(caption)
            self.caption = caption
        if not self.paused:
            if self.mode == "reveal":
                elapsed = self.mode_seconds if self.reveal_profile is not None else 0.0
                self.renderer.advance_reveal(dt, elapsed, target)
            else:
                self.renderer.flow = 1.0
                self.renderer.advance(dt, target)

    def on_key_press(self, symbol, modifiers):
        if symbol == key.F:
            self.window.set_fullscreen(not self.window.fullscreen)
        elif symbol == key.SPACE:
            self.paused = not self.paused
        elif symbol == key.L:
            if self.osc is None:
                try:
                    self.osc = OscInput(self.port)
                except OSError as error:
                    print(f"OSC : port {self.port} indisponible ({error}).", file=sys.stderr)
                    return
            if self.live_mode == "reveal" and self.mode != "reveal":
                self.renderer.reset_circle()
                self.mode_seconds = 0.0
            self.mode = self.live_mode
        elif symbol in (key.D, key._7, key._8):
            self.mode = {key.D: "demo", key._7: "combinations", key._8: "rapid"}[symbol]
            self.mode_seconds = 0.0
        elif key._0 <= symbol <= key._6:
            self.mode = "manual"
            self.selected = symbol - key._1 if symbol != key._0 else None
            self.fixed = [float(i == self.selected) for i in range(len(TRAITS))]
        elif self.mode == "manual" and self.selected is not None and symbol in (key.UP, key.DOWN):
            delta = 1 if symbol == key.UP else -1
            value = round(10 * self.fixed[self.selected]) + delta
            self.fixed[self.selected] = min(10, max(0, value)) / 10

    def close(self):
        if self.osc is not None:
            self.osc.close()


def trait_assignment(argument):
    name, _, raw = argument.partition("=")
    name = ALIASES.get(name, name)
    try:
        value = float(raw)
    except ValueError:
        value = None
    if name not in TRAITS or value is None or not 0 <= value <= 10:
        raise argparse.ArgumentTypeError(f"Attendu : TRAIT=0..10 ({', '.join(TRAITS)}).")
    return name, value / 10


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--demo", action="store_true", help="Enchaîner les traits isolés et les compositions.")
    modes.add_argument("--trait", action="append", type=trait_assignment, help="Fixer un trait sur 10. Option répétable.")
    modes.add_argument("--session-reveal", action="store_true", help="Attendre le profil final et exporter sa révélation.")
    parser.add_argument("--osc-port", type=int, default=DEFAULT_OSC_PORT, help="Port UDP local du pont MindSight.")
    parser.add_argument("--strands", type=int, default=DEFAULT_STRANDS,
                        help=f"Nombre de filaments de {SAMPLES} particules (défaut : {DEFAULT_STRANDS}).")
    args = parser.parse_args()
    if not 1 <= args.osc_port <= 65535:
        parser.error("Le port OSC doit être compris entre 1 et 65535.")
    if not 24 <= args.strands <= 1536:
        parser.error("Le nombre de filaments doit être compris entre 24 et 1536.")
    assignments = dict(args.trait or ())
    levels = tuple(assignments.get(name, 0.0) for name in TRAITS)
    mode = "demo" if args.demo else "manual" if args.trait else "reveal" if args.session_reveal else "live"
    window = renderer = portrait = None
    try:
        window = create_window(1360, 820)
        renderer = Renderer(args.strands, levels, flow=0.0 if args.session_reveal else 1.0)
        portrait = Portrait(window, renderer, args.osc_port, mode=mode, fixed=levels)
        pyglet.clock.schedule(portrait.update)
        pyglet.app.run()
    except (OSError, RuntimeError, pyglet.window.WindowException, gl.GLException) as error:
        parser.exit(1, f"MindSight OpenGL : {error}\n")
    except KeyboardInterrupt:
        pass
    finally:
        if portrait is not None:
            pyglet.clock.unschedule(portrait.update)
            portrait.close()
        if window is not None and window.context is not None:
            window.switch_to()
            if renderer is not None:
                renderer.close()
            window.close()


if __name__ == "__main__":
    main()
