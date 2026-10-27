"""Lot L8 (GET-INJS) — LOT 3 : tests de la couche API LMD.

Ces tests exercent les **routes ajoutées** sous ``/api/edts/lmd/…`` qui
exposent le moteur du LOT 2. Ils construisent leurs propres données dans la
base de test Django (``TestCase``, transaction annulée en fin de test) : la base
de développement n'est jamais touchée.

Couverture :
- routes        : présence des routes LMD, résolution sans capture croisée ;
- audit         : OK / WARNING / BLOCKING, aucune donnée absente présentée
                   comme valide, capacité NULL jamais « suffisante » ;
- ressources    : disponibilités enseignants/salles, canevas vide explicite ;
- génération    : moteur LOT 2 appelé, persistance, refus hors périmètre INJS ;
- validation    : refus si violation bloquante, statut non usurpé ;
- publication   : idempotence, refus de republication, contrôle de version ;
- déplacement   : revalidation C1→C10, refus d'un déplacement bloquant ;
- annulation    : traçable, réversible, sans suppression physique ;
- sécurité      : lecture / planification / validation, refus hors RBAC ;
- régression    : ``POST /api/edts/emplois/{id}/generer/`` reste conforme à son
                   contrat historique (``generer_brouillon``).
"""

from datetime import time

from django.test import TestCase
from django.urls import resolve
from rest_framework.test import APIClient

from edts.moteur import generation as G
from edts.models import CreneauTemplate, EmploiDuTemps
from edts.tests.test_lot2_moteur import FabriqueLMD
from formations.models import RefFormation
from formations.referentiel_injs_l6 import SOURCE_A45
from scolarite.models import Groupe, Parcours

ROUTES_LMD = [
    '/api/edts/lmd/audit/', '/api/edts/lmd/constraints/',
    '/api/edts/lmd/slots/', '/api/edts/lmd/versions/',
    '/api/edts/lmd/generate/', '/api/edts/lmd/availability/teachers/',
    '/api/edts/lmd/availability/rooms/', '/api/edts/lmd/12/audit/',
    '/api/edts/lmd/12/result/', '/api/edts/lmd/12/grille/',
    '/api/edts/lmd/12/validate/', '/api/edts/lmd/12/publish/',
    '/api/edts/lmd/items/5/move/', '/api/edts/lmd/items/5/cancel/',
]


def creer_utilisateur(nom, role):
    from django.contrib.auth import get_user_model

    U = get_user_model()
    user = U.objects.create_user(username=nom, password='x')
    user.role = role
    user.save()
    return user


class BaseLMD(TestCase):
    """Fabrique partagée : chaque test est autonome et jetable."""

    def setUp(self):
        self.client_api = APIClient()
        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.groupe = self.f.creer_groupe()
        self.salle = self.f.creer_salle('Salle A', 'SALLE', 30)

    def connecter(self, role, nom='u_lmd'):
        user = creer_utilisateur(nom, role)
        self.client_api.force_authenticate(user=user)
        return user

    def creer_edt(self, statut='BROUILLON', titre='EDT LMD test'):
        return EmploiDuTemps.objects.create(
            annee_academique=self.f.annee, population_type='FORMATION',
            population_id=self.f.cycle.pk, titre=titre, statut=statut,
            semaine_debut=1, semaine_fin=10, rentree=self.f.annee.date_debut,
        )

    def parametres_generation(self, **extras):
        params = {
            'annee_academique_id': self.f.annee.pk,
            'ref_formation_id': self.f.cycle.pk,
            'parcours_id': self.f.parcours.pk,
            'niveau_id': self.f.niveau.pk,
            'semestre_id': self.f.semestre.pk,
            'groupe_ids': str(self.groupe.pk),
        }
        params.update(extras)
        return params

    def generer_et_persister(self, volume=2, type_ens='CM'):
        """Génère via la route LMD avec persistance — chemin nominal complet.

        L'unicité (année, population, version) impose un EDT distinct par test.
        Chaque test crée donc son propre cycle INJS (le référentiel L6 ne
        retient que les cycles qualifiés INJS) : les données de développement
        ne sont jamais touchées. L'affectation pédagogique est rattachée à ce
        cycle — sans quoi les filtres de périmètre du moteur la rejettent.
        """
        suffixe = self._testMethodName[:16].upper().replace('_', '-')
        cycle = RefFormation.objects.create(
            intitule=f'CYCLE INJS TEST {suffixe}', perimetre='INJS',
            filiere_code='F01', source=SOURCE_A45,
        )
        self.f.creer_creneaux(jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)))
        parcours = Parcours.objects.create(
            code=f'P-{suffixe[:8]}', intitule='Parcours test',
            ref_formation=cycle)
        groupe = Groupe.objects.create(
            annee_academique=self.f.annee, ref_formation=cycle,
            parcours=parcours, niveau=self.f.niveau, nom='L1-G1',
            capacite_max=30)
        self.f.creer_affectation(volume=volume, type_ens=type_ens,
                                 groupe=groupe, ref_formation=cycle,
                                 parcours=parcours)
        edt = self.creer_edt()
        edt.population_id = cycle.pk
        edt.save(update_fields=['population_id'])
        params = self.parametres_generation(
            ref_formation_id=cycle.pk, parcours_id=parcours.pk,
            groupe_ids=str(groupe.pk), emploi_du_temps_id=edt.pk, persister='1')
        reponse = self.client_api.post(
            '/api/edts/lmd/generate/', params, format='json')
        return edt, reponse


class TestRoutesLMD(TestCase):
    """Les routes LMD existent et ne se capturent pas entre elles."""

    def test_les_quatorze_routes_resolvent(self):
        for url in ROUTES_LMD:
            with self.subTest(url=url):
                self.assertTrue(callable(resolve(url).func))

    def test_alias_timetable_est_monte_egalement(self):
        """Le même jeu de routes est monté sur /api/timetable/."""
        for url in ROUTES_LMD:
            with self.subTest(url=url):
                self.assertTrue(
                    callable(resolve(url.replace('/edts/', '/timetable/')).func))

    def test_audit_de_preparation_ne_prend_pas_le_chemin_pk(self):
        """`lmd/audit/` (préparation) et `lmd/<pk>/audit/` (EDT) coexistent."""
        preparation = resolve('/api/edts/lmd/audit/')
        self.assertNotIn('pk', preparation.kwargs)
        self.assertEqual(preparation.kwargs, {})


class TestAuditLMD(BaseLMD):
    """Un audit distingue OK / WARNING / BLOCKING et ne masque aucune absence."""

    def test_audit_bloque_sans_affectation_pedagogique(self):
        self.connecter('SECRETARIAT')
        corps = self.client_api.get('/api/edts/lmd/audit/').json()
        self.assertFalse(corps['generable'])
        self.assertEqual(corps['statut'], 'BLOCKING')
        codes = {c['code'] for c in corps['controles']}
        self.assertIn('AFFECTATIONS_PEDAGOGIQUES_VIDES', codes)
        for controle in corps['controles']:
            if controle['niveau'] == 'BLOCKING':
                self.assertTrue(controle['action_recommandee'],
                                'Tout blocage doit indiquer une action.')

    def test_audit_bloque_sans_canevas(self):
        """Affectations présentes mais canevas vide → CANEVAS_HORAIRE_VIDE."""
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.connecter('SECRETARIAT')
        corps = self.client_api.get('/api/edts/lmd/audit/').json()
        codes = {c['code'] for c in corps['controles']}
        self.assertIn('CANEVAS_HORAIRE_VIDE', codes)
        self.assertFalse(corps['generable'])
        bloquant = next(c for c in corps['controles']
                        if c['code'] == 'CANEVAS_HORAIRE_VIDE')
        for mot in ('canevas', 'génération'):
            self.assertIn(mot, bloquant['action_recommandee'].lower())

    def test_audit_signale_les_capacites_inconnues(self):
        """capacité NULL → WARNING, jamais « capacité suffisante »."""
        from formations.models import RefSalle

        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        RefSalle.objects.create(site=self.f.site, batiment=self.f.batiment,
                                nom='Salle sans capacité', type_lieu='SALLE',
                                capacite=None)
        self.connecter('SECRETARIAT')
        corps = self.client_api.get('/api/edts/lmd/audit/').json()
        avertissement = next((c for c in corps['controles']
                             if c['code'] == 'CAPACITE_INCONNUE'), None)
        self.assertIsNotNone(avertissement)
        self.assertEqual(avertissement['niveau'], 'WARNING')
        self.assertIn('Salle sans capacité',
                      avertissement['detail']['salles_sans_capacite'])

    def test_audit_est_generable_quand_les_prerequis_sont_fournis(self):
        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        self.connecter('SECRETARIAT')
        corps = self.client_api.get('/api/edts/lmd/audit/').json()
        self.assertTrue(corps['generable'])
        self.assertNotEqual(corps['statut'], 'BLOCKING')

    def test_audit_refuse_une_formation_hors_perimetre_injs(self):
        """Un cycle legacy ne doit jamais être accepté comme formation INJS."""
        legacy = FabriqueLMD(self).creer_base(perimetre='LEGACY', filiere='',
                                             suffixe='-LEG')
        legacy.creer_maquette()
        self.connecter('SECRETARIAT')
        r = self.client_api.get(
            f'/api/edts/lmd/audit/?ref_formation_id={legacy.cycle.pk}')
        codes = {c['code'] for c in r.json()['controles']}
        self.assertIn('CHAINE_LMD_INCOHERENTE', codes)


class TestRessourcesLMD(BaseLMD):
    """Disponibilités (modèle LOT 1) et canevas — aucune donnée inventée."""

    def setUp(self):
        super().setUp()
        self.connecter('SECRETARIAT')

    def test_disponibilites_absentes_sont_un_warning_explicite(self):
        for url in ('/api/edts/lmd/availability/teachers/',
                    '/api/edts/lmd/availability/rooms/'):
            with self.subTest(url=url):
                corps = self.client_api.get(url).json()
                self.assertEqual(corps['statut'], 'WARNING')
                self.assertEqual(corps['code'], 'AUCUNE_DISPONIBILITE')
                self.assertIn('explication', corps)
                self.assertIn('action_recommandee', corps)

    def test_disponibilites_enseignant_et_salle(self):
        from edts.models import DisponibiliteHoraire

        DisponibiliteHoraire.objects.create(
            annee_academique=self.f.annee, enseignant=self.f.formateur,
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
            statut='INDISPONIBLE', motif='Réunion')
        DisponibiliteHoraire.objects.create(
            annee_academique=self.f.annee, salle=self.salle,
            jour='MARDI', heure_debut=time(10, 0), heure_fin=time(12, 0),
            statut='PREFERENCE', motif='Préférence')
        prof = self.client_api.get('/api/edts/lmd/availability/teachers/').json()
        self.assertEqual(prof['statut'], 'OK')
        self.assertEqual(prof['nb_indisponibilites'], 1)
        self.assertTrue(prof['disponibilites'][0]['bloquant'])
        salles = self.client_api.get('/api/edts/lmd/availability/rooms/').json()
        self.assertEqual(salles['nb_indisponibilites'], 0,
                         'Une PREFERENCE n’est pas une indisponibilité bloquante.')

    def test_canevas_vide_remonte_le_motif_explicite(self):
        corps = self.client_api.get('/api/edts/lmd/slots/').json()
        self.assertEqual(corps['statut'], 'BLOCKING')
        self.assertEqual(corps['motif_echec'], 'CANEVAS_HORAIRE_VIDE')
        self.assertIn('Configurer les créneaux horaires',
                      corps['action_recommandee'])

    def test_canevas_expose_les_creneaux_reels(self):
        self.f.creer_creneaux(jours=('LUNDI',), heures=((8, 10), (10, 12)))
        corps = self.client_api.get('/api/edts/lmd/slots/').json()
        self.assertEqual(corps['statut'], 'OK')
        self.assertEqual(corps['nb_creneaux'], 2)
        self.assertEqual(corps['creneaux'][0]['jour_libelle'], 'Lundi')

    def test_contraintes_separe_dures_et_preferences(self):
        """Les dures C1→C10 sont exposées ; une préférence n'est jamais dure."""
        corps = self.client_api.get('/api/edts/lmd/constraints/').json()
        codes = [c['code'] for c in corps['dures']]
        for attendu in ('C1', 'C2', 'C3', 'C4', 'C5',
                        'C6', 'C7', 'C8', 'C9', 'C10'):
            self.assertTrue(any(code.startswith(attendu) for code in codes),
                            f'La contrainte {attendu} doit être exposée.')
        self.assertNotIn('PREFERENCE', [c['code'] for c in corps['dures']],
                         'Une préférence ne doit pas être une contrainte dure.')


class TestGenerationLMD(BaseLMD):
    """La route LMD appelle le moteur LOT 2 et materialise le plan."""

    def setUp(self):
        super().setUp()
        self.connecter('SECRETARIAT')

    def test_generation_avec_persistance_et_tracabilite(self):
        edt, reponse = self.generer_et_persister()
        self.assertEqual(reponse.status_code, 201, reponse.content)
        corps = reponse.json()
        self.assertTrue(corps['persiste'])
        self.assertEqual(corps['status'], G.GENERATION_OK)
        self.assertEqual(corps['creneaux_generes'], 1)
        self.assertEqual(corps['nb_besoins'], 1)
        # La séance persistée pointe bien vers son affectation pédagogique.
        seance = edt.affectations.filter(actif=True).first()
        self.assertIsNotNone(seance)
        self.assertIsNotNone(seance.affectation_pedagogique_id)
        self.assertEqual(corps['affectation_pedagogique_ids'],
                         [seance.affectation_pedagogique_id])

    def test_generation_sans_persister_n_ecrit_rien(self):
        """Le moteur propose un plan qu'il n'écrit pas par défaut."""
        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        reponse = self.client_api.post(
            '/api/edts/lmd/generate/', self.parametres_generation(), format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.json()['persiste'])
        self.assertEqual(EmploiDuTemps.objects.count(), 0)

    def test_generation_bloquee_par_absence_daffectations(self):
        self.f.creer_creneaux(heures=((8, 10),))
        r = self.client_api.post('/api/edts/lmd/generate/',
                                 self.parametres_generation(), format='json')
        self.assertEqual(r.status_code, 409)
        corps = r.json()
        self.assertEqual(corps['motif_echec'], 'AFFECTATIONS_PEDAGOGIQUES_VIDES')
        self.assertIn('action_recommandee', corps['detail'])

    def test_generation_refuse_une_formation_hors_perimetre_injs(self):
        legacy = FabriqueLMD(self).creer_base(perimetre='LEGACY', filiere='',
                                             suffixe='-LEG')
        legacy.creer_maquette()
        self.f.creer_creneaux(heures=((8, 10),))
        params = self.parametres_generation(ref_formation_id=legacy.cycle.pk)
        r = self.client_api.post('/api/edts/lmd/generate/', params, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['motif_echec'], 'CHAINE_LMD_INCOHERENTE')

    def test_generation_refuse_un_groupe_hors_formation(self):
        """Aucun dropdown ne doit proposer de valeur incohérente."""
        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        autre = FabriqueLMD(self).creer_base(suffixe='-ALT').creer_groupe(nom='G-ALT')
        params = self.parametres_generation(groupe_ids=str(autre.pk))
        r = self.client_api.post('/api/edts/lmd/generate/', params, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['motif_echec'], 'CHAINE_LMD_INCOHERENTE')

    def test_persister_exige_un_edt_connu(self):
        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self.client_api.post(
            '/api/edts/lmd/generate/',
            self.parametres_generation(emploi_du_temps_id=999999, persister='1'),
            format='json')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['motif_echec'], 'EDT_INTROUVABLE')

    def test_generation_refuse_un_edt_publie(self):
        edt = self.creer_edt(statut='PUBLIE')
        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self.client_api.post(
            '/api/edts/lmd/generate/',
            self.parametres_generation(emploi_du_temps_id=edt.pk, persister='1'),
            format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['motif_echec'], 'STATUT_EDT_INVALIDE')




class TestValiderPublierLMD(BaseLMD):
    """Validation avant publication ; refus si violation bloquante."""

    def test_valider_un_edt_genere_par_le_moteur(self):
        self.connecter('DIRECTION', nom='dir_val')
        edt, _gen = self._generer_comme_planificateur()
        r = self.client_api.post(f'/api/edts/lmd/{edt.pk}/validate/')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertTrue(corps['valide'], corps)
        self.assertEqual(corps['statut_edt'], 'VALIDE')
        edt.refresh_from_db()
        self.assertEqual(edt.statut, 'VALIDE')
        self.assertEqual(edt.valide_par.username, 'dir_gen')

    def test_valider_refuse_en_presence_de_violations(self):
        """Deux séances en conflit (C2) → validation refusée, statut conservé."""
        self.connecter('DIRECTION')
        edt, _gen = self._generer_comme_planificateur()
        creneau = CreneauTemplate.objects.order_by('jour', 'heure_debut').first()
        affectation_conf = self.f.creer_affectation(volume=2, groupe=self.groupe)
        AffectationCreneau.objects.create(
            emploi_du_temps=edt, creneau_template=creneau, semaine_debut=1,
            semaine_fin=1, salle=self.salle, salle_nom=self.salle.nom,
            formation=self.f.cycle, groupe=self.groupe,
            affectation_pedagogique=affectation_conf,
            nature='COURS', intitule='Doublon', actif=True)
        r = self.client_api.post(f'/api/edts/lmd/{edt.pk}/validate/')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertFalse(corps['valide'])
        self.assertTrue(corps['violations'])
        edt.refresh_from_db()
        self.assertNotEqual(edt.statut, 'VALIDE')

    def test_publier_est_idempotent_et_versionne(self):
        self.connecter('DIRECTION')
        edt, _gen = self._generer_comme_planificateur()
        r1 = self.client_api.post(f'/api/edts/lmd/{edt.pk}/validate/')
        self.assertTrue(r1.json()['valide'], r1.content)
        p1 = self.client_api.post(f'/api/edts/lmd/{edt.pk}/publish/')
        self.assertEqual(p1.status_code, 200, p1.content)
        self.assertTrue(p1.json()['publie'])
        version = p1.json().get('version', edt.version)
        # Republication : refus explicite EDT_DEJA_PUBLIE, pas de doublon.
        p2 = self.client_api.post(f'/api/edts/lmd/{edt.pk}/publish/')
        self.assertEqual(p2.status_code, 409)
        self.assertEqual(p2.json()['motif_echec'], 'EDT_DEJA_PUBLIE')
        # Conflit de version : l'EDT a changé depuis le chargement.
        p3 = self.client_api.post(
            f'/api/edts/lmd/{edt.pk}/publish/', {'version': version + 99})
        self.assertEqual(p3.status_code, 409)
        self.assertEqual(p3.json()['motif_echec'], 'VERSION_EDT_MODIFIEE')

    def test_publier_un_edt_vide_est_refuse(self):
        self.connecter('DIRECTION')
        edt = self.creer_edt()
        p = self.client_api.post(f'/api/edts/lmd/{edt.pk}/publish/')
        self.assertEqual(p.status_code, 409)
        self.assertEqual(p.json()['motif_echec'], 'AUCUNE_AFFECTATION_A_PUBLIER')

    def _generer_comme_planificateur(self):
        """Génère avec un compte planification, puis ré-authentifie en DIRECTION."""
        secretaire = creer_utilisateur('plan_gen', 'SECRETARIAT')
        self.client_api.force_authenticate(user=secretaire)
        edt, reponse = self.generer_et_persister()
        self.assertEqual(reponse.status_code, 201, reponse.content)
        direction = creer_utilisateur('dir_gen', 'DIRECTION')
        self.client_api.force_authenticate(user=direction)
        return edt, reponse


from edts.models import AffectationCreneau  # noqa: E402 — après les classes


class TestDeplacerAnnulerLMD(BaseLMD):
    """Tout déplacement passe par une revalidation C1→C10."""

    def test_deplacer_vers_un_creneau_compatible_est_accepte(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        seance = edt.affectations.filter(actif=True).first()
        creneaux = list(CreneauTemplate.objects.order_by('jour', 'heure_debut'))
        libres = [c for c in creneaux if c.pk != seance.creneau_template_id]
        self.assertTrue(libres, 'Il faut au moins un créneau alternatif.')
        r = self.client_api.post(
            f'/api/edts/lmd/items/{seance.pk}/move/',
            {'creneau_template_id': libres[0].pk})
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertTrue(corps['accepted'], corps)
        seance.refresh_from_db()
        self.assertEqual(seance.creneau_template_id, libres[0].pk)

    def test_deplacer_en_conflit_est_refuse_sans_ecriture(self):
        """Même créneau et mêmes semaines pour le même groupe → violation C2."""
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        base = edt.affectations.filter(actif=True).first()
        cible_aff = self.f.creer_affectation(volume=2, groupe=self.groupe)
        cible = AffectationCreneau.objects.create(
            emploi_du_temps=edt, creneau_template=base.creneau_template,
            semaine_debut=base.semaine_debut, semaine_fin=base.semaine_fin,
            salle=None, salle_nom='', formation=self.f.cycle,
            groupe=self.groupe, affectation_pedagogique=cible_aff,
            nature='COURS', intitule='Cible', actif=True)
        avant = (cible.creneau_template_id, cible.salle_id)
        r = self.client_api.post(
            f'/api/edts/lmd/items/{cible.pk}/move/',
            {'creneau_template_id': base.creneau_template_id})
        self.assertEqual(r.status_code, 409, r.content)
        self.assertFalse(r.json()['accepted'])
        self.assertTrue(r.json()['violations'])
        cible.refresh_from_db()
        self.assertEqual((cible.creneau_template_id, cible.salle_id), avant)

    def test_move_get_propose_des_creneaux_compatibles(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        seance = edt.affectations.filter(actif=True).first()
        r = self.client_api.get(f'/api/edts/lmd/items/{seance.pk}/move/')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertIn('candidats', corps)
        self.assertGreaterEqual(corps['nb_candidats'], 0)

    def test_annuler_est_tracable_reversible_et_non_destructif(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        seance = edt.affectations.filter(actif=True).first()
        r = self.client_api.post(
            f'/api/edts/lmd/items/{seance.pk}/cancel/', {'motif': 'Salle fermée'})
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertTrue(corps['annulee'])
        self.assertTrue(corps['reversible'])
        self.assertEqual(corps['motif'], 'Salle fermée')
        seance.refresh_from_db()
        self.assertFalse(seance.actif)
        # L'historique est conservé : aucune suppression physique.
        self.assertTrue(
            AffectationCreneau.objects.filter(pk=seance.pk).exists())
        # Réactivation avec motif : l'opération est réversible.
        r2 = self.client_api.post(
            f'/api/edts/lmd/items/{seance.pk}/cancel/',
            {'motif': 'Salle rouverte', 'reactiver': '1'})
        self.assertEqual(r2.status_code, 200, r2.content)
        seance.refresh_from_db()
        self.assertTrue(seance.actif)

    def test_annuler_sans_motif_est_refuse(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        seance = edt.affectations.filter(actif=True).first()
        r = self.client_api.post(f'/api/edts/lmd/items/{seance.pk}/cancel/', {})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['motif_echec'], 'MOTIF_ANNULATION_REQUIS')


class TestResultatGrilleVersionsLMD(BaseLMD):
    """Restitution filtrable, grilles réutilisées, versions jamais écrasées."""

    def test_result_filtre_et_trace_vers_affectation_pedagogique(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        r = self.client_api.get(f'/api/edts/lmd/{edt.pk}/result/')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertEqual(corps['version'], edt.version)
        self.assertGreaterEqual(corps['nb_seances'], 1)
        ligne = corps['seances'][0]
        for cle in ('jour', 'heure_debut', 'formation', 'groupe', 'enseignant',
                    'salle', 'nature', 'affectation_pedagogique_id'):
            self.assertIn(cle, ligne)
        self.assertIsNotNone(ligne['affectation_pedagogique_id'])
        # Filtres serveur : groupe inexistant → aucune séance.
        r2 = self.client_api.get(
            f'/api/edts/lmd/{edt.pk}/result/?groupe_id=999999')
        self.assertEqual(r2.json()['nb_seances'], 0)

    def test_grille_reutilise_la_logique_existante(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        for vue in ('groupe', 'enseignant', 'salle', 'formation', 'semaine'):
            with self.subTest(vue=vue):
                r = self.client_api.get(
                    f'/api/edts/lmd/{edt.pk}/grille/?vue={vue}')
                self.assertEqual(r.status_code, 200, r.content)
                self.assertIn('grille', r.json())
        r = self.client_api.get(f'/api/edts/lmd/{edt.pk}/grille/?vue=inconnue')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['motif_echec'], 'VUE_INCONNUE')

    def test_versions_expose_l_historique_sans_ecrasement(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        r = self.client_api.get('/api/edts/lmd/versions/')
        self.assertEqual(r.status_code, 200, r.content)
        versions = [v for v in r.json()['versions'] if v['id'] == edt.pk]
        self.assertEqual(len(versions), 1)
        v = versions[0]
        for cle in ('libelle', 'statut', 'creee_le', 'motif_modification',
                    'nb_seances'):
            self.assertIn(cle, v)

    def test_edt_audit_expose_la_validation_d_un_edt_existant(self):
        self.connecter('SECRETARIAT')
        edt, _gen = self.generer_et_persister()
        r = self.client_api.get(f'/api/edts/lmd/{edt.pk}/audit/')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertIn('valide', corps)
        self.assertEqual(corps['emploi_du_temps_id'], edt.pk)


class TestSecuriteLMD(BaseLMD):
    """Le RBAC existant s'applique — aucun second système n'est créé."""

    def test_lecture_ouverte_a_tout_authentifie(self):
        self.connecter('AUDITEUR')
        self.assertEqual(
            self.client_api.get('/api/edts/lmd/constraints/').status_code, 200)
        self.assertEqual(
            self.client_api.get('/api/edts/lmd/slots/').status_code, 200)

    def test_generation_refusee_hors_planification(self):
        self.connecter('AUDITEUR')
        r = self.client_api.post('/api/edts/lmd/generate/', {}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_validation_refusee_hors_direction(self):
        self.connecter('SECRETARIAT')
        edt = self.creer_edt()
        r = self.client_api.post(f'/api/edts/lmd/{edt.pk}/validate/')
        self.assertEqual(r.status_code, 403)
        r2 = self.client_api.post(f'/api/edts/lmd/{edt.pk}/publish/')
        self.assertEqual(r2.status_code, 403)

    def test_anonyme_refuse_partout(self):
        for methode, url in (
                ('get', '/api/edts/lmd/audit/'),
                ('get', '/api/edts/lmd/slots/'),
                ('post', '/api/edts/lmd/generate/')):
            with self.subTest(url=url):
                appel = getattr(self.client_api, methode)
                kwargs = {'format': 'json'} if methode == 'post' else {}
                self.assertIn(appel(url, **kwargs).status_code, (401, 403))


class TestRegressionGenerateurHistorique(BaseLMD):
    """`POST /api/edts/emplois/{id}/generer/` (`generer_brouillon`) est intact."""

    def test_le_generateur_historique_fonctionne_toujours(self):
        self.connecter('SECRETARIAT')
        edt = self.creer_edt()
        self.f.creer_creneaux(heures=((8, 10),))
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        r = self.client_api.post(f'/api/edts/emplois/{edt.pk}/generer/')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertIn('seances_placees', corps)

    def test_le_generateur_historique_refuse_un_edt_non_brouillon(self):
        self.connecter('SECRETARIAT')
        edt = self.creer_edt(statut='VALIDE')
        r = self.client_api.post(f'/api/edts/emplois/{edt.pk}/generer/')
        self.assertEqual(r.status_code, 409)
