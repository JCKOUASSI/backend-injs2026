"""
Modèles de l'app referentiels.
TypeFormation et Module constituent le référentiel global partagé par les autres apps.
"""

from django.db import models
from django.db.models import Q


class Specialite(models.Model):
    """Référentiel de spécialités pédagogiques (rattachées aux formateurs et aux modules)."""

    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Spécialité"
        verbose_name_plural = "Spécialités"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.libelle}"


class TypeFormation(models.Model):
    """
    Type de formation (ex : FAC, FAB).
    Référentiel global utilisé par les formations et le paramétrage.
    """

    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Type de formation"
        verbose_name_plural = "Types de formation"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.libelle}"


class Module(models.Model):
    """
    Module de formation (ex : Culture Civique, Informatique).
    Référentiel global ; les associations avec les types de formation
    sont gérées dans l'app parametrage (ModuleTypeFormation).
    """

    titre = models.CharField(max_length=200, unique=True)
    actif = models.BooleanField(default=True)
    specialite = models.ForeignKey(
        Specialite,
        on_delete=models.PROTECT,
        related_name="modules",
        help_text=(
            "Spécialité du module. Pour le dispatch des formateurs : prise en compte de cette "
            "spécialité et de toute autre entrée du référentiel dont le code ou le libellé est "
            "identique au titre du module (insensible à la casse)."
        ),
    )

    class Meta:
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        ordering = ["titre"]

    def __str__(self) -> str:
        return self.titre

    def ids_specialites_pour_matching_formateurs(self) -> frozenset[int]:
        """
        Identifiants de spécialités pour lesquelles un formateur peut intervenir sur ce module.

        Inclut la spécialité référencée sur le module et toute ``Specialite`` dont le ``code`` ou le
        ``libelle`` correspond au ``titre`` du module (égalité insensible à la casse, espaces bords
        ignorés). Permet d'aligner le référentiel formateurs sur le nom métier du module.
        """
        cache_attr = "_cache_ids_specialites_matching_formateurs"
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        ids: set[int] = {int(self.specialite_id)}
        titre = (self.titre or "").strip()
        if titre:
            ids.update(
                Specialite.objects.filter(Q(code__iexact=titre) | Q(libelle__iexact=titre)).values_list("pk", flat=True)
            )
        result = frozenset(ids)
        setattr(self, cache_attr, result)
        return result
