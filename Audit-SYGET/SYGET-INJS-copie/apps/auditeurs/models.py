"""
Modèles de l'app auditeurs.
"""

from django.db import models


class Auditeur(models.Model):
    """
    Auditeur : participant à une formation.
    Peut être importé par fichier Excel ou créé manuellement.
    """

    class Genre(models.TextChoices):
        MASCULIN = "M", "Masculin"
        FEMININ = "F", "Féminin"

    matricule = models.CharField(max_length=30, unique=True, verbose_name="N° d'inscription")
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, verbose_name="Prénom(s)")
    genre = models.CharField(max_length=1, choices=Genre.choices, blank=True, verbose_name="Genre")
    date_naissance = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    lieu_naissance = models.CharField(max_length=200, blank=True, verbose_name="Lieu de naissance")
    telephone_1 = models.CharField(max_length=20, blank=True, verbose_name="Téléphone 1")
    telephone_2 = models.CharField(max_length=20, blank=True, verbose_name="Téléphone 2")
    type_concours = models.CharField(max_length=100, blank=True, verbose_name="Type concours")
    libelle_concours = models.CharField(max_length=200, blank=True, verbose_name="Libellé concours")
    categorie = models.CharField(max_length=50, blank=True, verbose_name="Catégorie")
    grade = models.CharField(max_length=20, blank=True, verbose_name="Grade")
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auditeur"
        verbose_name_plural = "Auditeurs"
        ordering = ["nom", "prenom"]

    def __str__(self) -> str:
        return f"{self.nom.upper()} {self.prenom} ({self.matricule})"

    @property
    def nom_complet(self) -> str:
        """Retourne le nom complet formaté."""
        return f"{self.nom.upper()} {self.prenom}"

    @property
    def grade_groupe(self) -> str:
        """Retourne la combinaison Grade-Groupe pour le premier groupe de formation."""
        premier_groupe = self.groupes.select_related("groupe").first()
        if premier_groupe:
            nom_groupe = premier_groupe.groupe.nom
            if self.grade:
                return f"{self.grade}-{nom_groupe}"
            return nom_groupe
        return self.grade or "—"
