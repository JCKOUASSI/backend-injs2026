from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0024_affectation_unique_formateur_par_groupe"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="affectationformateurgroupe",
            name="uniq_formateur_par_groupe",
        ),
    ]
