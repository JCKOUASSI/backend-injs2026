from django import forms

from .models import Module, TypeFormation


class TypeFormationForm(forms.ModelForm):
    """Formulaire de création / modification d'un type de formation."""

    class Meta:
        model = TypeFormation
        fields = ["code", "libelle"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: FAC"}),
            "libelle": forms.TextInput(attrs={"class": "form-control", "placeholder": "Libellé complet"}),
        }


class ModuleForm(forms.ModelForm):
    """Formulaire de création / modification d'un module dans le référentiel global."""

    class Meta:
        model = Module
        fields = ["titre", "specialite"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Titre du module"}),
            "specialite": forms.Select(attrs={"class": "form-control"}),
        }
