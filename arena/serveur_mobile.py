#!/usr/bin/env python3
"""Serveur de l'aperçu mobile (Flutter web).

Deux rôles, dans un seul processus, pour rester dans la même origine :

1. servir le build web de l'application mobile (``flutter build web``) ;
2. **relayer** ``/api/*`` vers l'API Django locale (``127.0.0.1:8000``).

Le relais est indispensable : le navigateur de l'utilisateur ne voit pas le
bac à sable, donc il ne peut pas appeler ``127.0.0.1:8000``. Comme le build est
configuré avec ``API_BASE_URL`` vide, l'application appelle ``/api/...`` sur sa
propre origine et ce serveur transmet à Django — sans CORS, sans URL codée en
dur, et sans exposer l'API sur un second port public.

Usage :  python3 arena/serveur_mobile.py [--port 3001] [--racine <build/web>]
"""

from __future__ import annotations

import argparse
import os
import posixpath
import sys
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

CIBLE_API = os.environ.get("API_INTERNE", "http://127.0.0.1:8000")
RACINE_DEFAUT = os.environ.get("BUILD_WEB", "qr_badge_mobile/build/web")

# En-têtes hop-by-hop : jamais recopiés d'un côté à l'autre (RFC 7230 §6.1).
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


class RepondeurMobile(SimpleHTTPRequestHandler):
    """Fichiers statiques + relais /api, avec repli SPA sur index.html."""

    racine = RACINE_DEFAUT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.racine, **kwargs)

    # ── Journal ────────────────────────────────────────────────────────────
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[mobile] {fmt % args}\n")

    # ── Relais API ─────────────────────────────────────────────────────────
    def _est_api(self):
        return self.path == "/api" or self.path.startswith("/api/")

    def _relayer(self, methode):
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur) if longueur else None

        en_tetes = {
            cle: valeur for cle, valeur in self.headers.items()
            if cle.lower() not in HOP_BY_HOP
        }
        requete = urllib.request.Request(
            f"{CIBLE_API}{self.path}", data=corps, headers=en_tetes, method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=120) as reponse:
                contenu = reponse.read()
                statut = reponse.status
                entetes = reponse.headers
        except urllib.error.HTTPError as erreur:
            # Les refus métier (400/403/409…) sont de vraies réponses : on les
            # transmet telles quelles, jamais transformées en 500.
            contenu = erreur.read()
            statut = erreur.code
            entetes = erreur.headers
        except Exception as erreur:  # API injoignable : message explicite
            message = (
                '{"detail":"API Django injoignable sur ' + CIBLE_API +
                ' — lancer ./arena/lancer-api.sh"}'
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            self.log_message("relais impossible : %s", erreur)
            return

        self.send_response(statut)
        for cle, valeur in entetes.items():
            if cle.lower() in HOP_BY_HOP or cle.lower() == "content-encoding":
                continue
            self.send_header(cle, valeur)
        self.send_header("Content-Length", str(len(contenu)))
        self.end_headers()
        if methode != "HEAD":
            self.wfile.write(contenu)

    def do_GET(self):
        if self._est_api():
            return self._relayer("GET")
        return super().do_GET()

    def do_HEAD(self):
        if self._est_api():
            return self._relayer("HEAD")
        return super().do_HEAD()

    def do_POST(self):
        if self._est_api():
            return self._relayer("POST")
        self.send_error(405)

    def do_PUT(self):
        if self._est_api():
            return self._relayer("PUT")
        self.send_error(405)

    def do_PATCH(self):
        if self._est_api():
            return self._relayer("PATCH")
        self.send_error(405)

    def do_DELETE(self):
        if self._est_api():
            return self._relayer("DELETE")
        self.send_error(405)

    def do_OPTIONS(self):
        if self._est_api():
            return self._relayer("OPTIONS")
        self.send_error(405)

    # ── Repli SPA (routes Flutter gérées côté client) ──────────────────────
    def send_head(self):
        chemin = self.translate_path(self.path)
        if not os.path.exists(chemin) or os.path.isdir(chemin):
            index = os.path.join(self.racine, "index.html")
            if os.path.isfile(index) and "." not in posixpath.basename(
                    self.path.rstrip("/") or "/"):
                self.path = "/index.html"
        return super().send_head()


def main():
    analyseur = argparse.ArgumentParser(description="Aperçu mobile Flutter web")
    analyseur.add_argument("--port", type=int,
                           default=int(os.environ.get("PORT", "3001")))
    analyseur.add_argument("--racine", default=RACINE_DEFAUT)
    options = analyseur.parse_args()

    if not os.path.isdir(options.racine):
        print(
            "Build web absent : " + options.racine + "\n"
            "Lancer d'abord ./arena/lancer-mobile.sh (qui exécute "
            "`flutter build web`).",
            file=sys.stderr,
        )
        return 2

    RepondeurMobile.racine = options.racine
    serveur = ThreadingHTTPServer(("0.0.0.0", options.port), RepondeurMobile)
    print(f"[mobile] http://0.0.0.0:{options.port}  →  {options.racine}")
    print(f"[mobile] /api/* relayé vers {CIBLE_API}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
