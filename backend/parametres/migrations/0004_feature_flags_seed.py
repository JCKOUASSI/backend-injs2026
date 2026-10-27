"""P00-08 — feature flags initiaux, tous LIVRÉS DÉSACTIVÉS.

Ajoute la catégorie de paramètres « flags » et crée une entrée en base par
lot à venir (LOT 1 → LOT 12) ainsi qu'un flag de réserve pour le gate humain
G2 (niveaux N0–N4, P01-05). Aucun flag n'est consommé à ce stade : les
comportements nouveaux seront branchés derrière ces interrupteurs au fil des
lots et pourront être éteints en une minute.
"""

from django.db import migrations, models

# (clé, libellé, description, ordre d'affichage)
FLAGS = [
    (
        'flag.lot01_socle_referentiels_rbac',
        'LOT 1 — Socle transversal, référentiels, hiérarchie campus, RBAC exécutable',
        'Active les apports du LOT 1 (audit, soft delete, codes métier, 19 '
        'référentiels, hiérarchie campus, calendrier académique, matrice '
        'rôles exécutable).',
        10,
    ),
    (
        'flag.lot02_verrous_maquettes_notes',
        'LOT 2 — Verrous des maquettes actives et des notes, journal',
        'Active les verrous académiques du LOT 2 (maquettes ACTIVES, notes, '
        'ECTS) et les chantiers transverses amorcés à ce lot.',
        20,
    ),
    (
        'flag.lot03_admissions_chaine_depense',
        'LOT 3 — Admissions / concours et chaîne de la dépense',
        'Active la chaîne admissions/concours (pièces, admissibilité, '
        'admission) et la chaîne dépense (engagement → facture → paiement).',
        30,
    ),
    (
        'flag.lot04_fiches_360_pedagogie',
        'LOT 4 — Fiche étudiant 360, situations académiques, pédagogie écrantée',
        'Active la fiche étudiant 360°, les situations académiques et la '
        'pédagogie écrantée (résorption D1, D2, D3).',
        40,
    ),
    (
        'flag.lot05_charge_enseignants',
        'LOT 5 — Charge des enseignants et suites pédagogiques',
        'Active les fonctionnalités du LOT 5 (charge des enseignants et '
        'modules apparentés).',
        50,
    ),
    (
        'flag.lot06_edt_campus_patrimoine',
        'LOT 6 — Moteur de planification EDT, 5 vues, campus / patrimoine',
        'Active le moteur de planification des emplois du temps, les vues, '
        'la synchronisation externe, le gabarit d’écrans et le domaine '
        'campus/patrimoine.',
        60,
    ),
    (
        'flag.lot07_qr_rh_ged',
        'LOT 7 — Badgeage QR anti-fraude, administration, RH, GED',
        'Active la consolidation du badgeage QR et de sa chaîne anti-fraude, '
        'l’administration, les ressources humaines et la GED.',
        70,
    ),
    (
        'flag.lot08_evaluations_jurys_cloture_comptable',
        'LOT 8 — Évaluations → notes → jurys → diplômes, clôture comptable',
        'Active la fin de la chaîne pédagogique (évaluations, notes, jurys, '
        'diplômes) et la clôture du volet comptable (immobilisations).',
        80,
    ),
    (
        'flag.lot09_finances_etudiantes_decisionnel',
        'LOT 9 — Finances étudiantes et couche décisionnelle (BI)',
        'Active les tarifs, échéanciers et factures étudiants, ainsi que la '
        'couche décisionnelle et les tableaux de bord par profil.',
        90,
    ),
    (
        'flag.lot10_organisation_administrative',
        'LOT 10 — Organisation administrative (directions, services, postes, fonctions)',
        'Active l’organisation administrative : directions, services, postes '
        'et fonctions.',
        100,
    ),
    (
        'flag.lot11_notifications_multicanal',
        'LOT 11 — Notifications multi-canal et portails',
        'Active le hub de notifications multi-canal et les portails associés.',
        110,
    ),
    (
        'flag.lot12_securite_retrait_legacy',
        'LOT 12 — Durcissement sécurité, industrialisation, retrait du legacy',
        'Active les fonctionnalités du dernier lot : durcissement, '
        'industrialisation de l’exploitation, retrait du socle legacy et '
        'recette des 18 modules.',
        120,
    ),
    (
        'flag.g2_niveaux_n4_validation',
        'G2 — Niveaux N0–N4 validés par le commanditaire (P01-05)',
        'Réserve pour le gate humain G2 : fait passer les niveaux '
        'd’accès de « provisoires » à « validés » une fois la matrice '
        'rôles → N0–N4 validée.',
        200,
    ),
]

FLAG_KEYS = [cle for cle, _libelle, _desc, _ordre in FLAGS]

ADMIN_ROLES = '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]'


def seed_feature_flags(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    for cle, libelle, description, ordre in FLAGS:
        Parametre.objects.get_or_create(
            cle=cle,
            defaults={
                'libelle': libelle,
                'description': description,
                'categorie': 'flags',
                'ordre': ordre,
                'type': 'bool',
                'valeur': 'false',
                'valeur_defaut': 'false',
                'choices_json': '',
                'regex_validation': '',
                # Seuls les administrateurs voient le catalogue et le modifient ;
                # les autres utilisateurs n'ont que la carte booléenne via
                # GET /api/parametres/flags/.
                'modifiable': True,
                'modifiable_par_roles': ADMIN_ROLES,
                'lecturable_par_roles': ADMIN_ROLES,
                'actif': True,
            },
        )


def unseed_feature_flags(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    Parametre.objects.filter(cle__in=FLAG_KEYS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('parametres', '0003_categories_mvp_seed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parametre',
            name='categorie',
            field=models.CharField(
                choices=[
                    ('general', 'Général'),
                    ('scolarite', 'Scolarité / LMD'),
                    ('presences', 'Présences'),
                    ('edt', 'EDT (import)'),
                    ('notifications', 'Notifications'),
                    ('securite', 'Sécurité'),
                    ('interface', 'Interface'),
                    ('finance', 'Finance'),
                    ('flags', 'Fonctionnalités (feature flags)'),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_feature_flags, reverse_code=unseed_feature_flags),
    ]
