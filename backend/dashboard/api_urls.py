from django.urls import path
from . import api_views

app_name = 'dashboard_api'

urlpatterns = [
    path('overview/', api_views.overview, name='overview'),
    path('admissions/', api_views.admissions_dashboard, name='admissions'),
    path('scolarite/', api_views.scolarite_dashboard, name='scolarite'),
    path('pedagogie/', api_views.pedagogie_dashboard, name='pedagogie'),
    path('presences/', api_views.presences_dashboard, name='presences'),
    path('finances/', api_views.finances_dashboard, name='finances'),
    path('examens/', api_views.examens_dashboard, name='examens'),
    # Alias frontend Dashboard Engine (onglet « Jurys & Diplômation »)
    path('jurys/', api_views.examens_dashboard, name='jurys'),
    path('logistique/', api_views.logistique_dashboard, name='logistique'),
    path('etudiant/', api_views.etudiant_dashboard, name='etudiant'),
    path('enseignant/', api_views.enseignant_dashboard, name='enseignant'),
]
