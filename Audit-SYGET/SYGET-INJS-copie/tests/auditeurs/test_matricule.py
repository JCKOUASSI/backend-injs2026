from apps.auditeurs.matricule import generer_matricule


class TestGenererMatricule:
    """Tests pour la génération de matricule."""

    def test_format_de_base(self):
        """Le matricule généré respecte le format attendu."""
        matricule = generer_matricule("Martin", "Jean")
        assert matricule.startswith("MAJE")
        assert len(matricule) == 8

    def test_majuscules(self):
        """Le matricule est toujours en majuscules."""
        matricule = generer_matricule("dupont", "alice")
        assert matricule == matricule.upper()

    def test_longueur_noms_courts(self):
        """Un nom court ne provoque pas d'erreur."""
        matricule = generer_matricule("Li", "Bo")
        assert len(matricule) == 8
