"""Aligne le schéma sur les modèles (métadonnées et index déjà présents dans le code).

Constat d'audit : ``manage.py makemigrations --check`` signalait une dérive
entre les modèles et les migrations pour deux champs. Aucune donnée n'est
modifiée ; seules les métadonnées (``help_text``, ``choices``) et l'index de
``refformation.perimetre`` (filtre du référentiel L6) sont alignés.

Sans cette migration, tout déploiement restait « en attente de migration » et
la CI de contrôle (``makemigrations --check``) échouait.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0097_alter_refsalle_type_lieu'),
    ]

    operations = [
        migrations.AlterField(
            model_name='financesettings',
            name='export_organisme',
            field=models.CharField(blank=True, default='', help_text='Nom affiché sur les états financiers.', max_length=255, verbose_name='Organisme'),
        ),
        migrations.AlterField(
            model_name='refformation',
            name='perimetre',
            field=models.CharField(choices=[('INJS', 'INJS validé'), ('LEGACY', 'Legacy / autre source'), ('NON_DETERMINE', 'Non déterminé')], db_index=True, default='NON_DETERMINE', help_text='L6 : INJS = filière validée par la source métier ; LEGACY = corpus étranger exclu du référentiel INJS.', max_length=20),
        ),
    ]
