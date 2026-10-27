from django.db import migrations, models


def apply_salle_columns(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        # Dev local (SQLITE) : les opérations d'état AddField ne créent pas la
        # colonne physiquement dans un SeparateDatabaseAndState — on les crée ici.
        RefSalle = apps.get_model('formations', 'RefSalle')
        dev_fields = [
            models.CharField(
                choices=[
                    ('SALLE', 'Salle'),
                    ('AMPHI', 'Amphithéâtre'),
                    ('GYMNASE', 'Gymnase'),
                    ('REUNION', 'Salle de réunion'),
                    ('CONFERENCE', 'Salle de conférence'),
                ],
                default='SALLE',
                max_length=20,
            ),
            models.PositiveIntegerField(blank=True, null=True),
            models.CharField(blank=True, default='', max_length=255),
            models.DateField(blank=True, null=True),
            models.DateField(blank=True, null=True),
        ]
        for name, field in zip(
            ['type_lieu', 'capacite', 'equipements', 'indisponible_du', 'indisponible_au'],
            dev_fields,
        ):
            field.set_attributes_from_name(name)
            schema_editor.add_field(RefSalle, field)
        return
    with connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE formations_refsalle
              ADD COLUMN IF NOT EXISTS type_lieu varchar(20);
            ALTER TABLE formations_refsalle
              ADD COLUMN IF NOT EXISTS capacite integer;
            ALTER TABLE formations_refsalle
              ADD COLUMN IF NOT EXISTS equipements varchar(255);
            ALTER TABLE formations_refsalle
              ADD COLUMN IF NOT EXISTS indisponible_du date;
            ALTER TABLE formations_refsalle
              ADD COLUMN IF NOT EXISTS indisponible_au date;

            UPDATE formations_refsalle
               SET type_lieu = 'SALLE'
             WHERE type_lieu IS NULL OR btrim(type_lieu) = '';
            UPDATE formations_refsalle
               SET equipements = ''
             WHERE equipements IS NULL;

            ALTER TABLE formations_refsalle ALTER COLUMN type_lieu SET DEFAULT 'SALLE';
            ALTER TABLE formations_refsalle ALTER COLUMN type_lieu SET NOT NULL;
            ALTER TABLE formations_refsalle ALTER COLUMN equipements SET DEFAULT '';
            ALTER TABLE formations_refsalle ALTER COLUMN equipements SET NOT NULL;

            ALTER TABLE formations_refsalle DROP CONSTRAINT IF EXISTS formations_refsalle_capacite_check;
            ALTER TABLE formations_refsalle
              ADD CONSTRAINT formations_refsalle_capacite_check CHECK (capacite IS NULL OR capacite >= 0);
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0085_notificationfinanceajustement'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(apply_salle_columns, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='refsalle',
                    name='type_lieu',
                    field=models.CharField(
                        choices=[
                            ('SALLE', 'Salle'),
                            ('AMPHI', 'Amphithéâtre'),
                            ('GYMNASE', 'Gymnase'),
                            ('REUNION', 'Salle de réunion'),
                            ('CONFERENCE', 'Salle de conférence'),
                        ],
                        default='SALLE',
                        max_length=20,
                    ),
                ),
                migrations.AddField(
                    model_name='refsalle',
                    name='capacite',
                    field=models.PositiveIntegerField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='refsalle',
                    name='equipements',
                    field=models.CharField(blank=True, default='', max_length=255),
                ),
                migrations.AddField(
                    model_name='refsalle',
                    name='indisponible_du',
                    field=models.DateField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='refsalle',
                    name='indisponible_au',
                    field=models.DateField(blank=True, null=True),
                ),
            ],
        ),
    ]
