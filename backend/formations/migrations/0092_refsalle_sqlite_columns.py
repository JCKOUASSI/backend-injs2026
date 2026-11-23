# P00-01 — Correctif de stabilisation du sandbox.
#
# La migration 0086 utilise SeparateDatabaseAndState avec, pour SQLite, un
# RunPython qui ajoute les colonnes via schema_editor.add_field(). Or Django
# 5.1.4 reconstruit la table (``_remake_table``) pour tout champ non-null ou
# avec défaut : dès la 3e colonne (``equipements``), la table est recréée à
# partir de l'état du modèle à 0085, ce qui élimine physiquement
# ``type_lieu`` et ``capacite`` (bien qu'elles restent déclarées dans l'état
# des migrations). Le chemin PostgreSQL de 0086 (RunSQL) est correct : cette
# migration ne fait donc rien sur PostgreSQL.
#
# Sur SQLite, on complète le schéma physique par un ALTER TABLE natif et
# idempotent (on n'agit que sur les colonnes réellement absentes). Aucune
# opération d'état n'est nécessaire : les champs sont déjà connus de l'état
# depuis 0086.
from django.db import migrations


def _existing_columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def add_sqlite_columns(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'sqlite':
        # PostgreSQL : les colonnes ont été créées par le RunSQL de 0086.
        return

    cursor = connection.cursor()
    table = 'formations_refsalle'
    columns = _existing_columns(cursor, table)

    # ALTER TABLE ADD COLUMN accepte un NOT NULL uniquement avec un défaut
    # non-null constant ; capacite est nullable.
    statements = {
        'type_lieu': (
            "ALTER TABLE formations_refsalle "
            "ADD COLUMN type_lieu varchar(20) NOT NULL DEFAULT 'SALLE'"
        ),
        'capacite': (
            "ALTER TABLE formations_refsalle ADD COLUMN capacite integer"
        ),
    }
    for name, sql in statements.items():
        if name not in columns:
            cursor.execute(sql)


def remove_sqlite_columns(apps, schema_editor):
    # SQLite ne supporte pas DROP COLUMN avant la 3.35 et, de toute façon,
    # ces colonnes font partie de l'état du modèle depuis 0086 : il n'y a rien
    # à annuler (base de développement/sandbox uniquement).
    return


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0091_lot1_notes_workflow'),
    ]

    operations = [
        migrations.RunPython(add_sqlite_columns, remove_sqlite_columns),
    ]
