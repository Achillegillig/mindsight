"""Transmet les révisions du portrait MindSight à TouchDesigner via OSC."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import AnyUrl
from pythonosc.udp_client import SimpleUDPClient
import yaml

MAPPING_PATH = Path(__file__).with_name("mapping.yaml")
OSC_FLOAT_MAX = 3.4028234663852886e38


def load_mapping(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    channels = data.get("channels") if isinstance(data, dict) else None
    if not isinstance(channels, list) or not channels:
        raise ValueError("Le fichier OSC doit définir une liste de canaux.")
    addresses = set()
    for channel in channels:
        if not isinstance(channel, dict) or not isinstance(channel.get("dimension"), str):
            raise ValueError("Chaque canal OSC doit référencer une dimension.")
        address, idle = channel.get("address"), channel.get("idle")
        if not isinstance(address, str) or not address.startswith("/") or address in addresses:
            raise ValueError("Les adresses OSC doivent commencer par / et être uniques.")
        if channel.get("signal") not in ("appui", "contre_appui"):
            raise ValueError("Signal OSC inconnu.")
        if idle is not None and (type(idle) not in (float, int) or not 0 <= idle <= 1):
            raise ValueError("La valeur de repos OSC doit être comprise entre 0 et 1.")
        scale = channel.get("scale", 1.0)
        if type(scale) not in (float, int) or not 0 < scale <= OSC_FLOAT_MAX:
            raise ValueError("Le facteur d’échelle OSC doit être positif et représentable en float32.")
        addresses.add(address)
    return channels


def forward_snapshot(snapshot, channels, osc):
    dimensions = {item["id"]: item for item in snapshot["dimensions"]}
    for channel in channels:
        value = dimensions.get(channel["dimension"], {}).get(channel["signal"])
        if value is None:
            value = channel.get("idle")
        if value is not None:
            osc.send_message(channel["address"], float(value) * channel.get("scale", 1.0))


async def bridge(url, session_id, channels, osc, *, interval=0.25, once=False):
    revision = -1
    uri = AnyUrl(f"mindsight://sessions/{session_id}/dimensions")
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            while True:
                resource = await client.read_resource(uri)
                snapshot = json.loads(resource.contents[0].text)
                if snapshot["session_id"] != session_id:
                    raise ValueError("Le résultat MCP appartient à une autre session.")
                if snapshot["revision"] > revision:
                    forward_snapshot(snapshot, channels, osc)
                    revision = snapshot["revision"]
                if once:
                    return
                await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True, help="Identifiant affiché dans le terminal de MindSight.")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8001/mcp")
    parser.add_argument("--osc-host", default="127.0.0.1")
    parser.add_argument("--osc-port", type=int, default=9000)
    parser.add_argument("--mapping", type=Path, default=MAPPING_PATH)
    parser.add_argument("--once", action="store_true", help="Transmettre une seule révision.")
    args = parser.parse_args()
    try:
        with SimpleUDPClient(args.osc_host, args.osc_port) as osc:
            asyncio.run(bridge(args.mcp_url, args.session_id, load_mapping(args.mapping), osc, once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
