#!/usr/bin/env python3
"""Banc annuel REPRODUCTIBLE et fictif du vrai solveur v2, hors production.

Exécuter avec PYTHONPATH pointant vers une extraction isolée de 70d08da
+ phases 2–5 et GETINJS_PHASE6_ISOLATED=1. SQLite exige USE_SQLITE=1 et
SQLITE_PATH=/tmp/... ; PostgreSQL exige en outre GETINJS_PG_ISOLATED=1,
une base BENCH locale vide et le socket de test explicitement autorisé.
Ne jamais importer les CSV dans une base réelle.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import timedelta
import os
import resource
import sys
import time
from contextlib import contextmanager
from datetime import date, time as horaire
from pathlib import Path


def mesure_memoire():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # Linux KiB


@contextmanager
def compte_sql():
    from django.db import connection
    compte = {'sql': 0}
    def tracer(execute, sql, params, many, context):
        compte['sql'] += 1
        return execute(sql, params, many, context)
    with connection.execute_wrapper(tracer):
        yield compte


def preparer(csv_dir, taille):
    from scolarite.models import AnneeAcademique, Niveau, Groupe
    from formations.models import RefFormation, RefSalle, RefSite, Formateur
    from edts.models import (CreneauTemplate, InscriptionImportee, PeriodeAcademique,
                              RevisionCalendrier, DisponibiliteHoraire)
    # AnneeAcademique.libelle max_length=20 : SQLite tolère une valeur trop
    # longue, PostgreSQL l'interdit. Garder une étiquette BENCHMARK valide.
    annee = AnneeAcademique.objects.create(libelle=f'BENCHMARK-P6-{taille}',
        date_debut=date(2098, 10, 1), date_fin=date(2099, 9, 30), fiabilite='A_RENSEIGNER')
    formation = RefFormation.objects.create(intitule='BENCH FICTIF PHASE 6',
        perimetre='INJS', filiere_code='F01', source='BENCH_NON_IMPORTABLE')
    niveau = Niveau.objects.create(code=f'B{taille}', libelle='Niveau fictif')
    site = RefSite.objects.create(nom='SITE FICTIF BENCH')
    groupes_csv = list(csv.DictReader((csv_dir / 'groupes_BENCH_NON_IMPORTABLE.csv').open(), delimiter=';'))
    groupes = Groupe.objects.bulk_create([Groupe(annee_academique=annee, ref_formation=formation,
        niveau=niveau, nom=g['groupe_test'], capacite_max=60) for g in groupes_csv], batch_size=256)
    groupes = list(Groupe.objects.filter(annee_academique=annee).order_by('nom'))
    correspondance = {g.nom: g.pk for g in groupes}
    # Imports synthétiques, jamais des participants QR. Le chrono inclut ce bulk insert.
    t0 = time.monotonic()
    tampon = []
    with (csv_dir / 'etudiants_BENCH_NON_IMPORTABLE.csv').open() as f:
        for ligne in csv.DictReader(f, delimiter=';'):
            tampon.append(InscriptionImportee(annee_academique=annee, ref_formation=formation,
                niveau=niveau, groupe_id=correspondance[ligne['groupe_test']],
                matricule=ligne['matricule_fictif'], nom='SYNTHETIQUE',
                statut='INSCRIT', fichier='BENCH_NON_IMPORTABLE'))
            if len(tampon) == 256:
                InscriptionImportee.objects.bulk_create(tampon, batch_size=256)
                tampon.clear()
    if tampon:
        InscriptionImportee.objects.bulk_create(tampon, batch_size=256)
    duree_import = time.monotonic() - t0
    formateurs = Formateur.objects.bulk_create([Formateur(numerobadge=f'B-{taille}-{i}',
        nom='FICTIF', prenom=str(i)) for i in range(40)])
    formateurs = list(Formateur.objects.filter(numerobadge__startswith=f'B-{taille}-').order_by('pk'))
    RefSalle.objects.bulk_create([RefSalle(site=site, nom=f'SALLE-B-{i}', capacite=60,
        type_lieu=('TP' if i < 2 else 'SALLE')) for i in range(20)])
    # Quatre plages, 6 jours : salles rares mais capacité annuelle suffisante.
    for jour in ('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI'):
        for debut, fin in ((8, 10), (10, 12), (13, 15), (15, 17)):
            CreneauTemplate.objects.create(jour=jour, heure_debut=horaire(debut),
                heure_fin=horaire(fin))
    revision = RevisionCalendrier.objects.create(annee_academique=annee, numero=1)
    # OFFICIEL ici est une valeur TECHNIQUE de test du solveur, pas une attestation INJS.
    PeriodeAcademique.objects.create(annee_academique=annee, revision=revision, type='COURS',
        date_debut=annee.date_debut, date_fin=annee.date_fin, statut_validation='VALIDEE',
        fiabilite='OFFICIEL', source_document='SOURCE SYNTHETIQUE DE TEST NON OFFICIELLE')
    for debut, fin in ((date(2098, 12, 20), date(2099, 1, 5)),
                       (date(2099, 4, 1), date(2099, 4, 10))):
        # Les vacances ciblées sur ce groupe respectent la sémantique de recouvrement.
        PeriodeAcademique.objects.create(annee_academique=annee, revision=revision,
            type='VACANCES', portee='GROUPE', groupe=groupes[0],
            date_debut=debut, date_fin=fin, statut_validation='VALIDEE',
            fiabilite='OFFICIEL', source_document='SOURCE SYNTHETIQUE DE TEST NON OFFICIELLE')
    PeriodeAcademique.objects.create(annee_academique=annee, revision=revision,
        type='FERIE', date_debut=date(2099, 5, 1), date_fin=date(2099, 5, 1),
        statut_validation='VALIDEE', fiabilite='OFFICIEL',
        source_document='SOURCE SYNTHETIQUE DE TEST NON OFFICIELLE')
    # Indisponibilité dure contrôlée : formateur partagé entre les groupes.
    DisponibiliteHoraire.objects.create(annee_academique=annee,
        enseignant=formateurs[0], jour='MARDI', heure_debut=horaire(8),
        heure_fin=horaire(10), statut='INDISPONIBLE')
    return annee, groupes, formateurs, duree_import


def travaux(csv_dir, annee, groupes, formateurs):
    from edts.moteur.planification_v2 import TravailSeance
    ids = {g.nom: g.pk for g in groupes}
    effectifs = {g.nom: g.capacite_max for g in groupes}
    # Le volume est inventé pour le benchmark, JAMAIS pour une année réelle.
    with (csv_dir / 'besoins_BENCH_NON_IMPORTABLE.csv').open() as f:
        for ligne in csv.DictReader(f, delimiter=';'):
            numero = int(ligne['ecue_fictif'].rsplit('-', 1)[-1])
            groupe_nom = ligne['groupe_test']
            # Type d'essai indépendant : la source CSV reste non importable.
            type_seance = ('CM', 'TD', 'TP', 'CM')[numero - 1]
            formateur_id = formateurs[(list(ids).index(groupe_nom) + numero) % len(formateurs)].pk
            for ordinal in range(1, int(ligne['occurrences_test']) + 1):
                # Les ECUE du CSV sont des étiquettes de test, sans FK métier :
                # ordinal unique par groupe/type pour éviter toute collision.
                yield TravailSeance(annee.pk, ids[groupe_nom], 0, type_seance,
                    (numero - 1) * 12 + ordinal, int(ligne['duree_minutes_test']), effectifs[groupe_nom],
                    formateur_id=formateur_id, source_confirmee=True,
                    source_document='SOURCE SYNTHETIQUE DE TEST NON OFFICIELLE')


def executer(args):
    from django.conf import settings
    from django.db import connection
    sqlite_isole = (connection.vendor == 'sqlite' and
        str(connection.settings_dict['NAME']).startswith('/tmp/'))
    pg_isole = (connection.vendor == 'postgresql' and
        os.getenv('GETINJS_PG_ISOLATED') == '1' and
        connection.settings_dict['HOST'] == '/tmp/getinjs-pg-socket' and
        str(connection.settings_dict['PORT']) == '55432' and
        str(connection.settings_dict['NAME']).startswith('getinjs_bench_'))
    if (os.getenv('GETINJS_PHASE6_ISOLATED') != '1' or not settings.DEBUG or
        not (sqlite_isole or pg_isole)):
        raise RuntimeError('Banc refusé : base locale jetable SQLite ou PostgreSQL isolé requis.')
    if pg_isole:
        from scolarite.models import AnneeAcademique
        from edts.models import AffectationCreneau, InscriptionImportee
        if (AnneeAcademique.objects.exists() or AffectationCreneau.objects.exists() or
                InscriptionImportee.objects.exists()):
            raise RuntimeError('Base PostgreSQL BENCH non vide : refus de réutilisation.')
    # Le flag n'est PAS un réglage de production. L'activer seulement après
    # validation de la base jetable locale ; le processus ne sert aucune API.
    settings.GETINJS_V2_EXPERIMENTAL_WRITE = True
    csv_dir = Path(args.csv_dir).resolve()
    manifeste = json.loads((csv_dir / 'manifest.json').read_text())
    if (manifeste.get('nature') != 'DONNEES_SYNTHETIQUES_NON_IMPORTABLES' or
        manifeste.get('etudiants') != args.etudiants):
        raise ValueError('Manifest de charge fictive incohérent.')
    annee, groupes, formateurs, import_s = preparer(csv_dir, args.etudiants)
    from edts.moteur.campagnes_v2 import simuler_campagne_v2
    from edts.moteur.application_v2 import (appliquer_ligne, appliquer_proposition_automatique,
                                             proposer_ligne)
    from edts.models import AffectationCreneau
    from edts.models_interop import SeanceRegistre
    source = travaux(csv_dir, annee, groupes, formateurs)
    if args.mode == 'semaine':
        # Une fenêtre de quatre journées de la première semaine ouvrée, avec
        # occupation SQL revalidée et protocole QR ; 30 groupes indépendants.
        import itertools
        latences = []
        statuts = Counter()
        codes = Counter()
        with compte_sql() as sql:
            for _, besoins in itertools.groupby(source, key=lambda t: t.groupe_id):
                if len(latences) == min(30, len(groupes)):
                    break
                debut_groupe = time.monotonic()
                for idx, travail in enumerate(itertools.islice(besoins, 4)):
                    decision = proposer_ligne(travail, revision=1,
                        jour=date(2098, 10, 13) + timedelta(days=idx))
                    if decision.statut == 'PLACEE':
                        decision = appliquer_ligne(travail, decision, revision=1)
                    statuts[decision.statut] += 1
                    codes[decision.code] += 1
                latences.append(time.monotonic() - debut_groupe)
            sql_nombre = sql['sql']
        triees = sorted(latences)
        return {'mode': args.mode, 'etudiants_synthetiques_importes': args.etudiants,
            'groupes_mesures': len(latences), 'occurrences_cibles': len(latences) * 4,
            'decisions': dict(statuts), 'codes': dict(codes),
            'p95_groupe_semaine_s': round(triees[max(0, int(0.95 * len(triees) + 0.9999) - 1)], 3),
            'max_groupe_semaine_s': round(max(latences), 3), 'sql_mesure': sql_nombre,
            'maxrss_kib': mesure_memoire(), 'duree_import_s': round(import_s, 3),
            'placements_persistes': AffectationCreneau.objects.filter(
                emploi_du_temps__annee_academique=annee).count(),
            'registres_qr': SeanceRegistre.objects.filter(
                affectation__emploi_du_temps__annee_academique=annee).count(),
            'source': 'FICTIVE_NON_OFFICIELLE'}
    compteur = {'PLACEE': 0, 'ECHEC': 0, 'A_REVOIR': 0}
    codes = Counter()
    exemples_echec = []
    debut = time.monotonic()
    dernier = -1
    groupes_finis = 0
    lignes = 0
    sql_compte = 0
    with compte_sql() as sql:
        for travail, decision in zip(source, simuler_campagne_v2(travaux(csv_dir, annee, groupes, formateurs),
                                                                  revision=1, graine=42)):
            if travail.groupe_id != dernier:
                if dernier != -1:
                    groupes_finis += 1
                dernier = travail.groupe_id
                if groupes_finis and groupes_finis % 10 == 0 and lignes % 48 == 0:
                    print(json.dumps({'groupes': groupes_finis, 'lignes': lignes,
                        'elapsed_s': round(time.monotonic() - debut, 3), 'sql': sql['sql']}), flush=True)
            initiale = decision
            if args.mode == 'commit' and decision.statut == 'PLACEE':
                decision = appliquer_proposition_automatique(travail, decision, revision=1, graine=42)
            compteur[decision.statut] += 1
            codes[decision.code] += 1
            if decision.statut != 'PLACEE' and len(exemples_echec) < 8:
                exemples_echec.append({'code': decision.code, 'type': travail.type_seance,
                    'ordinal': travail.ordinal, 'groupe_index': groupes.index(next(
                        g for g in groupes if g.pk == travail.groupe_id)) + 1,
                    'simulation_date': str(initiale.jour), 'simulation_salle': initiale.salle_id,
                    'simulation_slot': initiale.creneau_id})
            lignes += 1
            if time.monotonic() - debut > args.budget_secondes:
                break
        sql_compte = sql['sql']
    termine = lignes == manifeste['besoins_fictifs'] * 12
    return {'mode': args.mode, 'etudiants_synthetiques_importes': args.etudiants,
        'groupes_cibles': len(groupes), 'besoins_cibles': manifeste['besoins_fictifs'],
        'occurrences_cibles': manifeste['besoins_fictifs'] * 12,
        'groupes_finies': groupes_finis + int(termine), 'occurrences_traitees': lignes,
        'termine': termine, 'duree_import_s': round(import_s, 3),
        'duree_calcul_ou_commit_s': round(time.monotonic() - debut, 3),
        'maxrss_kib': mesure_memoire(), 'sql_mesure': sql_compte,
        'decisions': compteur, 'codes': dict(codes), 'exemples_echec': exemples_echec,
        'placements_persistes': AffectationCreneau.objects.filter(
            emploi_du_temps__annee_academique=annee, cle_occurrence_v2__isnull=False).count(),
        'registres_qr': SeanceRegistre.objects.filter(
            affectation__emploi_du_temps__annee_academique=annee).count(),
        'limite_s': args.budget_secondes, 'source': 'FICTIVE_NON_OFFICIELLE'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv-dir', required=True)
    parser.add_argument('--etudiants', type=int, choices=(5000, 10000, 15000), required=True)
    parser.add_argument('--mode', choices=('simulation', 'commit', 'semaine'), required=True)
    parser.add_argument('--budget-secondes', type=int, default=600)
    args = parser.parse_args()
    if __name__ == '__main__':
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        import django
        django.setup()
        try:
            print(json.dumps(executer(args), ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({'erreur': type(exc).__name__, 'message': str(exc)[:300]}), flush=True)
            raise
