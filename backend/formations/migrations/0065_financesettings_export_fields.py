from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0064_refformation_prix_heure_realisee'),
    ]

    operations = [
        migrations.AddField(
            model_name='financesettings',
            name='afficher_montants_exports',
            field=models.BooleanField(
                default=True,
                help_text="Valeur par défaut lors de l'export PDF/Excel (modifiable à chaque export).",
                verbose_name='Afficher les montants sur les états financiers',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_adresse',
            field=models.TextField(blank=True, default='', verbose_name='Adresse / coordonnées'),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_entete_ligne1',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Ex. République de Côte d'Ivoire",
                max_length=255,
                verbose_name='En-tête ligne 1',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_entete_ligne2',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex. Ministère / Direction',
                max_length=255,
                verbose_name='En-tête ligne 2',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_mention_legale',
            field=models.TextField(blank=True, default='', verbose_name='Mention légale / pied de page'),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_organisme',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Nom affiché sur les états financiers (ex. CPFAE).',
                max_length=255,
                verbose_name='Organisme',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_reference_prefix',
            field=models.CharField(
                blank=True,
                default='EFI',
                max_length=30,
                verbose_name='Préfixe de référence document',
            ),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_signataire_fonction',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Fonction du signataire'),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_signataire_nom',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Nom du signataire'),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='export_titre_document',
            field=models.CharField(
                blank=True,
                default='ÉTAT FINANCIER FORMATEUR',
                max_length=255,
                verbose_name='Titre des états financiers',
            ),
        ),
    ]
