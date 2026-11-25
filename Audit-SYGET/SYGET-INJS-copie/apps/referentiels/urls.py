from django.urls import path

from .views import ModuleCreateView, ModuleDeleteView, ModuleListView, ModuleUpdateView, TypeFormationListView

app_name = "referentiels"

urlpatterns = [
    path("modules/", ModuleListView.as_view(), name="module_list"),
    path("modules/create/", ModuleCreateView.as_view(), name="module_create"),
    path("modules/<int:pk>/update/", ModuleUpdateView.as_view(), name="module_update"),
    path("modules/<int:pk>/delete/", ModuleDeleteView.as_view(), name="module_delete"),
    path("types/", TypeFormationListView.as_view(), name="type_list"),
]
