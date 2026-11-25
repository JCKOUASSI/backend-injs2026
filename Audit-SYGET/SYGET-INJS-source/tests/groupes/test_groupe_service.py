"""
Tests du service de gestion des groupes.
"""

import pytest

from apps.formations.models import FormationModule
from apps.auditeurs.models import Auditeur
from apps.formations.models import Inscription
from apps.groupes.repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository
from apps.groupes.services import GroupeService
from apps.seances.models import Seance


@pytest.mark.django_db
class TestGroupeService:
    """Vérifie les règles métier de gestion des groupes."""

    def _service(self):
        return GroupeService(
            repo=GroupeRepository(),
            config_repo=ConfigGroupeRepository(),
            jours_repo=JourCoursRepository(),
        )

    def _module_formation(self, formation):
        from apps.referentiels.models import Module, Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module = Module.objects.create(titre=f"Module test {formation.pk}", specialite=spec)
        return FormationModule.objects.create(
            formation=formation,
            module=module,
            volume_horaire=20,
            site_nom=f"SITE-{formation.pk}",
        )

    def _prepare_planning_prereqs(self, formation, parametres):
        """Configure jours + au moins une salle active pour permettre la génération de séances."""
        from apps.parametrage.models import Batiment, Salle, Site

        parametres.jours_defaut = [0, 1, 2, 3, 4]
        parametres.save(update_fields=["jours_defaut"])

        site = Site.objects.create(nom=f"SITE-{formation.pk}", actif=True)
        bat = Batiment.objects.create(site=site, nom=f"BAT-{formation.pk}", actif=True)
        Salle.objects.create(
            batiment=bat,
            nom=f"SALLE-{formation.pk}",
            capacite_max=40,
            actif=True,
        )

    def test_creer_groupe(self, formation, parametres):
        """Un groupe est créé et sa configuration initialisée."""
        groupe = self._service().creer(
            formation_id=formation.pk,
            nom="Groupe A",
            max_auditeurs=20,
        )
        assert groupe.pk is not None
        assert groupe.nom == "Groupe A"
        assert groupe.max_auditeurs == 20
        assert hasattr(groupe, "config")

    def test_nom_duplique_leve_erreur(self, formation, parametres):
        """Deux groupes portant le même nom dans la même formation levent ValueError."""
        svc = self._service()
        svc.creer(formation_id=formation.pk, nom="Groupe B")
        with pytest.raises(ValueError, match="existe déjà"):
            svc.creer(formation_id=formation.pk, nom="Groupe B")

    def test_ajouter_auditeur(self, formation, auditeur, parametres):
        """Un auditeur peut être ajouté à un groupe."""
        groupe = self._service().creer(formation_id=formation.pk, nom="Groupe C")
        ga = self._service().ajouter_auditeur(groupe.pk, auditeur.pk)
        assert ga.pk is not None
        assert ga.auditeur == auditeur

    def test_double_ajout_auditeur_leve_erreur(self, formation, auditeur, parametres):
        """Ajouter le même auditeur deux fois lève ValueError."""
        svc = self._service()
        groupe = svc.creer(formation_id=formation.pk, nom="Groupe D")
        svc.ajouter_auditeur(groupe.pk, auditeur.pk)
        with pytest.raises(ValueError, match="déjà dans ce groupe"):
            svc.ajouter_auditeur(groupe.pk, auditeur.pk)

    def test_capacite_max_leve_erreur(self, formation, auditeur, auditeur2, parametres):
        """Ajouter un auditeur à un groupe plein lève ValueError."""
        svc = self._service()
        groupe = svc.creer(formation_id=formation.pk, nom="Groupe E", max_auditeurs=1)
        svc.ajouter_auditeur(groupe.pk, auditeur.pk)
        with pytest.raises(ValueError, match="capacité maximale"):
            svc.ajouter_auditeur(groupe.pk, auditeur2.pk)

    def test_nb_auditeurs_propriete(self, formation, auditeur, auditeur2, parametres):
        """La propriété nb_auditeurs reflète les membres réels."""
        svc = self._service()
        groupe = svc.creer(formation_id=formation.pk, nom="Groupe F")
        assert groupe.nb_auditeurs == 0
        svc.ajouter_auditeur(groupe.pk, auditeur.pk)
        svc.ajouter_auditeur(groupe.pk, auditeur2.pk)
        groupe.refresh_from_db()
        assert groupe.nb_auditeurs == 2

    def test_generation_auto_par_grade(self, formation, auditeur, auditeur2, parametres):
        """Les groupes automatiques distinguent les auditeurs par grade."""
        self._prepare_planning_prereqs(formation, parametres)
        fm = self._module_formation(formation)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur2)

        nb = self._service().generer_automatiquement_par_grade(formation.pk)
        groupes = self._service().list_par_formation(formation.pk)

        assert nb == 2
        assert len(groupes) == 2
        assert any(g.nom == "A2_GROUPE1" for g in groupes)
        assert any(g.nom == "A3_GROUPE1" for g in groupes)
        assert all(g.nb_auditeurs == 1 for g in groupes)

    def test_generation_auto_cree_affectations_formateur(
        self, formation, auditeur, auditeur2, parametres, formateur_general_planning
    ):
        """La génération auto crée des affectations groupe/module/formateur pour le planning."""
        from apps.formations.models import AffectationFormateurGroupe

        self._prepare_planning_prereqs(formation, parametres)
        fm = self._module_formation(formation)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur2)

        self._service().generer_automatiquement_par_grade(formation.pk)
        groupes = self._service().list_par_formation(formation.pk)

        for g in groupes:
            aff = AffectationFormateurGroupe.objects.filter(groupe=g, module_id=fm.module_id)
            assert aff.count() == 1
            assert aff.first().formateur_id == formateur_general_planning.pk

    def test_generation_auto_affecte_formateur_repli_si_specialite_module_sans_formateur(
        self, formation, auditeur, parametres, formateur_general_planning
    ):
        """Sans formateur pour la spécialité du module, on retombe sur GENERAL puis le planning reçoit un formateur."""
        from apps.formations.models import AffectationFormateurGroupe
        from apps.referentiels.models import Module, Specialite

        self._prepare_planning_prereqs(formation, parametres)
        spec_droit = Specialite.objects.create(code="DROIT_TEST", libelle="Droit test")
        module = Module.objects.create(titre="Module droit test", specialite=spec_droit)
        fm = FormationModule.objects.create(
            formation=formation,
            module=module,
            volume_horaire=8,
            site_nom=f"SITE-{formation.pk}",
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)

        self._service().generer_automatiquement_par_grade(formation.pk)
        groupe = self._service().list_par_formation(formation.pk)[0]
        aff = AffectationFormateurGroupe.objects.filter(groupe=groupe, module_id=module.pk)
        assert aff.count() == 1
        assert aff.first().formateur_id == formateur_general_planning.pk
        assert Seance.objects.filter(groupe=groupe).exists()
        assert Seance.objects.filter(groupe=groupe, formateur_nom="POOL").exists()

    def test_affectation_auto_formateur_eligible_si_libelle_specialite_egal_titre_module(
        self, formation, auditeur, parametres
    ):
        """Le formateur peut être choisi via une spécialité dont le libellé = titre du module (FK autre)."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.referentiels.models import Module, Specialite

        spec_gen = Specialite.objects.get(code="GENERAL")
        titre_unique = f"Module aligné titre {formation.pk}"
        spec_par_libelle = Specialite.objects.create(code=f"SPEC_TITRE_{formation.pk}", libelle=titre_unique)
        module = Module.objects.create(titre=titre_unique, specialite=spec_gen)
        fm = FormationModule.objects.create(
            formation=formation,
            module=module,
            volume_horaire=8,
            site_nom=f"SITE-{formation.pk}",
        )
        f = Formateur.objects.create(
            numero=f"+2250999888{formation.pk:04d}",
            nom="AAA",
            prenom="Titre",
            email="pt@t.ci",
            telephone="",
            organisation="T",
        )
        f.specialites.add(spec_par_libelle)
        Inscription.objects.create(
            formation=formation,
            formation_module=fm,
            auditeur=auditeur,
        )
        g = self._service().creer(formation_id=formation.pk, nom="G align titre", max_auditeurs=25)
        n = self._service()._affecter_formateurs_manquants_pour_formation(formation.pk)
        assert n >= 1
        aff = AffectationFormateurGroupe.objects.get(groupe=g, module_id=module.pk)
        assert aff.formateur_id == f.pk

    def test_meme_formateur_peut_couvrir_plusieurs_modules_meme_groupe_si_specialite(self, formation, parametres):
        """Affectation auto : mono-spécialité → au plus un module par groupe ; ici un seul créé."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.referentiels.models import Module, Specialite

        spec_x = Specialite.objects.create(code="SPEC_MULTI_MOD", libelle="Spé multi modules")
        m1 = Module.objects.create(titre="Mod A", specialite=spec_x)
        m2 = Module.objects.create(titre="Mod B", specialite=spec_x)
        FormationModule.objects.create(
            formation=formation,
            module=m1,
            volume_horaire=4,
            site_nom=f"SITE-{formation.pk}",
        )
        FormationModule.objects.create(
            formation=formation,
            module=m2,
            volume_horaire=4,
            site_nom=f"SITE-{formation.pk}",
        )
        g = self._service().creer(formation_id=formation.pk, nom="G multi mod", max_auditeurs=25)
        f_only = Formateur.objects.create(
            numero="+2250999777001",
            nom="SEUL",
            prenom="Un",
            email="s@t.ci",
            telephone="",
            organisation="T",
        )
        f_only.specialites.add(spec_x)
        n = self._service()._affecter_formateurs_manquants_pour_formation(formation.pk)
        assert n == 1
        aff = AffectationFormateurGroupe.objects.filter(groupe=g)
        assert aff.count() == 1
        assert aff.first().formateur_id == f_only.pk
        assert aff.first().module_id in {m1.pk, m2.pk}

    def test_formateur_multi_specialites_meme_groupe_deux_modules_distincts(self, formation, parametres):
        """Deux spécialités : jusqu'à deux modules sur le même groupe ici (un par spécialité)."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.referentiels.models import Module, Specialite

        s1 = Specialite.objects.create(code="SPEC_MS_A", libelle="S A ms")
        s2 = Specialite.objects.create(code="SPEC_MS_B", libelle="S B ms")
        m1 = Module.objects.create(titre="Mod ms A", specialite=s1)
        m2 = Module.objects.create(titre="Mod ms B", specialite=s2)
        FormationModule.objects.create(
            formation=formation,
            module=m1,
            volume_horaire=4,
            site_nom=f"SITE-{formation.pk}",
        )
        FormationModule.objects.create(
            formation=formation,
            module=m2,
            volume_horaire=4,
            site_nom=f"SITE-{formation.pk}",
        )
        g = self._service().creer(formation_id=formation.pk, nom="G ms", max_auditeurs=25)
        f_multi = Formateur.objects.create(
            numero="+2250999555001",
            nom="DOUBLE",
            prenom="Spec",
            email="d@t.ci",
            telephone="",
            organisation="T",
        )
        f_multi.specialites.add(s1, s2)
        n = self._service()._affecter_formateurs_manquants_pour_formation(formation.pk)
        assert n == 2
        aff = AffectationFormateurGroupe.objects.filter(groupe=g).order_by("module_id")
        assert all(a.formateur_id == f_multi.pk for a in aff)
        assert {a.module_id for a in aff} == {m1.pk, m2.pk}

    def test_deux_specialites_plafond_deux_modules_par_groupe(self, formation, parametres):
        """2 spécialités sur F → au plus 2 modules sur le même groupe ; le 3e va à un autre éligible."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.referentiels.models import Module, Specialite

        s1 = Specialite.objects.create(code="SPEC_CAP_A", libelle="S A cap")
        s2 = Specialite.objects.create(code="SPEC_CAP_B", libelle="S B cap")
        m1 = Module.objects.create(titre="Mod cap 1", specialite=s1)
        m2 = Module.objects.create(titre="Mod cap 2", specialite=s1)
        m3 = Module.objects.create(titre="Mod cap 3", specialite=s2)
        FormationModule.objects.create(formation=formation, module=m1, volume_horaire=4, site_nom=f"S-{formation.pk}")
        FormationModule.objects.create(formation=formation, module=m2, volume_horaire=4, site_nom=f"S-{formation.pk}")
        FormationModule.objects.create(formation=formation, module=m3, volume_horaire=4, site_nom=f"S-{formation.pk}")
        g = self._service().creer(formation_id=formation.pk, nom="G cap", max_auditeurs=25)
        f_multi = Formateur.objects.create(
            numero="+2250999444001",
            nom="CAP2",
            prenom="Deux",
            email="c2@t.ci",
            telephone="",
            organisation="T",
        )
        f_multi.specialites.add(s1, s2)
        f_s2 = Formateur.objects.create(
            numero="+2250999444002",
            nom="SEULS2",
            prenom="S2",
            email="s2@t.ci",
            telephone="",
            organisation="T",
        )
        f_s2.specialites.add(s2)
        n = self._service()._affecter_formateurs_manquants_pour_formation(formation.pk)
        assert n == 3
        by_mid = {
            a.module_id: a.formateur_id
            for a in AffectationFormateurGroupe.objects.filter(groupe=g, module_id__in=[m1.pk, m2.pk, m3.pk])
        }
        assert by_mid[m1.pk] == f_multi.pk
        assert by_mid[m2.pk] == f_multi.pk
        assert by_mid[m3.pk] == f_s2.pk

    def test_meme_module_round_robin_formateurs_meme_specialite(self, formation, parametres):
        """Plusieurs formateurs pour la spécialité du module : un groupe chacun, puis reprise cyclique."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.referentiels.models import Module, Specialite

        spec = Specialite.objects.create(code="SPEC_UN_MOD", libelle="Spé un module")
        m = Module.objects.create(titre="Mod unique", specialite=spec)
        FormationModule.objects.create(
            formation=formation,
            module=m,
            volume_horaire=4,
            site_nom=f"SITE-{formation.pk}",
        )
        g1 = self._service().creer(formation_id=formation.pk, nom="G1", max_auditeurs=25)
        g2 = self._service().creer(formation_id=formation.pk, nom="G2", max_auditeurs=25)
        g3 = self._service().creer(formation_id=formation.pk, nom="G3", max_auditeurs=25)
        fa = Formateur.objects.create(
            numero="+2250999778001",
            nom="AAA",
            prenom="Un",
            email="a@t.ci",
            telephone="",
            organisation="T",
        )
        fb = Formateur.objects.create(
            numero="+2250999778002",
            nom="ZZZ",
            prenom="Deux",
            email="z@t.ci",
            telephone="",
            organisation="T",
        )
        fa.specialites.add(spec)
        fb.specialites.add(spec)
        n = self._service()._affecter_formateurs_manquants_pour_formation(formation.pk)
        assert n == 3
        by_g = {
            a.groupe_id: a.formateur_id
            for a in AffectationFormateurGroupe.objects.filter(module=m, groupe_id__in=[g1.pk, g2.pk, g3.pk])
        }
        assert by_g[g1.pk] == fa.pk
        assert by_g[g2.pk] == fb.pk
        assert by_g[g3.pk] == fa.pk

    def test_un_formateur_par_groupe_par_specialite_deux_modules(self, formation, parametres):
        """Mono sur M1 en base : le second module même spécialité va à un autre éligible, pas au même mono."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.referentiels.models import Module, Specialite

        spec = Specialite.objects.create(code="SPEC_DUP_MOD", libelle="Spé deux modules")
        m1 = Module.objects.create(titre="Mod A dup", specialite=spec)
        m2 = Module.objects.create(titre="Mod B dup", specialite=spec)
        FormationModule.objects.create(
            formation=formation,
            module=m1,
            volume_horaire=4,
            site_nom=f"S-{formation.pk}",
        )
        FormationModule.objects.create(
            formation=formation,
            module=m2,
            volume_horaire=4,
            site_nom=f"S-{formation.pk}",
        )
        g1 = self._service().creer(formation_id=formation.pk, nom="G uniq", max_auditeurs=25)
        fa = Formateur.objects.create(
            numero="+2250999666001",
            nom="AAA",
            prenom="Un",
            email="a@t.ci",
            telephone="",
            organisation="T",
        )
        fb = Formateur.objects.create(
            numero="+2250999666002",
            nom="ZZZ",
            prenom="Deux",
            email="z@t.ci",
            telephone="",
            organisation="T",
        )
        fa.specialites.add(spec)
        fb.specialites.add(spec)
        AffectationFormateurGroupe.objects.create(groupe=g1, module=m1, formateur=fb)

        n = self._service()._affecter_formateurs_manquants_pour_formation(formation.pk)
        assert n == 1
        ids = set(
            AffectationFormateurGroupe.objects.filter(groupe=g1, module_id__in=[m1.pk, m2.pk]).values_list(
                "formateur_id", flat=True
            )
        )
        assert ids == {fa.pk, fb.pk}

    def test_un_auditeur_ne_peut_pas_etre_dans_deux_groupes_de_la_meme_formation(self, formation, auditeur, parametres):
        """Un auditeur est limité à un seul groupe par formation."""
        svc = self._service()
        groupe_a = svc.creer(formation_id=formation.pk, nom="Groupe A")
        groupe_b = svc.creer(formation_id=formation.pk, nom="Groupe B")
        svc.ajouter_auditeur(groupe_a.pk, auditeur.pk)

        with pytest.raises(ValueError, match="autre groupe de cette formation"):
            svc.ajouter_auditeur(groupe_b.pk, auditeur.pk)

    def test_generation_auto_split_si_capacite_depassee(self, formation, auditeur, parametres):
        """Un grade peut être réparti sur plusieurs groupes selon la capacité paramétrée."""
        self._prepare_planning_prereqs(formation, parametres)
        # Capacité volontairement basse pour forcer le split.
        parametres.max_auditeurs_groupe_defaut = 2
        parametres.save(update_fields=["max_auditeurs_groupe_defaut"])

        a3_2 = Auditeur.objects.create(
            nom="KOUASSI",
            prenom="Paul",
            matricule="KOUP0001",
            grade="A3",
            genre="M",
            categorie="A",
        )
        a3_3 = Auditeur.objects.create(
            nom="KOFFI",
            prenom="Marie",
            matricule="KOFM0001",
            grade="A3",
            genre="F",
            categorie="A",
        )

        fm = self._module_formation(formation)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=a3_2)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=a3_3)

        nb = self._service().generer_automatiquement_par_grade(formation.pk)
        groupes = self._service().list_par_formation(formation.pk)

        assert nb == 2
        assert len(groupes) == 2
        assert sorted(g.nb_auditeurs for g in groupes) == [1, 2]
        assert any(g.nom == "A3_GROUPE1" for g in groupes)
        assert any(g.nom == "A3_GROUPE2" for g in groupes)

    def test_generation_auto_sans_mixage_grades_separe_par_grade(self, formation, parametres):
        """Sans mixage : un groupe par grade, noms avec suffixe grade."""
        self._prepare_planning_prereqs(formation, parametres)
        parametres.groupes_auto_mixage_grades = False
        parametres.save(update_fields=["groupes_auto_mixage_grades"])

        fm = self._module_formation(formation)
        aud_a3 = Auditeur.objects.create(
            nom="GRA", prenom="A3", matricule="GRA3001", grade="A3", genre="M", categorie="A"
        )
        aud_b = Auditeur.objects.create(nom="GRB", prenom="B", matricule="GRB0001", grade="B", genre="F", categorie="B")
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=aud_a3)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=aud_b)

        self._service().generer_automatiquement_par_grade(formation.pk, mixage_grades=False)
        noms = {g.nom for g in self._service().list_par_formation(formation.pk)}
        assert any("A3" in n for n in noms)
        assert any("B" in n for n in noms)
        assert not any(n.strip().endswith("Groupe 1") or n == "Groupe 1" for n in noms)

    def test_generation_auto_avec_mixage_grades_dans_meme_groupe(self, formation, parametres):
        """Avec mixage : groupes multi-grades par catégorie, jamais entre catégories."""
        self._prepare_planning_prereqs(formation, parametres)
        parametres.max_auditeurs_groupe_defaut = 2
        parametres.save(update_fields=["max_auditeurs_groupe_defaut"])

        fm = self._module_formation(formation)
        aud_a3_1 = Auditeur.objects.create(
            nom="MIX", prenom="A1", matricule="MIXA001", grade="A3", genre="M", categorie="A"
        )
        aud_a3_2 = Auditeur.objects.create(
            nom="MIX", prenom="A2", matricule="MIXA002", grade="A3", genre="F", categorie="A"
        )
        aud_b1 = Auditeur.objects.create(
            nom="MIX", prenom="B1", matricule="MIXB001", grade="B", genre="M", categorie="B"
        )
        aud_b2 = Auditeur.objects.create(
            nom="MIX", prenom="B2", matricule="MIXB002", grade="B", genre="F", categorie="B"
        )
        for aud in (aud_a3_1, aud_a3_2, aud_b1, aud_b2):
            Inscription.objects.create(formation=formation, formation_module=fm, auditeur=aud)

        nb = self._service().generer_automatiquement_par_grade(formation.pk, mixage_grades=True)
        groupes = list(self._service().list_par_formation(formation.pk))
        assert nb == 2
        assert {g.nom for g in groupes} == {"A_GROUPE1", "B_GROUPE1"}
        for g in groupes:
            categories = set(g.membres.values_list("auditeur__categorie", flat=True))
            if g.nom.startswith("A_"):
                assert categories == {"A"}
                assert sorted(g.membres.values_list("auditeur__grade", flat=True)) == ["A3", "A3"]
            else:
                assert categories == {"B"}
                assert sorted(g.membres.values_list("auditeur__grade", flat=True)) == ["B", "B"]

    def test_generation_auto_mixage_grades_melange_grades_meme_categorie(self, formation, parametres):
        """Avec mixage : A3 et A2 (catégorie A) peuvent partager un même groupe."""
        self._prepare_planning_prereqs(formation, parametres)
        parametres.max_auditeurs_groupe_defaut = 3
        parametres.save(update_fields=["max_auditeurs_groupe_defaut"])

        fm = self._module_formation(formation)
        aud_a3 = Auditeur.objects.create(
            nom="MIX", prenom="A3", matricule="MIXA003", grade="A3", genre="M", categorie="A"
        )
        aud_a2 = Auditeur.objects.create(
            nom="MIX", prenom="A2", matricule="MIXA004", grade="A2", genre="F", categorie="A"
        )
        aud_b = Auditeur.objects.create(nom="MIX", prenom="B", matricule="MIXB003", grade="B", genre="M", categorie="B")
        for aud in (aud_a3, aud_a2, aud_b):
            Inscription.objects.create(formation=formation, formation_module=fm, auditeur=aud)

        nb = self._service().generer_automatiquement_par_grade(formation.pk, mixage_grades=True)
        groupes = {g.nom: g for g in self._service().list_par_formation(formation.pk)}
        assert nb == 2
        assert set(groupes) == {"A_GROUPE1", "B_GROUPE1"}
        assert sorted(groupes["A_GROUPE1"].membres.values_list("auditeur__grade", flat=True)) == [
            "A2",
            "A3",
        ]
        assert list(groupes["B_GROUPE1"].membres.values_list("auditeur__grade", flat=True)) == ["B"]

    def test_generation_auto_mixe_type_concours_entre_groupes(self, formation, parametres):
        """La répartition automatique mélange autant que possible les types concours."""
        self._prepare_planning_prereqs(formation, parametres)
        parametres.max_auditeurs_groupe_defaut = 2
        parametres.save(update_fields=["max_auditeurs_groupe_defaut"])

        a3_a1 = Auditeur.objects.create(
            nom="ALPHA",
            prenom="Un",
            matricule="MIXA0001",
            grade="A3",
            genre="M",
            categorie="A",
            type_concours="A",
        )
        a3_a2 = Auditeur.objects.create(
            nom="BETA",
            prenom="Deux",
            matricule="MIXA0002",
            grade="A3",
            genre="F",
            categorie="A",
            type_concours="A",
        )
        a3_b1 = Auditeur.objects.create(
            nom="GAMMA",
            prenom="Trois",
            matricule="MIXB0001",
            grade="A3",
            genre="M",
            categorie="A",
            type_concours="B",
        )
        a3_b2 = Auditeur.objects.create(
            nom="DELTA",
            prenom="Quatre",
            matricule="MIXB0002",
            grade="A3",
            genre="F",
            categorie="A",
            type_concours="B",
        )

        fm = self._module_formation(formation)
        for aud in (a3_a1, a3_a2, a3_b1, a3_b2):
            Inscription.objects.create(formation=formation, formation_module=fm, auditeur=aud)

        nb = self._service().generer_automatiquement_par_grade(formation.pk)
        groupes = self._service().list_par_formation(formation.pk)

        assert nb == 2
        assert len(groupes) == 2
        assert all(g.nb_auditeurs == 2 for g in groupes)

        types_par_groupe = []
        for groupe in groupes:
            types_par_groupe.append(
                sorted(
                    groupe.membres.values_list("auditeur__type_concours", flat=True),
                )
            )
        assert all(types == ["A", "B"] for types in types_par_groupe)

    def test_generation_auto_ajoute_groupes_manquants_sans_reset(self, formation, parametres):
        """Avec des groupes existants, la génération ajoute les grades non encore affectés."""
        self._prepare_planning_prereqs(formation, parametres)

        fm = self._module_formation(formation)
        auditeur_a = Auditeur.objects.create(
            nom="AFO",
            prenom="Alpha",
            matricule="ADDG0001",
            grade="A3",
            genre="M",
            categorie="A",
        )
        auditeur_b = Auditeur.objects.create(
            nom="BLA",
            prenom="Bravo",
            matricule="ADDG0002",
            grade="B",
            genre="F",
            categorie="B",
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur_a)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur_b)

        nb1 = self._service().generer_automatiquement_par_grade(formation.pk)
        assert nb1 == 2

        # Simule l'arrivée tardive d'un nouveau grade B non affecté.
        auditeur_b2 = Auditeur.objects.create(
            nom="BONY",
            prenom="Charlie",
            matricule="ADDG0003",
            grade="B",
            genre="M",
            categorie="B",
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur_b2)

        nb2 = self._service().generer_automatiquement_par_grade(formation.pk)
        groupes = self._service().list_par_formation(formation.pk)

        assert nb2 == 1
        assert any(g.nom == "B_GROUPE2" for g in groupes)

    def test_generation_auto_cree_dabord_les_inscriptions_depuis_les_modules(
        self, formation, auditeur, auditeur2, parametres
    ):
        """Sans inscription préalable, la génération auto inscrit via grade_cible puis crée les groupes."""
        from apps.referentiels.models import Module

        self._prepare_planning_prereqs(formation, parametres)
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module_a3 = Module.objects.create(titre="Module A3", specialite=spec)
        module_a2 = Module.objects.create(titre="Module A2", specialite=spec)
        FormationModule.objects.create(
            formation=formation,
            module=module_a3,
            volume_horaire=12,
            grade_cible="A3",
            site_nom=f"SITE-{formation.pk}",
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_a2,
            volume_horaire=12,
            grade_cible="A2",
            site_nom=f"SITE-{formation.pk}",
        )

        assert Inscription.objects.filter(formation=formation).count() == 0

        nb = self._service().generer_automatiquement_par_grade(formation.pk)

        assert nb == 2
        assert Inscription.objects.filter(formation=formation).count() == 2

    def test_generation_auto_backfill_accepte_grade_parent(self, formation, parametres):
        """Un module ciblé sur B doit inscrire un auditeur de grade B3."""
        from apps.referentiels.models import Module

        self._prepare_planning_prereqs(formation, parametres)
        auditeur_b3 = Auditeur.objects.create(
            nom="BODO",
            prenom="Brice",
            matricule="GBAC0001",
            grade="B3",
            genre="M",
            categorie="B",
        )
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module_b = Module.objects.create(titre="Module B parent", specialite=spec)
        FormationModule.objects.create(
            formation=formation,
            module=module_b,
            volume_horaire=12,
            grade_cible="B",
            site_nom=f"SITE-{formation.pk}",
        )

        assert Inscription.objects.filter(formation=formation, auditeur=auditeur_b3).count() == 0
        nb = self._service().generer_automatiquement_par_grade(formation.pk)

        assert nb == 1
        assert Inscription.objects.filter(formation=formation, auditeur=auditeur_b3).count() == 1
        groupes = self._service().list_par_formation(formation.pk)
        assert any(g.nom == "B3_GROUPE1" for g in groupes)

    def test_generation_auto_backfill_accepte_multi_grades(self, formation, parametres):
        """Un module multi-grades doit permettre le backfill des grades listés."""
        from apps.referentiels.models import Module

        self._prepare_planning_prereqs(formation, parametres)
        auditeur_a3 = Auditeur.objects.create(
            nom="MIX",
            prenom="A3",
            matricule="MGRA3001",
            grade="A3",
            genre="M",
            categorie="A",
        )
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module_multi = Module.objects.create(titre="Module multi grades", specialite=spec)
        FormationModule.objects.create(
            formation=formation,
            module=module_multi,
            volume_horaire=12,
            grade_cible="A2, A3",
            site_nom=f"SITE-{formation.pk}",
        )

        nb = self._service().generer_automatiquement_par_grade(formation.pk)

        assert nb == 1
        assert Inscription.objects.filter(formation=formation, auditeur=auditeur_a3).count() == 1

    def test_generation_auto_backfill_avec_inscriptions_existantes(self, formation, parametres):
        """Même avec des inscrits existants, les auditeurs d'un nouveau grade sont pris en compte."""
        from apps.referentiels.models import Module

        self._prepare_planning_prereqs(formation, parametres)
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module_a3 = Module.objects.create(titre="Module A3 existant", specialite=spec)
        module_b = Module.objects.create(titre="Module B ajouté", specialite=spec)
        fm_a3 = FormationModule.objects.create(
            formation=formation,
            module=module_a3,
            volume_horaire=8,
            grade_cible="A3",
            site_nom=f"SITE-{formation.pk}",
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_b,
            volume_horaire=8,
            grade_cible="B",
            site_nom=f"SITE-{formation.pk}",
        )

        auditeur_a3 = Auditeur.objects.create(
            nom="ALPHA",
            prenom="A3",
            matricule="BFIN0001",
            grade="A3",
            genre="M",
            categorie="A",
        )
        auditeur_b3 = Auditeur.objects.create(
            nom="BRAVO",
            prenom="B3",
            matricule="BFIN0002",
            grade="B3",
            genre="F",
            categorie="B",
        )
        Inscription.objects.create(formation=formation, formation_module=fm_a3, auditeur=auditeur_a3)

        nb = self._service().generer_automatiquement_par_grade(formation.pk)

        assert nb == 2
        assert Inscription.objects.filter(formation=formation, auditeur=auditeur_b3).count() == 1
        groupes = self._service().list_par_formation(formation.pk)
        assert any(g.nom == "A3_GROUPE1" for g in groupes)
        assert any(g.nom == "B3_GROUPE1" for g in groupes)

    def test_generation_auto_n_inclut_pas_auditeurs_d_une_autre_formation(
        self, formation, parametres, type_formation_fab
    ):
        """Le backfill ne doit pas importer des auditeurs déjà inscrits ailleurs."""
        import datetime

        from apps.formations.repositories import FormationModuleRepository, FormationRepository
        from apps.formations.services import FormationService
        from apps.referentiels.models import Module

        self._prepare_planning_prereqs(formation, parametres)
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module = Module.objects.create(titre="Module partagé", specialite=spec)
        FormationModule.objects.create(
            formation=formation,
            module=module,
            volume_horaire=8,
            grade_cible="A3",
            site_nom=f"SITE-{formation.pk}",
        )

        autre_formation = FormationService(FormationRepository(), FormationModuleRepository()).creer(
            type_formation_id=type_formation_fab.pk,
            intitule="Autre formation",
            vague="V2",
            date_debut=datetime.date(2025, 4, 1),
            date_fin=datetime.date(2025, 6, 30),
        )
        fm_autre = FormationModule.objects.create(
            formation=autre_formation,
            module=module,
            volume_horaire=8,
            grade_cible="A3",
            site_nom="SITE-AUTRE",
        )
        auditeur_externe = Auditeur.objects.create(
            nom="EXTERNE",
            prenom="Auditeur",
            matricule="EXTA3001",
            grade="A3",
            genre="M",
            categorie="A",
        )
        Inscription.objects.create(
            formation=autre_formation,
            formation_module=fm_autre,
            auditeur=auditeur_externe,
        )

        nb = self._service().generer_automatiquement_par_grade(formation.pk)

        assert nb == 0
        assert Inscription.objects.filter(formation=formation, auditeur=auditeur_externe).count() == 0

    def test_generation_auto_cree_aussi_le_planning_si_salles_disponibles(self, formation, auditeur, parametres):
        """Après création des groupes, les séances sont générées automatiquement."""
        from apps.parametrage.models import Batiment, Salle, Site
        from apps.referentiels.models import Module

        parametres.jours_defaut = [0, 1, 2, 3, 4]
        parametres.save(update_fields=["jours_defaut"])

        site = Site.objects.create(nom="SITE-1", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-1", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-1", capacite_max=40, actif=True)

        from apps.referentiels.models import Specialite

        spec = Specialite.objects.get(code="GENERAL")
        module = Module.objects.create(titre="Module planning auto", specialite=spec)
        fm = FormationModule.objects.create(
            formation=formation,
            module=module,
            volume_horaire=8,
            salle_nombre=1,
            salle_nom="",
            site_nom="SITE-1",
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)

        nb = self._service().generer_automatiquement_par_grade(formation.pk)

        assert nb == 1
        assert Seance.objects.filter(groupe__formation=formation).count() > 0
