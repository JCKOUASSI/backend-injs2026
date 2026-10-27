"""URLs API du module GET-INJS (lot L8) — Emploi du temps.

Préfixe : /api/edts/. L'alias /api/timetable/ (exigence P11) est monté dans
config/urls.py sur le même jeu de routes — les deux chemins sont équivalents
et versionnés ensemble.
"""

from django.urls import path

from . import api
from . import api_lmd as lmd

# Pas d'app_name volontaire : le jeu de routes est monté deux fois
# (/api/edts/ et /api/timetable/) — un namespace dupliqué déclenche urls.W005.
#
# ── LOT 3 — couche LMD (routes NOUVELLES, ajoutées) ─────────────────────────
# Toutes ces routes sont préfixées ``lmd/`` : aucune route existante n'est
# supprimée, renommée ou modifiée. Le générateur historique
# ``POST /api/edts/emplois/{id}/generer/`` (generer_brouillon) reste le chemin
# contractuel d'origine ; la couche LMD y ajoute le moteur du LOT 2.
urlpatterns_lmd = [
    # Pré-requis (§7, §17)
    # `lmd/audit/` est déclarée AVANT `lmd/<int:pk>/audit/` : ces deux chemins
    # sont distincts (`int:pk` ne capture pas le littéral « audit »), et cet
    # ordre garantit que l'audit de préparation ne soit jamais capté par pk.
    path('lmd/audit/', lmd.audit_api, name='edt-lmd-audit'),
    path('lmd/constraints/', lmd.contraintes_api, name='edt-lmd-contraintes'),
    path('lmd/versions/', lmd.versions_api, name='edt-lmd-versions'),

    # Ressources (§8, §9)
    path('lmd/availability/teachers/', lmd.disponibilites_enseignants_api,
         name='edt-lmd-availability-teachers'),
    path('lmd/availability/rooms/', lmd.disponibilites_salles_api,
         name='edt-lmd-availability-rooms'),
    path('lmd/slots/', lmd.slots_api, name='edt-lmd-slots'),

    # Génération / validation / publication (§6, §10, §11)
    path('lmd/generate/', lmd.generate_api, name='edt-lmd-generate'),
    # LOT 3 — génération COORDONNÉE multi-filières (ajout, aucune route
    # existante modifiée). Déclarée avant les routes `lmd/<int:pk>/…` : le
    # littéral « generate-coordinated » n'est pas capturé par `<int:pk>`.
    path('lmd/generate-coordinated/', lmd.generate_coordinated_api,
         name='edt-lmd-generate-coordinated'),
    path('lmd/<int:pk>/validate/', lmd.validate_api, name='edt-lmd-validate'),
    path('lmd/<int:pk>/publish/', lmd.publish_api, name='edt-lmd-publish'),

    # Restitution (§7, §24, §25, §28)
    # `edt_audit_api` porte un nom d'opération distinct (`edt_lmd_edt_audit`)
    # : `/api/docs/` reste non ambigu malgré la proximité des deux chemins.
    path('lmd/<int:pk>/audit/', lmd.edt_audit_api, name='edt-lmd-edt-audit'),
    path('lmd/<int:pk>/result/', lmd.result_api, name='edt-lmd-result'),
    path('lmd/<int:pk>/grille/', lmd.grille_api, name='edt-lmd-grille'),

    # Opérations sur séance (§12, §13)
    path('lmd/items/<int:pk>/move/', lmd.item_move_api, name='edt-lmd-item-move'),
    path('lmd/items/<int:pk>/cancel/', lmd.item_cancel_api, name='edt-lmd-item-cancel'),
]

urlpatterns = [
    # Référentiel horaire (P01)
    path('creneaux-types/', api.creneaux_types_api, name='edt-creneau-templates'),
    path('creneaux-types/<int:pk>/', api.creneau_template_detail_api, name='edt-creneau-template-detail'),

    # Emplois du temps + workflow (P05)
    path('emplois/', api.emplois_du_temps_api, name='edt-emplois-list'),
    path('emplois/<int:pk>/', api.emploi_du_temps_detail_api, name='edt-emploi-detail'),
    path('emplois/<int:pk>/soumettre/', api.emploi_du_temps_soumettre_api, name='edt-emploi-soumettre'),
    path('emplois/<int:pk>/valider/', api.emploi_du_temps_valider_api, name='edt-emploi-valider'),
    path('emplois/<int:pk>/publier/', api.emploi_du_temps_publier_api, name='edt-emploi-publier'),
    path('emplois/<int:pk>/depublier/', api.emploi_du_temps_depublier_api, name='edt-emploi-depublier'),
    path('emplois/<int:pk>/archiver/', api.emploi_du_temps_archiver_api, name='edt-emploi-archiver'),
    path('emplois/<int:pk>/generer/', api.emploi_du_temps_generer_api, name='edt-emploi-generer'),
    path('emplois/<int:pk>/grille/', api.emploi_du_temps_grille_api, name='edt-emploi-grille'),
    path('emplois/<int:pk>/export.csv/', api.emploi_du_temps_export_api, name='edt-emploi-export-csv'),
    path('emplois/<int:pk>/conflits/', api.emploi_du_temps_detecter_conflits_api,
         name='edt-emploi-detecter-conflits'),

    # Placements (P05, P08)
    path('affectations/', api.affectations_api, name='edt-affectations'),
    path('affectations/<int:pk>/', api.affectation_detail_api, name='edt-affectation-detail'),
    path('affectations/<int:pk>/deplacer/', api.affectation_deplacer_api, name='edt-affectation-deplacer'),

    # Conflits (P07)
    path('conflits/', api.conflits_api, name='edt-conflits'),
    path('conflits/<int:pk>/resoudre/', api.conflit_resoudre_api, name='edt-conflit-resoudre'),

    # Lecture allégée & annuaires pour sélecteurs
    path('publics/', api.edt_publics_api, name='edt-publics'),
    path('referentiel-enseignants/', api.referentiel_enseignants_api, name='edt-referentiel-enseignants'),
]

# Les routes LMD viennent APRÈS les routes historiques : leur préfixe `lmd/`
# ne peut de toute façon pas être capté par `creneaux-types/`, `emplois/`,
# `affectations/` ou `conflits/`, l'ordre les rend donc sans effet — il est
# conservé pour que la lecture du fichier reflète l'historique en premier.
urlpatterns += urlpatterns_lmd
