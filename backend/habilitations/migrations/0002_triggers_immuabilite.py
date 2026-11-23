"""Protection base de l'immuabilité du journal (PostgreSQL uniquement).

Pose une fonction PL/pgSQL et des déclencheurs ``BEFORE UPDATE`` et
``BEFORE DELETE`` qui lèvent une exception, en complément de la protection
ORM (U1, note de conception §5).

Le déclencheur n'est installé que sur PostgreSQL (moteur de production et de
CI) : les statements sont fournis en liste (jamais redécoupés par Django)
afin de préserver le bloc ``$$ ... $$`` du corps de fonction. Sur SQLite —
bascule de développement exclusive, jamais un moteur de production — le
vidage des bases de test des ``TransactionTestCase`` passe par un
``DELETE FROM`` général que le déclencheur bloquerait ; l'immuabilité y reste
garantie au niveau ORM (modèle, queryset, administration).

La migration est totalement réversible.
"""
from django.db import migrations

NOM_TABLE = 'habilitations_journalhabilitation'

FONCTION = """
CREATE OR REPLACE FUNCTION habilitations_journal_immuable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'Le journal des habilitations est append-only : operation % refusee',
        TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

DECLENCHEURS = [
    "CREATE TRIGGER hab_journal_no_update BEFORE UPDATE ON "
    f"{NOM_TABLE} FOR EACH ROW "
    "EXECUTE FUNCTION habilitations_journal_immuable();",
    "CREATE TRIGGER hab_journal_no_delete BEFORE DELETE ON "
    f"{NOM_TABLE} FOR EACH ROW "
    "EXECUTE FUNCTION habilitations_journal_immuable();",
]

DEPOSE = [
    f"DROP TRIGGER IF EXISTS hab_journal_no_update ON {NOM_TABLE};",
    f"DROP TRIGGER IF EXISTS hab_journal_no_delete ON {NOM_TABLE};",
    "DROP FUNCTION IF EXISTS habilitations_journal_immuable();",
]


class TriggerImmutableRunSQL(migrations.RunSQL):
    """Exécute la protection seulement sur PostgreSQL."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):

    dependencies = [
        ('habilitations', '0001_initial'),
    ]

    operations = [
        TriggerImmutableRunSQL(sql=[FONCTION, *DECLENCHEURS], reverse_sql=DEPOSE),
    ]
