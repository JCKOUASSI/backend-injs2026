"""
Formulaires de simulation : un bloc de paramètres par formation.
"""

from django import forms
from django.forms import formset_factory


class SimulationFormationForm(forms.Form):
    """Paramètres de dimensionnement pour une formation."""

    formation_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    intitule = forms.CharField(required=False, widget=forms.HiddenInput())

    nb_groupes = forms.IntegerField(
        label="Nombre de groupes",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    capacite_groupe = forms.IntegerField(
        label="Auditeurs par groupe",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    nb_modules = forms.IntegerField(
        label="Nombre de modules",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    heures_par_module = forms.IntegerField(
        label="Heures par module (max.)",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    nb_salles = forms.IntegerField(
        label="Nombre de salles disponibles",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    capacite_salle_moyenne = forms.IntegerField(
        label="Capacité moyenne d'une salle",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    tolerance_capacite_pct = forms.IntegerField(
        label="Tolérance capacité salle (%)",
        min_value=0,
        max_value=100,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100}),
    )
    jours_ouvres = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput(),
    )
    jours_semaine = forms.MultipleChoiceField(
        label="Jours travaillés par semaine",
        choices=[
            (0, "Lun"),
            (1, "Mar"),
            (2, "Mer"),
            (3, "Jeu"),
            (4, "Ven"),
            (5, "Sam"),
            (6, "Dim"),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    creneaux_par_jour = forms.TypedChoiceField(
        label="Créneaux par jour",
        choices=[(1, "1 (matin OU soir)"), (2, "2 (matin + soir)")],
        coerce=int,
        initial=2,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    duree_creneau_heures = forms.IntegerField(
        label="Durée d'un créneau (heures)",
        min_value=1,
        initial=4,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    max_salles_simultanees_module = forms.IntegerField(
        label="Salles utilisables simultanément par module",
        min_value=1,
        help_text="Au-delà du pool de salles, la valeur est plafonnée au nombre de salles.",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    date_debut = forms.DateField(
        label="Date de début",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    date_fin = forms.DateField(
        label="Date de fin prévue",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )


SimulationFormationFormSet = formset_factory(
    SimulationFormationForm,
    extra=0,
    min_num=0,
    validate_min=True,
    max_num=20,
)

# Alias rétro-compatibilité (tests, imports)
SimulationForm = SimulationFormationForm
