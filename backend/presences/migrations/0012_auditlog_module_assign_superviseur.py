from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presences', '0011_add_absent_non_badge_statut_and_auto_absent_action'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(
                choices=[
                    ('SCAN_ENTREE', 'Scan entrée (QR public)'),
                    ('SCAN_SORTIE', 'Scan sortie (QR public)'),
                    ('SCAN_SECURE_ENTREE', 'Scan sécurisé entrée (mobile)'),
                    ('SCAN_SECURE_SORTIE', 'Scan sécurisé sortie (mobile)'),
                    ('FORCE_ENTREE', 'Entrée forcée (encadrant/DFRC)'),
                    ('FORCE_SORTIE', 'Sortie forcée (encadrant/DFRC)'),
                    ('CLOSE_SESSION', 'Fermeture de session (encadrant/DFRC)'),
                    ('AUTO_ABSENT', 'Absent automatique (délai badge sortie dépassé)'),
                    ('DEVICE_UNBIND', 'Déliaison appareil'),
                    ('FORMATION_CREATE', 'Création de formation'),
                    ('FORMATION_UPDATE', 'Modification de formation'),
                    ('FORMATION_DELETE', 'Suppression de formation'),
                    ('FORMATION_STATUT', 'Changement de statut de formation'),
                    ('FORMATION_ASSIGN_SUPERVISEUR', 'Assignation superviseur'),
                    ('MODULE_ASSIGN_SUPERVISEUR', 'Assignation encadrant à un module'),
                    ('FORMATION_QR_GENERATE', 'Génération QR code'),
                    ('SEANCE_CREATE', 'Création de séance'),
                    ('SEANCE_START', 'Démarrage de séance'),
                    ('SEANCE_STOP', 'Arrêt de séance'),
                    ('SEANCE_DELETE', 'Suppression de séance'),
                    ('SEANCE_IMPORT', 'Import séances (Excel)'),
                    ('PARTICIPANT_CREATE', "Création d'auditeur"),
                    ('PARTICIPANT_UPDATE', "Modification d'auditeur"),
                    ('PARTICIPANT_DELETE', "Suppression d'auditeur"),
                    ('PARTICIPANT_ADD_FORMATION', 'Inscription auditeur à formation'),
                    ('PARTICIPANT_REMOVE_FORMATION', 'Désinscription auditeur de formation'),
                    ('PARTICIPANT_IMPORT', 'Import auditeurs (Excel)'),
                    ('FORMATEUR_CREATE', 'Création de formateur'),
                    ('FORMATEUR_UPDATE', 'Modification de formateur'),
                    ('FORMATEUR_DELETE', 'Suppression de formateur'),
                    ('FORMATEUR_ADD_FORMATION', 'Assignation formateur à formation'),
                    ('FORMATEUR_REMOVE_FORMATION', 'Retrait formateur de formation'),
                    ('FORMATEUR_IMPORT', 'Import formateurs (Excel)'),
                    ('USER_CREATE', "Création d'utilisateur"),
                    ('USER_DELETE', "Suppression d'utilisateur"),
                    ('IMPORT_EXCEL', 'Import Excel global'),
                ],
                max_length=40,
            ),
        ),
    ]
