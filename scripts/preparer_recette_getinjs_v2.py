#!/usr/bin/env python3
"""Construit un OVERLAY source GET-INJS pour recette isolée, jamais un déploiement.

L'overlay doit être appliqué à un checkout propre du commit de référence.
Il exclut volontairement scolarite.0021, les données fictives et les secrets.
Ne contacte aucune base ni aucun serveur ; ne pousse aucune branche.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

REFERENCE = '70d08dad1821caceb61b22fe22cf70e13155bf18'
ROOT = Path(__file__).resolve().parent.parent
SORTIE = ROOT / 'livrables/GET-INJS-RECETTE-ISOLEE'
FICHIERS = (
    'backend/edts/api.py',
    'backend/edts/api_getinjs.py',
    'backend/edts/api_interop.py',
    'backend/edts/api_lmd.py',
    'backend/edts/api_v2_experimental.py',
    'backend/edts/management/commands/traiter_campagne_v2.py',
    'backend/edts/migrations/0013_executionligne_periodeacademique_revisioncalendrier_and_more.py',
    'backend/edts/models.py',
    'backend/edts/models_fondations.py',
    'backend/edts/moteur/application_v2.py',
    'backend/edts/moteur/calendrier_v2.py',
    'backend/edts/moteur/campagnes_v2.py',
    'backend/edts/moteur/interop_presences.py',
    'backend/edts/moteur/occupation_v2.py',
    'backend/edts/moteur/planification_v2.py',
    'backend/edts/moteur/publication.py',
    'backend/edts/moteur/qr_v2.py',
    'backend/edts/tests/test_api_v2_phase5.py',
    'backend/edts/tests/test_fondations_v2.py',
    'backend/edts/tests/test_moteur_v2_phase3.py',
    'backend/edts/tests/test_phase6_postgres_concurrency.py',
    'backend/edts/tests/test_phase6_revalidation.py',
    'backend/edts/tests/test_qr_v2_phase4.py',
    'backend/edts/urls.py',
    'backend/presences/seances_edt_services.py',
    'frontend/src/App.jsx',
    'frontend/src/pages/getinjs/BenchV2.jsx',
    'frontend/src/pages/getinjs/BenchV2.test.jsx',
)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def preparer():
    git('cat-file', '-e', f'{REFERENCE}^{{commit}}')
    assert len(FICHIERS) == len(set(FICHIERS))
    assert all(n.startswith(('backend/edts/', 'backend/presences/',
                             'frontend/src/')) and '..' not in Path(n).parts
               for n in FICHIERS)
    assert not any('scolarite/' in n or '.env' in n for n in FICHIERS)
    manifest = {
        'nature': 'OVERLAY_RECETTE_LOCALE_NON_DEPLOYABLE_SEUL',
        'commit_reference': REFERENCE,
        'commit_source': git('rev-parse', 'HEAD'),
        'migrations_autorisees': ['edts.0013'],
        'migrations_exclues': ['scolarite.0021'],
        'fichiers': {},
    }
    SORTIE.mkdir(parents=True, exist_ok=True)
    archive = SORTIE / 'getinjs-v2-overlay-recette.tar.gz'
    # MTIME fixé : deux constructions à sources identiques ont le même hash.
    with archive.open('wb') as fichier:
        import gzip
        with gzip.GzipFile(filename='', mode='wb', fileobj=fichier, mtime=0) as compresse:
            with tarfile.open(mode='w', fileobj=compresse, format=tarfile.PAX_FORMAT) as tar:
                for nom in sorted(FICHIERS):
                    chemin = ROOT / nom
                    if not chemin.is_file() or chemin.is_symlink():
                        raise RuntimeError(f'Fichier source absent ou lien refusé : {nom}')
                    contenu = chemin.read_bytes()
                    manifest['fichiers'][nom] = hashlib.sha256(contenu).hexdigest()
                    entree = tarfile.TarInfo(nom)
                    entree.size = len(contenu)
                    entree.mtime = 0
                    entree.mode = 0o644
                    entree.uid = entree.gid = 0
                    entree.uname = entree.gname = ''
                    tar.addfile(entree, io.BytesIO(contenu))
    chemin_manifest = SORTIE / 'manifest.json'
    chemin_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + '\n')
    (SORTIE / 'SHA256SUMS.txt').write_text(
        f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n'
        f'{hashlib.sha256(chemin_manifest.read_bytes()).hexdigest()}  {chemin_manifest.name}\n')
    print(json.dumps({'nature': manifest['nature'], 'base': REFERENCE,
                      'fichiers': len(FICHIERS), 'octets_archive': archive.stat().st_size,
                      'scolarite_0021_incluse': False}, ensure_ascii=False))


if __name__ == '__main__':
    preparer()
