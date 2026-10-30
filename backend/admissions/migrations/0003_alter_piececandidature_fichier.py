"""Ajoute les validateurs de fichier sur la pièce de candidature (correctif d'audit).

Contrôle d'extension (PDF/JPG/PNG) et de taille, appliqué aussi par les
services métier. Aucune modification de schéma ni de donnée.
"""

import admissions.models
import core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0002_campagneadmission_candidature_campagne_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='piececandidature',
            name='fichier',
            field=models.FileField(blank=True, null=True, upload_to=admissions.models.piece_upload_path, validators=[core.validators.valider_piece_candidature]),
        ),
    ]
