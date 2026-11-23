import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('formations', '0012_formation_cours'),
    ]

    operations = [
        migrations.CreateModel(
            name='Secretariat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.CharField(blank=True, max_length=50, unique=True)),
                ('nom', models.CharField(help_text='Nom du secrétariat', max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('responsable', models.ForeignKey(blank=True, limit_choices_to={'role': 'SECRETARIAT'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='secretariats_resp', to=settings.AUTH_USER_MODEL)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Secrétariat',
                'verbose_name_plural': 'Secrétariats',
                'ordering': ['nom'],
            },
        ),
        migrations.AddField(
            model_name='formation',
            name='secretariat',
            field=models.ForeignKey(blank=True, help_text='Secrétariat responsable de cette formation', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='formations', to='formations.secretariat'),
        ),
        migrations.AddField(
            model_name='participant',
            name='secretariat',
            field=models.ForeignKey(blank=True, help_text='Secrétariat responsable de ce participant', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='participants', to='formations.secretariat'),
        ),
        migrations.AddField(
            model_name='formateur',
            name='secretariat',
            field=models.ForeignKey(blank=True, help_text='Secrétariat responsable de ce formateur', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='formateurs', to='formations.secretariat'),
        ),
    ]
