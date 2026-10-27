"""Imports en masse transactionnels et RÉVERSIBLES (C3 point 4, L3).

* l'exécution revérifie toutes les lignes puis écrit dans UNE seule
  transaction : une seule erreur (doublon apparu entre l'aperçu et
  l'exécution, rôle manquant) fait tout échouer sans rien créer ;
* chaque exécution reçoit une référence ``IMP-AAAAMMJJ-NNNN`` et lie les
  comptes qu'elle a créés (:attr:`CompteUtilisateur.import_execution`) ;
* l'annulation d'un geste est possible « d'un seul geste » par référence.
  Conformément à S5, elle NE SUPPRIME RIEN : les comptes sont désactivés
  (miroir ``is_active=False``), leur historique et le journal demeurent.
"""
from django.db import transaction
from django.utils import timezone

from ..models import CompteUtilisateur, ExecutionImport
from .comptes_admin import ErreurConsole, creer_compte, simuler_import
from .journalisation import journaliser

#: Correspondances explicites tirées de l'annexe A6, pour les lignes qui
#: n'explicitent pas leur rôle d'accès de transition.
LEGACY_DEDUIT = {
    'ETUDIANT': 'AUDITEUR',
    'ENSEIGNANT': 'FORMATEUR',
}


def _role_legacy(ligne, roles):
    legacy = (ligne.get('role_legacy') or '').strip()
    if legacy:
        return legacy
    if len(roles) == 1 and roles[0] in LEGACY_DEDUIT:
        return LEGACY_DEDUIT[roles[0]]
    # Un compte sans rôle de connexion ne peut pas être créé : on ne devine
    # jamais un rôle d'accès pour un profil administratif.
    return ''


def _reference(execution):
    jour = timezone.localdate().strftime('%Y%m%d')
    return f'IMP-{jour}-{execution.pk:04d}'


@transaction.atomic
def executer_import(acteur, lignes, meta=None, nom_fichier=''):
    """Valide puis crée tous les comptes, ou échoue sans aucune écriture."""
    meta = meta or {}
    if not lignes:
        raise ErreurConsole('IMPORT_VIDE', "Aucune ligne à importer.")

    # Seconde validation, juste avant l'écriture (l'aperçu peut dater).
    apercu = simuler_import(lignes)
    if apercu['erreurs']:
        raise ErreurConsole(
            'IMPORT_NON_VALIDE',
            "L'import contient des lignes en erreur : corrigez et rejouez "
            "le fichier ; aucune écriture n'est réalisée.",
            409,
        )

    execution = ExecutionImport.objects.create(
        reference='TEMP', statut=ExecutionImport.Statut.EN_COURS,
        nom_fichier=nom_fichier[:255], total=apercu['total'],
        lance_par=acteur,
    )
    execution.reference = _reference(execution)
    execution.save(update_fields=['reference'])

    comptes_crees = []
    lignes_rapport = []
    for entree in apercu['lignes']:
        ligne = entree['valeurs']
        roles = [r.strip() for r in (ligne.get('roles') or '').split(',') if r.strip()]
        role_legacy = _role_legacy(ligne, roles)
        if not role_legacy:
            # Coincé par une seconde vérification : on annule TOUT.
            raise ErreurConsole(
                'ROLE_LEGACY_REQUIS',
                f"La ligne {entree['numero']} ({ligne.get('username')}) doit "
                "expliciter un rôle d'accès (colonne role_legacy).",
                409,
            )
        # A6 : étudiants et enseignants sont des comptes MOBILE/PWA ; pour
        # eux, un canal non précisé est déduit MOBILE (la règle de transport
        # refuse leur connexion web).
        canal = (ligne.get('canal') or '').strip()
        if not canal and set(roles) <= {'ETUDIANT', 'ENSEIGNANT'}:
            canal = 'MOBILE'
        charge = {
            'identifiants': {
                'username': (ligne.get('username') or '').strip(),
                'email': ligne.get('email') or '',
                'mot_de_passe': ligne.get('mot_de_passe'),
                'role_legacy': role_legacy,
            },
            'personne': {
                'nom': ligne.get('nom') or '',
                'prenoms': ligne.get('prenoms') or '',
                'email': ligne.get('email') or '',
            },
            'canal': canal or 'WEB',
            'motif': f"Import en masse {execution.reference}",
            'roles': [{'role': code, 'motif': f"Import {execution.reference}"}
                      for code in roles],
        }
        compte = creer_compte(acteur, charge, meta)
        compte.import_execution = execution
        compte.save(update_fields=['import_execution'])
        comptes_crees.append(compte.pk)
        lignes_rapport.append({
            'numero': entree['numero'], 'username': charge['identifiants']['username'],
            'compte': compte.pk, 'roles': roles, 'etat': 'CREE',
        })

    execution.statut = ExecutionImport.Statut.TERMINE
    execution.crees = len(comptes_crees)
    execution.rapport = {
        'total': execution.total, 'crees': execution.crees,
        'comptes': comptes_crees, 'lignes': lignes_rapport,
        'message': (f"{execution.crees} compte(s) créé(s) en une transaction. "
                    "Annulable d'un seul geste par la référence d'exécution."),
    }
    execution.save()
    journaliser(
        'IMPORT_EXECUTE', acteur=acteur,
        nouvelle_valeur={
            'reference': execution.reference, 'crees': execution.crees,
            'fichier': execution.nom_fichier,
        },
        motif=f"Exécution d'import {execution.reference}",
        adresse_ip=meta.get('ip', ''), agent_utilisateur=meta.get('ua', ''),
    )
    return execution


@transaction.atomic
def annuler_import(execution, acteur, motif, meta=None):
    """Désactive tous les comptes créés par l'exécution (S5 : jamais supprimés)."""
    meta = meta or {}
    execution = ExecutionImport.objects.select_for_update().get(pk=execution.pk)
    if execution.statut == ExecutionImport.Statut.ANNULE:
        raise ErreurConsole('IMPORT_DEJA_ANNULE',
                            "Cet import est déjà annulé.", 409)
    if execution.statut != ExecutionImport.Statut.TERMINE:
        raise ErreurConsole(
            'IMPORT_NON_ANNULABLE',
            "Seul un import terminé (ayant effectivement créé des comptes) "
            "peut être annulé.",
            409,
        )
    if not (motif or '').strip():
        raise ErreurConsole('MOTIF_REQUIS',
                            "Un motif est obligatoire pour annuler un import.")

    comptes = list(execution.comptes_crees.select_related('user').order_by('pk'))
    traites = []
    # Réutilisation de la machine à états : ses gardes (deux administrateurs,
    # transition légale, motif) s'appliquent à chaque compte.
    for compte in comptes:
        if compte.statut != CompteUtilisateur.Statut.ACTIF:
            traites.append({'compte': compte.pk, 'etat': compte.statut, 'ignore': True})
            continue
        # On passe par le service qui journalise et applique le miroir User.
        from .comptes_admin import changer_statut
        changer_statut(
            compte, acteur, 'desactiver',
            f"Annulation de l'import {execution.reference} : {motif}",
            meta,
        )
        traites.append({'compte': compte.pk, 'etat': 'DESACTIVE'})

    execution.statut = ExecutionImport.Statut.ANNULE
    execution.annule_par = acteur
    execution.date_annulation = timezone.now()
    execution.motif_annulation = motif
    execution.rapport_annulation = {'comptes': traites, 'motif': motif}
    execution.save()
    journaliser(
        'IMPORTA_ANNULE', acteur=acteur,
        cible=execution,
        nouvelle_valeur={'reference': execution.reference,
                         'comptes_traites': len(traites)},
        motif=motif, adresse_ip=meta.get('ip', ''),
        agent_utilisateur=meta.get('ua', ''),
    )
    return execution


def serialiser_execution(execution):
    return {
        'id': execution.pk,
        'reference': execution.reference,
        'statut': execution.statut,
        'statut_libelle': execution.get_statut_display(),
        'nom_fichier': execution.nom_fichier,
        'total': execution.total,
        'crees': execution.crees,
        'erreurs': execution.erreurs,
        'rapport': execution.rapport,
        'rapport_annulation': execution.rapport_annulation,
        'date_execution': execution.date_execution.isoformat(),
        'date_annulation': execution.date_annulation.isoformat()
        if execution.date_annulation else None,
        'motif_annulation': execution.motif_annulation,
    }
