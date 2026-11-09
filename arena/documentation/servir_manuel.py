"""Serveur de consultation et de téléchargement du manuel INJS."""
import http.server
import socketserver
import os
import urllib.parse

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manuel_utilisateur")
PORT = 4400

TELECHARGEMENTS = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".md": "text/markdown; charset=utf-8",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=BASE, **k)

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in TELECHARGEMENTS:
            return TELECHARGEMENTS[ext]
        return super().guess_type(path)

    def end_headers(self):
        # les fichiers du dossier telechargements/ sont servis en piece jointe
        chemin = urllib.parse.unquote(self.path.split("?")[0])
        if chemin.startswith("/telechargements/") and not chemin.endswith("/"):
            nom = os.path.basename(chemin)
            self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as srv:
    print(f"Serveur actif sur 0.0.0.0:{PORT}")
    srv.serve_forever()
