"""Lecture MCP de l’instantané calculé par le serveur conversationnel."""

from contextlib import contextmanager
import socket
from threading import Thread
from time import monotonic

from mcp.server.fastmcp import FastMCP
import uvicorn


def create_mcp_server(service):
    mcp = FastMCP("MindSight", stateless_http=True, json_response=True, log_level="WARNING")

    @mcp.resource("mindsight://sessions/{session_id}/dimensions", mime_type="application/json")
    def session_dimensions(session_id: str) -> dict:
        """Dernière révision et signaux du portrait pour cette session."""
        try:
            return service.get_snapshot(session_id)
        except KeyError:
            raise ValueError("Session MindSight introuvable.") from None

    return mcp


@contextmanager
def serve_mcp(service, port):
    app = create_mcp_server(service).streamable_http_app()
    config = uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2)
    server = uvicorn.Server(config)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        address = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, name="mindsight-mcp")
        thread.start()
        try:
            deadline = monotonic() + 5
            while not server.started and thread.is_alive() and monotonic() < deadline:
                thread.join(0.01)
            if not server.started:
                raise RuntimeError("Le serveur MCP n’a pas démarré.")
            yield address
        finally:
            server.should_exit = True
            thread.join()
