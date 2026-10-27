"""Navigation latérale de l'admin Django personnalisé."""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def get_admin_sidebar_navigation():
  return [
    {
      'title': _('Navigation'),
      'separator': True,
      'items': [
        {
          'title': _('Accueil admin'),
          'icon': 'dashboard',
          'link': reverse_lazy('admin:index'),
        },
        {
          'title': _('Diagnostic volume horaire'),
          'icon': 'monitoring',
          'link': reverse_lazy('admin:formations_volume_horaire_diagnostic'),
        },
        {
          'title': _('Guide des actions'),
          'icon': 'menu_book',
          'link': reverse_lazy('admin:admin_guide_actions'),
        },
      ],
    },
    {
      'title': _('Pédagogie'),
      'separator': True,
      'collapsible': True,
      'items': [
        {
          'title': _('Formations'),
          'icon': 'school',
          'link': reverse_lazy('admin:formations_formation_changelist'),
        },
        {
          'title': _('Modules'),
          'icon': 'menu_book',
          'link': reverse_lazy('admin:formations_module_changelist'),
        },
        {
          'title': _('Séances'),
          'icon': 'event',
          'link': reverse_lazy('admin:formations_sessionmodule_changelist'),
        },
        {
          'title': _('Secrétariats'),
          'icon': 'apartment',
          'link': reverse_lazy('admin:formations_secretariat_changelist'),
        },
      ],
    },
    {
      'title': _('Personnes'),
      'separator': True,
      'collapsible': True,
      'items': [
        {
          'title': _('Étudiants'),
          'icon': 'groups',
          'link': reverse_lazy('admin:formations_participant_changelist'),
        },
        {
          'title': _('Enseignants'),
          'icon': 'person',
          'link': reverse_lazy('admin:formations_formateur_changelist'),
        },
      ],
    },
    {
      'title': _('Présences'),
      'separator': True,
      'collapsible': True,
      'items': [
        {
          'title': _('Pointages'),
          'icon': 'fact_check',
          'link': reverse_lazy('admin:presences_pointage_changelist'),
        },
        {
          'title': _('Codes QR'),
          'icon': 'qr_code_2',
          'link': reverse_lazy('admin:formations_qrtoken_changelist'),
        },
        {
          'title': _("Journal d'audit"),
          'icon': 'history',
          'link': reverse_lazy('admin:presences_auditlog_changelist'),
        },
      ],
    },
    {
      'title': _('Administration'),
      'separator': True,
      'collapsible': True,
      'items': [
        {
          'title': _('Utilisateurs'),
          'icon': 'manage_accounts',
          'link': reverse_lazy('admin:authentication_user_changelist'),
        },
        {
          'title': _('Groupes & permissions'),
          'icon': 'admin_panel_settings',
          'link': reverse_lazy('admin:auth_group_changelist'),
        },
        {
          'title': _('Liaisons appareils'),
          'icon': 'phonelink',
          'link': reverse_lazy('admin:presences_devicebinding_changelist'),
        },
      ],
    },
    {
      'title': _('Paramètres'),
      'separator': True,
      'collapsible': True,
      'items': [
        {
          'title': _('Paramètres finance'),
          'icon': 'payments',
          'link': reverse_lazy('admin:formations_financesettings_changelist'),
        },
        {
          'title': _('Paramètres applicatifs'),
          'icon': 'settings',
          'link': reverse_lazy('admin:parametres_parametre_changelist'),
        },
      ],
    },
    {
      'title': _('Référentiels'),
      'separator': True,
      'collapsible': True,
      'items': [
        {
          'title': _('Types de secrétariat'),
          'icon': 'category',
          'link': reverse_lazy('admin:formations_reftypesecretariat_changelist'),
        },
        {
          'title': _('Catégories'),
          'icon': 'label',
          'link': reverse_lazy('admin:formations_refcategorie_changelist'),
        },
        {
          'title': _('Grades'),
          'icon': 'military_tech',
          'link': reverse_lazy('admin:formations_refgrade_changelist'),
        },
        {
          'title': _('Vagues'),
          'icon': 'layers',
          'link': reverse_lazy('admin:formations_refvague_changelist'),
        },
        {
          'title': _('Cycles de formation'),
          'icon': 'library_books',
          'link': reverse_lazy('admin:formations_refformation_changelist'),
        },
        {
          'title': _('Modules catalogue'),
          'icon': 'inventory_2',
          'link': reverse_lazy('admin:formations_refmodule_changelist'),
        },
        {
          'title': _('Sites et locaux'),
          'icon': 'location_on',
          'link': reverse_lazy('admin:formations_refsite_changelist'),
        },
      ],
    },
  ]


def get_admin_tabs():
  return [
    {
      'models': [
        'formations.formation',
        'formations.module',
        'formations.sessionmodule',
        'formations.secretariat',
      ],
      'items': [
        {
          'title': _('Formations'),
          'link': reverse_lazy('admin:formations_formation_changelist'),
        },
        {
          'title': _('Modules'),
          'link': reverse_lazy('admin:formations_module_changelist'),
        },
        {
          'title': _('Séances'),
          'link': reverse_lazy('admin:formations_sessionmodule_changelist'),
        },
        {
          'title': _('Secrétariats'),
          'link': reverse_lazy('admin:formations_secretariat_changelist'),
        },
      ],
    },
    {
      'models': [
        'formations.participant',
        'formations.formateur',
      ],
      'items': [
        {
          'title': _('Étudiants'),
          'link': reverse_lazy('admin:formations_participant_changelist'),
        },
        {
          'title': _('Enseignants'),
          'link': reverse_lazy('admin:formations_formateur_changelist'),
        },
      ],
    },
    {
      'models': [
        'presences.pointage',
        'formations.qrtoken',
        'presences.auditlog',
        'presences.devicebinding',
      ],
      'items': [
        {
          'title': _('Pointages'),
          'link': reverse_lazy('admin:presences_pointage_changelist'),
        },
        {
          'title': _('Codes QR'),
          'link': reverse_lazy('admin:formations_qrtoken_changelist'),
        },
        {
          'title': _("Journal d'audit"),
          'link': reverse_lazy('admin:presences_auditlog_changelist'),
        },
        {
          'title': _('Liaisons appareils'),
          'link': reverse_lazy('admin:presences_devicebinding_changelist'),
        },
      ],
    },
    {
      'models': [
        'formations.reftypesecretariat',
        'formations.refcategorie',
        'formations.refgrade',
        'formations.refvague',
        'formations.refformation',
        'formations.refmodule',
        'formations.refsite',
        'formations.refbatiment',
        'formations.refsalle',
      ],
      'items': [
        {
          'title': _('Types secrétariat'),
          'link': reverse_lazy('admin:formations_reftypesecretariat_changelist'),
        },
        {
          'title': _('Catégories'),
          'link': reverse_lazy('admin:formations_refcategorie_changelist'),
        },
        {
          'title': _('Grades'),
          'link': reverse_lazy('admin:formations_refgrade_changelist'),
        },
        {
          'title': _('Vagues'),
          'link': reverse_lazy('admin:formations_refvague_changelist'),
        },
        {
          'title': _('Cycles'),
          'link': reverse_lazy('admin:formations_refformation_changelist'),
        },
        {
          'title': _('Modules catalogue'),
          'link': reverse_lazy('admin:formations_refmodule_changelist'),
        },
        {
          'title': _('Sites'),
          'link': reverse_lazy('admin:formations_refsite_changelist'),
        },
      ],
    },
    {
      'models': [
        'authentication.user',
        'formations.financesettings',
      ],
      'items': [
        {
          'title': _('Utilisateurs'),
          'link': reverse_lazy('admin:authentication_user_changelist'),
        },
        {
          'title': _('Paramètres finance'),
          'link': reverse_lazy('admin:formations_financesettings_changelist'),
        },
      ],
    },
  ]
