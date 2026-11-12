"""Comportements transverses du moteur Référentiels (PHASE 2).

Deux mixins réutilisables par **tous** les référentiels du registre :

* :class:`ExportReferentielMixin` — export Word / Excel / CSV / PDF ;
* :class:`ImportReferentielMixin` — import Excel / CSV en 5 étapes.

Ils ne connaissent qu'un modèle, un libellé de référentiel et un jeu de
lignes : aucune logique métier n'est dupliquée ici.
"""

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from . import colonnes as moteur_colonnes
from . import exportations as moteur_exports
from . import importations as moteur_imports


def payload_jsonisable(detail):
    """Rend un dictionnaire sérialisable en JSON (journal, rapports).

    Les valeurs importées peuvent contenir des instances de modèles (clés
    étrangères résolues), des dates ou des décimaux : elles sont converties
    en valeurs simples afin que l'écriture du journal ne puisse pas échouer
    — et surtout ne puisse pas invalider la transaction en silence.
    """
    from datetime import date, datetime
    from decimal import Decimal

    from django.db import models as modeles_django

    def convertir(valeur):
        if valeur is None or isinstance(valeur, (bool, int, float, str)):
            return valeur
        if isinstance(valeur, modeles_django.Model):
            return str(valeur)
        if isinstance(valeur, (datetime, date)):
            return valeur.isoformat()
        if isinstance(valeur, Decimal):
            return float(valeur)
        return str(valeur)

    if not isinstance(detail, dict):
        return {'valeur': convertir(detail)}
    return {cle: convertir(valeur) for cle, valeur in detail.items()}


class ExportReferentielMixin:
    """Ajoute l'action ``exporter/`` aux ViewSets dérivés."""

    @action(detail=False, methods=['get'], url_path='exporter')
    def exporter(self, request):
        """Export du référentiel : ``?export=csv|xlsx|docx|pdf`` (défaut xlsx).

        Le paramètre ``format`` est réservé par Django REST Framework pour la
        négociation de contenu (un ``?format=csv`` non géré par un renderer
        renverrait 404) : le choix du document passe donc par ``export``.

        Le périmètre exporté est **exactement** celui affiché à l'écran :
        recherche, filtres et tri courants sont appliqués avant la génération.
        """
        format_cible = (
            request.query_params.get('export')
            or request.query_params.get('format')
            or 'xlsx'
        ).lower()
        if format_cible not in moteur_exports.FORMATS:
            return Response(
                {'detail': f'Format « {format_cible} » non pris en charge. '
                           f'Formats disponibles : {", ".join(moteur_exports.FORMATS)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.filter_queryset(self.get_queryset())
        try:
            lignes = list(queryset[:moteur_exports.LIMITE_LIGNES])
        except Exception:  # pragma: no cover — filet de sécurité
            lignes = list(queryset)

        modele = queryset.model
        colonnes = moteur_colonnes.champs_exportables(modele)
        libelle_ref = self._libelle_referentiel(modele)
        titre = request.query_params.get('titre') or f"Référentiel « {libelle_ref} »"

        try:
            contenu, type_mime, nom_fichier = moteur_exports.generer_export(
                slug=self._slug_referentiel(),
                referentiel=libelle_ref,
                colonnes=colonnes,
                lignes=lignes,
                format_cible=format_cible,
                titre=titre,
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        reponse = HttpResponse(contenu, content_type=type_mime)
        reponse['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
        reponse['X-Total-Export'] = str(len(lignes))
        return reponse

    def _libelle_referentiel(self, modele):
        """Nom lisible du référentiel (registre, puis meta du modèle)."""
        entree = self._entree_registre()
        if entree:
            return entree.get('libelle') or modele._meta.verbose_name_plural.capitalize()
        return modele._meta.verbose_name_plural.capitalize()

    def _slug_referentiel(self):
        slug = getattr(self, 'slug', None)
        if slug:
            return slug
        entree = self._entree_registre()
        return (entree or {}).get('slug', 'referentiel')

    def _entree_registre(self):
        from referentiels.registre import REGISTRE

        modele = None
        try:
            modele = self.get_queryset().model
        except Exception:  # pragma: no cover
            return None
        for slug, donnees in REGISTRE.items():
            candidat = donnees.get('modele')
            nom = candidat if isinstance(candidat, str) else getattr(candidat, '__name__', '')
            app = getattr(getattr(candidat, '_meta', None), 'app_label', '') or ''
            if nom == modele.__name__:
                return {**donnees, 'slug': slug}
        return None


class ImportReferentielMixin:
    """Ajoute les actions d'import Excel/CSV en 5 étapes."""

    @action(detail=False, methods=['post'], url_path='importer/analyse')
    def importer_analyse(self, request):
        """Étapes 1 à 3 : contrôle, prévisualisation puis validation.

        Corps attendu (multipart) : ``fichier``, et facultativement
        ``a_entete`` (booléen), ``correspondance`` (JSON champ → index).
        Rien n'est écrit en base : la réponse est un pur rapport.
        """
        from rest_framework.exceptions import ValidationError

        fichier = request.FILES.get('fichier')
        if fichier is None:
            raise ValidationError({'fichier': 'Aucun fichier téléversé.'})

        try:
            extension = moteur_imports.controler_fichier(fichier)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        modele = self.get_queryset().model
        champs = moteur_colonnes.champs_importables(modele)
        correspondance = self._correspondance_depuis(request, champs)

        try:
            previsualisation = moteur_imports.previsualiser(
                fichier=fichier,
                extension=extension,
                champs_importables=champs,
                correspondance=correspondance,
                a_entete=self._booleen(request.data.get('a_entete', True)),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Étape 3 — validation (le jeu de champs est conservé pour la conversion)
        previsualisation['_colonnes_importables'] = champs
        try:
            validation = moteur_imports.valider(
                previsualisation=previsualisation,
                modele=modele,
                champ_libelle=moteur_colonnes.champ_libelle(modele),
                correspondance=correspondance,
                queryset=self.get_queryset(),
                rattachement=self._rattachement(modele),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Non sérialisable en l'état. Les relations, elles, sont déjà décrites
        # et chiffrées par la validation (y compris les références non
        # résolues par colonne) : ne pas les recalculer ici.
        validation.pop('_valides', None)
        return Response({
            'etape': 'validation',
            'slug': self._slug_referentiel(),
            'referentiel': self._libelle_referentiel(modele),
            'analyse_le': timezone.now().isoformat(),
            'previsualisation': {
                'total_lignes': previsualisation['total_lignes'],
                'entetes_fichier': previsualisation['entetes_fichier'],
                'colonnes_reconnues': previsualisation['colonnes_reconnues'],
                'colonnes_manquantes': previsualisation['colonnes_manquantes'],
                'correspondance': previsualisation['correspondance'],
                'doublons': previsualisation['doublons'],
                'apercu': previsualisation['apercu'],
            },
            'validation': validation,
            'modes_disponibles': list(moteur_imports.MODES),
        })

    @action(detail=False, methods=['post'], url_path='importer')
    def importer(self, request):
        """Étapes 4 et 5 : importation transactionnelle puis rapport final.

        Corps attendu : ``fichier``, ``mode`` (ajouter | mettre_a_jour |
        les_deux) et ``jeton`` (anti-double soumission, fourni par l'analyse).
        """
        from rest_framework.exceptions import ValidationError

        fichier = request.FILES.get('fichier')
        if fichier is None:
            raise ValidationError({'fichier': 'Aucun fichier téléversé.'})

        mode = request.data.get('mode') or 'les_deux'
        if mode not in moteur_imports.MODES:
            return Response(
                {'detail': f'Mode « {mode} » inconnu. '
                           f'Modes disponibles : {", ".join(moteur_imports.MODES)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            extension = moteur_imports.controler_fichier(fichier)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        modele = self.get_queryset().model
        champs = moteur_colonnes.champs_importables(modele)
        correspondance = self._correspondance_depuis(request, champs)

        try:
            previsualisation = moteur_imports.previsualiser(
                fichier=fichier, extension=extension, champs_importables=champs,
                correspondance=correspondance,
                a_entete=self._booleen(request.data.get('a_entete', True)),
            )
            previsualisation['_colonnes_importables'] = champs
            validation = moteur_imports.valider(
                previsualisation=previsualisation, modele=modele,
                champ_libelle=moteur_colonnes.champ_libelle(modele),
                correspondance=correspondance, queryset=self.get_queryset(),
                rattachement=self._rattachement(modele),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not validation['_valides']:
            return Response(
                {'detail': 'Aucune ligne valide à importer : corrigez les erreurs signalées.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rapport = moteur_imports.importer(
                validation=validation, modele=modele,
                champ_libelle=moteur_colonnes.champ_libelle(modele),
                mode=mode, utilisateur=request.user,
                queryset=self.get_queryset(),
                slug=self._slug_referentiel(),
                journaliser=self._journaliser_import,
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(rapport, status=status.HTTP_200_OK)

    def _rattachement(self, modele):
        """Champ de rattachement du registre servant à lever une ambiguïté.

        Le registre déclare ``unicite_par`` lorsqu'un libellé n'est unique
        que *par* un parent (un nom de bâtiment est unique par site). Ce champ
        est transmis au résolveur, qui s'en sert pour départager deux valeurs
        homonymes — uniquement quand le fichier le fournit.
        """
        entree = self._entree_registre() or {}
        unicite_par = entree.get("unicite_par") or ""
        if not unicite_par:
            return {}
        if unicite_par not in {f.name for f in modele._meta.concrete_fields}:
            return {}
        from .relations import cles_etrangeres

        return {
            field.name: unicite_par
            for field in cles_etrangeres(modele)
            if field.name != unicite_par
        }

    def _journaliser_import(self, objet, action, detail):
        """Branche le moteur sur le journal du référentiel.

        Le détail est **rendu sérialisable** avant l'écriture : le champ
        ``detail`` du journal est un JSON, et les valeurs importées peuvent
        porter des instances de modèles (clés étrangères résolues) ou des
        dates. Une erreur de sérialisation n'est **jamais** avalée : elle
        doit remonter, sinon la transaction serait annulée en silence et le
        rapport annoncerait des écritures qui n'existent pas.
        """
        journaliser = getattr(self, '_journaliser', None)
        if journaliser is None:
            return
        try:
            from referentiels.models import ReferentielJournal
        except ImportError:  # pragma: no cover
            return
        action_journal = (ReferentielJournal.Action.CREATION
                          if action == 'import_creation'
                          else ReferentielJournal.Action.MODIFICATION)
        journaliser(objet, action_journal, {
            'import': payload_jsonisable(detail),
        })

    @staticmethod
    def _booleen(valeur):
        if isinstance(valeur, bool):
            return valeur
        return str(valeur).lower() not in {'false', '0', 'non', 'n', ''}

    @staticmethod
    def _correspondance_depuis(request, champs):
        """Lit la correspondance de colonnes choisie par l'utilisateur."""
        import json

        brut = request.data.get('correspondance')
        if brut in (None, '', 'null'):
            return None
        if isinstance(brut, dict):
            donnees = brut
        else:
            try:
                donnees = json.loads(brut)
            except (TypeError, ValueError):
                return None
        if not isinstance(donnees, dict):
            return None
        autorises = {c['cle'] for c in champs}
        resultat = {}
        for cle, position in donnees.items():
            if cle not in autorises:
                continue
            try:
                resultat[cle] = None if position in (None, '', -1) else int(position)
            except (TypeError, ValueError):
                continue
        return resultat or None
