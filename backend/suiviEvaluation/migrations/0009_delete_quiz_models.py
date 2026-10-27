from django.db import migrations


class Migration(migrations.Migration):
    """
    Drop quiz tables on production servers that ran the old migration 0004.
    On fresh databases these tables don't exist, so we use IF EXISTS.
    No state changes — these models are not in the current migration state.
    SQLite compatible: no CASCADE (not supported by SQLite).
    """

    dependencies = [
        ('suiviEvaluation', '0008_quizmanuel_questionquiz_reponsequiz'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'DROP TABLE IF EXISTS "suiviEvaluation_reponsequiz";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_questionquiz";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_quizmanuel";'
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],
        ),
    ]
