from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    # Forward-declare to avoid circular import
    # (Secretariat is in formations app)
    class Role(models.TextChoices):
        """Rôles canoniques INJS-LMD (12 rôles).

        Lot L4a : les rôles `CPFAE_ADMIN` et `CHEF_CPFAE_ADMIN` sont historiques ;
        ils sont conservés pour compatibilité, mais ne sont plus utilisés dans
        l'interface INJS.
        `CHEF_INJS_ADMIN`. Ces deux identifiants étaient des vestiges de
        l'application historique Sygepcpfae ; les libellés affichés étaient
        déjà en terminologie INJS, seuls les codes portaient CPFAE.

        Lot L4b : plus aucune chaîne CPFAE n'est acceptée ni persistée. Le
        verrou est double — `choices` côté applicatif, contrainte CHECK côté
        base (migration `authentication.0024`).

        Le passage de 12 à 14 rôles exigerait une définition métier validée ;
        il n'a pas eu lieu dans le lot L4a.
        """
        ADMIN = 'ADMIN', 'Administrateur'
        DIRECTION = 'DIRECTION', 'Direction'
        CHEF_INJS_ADMIN = 'CHEF_INJS_ADMIN', 'Chef INJS Admin'
        INJS_ADMIN = 'INJS_ADMIN', 'INJS Admin'
        CHEF_SECRETARIAT = 'CHEF_SECRETARIAT', 'Chef Secrétariat'
        SECRETARIAT = 'SECRETARIAT', 'Secrétariat'
        FINANCE = 'FINANCE', 'Finance'
        ARCHIVE = 'ARCHIVE', 'Archiviste'
        ENCADRANT = 'ENCADRANT', 'Encadrant'
        SUPERVISEUR = 'SUPERVISEUR', 'Superviseur'
        FORMATEUR = 'FORMATEUR', 'Formateur'
        AUDITEUR = 'AUDITEUR', 'Étudiant'

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.AUDITEUR,
    )
    matricule = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text="N° matricule utilisé comme numéro de badgeage",
    )
    telephone = models.CharField(max_length=20, blank=True, default='')
    organisation = models.CharField(max_length=255, blank=True, default='')
    grade = models.CharField(max_length=20, blank=True, default='', help_text="Grade (A4, A3…)")
    secretariat = models.ForeignKey(
        'formations.Secretariat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='membres',
        help_text="Secrétariat auquel appartient cet utilisateur",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Si vrai, l'utilisateur doit changer son mot de passe avant d'utiliser les fonctions sensibles.",
    )

    objects = UserManager()

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        permissions = [
            ('access_web', 'Accès à la plateforme web'),
            ('operational_web', 'Personnel opérationnel web (hors module Finance)'),
            ('mutate_users', 'Créer ou modifier des comptes utilisateurs'),
            ('global_scope', 'Périmètre global (tous secrétariats)'),
            ('list_participants', 'Consulter la liste des participants'),
            ('finance_module', 'Accès au module Finance'),
            ('manage_questionnaires', 'Gérer les questionnaires d\'évaluation'),
            ('manage_notes', 'Gérer les notes et épreuves'),
            ('validate_decisions', 'Valider les décisions pédagogiques'),
            ('consult_evaluation', 'Consulter les évaluations'),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"

    @property
    def is_chef_injs_admin(self):
        return self.role == self.Role.CHEF_INJS_ADMIN

    @property
    def is_dfrc(self):
        return self.role == self.Role.INJS_ADMIN

    @property
    def is_chef_secretariat(self):
        return self.role == self.Role.CHEF_SECRETARIAT

    @property
    def is_secretariat(self):
        return self.role == self.Role.SECRETARIAT

    @property
    def is_finance(self):
        return self.role == self.Role.FINANCE

    @property
    def is_archive(self):
        return self.role == self.Role.ARCHIVE

    @property
    def is_encadrant(self):
        return self.role == self.Role.ENCADRANT

    @property
    def is_superviseur(self):
        return self.role == self.Role.SUPERVISEUR

    @property
    def is_formateur(self):
        return self.role == self.Role.FORMATEUR

    @property
    def is_direction(self):
        return self.role == self.Role.DIRECTION

    @property
    def is_auditeur(self):
        return self.role == self.Role.AUDITEUR
