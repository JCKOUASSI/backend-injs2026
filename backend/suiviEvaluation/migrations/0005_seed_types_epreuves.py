from django.db import migrations


TYPES_EPREUVES = [
    ('DEVOIR', 'Devoir', 1),
    ('CONTROLE', 'Contrôle continu', 2),
    ('EXAMEN', 'Examen', 3),
    ('ORAL', 'Épreuve orale', 4),
    ('PRATIQUE', 'Épreuve pratique', 5),
    ('TP', 'Travaux pratiques', 6),
    ('PROJET', 'Projet', 7),
]


def seed_types(apps, schema_editor):
    TypeEpreuve = apps.get_model('suiviEvaluation', 'TypeEpreuve')
    for code, libelle, ordre in TYPES_EPREUVES:
        TypeEpreuve.objects.get_or_create(
            code=code,
            defaults={'libelle': libelle, 'ordre': ordre, 'actif': True},
        )


def unseed_types(apps, schema_editor):
    TypeEpreuve = apps.get_model('suiviEvaluation', 'TypeEpreuve')
    TypeEpreuve.objects.filter(code__in=[c for c, _, _ in TYPES_EPREUVES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('suiviEvaluation', '0004_typeepreuve_questionnaire_anonyme_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
