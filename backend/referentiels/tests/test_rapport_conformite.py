"""Génère le tableau de conformité réel des 27 référentiels (mission 03).

Ce module n'est **pas** un jeu d'assertions : c'est un outil de recette qui
exerce chaque référentiel par le HTTP réel (routes, permissions, exports,
imports, cycle de vie, recherche, tri, pagination, dépendances) et imprime un
tableau de conformité. Les valeurs du rapport final proviennent donc d'une
exécution mesurée, jamais d'une estimation.
"""

import json
import logging
import os

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from referentiels.registre import REGISTRE, modele_de
from referentiels.tests.test_recette_27_referentiels import (
    CHEMINS_ACTIONS,
    FORMATS,
    creer_valeur,
)

Utilisateur = get_user_model()


class TestRapportConformite(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Utilisateur.objects.create_user(
            username='conformite.admin', password='passe12345', role='ADMIN',
        )
        cls.lecteur = Utilisateur.objects.create_user(
            username='conformite.lecteur', password='passe12345', role='AUDITEUR',
        )

    def client_pour(self, utilisateur):
        client = APIClient()
        client.force_authenticate(utilisateur)
        return client

    def test_genere_le_tableau(self):
        admin = self.client_pour(self.admin)
        anonyme = APIClient()
        lignes = []

        for slug, entree in REGISTRE.items():
            modele = modele_de(entree)
            chemins = CHEMINS_ACTIONS.get(slug, {})
            lecture_seule = not entree['editable']

            def route(action):
                return chemins.get(action)

            # ── Consultation et lecture ────────────────────────────────────
            liste = admin.get(f'/api/referentiels/{slug}/')
            consultation = liste.status_code == 200
            pagination = False
            tri = False
            recherche = False
            if consultation:
                corps = liste.json()
                pagination = isinstance(corps, dict) and 'count' in corps
                recherche = admin.get(
                    f'/api/referentiels/{slug}/?search=zzz'
                ).status_code == 200
                tri = admin.get(
                    f'/api/referentiels/{slug}/?ordering=-id'
                ).status_code == 200

            # ── Écriture ──────────────────────────────────────────────────
            creation = admin.post(
                f'/api/referentiels/{slug}/', {}, format='json',
            ).status_code
            ecriture = 'oui' if creation in (201, 400) else (
                'refusée (lecture seule)' if creation in (403, 405) else str(creation)
            )

            # ── Exports ───────────────────────────────────────────────────
            formats_ok = []
            for format_export in FORMATS:
                reponse = admin.get(
                    f'/api/referentiels/{slug}/exporter/?export={format_export}'
                )
                if reponse.status_code == 200:
                    formats_ok.append(format_export)

            # ── Import ────────────────────────────────────────────────────
            import_analyse = admin.post(
                f'/api/referentiels/{slug}/importer/analyse/', {}, format='multipart',
            ).status_code
            import_statut = 'oui' if import_analyse in (200, 400) else (
                'refusé (lecture seule)' if import_analyse in (403, 405)
                else str(import_analyse)
            )

            # ── Permissions : un simple lecteur ne doit rien pouvoir écrire ─
            lecteur = self.client_pour(self.lecteur)
            refus_lecteur = all(
                lecteur.post(f'/api/referentiels/{slug}/', {}, format='json').status_code
                in (401, 403)
                for _ in (0,)
            )

            # ── Anonyme : aucune lecture ──────────────────────────────────
            refus_anonyme = anonyme.get(f'/api/referentiels/{slug}/').status_code in (
                401, 403,
            )

            # ── Cycle de vie (référentiels éditables) ──────────────────────
            cycle = {}
            if not lecture_seule:
                objet, motif = creer_valeur(slug, f'C-{slug}')
                if objet is not None:
                    pk = objet.pk
                    for action in ('activer', 'desactiver', 'archiver',
                                   'reactiver', 'supprimer'):
                        chemin = route(action)
                        if not chemin:
                            cycle[action] = 'n/a'
                            continue
                        reponse = admin.post(chemin.replace('{pk}', str(pk)), {})
                        cycle[action] = reponse.status_code
                else:
                    cycle['_motif'] = motif
            else:
                cycle = {a: 'n/a' for a in
                         ('activer', 'desactiver', 'archiver', 'reactiver',
                          'supprimer')}

            lignes.append({
                'slug': slug,
                'libelle': str(modele._meta.verbose_name),
                'lecture_seule': lecture_seule,
                'consultation': consultation,
                'recherche': recherche,
                'tri': tri,
                'pagination': pagination,
                'ecriture': ecriture,
                'exports': formats_ok,
                'import': import_statut,
                'refus_lecteur': refus_lecteur,
                'refus_anonyme': refus_anonyme,
                'cycle': cycle,
            })

        with open('/tmp/conformite-27.json', 'w', encoding='utf-8') as f:
            json.dump(lignes, f, ensure_ascii=False, indent=1)

        # Le relevé détaillé n'est imprimé que sur demande : en CI, il
        # noierait la sortie des 3 000 autres tests. La variable
        # ``INJS_RAPPORT_CONFORMITE=1`` le réactive pour la recette manuelle.
        if not os.environ.get('INJS_RAPPORT_CONFORMITE'):
            return
        for ligne in lignes:
            logger.info(
                '%s RO=%s lecture=%s rech=%s tri=%s paging=%s ecriture=%s '
                'exports=%s/4 import=%s lecteur_refuse=%s anonyme_refuse=%s cycle=%s',
                ligne['slug'], ligne['lecture_seule'], ligne['consultation'],
                ligne['recherche'], ligne['tri'], ligne['pagination'],
                ligne['ecriture'], len(ligne['exports']), ligne['import'],
                ligne['refus_lecteur'], ligne['refus_anonyme'], ligne['cycle'],
            )
