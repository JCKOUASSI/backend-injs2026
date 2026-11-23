from django.db import migrations


class Migration(migrations.Migration):
    """
    Supprime les tables d'évaluation académique legacy (migration 0004) sur les
    bases qui les ont encore, et nettoie l'état Django (modèles absents de models.py).
    """

    dependencies = [
        ('suiviEvaluation', '0009_delete_quiz_models'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'DROP TABLE IF EXISTS "suiviEvaluation_historiquenotemodification";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_noteepreuve";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_suivimoduleauditeur";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_moyennemodule";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_ficheauditeuracademique_modules_suivis";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_ficheauditeuracademique";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_ficheformateur";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_decisionpedagogique";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_exportrapport";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_parametresevaluation";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_epreuve";'
                        'DROP TABLE IF EXISTS "suiviEvaluation_typeepreuve";'
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.DeleteModel(name='HistoriqueNoteModification'),
                migrations.DeleteModel(name='NoteEpreuve'),
                migrations.DeleteModel(name='MoyenneModule'),
                migrations.DeleteModel(name='SuiviModuleAuditeur'),
                migrations.DeleteModel(name='FicheAuditeurAcademique'),
                migrations.DeleteModel(name='FicheFormateur'),
                migrations.DeleteModel(name='ExportRapport'),
                migrations.DeleteModel(name='ParametresEvaluation'),
                migrations.DeleteModel(name='DecisionPedagogique'),
                migrations.DeleteModel(name='Epreuve'),
                migrations.DeleteModel(name='TypeEpreuve'),
            ],
        ),
    ]
