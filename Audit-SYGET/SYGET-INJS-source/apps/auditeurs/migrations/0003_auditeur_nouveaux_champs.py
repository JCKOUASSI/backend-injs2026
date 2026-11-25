from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Ajout des champs manquants sur Auditeur :
    genre, date_naissance, lieu_naissance, telephone_2,
    type_concours, libelle_concours, categorie.
    Renommage telephone → telephone_1.
    Suppression du champ service (remplacé par les nouvelles données concours).
    """

    dependencies = [("auditeurs", "0002_auditeur_matricule")]

    operations = [
        migrations.RenameField(
            model_name="auditeur",
            old_name="telephone",
            new_name="telephone_1",
        ),
        migrations.RemoveField(
            model_name="auditeur",
            name="service",
        ),
        migrations.AddField(
            model_name="auditeur",
            name="genre",
            field=models.CharField(
                blank=True,
                choices=[("M", "Masculin"), ("F", "Féminin")],
                max_length=1,
                verbose_name="Genre",
            ),
        ),
        migrations.AddField(
            model_name="auditeur",
            name="date_naissance",
            field=models.DateField(blank=True, null=True, verbose_name="Date de naissance"),
        ),
        migrations.AddField(
            model_name="auditeur",
            name="lieu_naissance",
            field=models.CharField(blank=True, max_length=200, verbose_name="Lieu de naissance"),
        ),
        migrations.AddField(
            model_name="auditeur",
            name="telephone_2",
            field=models.CharField(blank=True, max_length=20, verbose_name="Téléphone 2"),
        ),
        migrations.AddField(
            model_name="auditeur",
            name="type_concours",
            field=models.CharField(blank=True, max_length=100, verbose_name="Type concours"),
        ),
        migrations.AddField(
            model_name="auditeur",
            name="libelle_concours",
            field=models.CharField(blank=True, max_length=200, verbose_name="Libellé concours"),
        ),
        migrations.AddField(
            model_name="auditeur",
            name="categorie",
            field=models.CharField(blank=True, max_length=50, verbose_name="Catégorie"),
        ),
        migrations.AlterField(
            model_name="auditeur",
            name="matricule",
            field=models.CharField(max_length=30, unique=True, verbose_name="N° d'inscription"),
        ),
        migrations.AlterField(
            model_name="auditeur",
            name="prenom",
            field=models.CharField(max_length=100, verbose_name="Prénom(s)"),
        ),
        migrations.AlterField(
            model_name="auditeur",
            name="grade",
            field=models.CharField(blank=True, max_length=20, verbose_name="Grade"),
        ),
        migrations.AlterField(
            model_name="auditeur",
            name="telephone_1",
            field=models.CharField(blank=True, max_length=20, verbose_name="Téléphone 1"),
        ),
    ]
