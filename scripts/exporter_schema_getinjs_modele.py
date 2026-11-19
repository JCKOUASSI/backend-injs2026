"""Inventaire documentaire du schéma GET INJS depuis les modèles Django chargés.

À exécuter dans une copie isolée du COMMIT DÉPLOYÉ, jamais contre la base
publique. N'ouvre aucune connexion SQL et n'exporte aucune donnée personnelle.
"""
import csv
import json
import os
from pathlib import Path

import django
from django.apps import apps

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

COMMIT = '70d08dad1821caceb61b22fe22cf70e13155bf18'
OUT = Path(os.environ['GETINJS_SCHEMA_OUT'])
OUT.mkdir(parents=True, exist_ok=True)

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
selected = {m._meta.db_table for m in models}
result = {'commit': COMMIT, 'nature': 'Schéma inféré des modèles Django déployés ; pas un dump PostgreSQL.',
          'tables': [], 'relations': [], 'tables_externes': []}
externes = set()
for model in models:
    table = model._meta.db_table
    champs = []
    for f in model._meta.fields:
        rel = f.remote_field.model._meta.db_table if f.is_relation else None
        col = {
            'colonne': f.column, 'champ_django': f.name,
            'type_django': f.get_internal_type(), 'nullable': f.null,
            'cle_primaire': f.primary_key, 'unique': f.unique,
            'index_individuel': f.db_index, 'longueur_max': getattr(f, 'max_length', None),
            'reference_table': rel, 'reference_colonne': f.target_field.column if rel else None,
            'relation': 'one_to_one' if f.one_to_one else 'many_to_one' if rel else None,
        }
        champs.append(col)
        if rel:
            result['relations'].append({'depuis_table': table, 'depuis_colonne': f.column,
                                        'vers_table': rel, 'vers_colonne': f.target_field.column,
                                        'nullable': f.null, 'relation': col['relation']})
            if rel not in selected:
                externes.add(rel)
    constraints = [
        {'nom': c.name, 'type': type(c).__name__,
         'champs': list(getattr(c, 'fields', []))}
        for c in model._meta.constraints
    ]
    indexes = [
        {'nom': i.name, 'champs': list(i.fields), 'type': type(i).__name__}
        for i in model._meta.indexes
    ]
    m2m = [
        {'champ': f.name, 'table_jointure': f.remote_field.through._meta.db_table,
         'cible': f.remote_field.model._meta.db_table,
         'auto_generee': f.remote_field.through._meta.auto_created is not False}
        for f in model._meta.many_to_many
    ]
    result['tables'].append({'application': model._meta.app_label,
                             'modele': model.__name__, 'table': table,
                             'colonnes': champs, 'contraintes_modele': constraints,
                             'index_modele': indexes, 'many_to_many': m2m})
result['tables_externes'] = sorted(externes)
base = 'GET-INJS-SCHEMA-70d08da'
(OUT / f'{base}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
with (OUT / f'{base}-colonnes.csv').open('w', newline='', encoding='utf-8-sig') as out:
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['application','table','colonne','champ_django','type_django','nullable',
                     'cle_primaire','unique','index_individuel','longueur_max',
                     'reference_table','reference_colonne','relation'])
    for table in result['tables']:
        for f in table['colonnes']:
            writer.writerow([table['application'],table['table'],*[f[k] for k in (
                'colonne','champ_django','type_django','nullable','cle_primaire',
                'unique','index_individuel','longueur_max','reference_table',
                'reference_colonne','relation')]])

# Deux diagrammes lisibles ; l'inventaire JSON/CSV reste exhaustif pour le
# périmètre sélectionné (dont relations vers d'autres applications).
graphes = {
    'principal': {
        'scolarite_anneeacademique', 'formations_refformation', 'scolarite_niveau',
        'scolarite_semestre', 'scolarite_parcours', 'scolarite_groupe',
        'scolarite_maquette', 'scolarite_ue', 'scolarite_ecue',
        'scolarite_affectationpedagogique', 'edts_inscriptionimportee',
        'edts_campagnegeneration', 'edts_executioncampagne',
        'edts_emploidutemps', 'edts_creneautemplate',
        'edts_affectationcreneau', 'formations_refsalle',
    },
    'interop': {
        'edts_affectationcreneau', 'gi_seance_registre', 'gi_seance_historique',
        'gi_seance_evenement', 'gi_seance_instantane', 'gi_salle_geolocalisation',
        'formations_refsalle', 'edts_emploidutemps',
    },
}
for name, nodes in graphes.items():
    lines = ['erDiagram']
    for table in result['tables']:
        if table['table'] in nodes:
            pk = next((c['colonne'] for c in table['colonnes'] if c['cle_primaire']), 'id')
            lines.append(f'  {table["table"]} {{')
            lines.append(f'    bigint {pk} PK')
            lines.append('  }')
    for rel in result['relations']:
        if rel['depuis_table'] in nodes and rel['vers_table'] in nodes:
            cardinalite = 'o|' if rel['nullable'] else '||'
            multiple = 'o|' if rel['relation'] == 'one_to_one' else 'o{'
            lines.append(f'  {rel["vers_table"]} {cardinalite}--{multiple} {rel["depuis_table"]} : {rel["depuis_colonne"]}')
    (OUT / f'{base}-{name}.mmd').write_text('\n'.join(lines)+'\n')
print('MODELES', len(result['tables']), 'COLONNES', sum(len(t['colonnes']) for t in result['tables']),
      'RELATIONS', len(result['relations']), 'EXTERNES',len(externes))
