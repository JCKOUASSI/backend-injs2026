"""Reférentiel métier INJS (Phase 1)"""
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class DepartementService(models.Model):
    """1. Departement/Service de l'INJS."""
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    type = models.CharField(max_length=20, choices=[("DEPARTEMENT", "Departement"), ("SERVICE", "Service")], default='DEPARTEMENT')
    description = models.TextField(blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='departements_resp')

    class Meta:
        verbose_name = "Departement/Service"
        verbose_name_plural = "Departements/Services"
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.get_type_display()})"

