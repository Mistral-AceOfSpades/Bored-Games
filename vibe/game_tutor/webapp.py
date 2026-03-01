from __future__ import annotations

import cgi
import html
import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vibe.game_tutor.orchestrator import MistralVibeOrchestrator


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.uploads = self.root / "uploads"
        self.sessions = self.root / "sessions"

    def ensure(self) -> None:
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.sessions.mkdir(parents=True, exist_ok=True)

    def new_session_path(self) -> Path:
        self.ensure()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        session_dir = self.sessions / stamp
        session_dir.mkdir(parents=True, exist_ok=False)
        return session_dir


def build_from_uploaded_rules(
    *,
    filename: str,
    rules_text: str,
    storage: LocalStorage,
    orchestrator: MistralVibeOrchestrator,
) -> dict[str, object]:
    session_dir = storage.new_session_path()
    safe_name = Path(filename).name or "rules.txt"
    upload_path = storage.uploads / safe_name
    upload_path.write_text(rules_text, encoding="utf-8")

    manifest = orchestrator.run_from_text(rules_text, safe_name, session_dir)
    manifest_path = session_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "session_id": session_dir.name,
        "session_dir": str(session_dir),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


class GameTutorRequestHandler(BaseHTTPRequestHandler):
    server: "GameTutorServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        match parsed.path:
            case "/":
                self._send_html(self._render_home())
            case "/sessions":
                self._send_html(self._render_sessions())
            case "/session":
                params = parse_qs(parsed.query)
                session_id = params.get("id", [""])[0]
                self._send_html(self._render_session(session_id))
            case _:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        if self.path != "/upload":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            },
        )

        if "rules_file" not in form:
            self.send_error(HTTPStatus.BAD_REQUEST, "rules_file is required")
            return

        uploaded = form["rules_file"]
        if not isinstance(uploaded, cgi.FieldStorage) or uploaded.file is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid upload")
            return

        rules_text = uploaded.file.read().decode("utf-8")
        if not rules_text.strip():
            self.send_error(HTTPStatus.BAD_REQUEST, "Uploaded file is empty")
            return

        filename = uploaded.filename or "rules.txt"
        result = build_from_uploaded_rules(
            filename=filename,
            rules_text=rules_text,
            storage=self.server.storage,
            orchestrator=self.server.orchestrator,
        )
        location = f"/session?id={result['session_id']}"
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _render_home(self) -> str:
        return """<!doctype html>
<html>
  <head>
    <meta charset='utf-8'>
    <title>Game Tutor Builder</title>
    <style>
      body { font-family: sans-serif; margin: 2rem auto; max-width: 900px; line-height: 1.4; }
      .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-top: 1rem; }
      button { padding: 0.6rem 1rem; }
    </style>
  </head>
  <body>
    <h1>Game Tutor Builder</h1>
    <p>Upload game rules, then generate tutorials, strategy modules, and a practice UI stored locally.</p>

    <section class='card'>
      <h2>Upload Rules</h2>
      <form method='post' action='/upload' enctype='multipart/form-data'>
        <input type='file' name='rules_file' accept='.txt,.md,text/plain,text/markdown' required />
        <button type='submit'>Build Tutor</button>
      </form>
    </section>

    <section class='card'>
      <h2>Saved Sessions</h2>
      <p><a href='/sessions'>Browse local generated sessions</a></p>
    </section>
  </body>
</html>"""

    def _render_sessions(self) -> str:
        sessions = sorted(
            (path for path in self.server.storage.sessions.iterdir() if path.is_dir()),
            key=lambda item: item.name,
            reverse=True,
        ) if self.server.storage.sessions.exists() else []

        items = "".join(
            f"<li><a href='/session?id={html.escape(path.name)}'>{html.escape(path.name)}</a></li>"
            for path in sessions
        )
        if not items:
            items = "<li>No sessions yet.</li>"

        return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Sessions</title></head>
<body>
  <h1>Generated Sessions</h1>
  <ul>{items}</ul>
  <p><a href='/'>Back to upload</a></p>
</body></html>"""

    def _render_session(self, session_id: str) -> str:
        if not session_id:
            return "<h1>Session not specified</h1>"

        session_path = self.server.storage.sessions / session_id
        manifest_path = session_path / "manifest.json"
        if not manifest_path.exists():
            return f"<h1>Session not found: {html.escape(session_id)}</h1>"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_html = html.escape(json.dumps(manifest, indent=2))
        ui_paths = "".join(
            f"<li><code>{html.escape(path)}</code></li>" for path in manifest.get("ui_files", [])
        ) or "<li>No UI files</li>"

        return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Session {html.escape(session_id)}</title></head>
<body>
  <h1>Session {html.escape(session_id)}</h1>
  <p>Stored locally at: <code>{html.escape(str(session_path))}</code></p>
  <h2>Generated UI Files</h2>
  <ul>{ui_paths}</ul>
  <h2>Manifest</h2>
  <pre>{manifest_html}</pre>
  <p><a href='/sessions'>Back to sessions</a></p>
</body></html>"""

    def _send_html(self, content: str) -> None:
        payload = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class GameTutorServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        storage: LocalStorage,
        orchestrator: MistralVibeOrchestrator,
    ) -> None:
        super().__init__(server_address, GameTutorRequestHandler)
        self.storage = storage
        self.orchestrator = orchestrator


def run_server(host: str = "127.0.0.1", port: int = 8765, storage_root: Path = Path("game-tutor/generated")) -> None:
    storage = LocalStorage(storage_root)
    storage.ensure()
    orchestrator = MistralVibeOrchestrator()
    server = GameTutorServer((host, port), storage=storage, orchestrator=orchestrator)
    print(f"Game Tutor UI running at http://{host}:{port}")
    print(f"Local storage: {storage_root}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
