from django.urls import path

from . import charges_api

urlpatterns = [
    path('charges/<int:enseignant_id>/',        charges_api.charge_enseignant,     name='enseignants-charge'),
    path('affectations/',                       charges_api.affectation_list,      name='enseignants-affectation-list'),
    path('affectations/<int:pk>/',              charges_api.affectation_detail,    name='enseignants-affectation-detail'),
    path('indisponibilites/',                   charges_api.indisponibilite_list,  name='enseignants-indisponibilite-list'),
    path('anomalies/',                          charges_api.anomalies_list,        name='enseignants-anomalies'),
    path('occupation/',                         charges_api.occupation_report,     name='enseignants-occupation'),
]
