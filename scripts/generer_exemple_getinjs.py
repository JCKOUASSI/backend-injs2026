"""Génère un jeu SYNTHÉTIQUE depuis les modèles du commit déployé.

Exécution : cd <archive-du-commit>/backend && DJANGO_SETTINGS_MODULE=config.settings
DJANGO_DEBUG=1 USE_SQLITE=1 SQLITE_PATH=/tmp/getinjs-sans-db.sqlite3
GETINJS_EXEMPLE_OUT=<sortie> python <chemin-de-ce-script>
Aucune connexion à la base de données n'est effectuée.
"""
import csv
import json
import os
from pathlib import Path

import django
from django.apps import apps

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

commit = '70d08dad1821caceb61b22fe22cf70e13155bf18'
root = Path(os.environ['GETINJS_EXEMPLE_OUT'])
root.mkdir(parents=True, exist_ok=True)
base = 'GET-INJS-EXEMPLE-SYNTHETIQUE-70d08da'
date = '2026-11-15T10:00:00+00:00'  # horodatage inventé, pas une mesure
rows = {
    'scolarite_anneeacademique': [
        dict(id=900001, libelle='2026-2027', date_debut='2026-10-01',
             date_fin='2027-09-30', courante=True, actif=True, cloturee=False,
             description='Exemple pédagogique ; bornes provisoires, non officielles',
             source_document='DEMONSTRATION_SANS_SOURCE', fiabilite='A_RENSEIGNER')],
    'formations_refformation': [
        dict(id=900101, intitule='Formation fictive DEMO', perimetre='INJS',
             filiere_code='F01', source='EXEMPLE_SYNTHETIQUE', code='DEMO-F01',
             type_diplome='LICENCE', description='Intitulé inventé, aucun référentiel officiel')],
    'scolarite_niveau': [
        dict(id=900201, code='DEMO-L1', libelle='Licence 1 (démonstration)',
             cycle='LICENCE', ordre=1, credits_requis=60)],
    'scolarite_parcours': [
        dict(id=900301, ref_formation_id=900101, code='DEMO-P1',
             intitule='Parcours fictif', actif=True)],
    'scolarite_semestre': [
        dict(id=900401, niveau_id=900201, numero=1, libelle='Semestre 1 (démo)', actif=True)],
    'scolarite_groupe': [
        dict(id=900501, annee_academique_id=900001, ref_formation_id=900101,
             parcours_id=900301, niveau_id=900201, nom='DEMO-G1', capacite_max=30)],
    'scolarite_maquette': [
        dict(id=900601, annee_academique_id=900001, ref_formation_id=900101,
             parcours_id=900301, niveau_id=900201, version=1, statut='BROUILLON',
             libelle='Maquette fictive non validée',
             commentaire_validation='Ne pas valider : maquette et heures non officielles')],
    'scolarite_ue': [
        dict(id=900701, maquette_id=900601, semestre_id=900401, code='DEMO-UE01',
             intitule='UE fictive non officielle', credits=0,
             caractere='OBLIGATOIRE', ordre=1, statut='BROUILLON')],
    'scolarite_ecue': [
        dict(id=900801, ue_id=900701, code='DEMO-ECUE01',
             intitule='ECUE fictive : volume à confirmer', credits=0,
             coefficient='1.00', volume_cm='0.00', volume_td='0.00',
             volume_tp='0.00', archive=False, ordre=1, statut='BROUILLON')],
    'edts_creneautemplate': [
        dict(id=900901, jour='LUNDI', heure_debut='08:00:00',
             heure_fin='10:00:00', duree_prevue_minutes=120)],
    'edts_inscriptionimportee': [
        dict(id=901001, annee_academique_id=900001, matricule='DEMO-ETU-001',
             nom='FICTIF', prenoms='Exemple Un', filiere_code='F01',
             ref_formation_id=900101, parcours_id=900301, niveau_id=900201,
             semestre_id=900401, groupe_id=900501, statut='INSCRIT',
             fichier='exemple_synthetique_sans_import.csv', ligne_source=1),
        dict(id=901002, annee_academique_id=900001, matricule='DEMO-ETU-002',
             nom='FICTIF', prenoms='Exemple Deux', filiere_code='F01',
             ref_formation_id=900101, parcours_id=900301, niveau_id=900201,
             semestre_id=900401, groupe_id=900501, statut='INSCRIT',
             fichier='exemple_synthetique_sans_import.csv', ligne_source=2)],
    'edts_campagnegeneration': [
        dict(id=901101, annee_academique_id=900001,
             libelle='EXEMPLE — campagne non exécutable (volumes inconnus)',
             semaines=[1], perimetre={'formations': [900101], 'niveaux': [900201],
                                      'groupes': [900501]},
             parametres={}, statut='BROUILLON', bilan={}, anomalies=[], statistiques={})],
}

models = list(apps.get_app_config('edts').get_models())
models += [apps.get_model(app, name) for app, name in (
    *((('scolarite', n) for n in (
        'AnneeAcademique', 'Niveau', 'Semestre', 'Groupe', 'Maquette',
        'UE', 'ECUE', 'AffectationPedagogique', 'Parcours'))),
    *((('formations', n) for n in (
        'RefVague', 'RefFormation', 'RefSalle', 'Formateur'))),
    ('authentication', 'User'),
)]
models = sorted(models, key=lambda m: m._meta.db_table)
known = {m._meta.db_table: m for m in models}
assert set(rows) <= set(known)
for table, examples in rows.items():
    model = known[table]
    columns = {f.column: f for f in model._meta.fields}
    for example in examples:
        assert set(example) <= set(columns), (table, set(example)-set(columns))
        for column, field in columns.items():
            if column in example:
                value = example[column]
            elif field.null:
                value = None
            elif field.has_default():
                value = field.get_default()
            elif field.get_internal_type() in ('DateTimeField', 'DateField') and (field.auto_now or field.auto_now_add):
                value = date
            elif field.blank and field.get_internal_type() in ('CharField', 'TextField'):
                value = ''
            else:
                raise ValueError(f'Champ requis absent : {table}.{column}')
            example[column] = value
            if field.choices and value not in ('', None):
                assert value in {c[0] for c in field.choices}, (table, column, value)
            if field.max_length and value is not None:
                assert len(str(value)) <= field.max_length, (table, column)
            if field.is_relation and value is not None:
                target = field.remote_field.model._meta.db_table
                assert any(x['id'] == value for x in rows.get(target, [])), (table, column, target, value)
            elif value is not None and field.get_internal_type() not in ('JSONField', 'DateTimeField'):
                field.to_python(value)

# Les fichiers vides documentent les tables sans inventer d'exécution, d'EDT,
# de publication de séance ou d'identité réelle. Pas de SQL INSERT exploitable.
for model in models:
    table = model._meta.db_table
    columns = [f.column for f in model._meta.fields]
    with (root / (table + '.csv')).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=';')
        writer.writeheader()
        for row in rows.get(table, []):
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list))
                             else v for k, v in row.items()})

# contrôle d'intégrité après remplissage de toutes les colonnes
assert len(models) == 28
assert sum(map(len, rows.values())) == 13
(root / (base + '.json')).write_text(json.dumps({
    'nature': 'EXEMPLE_SYNTHETIQUE_NON_IMPORTABLE', 'commit_code': commit,
    'donnees_production': False, 'import_autorise': False,
    'tables': {m._meta.db_table: rows.get(m._meta.db_table, []) for m in models},
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('tables', len(models), 'lignes fictives', sum(map(len, rows.values())),
      'tables remplies', len(rows), 'tables vides', len(models)-len(rows))
