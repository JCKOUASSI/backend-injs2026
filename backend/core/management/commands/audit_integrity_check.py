"""Commande d'intégrité du journal d'audit unifié (P01-01).

Vérifie, en lecture seule, la cohérence du registre :

1. **codes en doublon** (la contrainte unique devrait les interdire) ;
2. **séquences trouées ou en avance sur le compteur**, journée par journée ;
3. **répliques orphelines** : une entrée core indique une source dont
   l'enregistrement d'origine a disparu (les journaux sources ne sont jamais
   censés être purgés) ;
4. **dédoublonnage de réplication** : une même entrée source ne doit produire
   qu'une seule réplique ;
5. **compteurs incohérents** : le ``dernier_numero`` doit correspondre au
   nombre d'événements de la journée (la séquence est continue à partir de 1).

La commande ne modifie rien et sort en code 1 dès qu'une anomalie est trouvée
: elle est branchée dans la CI (job Backend) après les tests.
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from core.audit_services import PREFIXE_CODE
from core.models import CompteurCode, EvenementAudit


def analyser_codes(evenements):
    """Détecte codes en doublon et codes mal formés. Pur."""
    anomalies = []
    codes = [e.code for e in evenements]
    for code, nombre in Counter(codes).items():
        if nombre > 1:
            anomalies.append(f'Code en doublon {code} ({nombre} occurrences)')
    for code in codes:
        parties = code.split('-')
        if (
            len(parties) != 3
            or parties[0] != PREFIXE_CODE
            or len(parties[1]) != 8
            or not parties[1].isdigit()
            or len(parties[2]) != 6
            or not parties[2].isdigit()
        ):
            anomalies.append(f'Code mal formé : {code}')
    return anomalies


def analyser_sequences(evenements, compteurs):
    """Vérifie la continuité des séquences par journée. Pur."""
    anomalies = []
    par_jour = defaultdict(list)
    for e in evenements:
        parties = e.code.rsplit('-', 1)
        jour = parties[0]  # ex. AUDIT-20260913
        try:
            numero = int(parties[1])
        except (IndexError, ValueError):
            continue  # déjà signalé par analyser_codes
        par_jour[jour].append(numero)

    compteurs_par_cle = {c.cle: c.dernier_numero for c in compteurs}

    for jour, numeros in par_jour.items():
        numeros.sort()
        attendus = list(range(1, len(numeros) + 1))
        if numeros != attendus:
            manquants = sorted(set(attendus) - set(numeros))
            sup = sorted(set(numeros) - set(attendus))
            anomalies.append(
                f'Séquence discontinue pour {jour} '
                f'(manquants {manquants}, hors suite {sup})'
            )
        compteur = compteurs_par_cle.get(jour)
        if compteur is None:
            anomalies.append(f'Aucun compteur pour {jour} ({len(numeros)} événements)')
        elif compteur != len(numeros):
            anomalies.append(
                f'Compteur {jour} incohérent : compteur={compteur}, '
                f'événements={len(numeros)}'
            )

    # Compteur dont la journée n'a aucun événement.
    cles_evenements = set(par_jour)
    for cle, numero in compteurs_par_cle.items():
        if cle not in cles_evenements and numero:
            anomalies.append(f'Compteur {cle} à {numero} sans événement')
    return anomalies


def analyser_repliques(evenements):
    """Dédoublonnage des répliques source (pur, sans accès aux tables sources)."""
    anomalies = []
    vues = Counter(
        (e.source, e.source_entree_id)
        for e in evenements
        if e.source_entree_id is not None
    )
    for (source, entree_id), nombre in vues.items():
        if nombre > 1:
            anomalies.append(
                f'{nombre} répliques pour {source} entrée n°{entree_id} '
                '(idempotence de réplication en défaut)'
            )
    return anomalies


def verifier_orphelins():
    """Vérifie que chaque réplique pointe encore vers son entrée source."""
    orphelins = []

    def _comptes(modele, source):
        ids = list(
            EvenementAudit.objects
            .filter(source=source, source_entree_id__isnull=False)
            .values_list('source_entree_id', flat=True)
        )
        if not ids:
            return
        existants = set(
            modele.objects.filter(pk__in=ids).values_list('pk', flat=True)
        )
        for identifiant in ids:
            if identifiant not in existants:
                orphelins.append(f'{source} entrée n°{identifiant} introuvable')

    from presences.models import AuditLog
    from referentiels.models import ReferentielJournal
    from scolarite.models import JournalScolarite
    _comptes(AuditLog, EvenementAudit.Source.PRESENCES)
    _comptes(JournalScolarite, EvenementAudit.Source.SCOLARITE)
    _comptes(ReferentielJournal, EvenementAudit.Source.REFERENTIELS)
    return orphelins


class Command(BaseCommand):
    help = "Vérifie l'intégrité du journal d'audit unifié (codes, séquences, répliques)."

    def handle(self, *args, **options):
        evenements = list(
            EvenementAudit.objects.all().only('code', 'source', 'source_entree_id')
        )
        compteurs = list(CompteurCode.objects.all())

        anomalies = []
        anomalies.extend(analyser_codes(evenements))
        anomalies.extend(analyser_sequences(evenements, compteurs))
        anomalies.extend(analyser_repliques(evenements))
        anomalies.extend(verifier_orphelins())

        if anomalies:
            self.stderr.write(
                self.style.ERROR(
                    f"Intégrité du journal d'audit NON CONFORME — "
                    f"{len(anomalies)} anomalie(s) :"
                )
            )
            for ligne in anomalies:
                self.stderr.write(f'  - {ligne}')
            raise CommandError('audit_integrity_check : anomalies détectées')

        self.stdout.write(self.style.SUCCESS(
            f"Intégrité du journal d'audit CONFORME — {len(evenements)} événement(s), "
            f"{len(compteurs)} compteur(s), aucune anomalie."
        ))
