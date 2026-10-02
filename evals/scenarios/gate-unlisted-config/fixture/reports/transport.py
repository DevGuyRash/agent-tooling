"""Calls to other services go through the service mesh, as the reports service."""
import json
import subprocess

SERVICE = "reports"


class MeshError(Exception):
    """A call through the mesh failed (refused, not found, or the target errored)."""


class MeshTransport:
    """GET requests to another service through `meshctl curl`."""

    def __init__(self, target: str, env: str):
        self.target = target
        self.env = env

    def get(self, path: str) -> dict:
        r = subprocess.run(["meshctl", "curl", "--as", SERVICE, "--env", self.env, self.target, path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise MeshError(r.stderr.strip() or f"meshctl exited with status {r.returncode}")
        return json.loads(r.stdout)
