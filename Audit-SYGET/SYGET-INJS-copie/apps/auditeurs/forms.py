from django import forms
from django.core.exceptions import ValidationError

from apps.formations.models import Formation, FormationModule

from .models import Auditeur


class AuditeurForm(forms.ModelForm):
    """Formulaire de création / modification d'un auditeur."""

    class Meta:
        model = Auditeur
        fields = [
            "nom",
            "prenom",
            "genre",
            "date_naissance",
            "lieu_naissance",
            "telephone_1",
            "telephone_2",
            "type_concours",
            "libelle_concours",
            "categorie",
            "grade",
            "email",
        ]
        widgets = {
            "nom": forms.TextInput(attrs={"class": "form-control", "placeholder": "NOM (majuscules)"}),
            "prenom": forms.TextInput(attrs={"class": "form-control", "placeholder": "Prénom(s)"}),
            "genre": forms.Select(attrs={"class": "form-select"}),
            "date_naissance": forms.DateInput(
                attrs={"class": "form-control", "type": "date"},
                format="%Y-%m-%d",
            ),
            "lieu_naissance": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : Abidjan"}),
            "telephone_1": forms.TextInput(attrs={"class": "form-control"}),
            "telephone_2": forms.TextInput(attrs={"class": "form-control"}),
            "type_concours": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Ex : Direct, Professionnel"}
            ),
            "libelle_concours": forms.TextInput(attrs={"class": "form-control"}),
            "categorie": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : A, B, C"}),
            "grade": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: A3"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["genre"].empty_label = "— Sélectionner —"
        self.fields["date_naissance"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]


class ImportAuditeursForm(forms.Form):
    """Formulaire d'import d'auditeurs depuis un fichier Excel."""

    formation = forms.ModelChoiceField(
        queryset=Formation.objects.select_related("type_formation").order_by("-date_debut", "intitule"),
        required=True,
        label="Formation d'inscription",
        help_text="Les auditeurs créés seront inscrits aux modules de cette formation compatibles avec leur grade.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fichier = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".xlsx,.xls"}),
        label="Fichier Excel (.xlsx)",
    )

    def clean_formation(self):
        formation = self.cleaned_data["formation"]
        if not FormationModule.objects.filter(formation=formation).exists():
            raise ValidationError(
                "Cette formation n'a aucun module : ajoutez au moins un module avant d'importer des auditeurs."
            )
        return formation
