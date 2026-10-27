from django.urls import path
from . import views

urlpatterns = [
    # Export par formation (toutes séances de tous les modules)
    path('formation/<int:pk>/pdf/', views.export_pdf, name='export-pdf'),
    path('formation/<int:pk>/excel/', views.export_excel, name='export-excel'),
    # Export par module (toutes séances d'un module spécifique)
    path('module/<int:module_pk>/pdf/', views.export_pdf_module, name='export-pdf-module'),
    path('module/<int:module_pk>/excel/', views.export_excel_module, name='export-excel-module'),
    # Export par session
    path('session/<int:session_pk>/pdf/', views.export_pdf_session, name='export-pdf-session'),
    path('session/<int:session_pk>/excel/', views.export_excel_session, name='export-pdf-session-excel'),
    # Export finance par formateur
    path('formateur/<int:formateur_pk>/pdf/', views.export_finance_formateur_pdf, name='export-finance-formateur-pdf'),
    path('formateur/<int:formateur_pk>/excel/', views.export_finance_formateur_excel, name='export-finance-formateur-excel'),
    # Export finance consolidé (tous les formateurs)
    path('finance/synthese/pdf/', views.export_finance_synthese_pdf, name='export-finance-synthese-pdf'),
    path('finance/synthese/excel/', views.export_finance_synthese_excel, name='export-finance-synthese-excel'),
    path('finance/encadrants/pdf/', views.export_finance_encadrants_pdf, name='export-finance-encadrants-pdf'),
    path('finance/encadrants/excel/', views.export_finance_encadrants_excel, name='export-finance-encadrants-excel'),
    # Export liste de classe auditeurs (par groupe)
    path('participants/liste-classe/pdf/', views.export_liste_classe_pdf, name='export-liste-classe-pdf'),
    path('participants/liste-classe/excel/', views.export_liste_classe_excel, name='export-liste-classe-excel'),
]
