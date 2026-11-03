"""Ajoute les validateurs de fichier sur la preuve de paiement (correctif d'audit).

Contrôle d'extension (PDF/JPG/PNG) et de taille, appliqué aussi par les
services métier. Aucune modification de schéma ni de donnée.
"""

import core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finances_etudiantes', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paiement',
            name='preuve',
            field=models.FileField(blank=True, help_text='Pièce justificative du paiement (obligatoire pour CONFIRME)', null=True, upload_to='finances_proofs/', validators=[core.validators.valider_preuve_paiement]),
        ),
    ]
