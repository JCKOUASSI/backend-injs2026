from django.urls import path

from . import api_views, concours_api

urlpatterns = [
    path('candidats/',                        api_views.candidat_list,           name='admissions-candidat-list'),
    path('candidats/<int:pk>/',               api_views.candidat_detail,         name='admissions-candidat-detail'),

    path('candidatures/',                     api_views.candidature_list,        name='admissions-candidature-list'),
    path('candidatures/stats/',               api_views.candidature_stats,       name='admissions-candidature-stats'),
    path('candidatures/<int:pk>/',            api_views.candidature_detail,      name='admissions-candidature-detail'),
    path('candidatures/<int:pk>/transition/', api_views.candidature_transition,  name='admissions-candidature-transition'),
    path('candidatures/<int:pk>/pieces/',     api_views.candidature_pieces,      name='admissions-candidature-pieces'),

    path('admissions/',                       api_views.admission_list,          name='admissions-admission-list'),
    path('admissions/stats/',                 api_views.admission_stats,         name='admissions-admission-stats'),
    path('admissions/<int:pk>/',              api_views.admission_detail,        name='admissions-admission-detail'),
    path('admissions/<int:pk>/decision/',     api_views.admission_decision,      name='admissions-admission-decision'),
    path('admissions/<int:pk>/annuler/',      api_views.admission_annuler,       name='admissions-admission-annuler'),

    path('pieces/<int:piece_id>/deposer/',    api_views.piece_deposer,           name='admissions-piece-deposer'),
    path('pieces/<int:piece_id>/verifier/',   api_views.piece_verifier,          name='admissions-piece-verifier'),
    path('pieces/<int:piece_id>/fichier/',    api_views.piece_telecharger,       name='admissions-piece-fichier'),

    # Lot L2 — campagnes et concours/sélection
    path('campagnes/',                        concours_api.campagne_list,        name='admissions-campagne-list'),
    path('campagnes/<int:pk>/',               concours_api.campagne_detail,      name='admissions-campagne-detail'),
    path('campagnes/<int:pk>/transition/',    concours_api.campagne_transition,  name='admissions-campagne-transition'),
    path('campagnes/<int:pk>/epreuves/',      concours_api.campagne_epreuve_create, name='admissions-campagne-epreuve-create'),
    path('campagnes/<int:pk>/classement/',    concours_api.campagne_classement,  name='admissions-campagne-classement'),
    path('campagnes/<int:pk>/classement/calculer/', concours_api.campagne_classement_calculer, name='admissions-classement-calculer'),
    path('campagnes/<int:pk>/classement/publier/',  concours_api.campagne_classement_publier, name='admissions-classement-publier'),
    path('epreuves/<int:pk>/surveillants/',   concours_api.epreuve_surveillant_add, name='admissions-epreuve-surveillant'),
    path('epreuves/<int:pk>/convocations/generer/', concours_api.epreuve_convocations_generer, name='admissions-convocations-generer'),
    path('epreuves/<int:pk>/verrouiller/',    concours_api.epreuve_verrouiller,   name='admissions-epreuve-verrouiller'),
    path('epreuves/<int:pk>/notes/',          concours_api.epreuve_notes,         name='admissions-epreuve-notes'),
    path('convocations/<int:pk>/presence/',   concours_api.convocation_presence, name='admissions-convocation-presence'),

    path('ref/<str:ressource>/',              api_views.referentiel_list,        name='admissions-ref-list'),
    path('ref/<str:ressource>/<int:pk>/',     api_views.referentiel_detail,      name='admissions-ref-detail'),
]
