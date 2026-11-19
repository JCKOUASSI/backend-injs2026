# Migration additive de la phase 2 GET-INJS, générée avec Django 5.1.4.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('edts', '0012_affectationcreneau_ecue'),
        ('formations', '0102_refformation_archive'),
        ('scolarite', '0020_archiver_inscriptions_utilisees'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExecutionLigne',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cle_travail', models.CharField(max_length=64)),
                ('cle_occurrence_v2', models.CharField(blank=True, max_length=64, null=True)),
                ('type_seance', models.CharField(choices=[('CM', 'Cours magistral'), ('TD', 'Travaux dirigés'), ('TP', 'Travaux pratiques'), ('EXAM', 'Examen')], max_length=4)),
                ('date_candidate', models.DateField(blank=True, null=True)),
                ('statut', models.CharField(choices=[('PLACEE', 'Placée'), ('ECHEC', 'Échec'), ('A_REVOIR', 'À revoir')], max_length=8)),
                ('code_contrainte', models.CharField(blank=True, default='', max_length=80)),
                ('score_souple', models.FloatField(blank=True, null=True)),
                ('version_calendrier', models.PositiveIntegerField(blank=True, null=True)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='PeriodeAcademique',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('COURS', 'Cours'), ('VACANCES', 'Vacances'), ('EXAMENS', 'Examens'), ('FERIE', 'Férié'), ('FERMETURE', 'Fermeture')], max_length=12)),
                ('portee', models.CharField(choices=[('GLOBAL', 'Toute l’année'), ('FORMATION', 'Formation'), ('NIVEAU', 'Niveau'), ('GROUPE', 'Groupe')], default='GLOBAL', max_length=12)),
                ('date_debut', models.DateField()),
                ('date_fin', models.DateField()),
                ('source_document', models.CharField(blank=True, default='', max_length=255)),
                ('fiabilite', models.CharField(choices=[('A_RENSEIGNER', 'À renseigner'), ('CADRAGE', 'Cadrage'), ('MODELISE', 'Modélisé'), ('OFFICIEL', 'Officiel vérifié')], default='A_RENSEIGNER', max_length=20)),
                ('statut_validation', models.CharField(choices=[('A_CONFIRMER', 'À confirmer'), ('VALIDEE', 'Validée par l’administration')], default='A_CONFIRMER', max_length=12)),
                ('actif', models.BooleanField(default=True)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='RevisionCalendrier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.PositiveIntegerField()),
                ('motif', models.CharField(blank=True, default='', max_length=255)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='VerrouJour',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
            ],
        ),
        migrations.AddField(
            model_name='affectationcreneau',
            name='cle_occurrence_v2',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='affectationcreneau',
            name='date_seance',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='affectationcreneau',
            name='minute_debut',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='affectationcreneau',
            name='minute_fin',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='affectationcreneau',
            name='revision_calendrier',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='heartbeat_le',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='lease_jusqua',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='lignes_a_revoir',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='lignes_echec',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='lignes_lues',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='lignes_placees',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='lignes_traitees',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='version_calendrier',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='executioncampagne',
            name='worker_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddIndex(
            model_name='affectationcreneau',
            index=models.Index(condition=models.Q(('actif', True), ('date_seance__isnull', False)), fields=['groupe', 'date_seance'], name='edt_v2_groupe_date_idx'),
        ),
        migrations.AddIndex(
            model_name='affectationcreneau',
            index=models.Index(condition=models.Q(('actif', True), ('date_seance__isnull', False)), fields=['formateur', 'date_seance'], name='edt_v2_prof_date_idx'),
        ),
        migrations.AddIndex(
            model_name='affectationcreneau',
            index=models.Index(condition=models.Q(('actif', True), ('date_seance__isnull', False)), fields=['salle', 'date_seance'], name='edt_v2_salle_date_idx'),
        ),
        migrations.AddConstraint(
            model_name='affectationcreneau',
            constraint=models.CheckConstraint(condition=models.Q(('date_seance__isnull', True), ('semaine_debut', models.F('semaine_fin')), _connector='OR'), name='edt_v2_occurrence_semaine_unique'),
        ),
        migrations.AddConstraint(
            model_name='affectationcreneau',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('minute_debut__isnull', True), ('minute_fin__isnull', True)), models.Q(('minute_debut__gte', 0), ('minute_fin__gt', models.F('minute_debut')), ('minute_fin__lte', 1440)), _connector='OR'), name='edt_v2_plage_minutes_valide'),
        ),
        migrations.AddField(
            model_name='executionligne',
            name='ecue',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lignes_edt_v2', to='scolarite.ecue'),
        ),
        migrations.AddField(
            model_name='executionligne',
            name='execution',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lignes_v2', to='edts.executioncampagne'),
        ),
        migrations.AddField(
            model_name='executionligne',
            name='groupe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lignes_edt_v2', to='scolarite.groupe'),
        ),
        migrations.AddField(
            model_name='periodeacademique',
            name='annee_academique',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='periodes_getinjs', to='scolarite.anneeacademique'),
        ),
        migrations.AddField(
            model_name='periodeacademique',
            name='formation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='periodes_getinjs', to='formations.refformation'),
        ),
        migrations.AddField(
            model_name='periodeacademique',
            name='groupe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='periodes_getinjs', to='scolarite.groupe'),
        ),
        migrations.AddField(
            model_name='periodeacademique',
            name='niveau',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='periodes_getinjs', to='scolarite.niveau'),
        ),
        migrations.AddField(
            model_name='revisioncalendrier',
            name='annee_academique',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='revisions_calendrier_getinjs', to='scolarite.anneeacademique'),
        ),
        migrations.AddField(
            model_name='periodeacademique',
            name='revision',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='periodes', to='edts.revisioncalendrier'),
        ),
        migrations.AddField(
            model_name='verroujour',
            name='annee_academique',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='verrous_edt_v2', to='scolarite.anneeacademique'),
        ),
        migrations.AddIndex(
            model_name='executionligne',
            index=models.Index(fields=['execution', 'statut', 'id'], name='edt_v2_exec_statut_idx'),
        ),
        migrations.AddIndex(
            model_name='executionligne',
            index=models.Index(fields=['execution', 'groupe', 'cle_travail'], name='edt_v2_exec_groupe_idx'),
        ),
        migrations.AddConstraint(
            model_name='executionligne',
            constraint=models.UniqueConstraint(fields=('execution', 'cle_travail'), name='edt_v2_exec_ligne_unique'),
        ),
        migrations.AddConstraint(
            model_name='revisioncalendrier',
            constraint=models.UniqueConstraint(fields=('annee_academique', 'numero'), name='edt_v2_rev_annee_num_unique'),
        ),
        migrations.AddIndex(
            model_name='periodeacademique',
            index=models.Index(fields=['annee_academique', 'revision', 'actif', 'date_debut', 'date_fin'], name='edt_v2_periode_dates_idx'),
        ),
        migrations.AddIndex(
            model_name='periodeacademique',
            index=models.Index(fields=['groupe', 'date_debut'], name='edt_v2_periode_groupe_idx'),
        ),
        migrations.AddConstraint(
            model_name='periodeacademique',
            constraint=models.CheckConstraint(condition=models.Q(('date_fin__gte', models.F('date_debut'))), name='edt_v2_periode_dates_valides'),
        ),
        migrations.AddConstraint(
            model_name='periodeacademique',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('formation__isnull', True), ('groupe__isnull', True), ('niveau__isnull', True), ('portee', 'GLOBAL')), models.Q(('formation__isnull', False), ('groupe__isnull', True), ('niveau__isnull', True), ('portee', 'FORMATION')), models.Q(('formation__isnull', True), ('groupe__isnull', True), ('niveau__isnull', False), ('portee', 'NIVEAU')), models.Q(('formation__isnull', True), ('groupe__isnull', False), ('niveau__isnull', True), ('portee', 'GROUPE')), _connector='OR'), name='edt_v2_periode_portee_coherente'),
        ),
        migrations.AddConstraint(
            model_name='verroujour',
            constraint=models.UniqueConstraint(fields=('annee_academique', 'date'), name='edt_v2_verrou_jour_unique'),
        ),
    ]
