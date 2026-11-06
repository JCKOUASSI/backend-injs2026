"""Contrôles de la configuration candidate de la passerelle Nginx (mission 02).

Les tests sont **statiques** : aucun nginx n'est disponible dans l'environnement
de développement. Ils vérifient la présence, la cohérence et la non-régression
des trois corrections demandées :

* **A** — le protocole public n'est plus écrasé par ``$scheme`` ;
* **B** — ``/admin/`` est fermée par défaut ;
* **C** — ``client_max_body_size`` est défini et cohérent avec les limites
  applicatives réelles (il n'est pas choisi arbitrairement).

La validation dynamique (``nginx -t``, puis les essais HTTPS/CSRF/cookies)
relève de la procédure d'application sur le VPS : voir
``docs/deploiement/mission-02/DEPLOY_INJS_MISSION_02_NGINX.md``.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from django.test import SimpleTestCase

from core.validators import TAILLE_MAX_PIECE, TAILLE_MAX_PREUVE

RACINE = Path(__file__).resolve().parents[3]
CONF = RACINE / 'docker' / 'nginx' / 'default.conf'
COMPOSE_PROD = RACINE / 'deploy' / 'production' / 'compose.yml'


class ConfigurationGatewayTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contenu = CONF.read_text(encoding='utf-8')
        # Contenu sans les lignes de commentaire : les contrôles de présence
        # d'une directive ne doivent pas être trompés par la documentation.
        cls.contenu_utile = '\n'.join(
            ligne for ligne in cls.contenu.splitlines()
            if not ligne.strip().startswith('#')
        )

    # ── A. Protocole public ─────────────────────────────────────────────────
    def test_le_scheme_local_ne_remplace_plus_le_protocole_public(self):
        """Anomalie de l'audit : `proxy_set_header X-Forwarded-Proto $scheme;`."""
        self.assertNotIn('X-Forwarded-Proto $scheme;', self.contenu)

    def test_le_protocole_transmis_par_le_proxy_est_relaye(self):
        self.assertIn('map $http_x_forwarded_proto $proto_public', self.contenu)
        self.assertIn('proxy_set_header X-Forwarded-Proto $proto_public', self.contenu)

    def test_le_repli_utilise_le_scheme_de_la_connexion_entrante(self):
        # Si NPM ne transmet rien, on retombe sur $scheme (pas d'en-tête vide).
        self.assertIn("''       $scheme;", self.contenu)

    # ── B. Administration Django ────────────────────────────────────────────
    def test_admin_est_fermee_par_defaut(self):
        bloc = self._bloc('/admin/')
        self.assertIn('deny all;', bloc)

    def test_admin_n_est_jamais_ouverte_a_tous(self):
        # Vérifié hors commentaires (la procédure documentée cite `allow all;`
        # pour mettre en garde, sans l'activer).
        self.assertNotIn('allow all;', self.contenu_utile)

    def test_les_api_du_frontend_restent_accessibles(self):
        self.assertIn('location /api/ {', self.contenu)
        self.assertIn('proxy_pass http://backend:8000;', self.contenu)
        self.assertIn('location / {', self.contenu)
        self.assertIn('proxy_pass http://frontend:80;', self.contenu)

    def test_static_et_media_restent_servis(self):
        self.assertIn('alias /app/staticfiles/;', self.contenu)
        self.assertIn('alias /app/media/;', self.contenu)

    # ── C. Taille des requêtes ──────────────────────────────────────────────
    def test_client_max_body_size_est_defini_explicitement(self):
        self.assertIn('client_max_body_size', self.contenu)

    def test_la_taille_couvre_le_pire_cas_applicatif(self):
        """Une pièce (10 Mio) + une preuve (5 Mio) + marge d'encodage."""
        valeur = self._client_max_body_size()
        pire_cas = TAILLE_MAX_PIECE + TAILLE_MAX_PREUVE  # 15 Mio
        self.assertGreaterEqual(valeur, pire_cas)

    def test_la_taille_reste_bornee(self):
        valeur = self._client_max_body_size()
        self.assertLessEqual(valeur, 64 * 1024 * 1024)

    # ── Structure ───────────────────────────────────────────────────────────
    def test_accolades_equilibrees(self):
        self.assertEqual(self.contenu.count('{'), self.contenu.count('}'))

    def test_le_fichier_est_celui_monte_par_le_compose(self):
        with COMPOSE_PROD.open(encoding='utf-8') as handle:
            compose = yaml.safe_load(handle)
        montages = compose['services']['gateway']['volumes']
        chemins = [m.split(':')[0] for m in montages]
        attendu = '../../docker/nginx/default.conf'
        self.assertIn(attendu, chemins)
        # La cible du montage doit exister dans le dépôt.
        self.assertTrue((RACINE / 'docker' / 'nginx' / 'default.conf').exists())

    def test_le_montage_est_en_lecture_seule(self):
        with COMPOSE_PROD.open(encoding='utf-8') as handle:
            compose = yaml.safe_load(handle)
        montages = compose['services']['gateway']['volumes']
        conf = [m for m in montages if 'nginx/default.conf' in m]
        self.assertTrue(conf)
        self.assertTrue(conf[0].endswith(':ro'))

    # ── Utilitaires ─────────────────────────────────────────────────────────
    def _client_max_body_size(self) -> int:
        import re

        motif = re.search(r'client_max_body_size\s+(\d+)([kKmMgG]?)\s*;', self.contenu)
        self.assertIsNotNone(motif, 'client_max_body_size introuvable')
        valeur, unite = int(motif.group(1)), motif.group(2).lower()
        return valeur * {'': 1, 'k': 1024, 'm': 1024 ** 2, 'g': 1024 ** 3}[unite]

    def _bloc(self, entete: str) -> str:
        debut = self.contenu.index(f'location {entete} {{')
        profondeur, i = 0, debut
        while i < len(self.contenu):
            if self.contenu[i] == '{':
                profondeur += 1
            elif self.contenu[i] == '}':
                profondeur -= 1
                if profondeur == 0:
                    return self.contenu[debut:i + 1]
            i += 1
        return self.contenu[debut:]
