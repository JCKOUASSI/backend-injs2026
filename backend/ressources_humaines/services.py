"""Services du lot L7 — Ressources Humaines.

Création d'agents, affectations historiées et disponibilités (chevauchement
interdit par le clean du modèle). La paie des formateurs n'est pas impactée :
le module formations conserve son propre périmètre.
"""
from scolarite.models import journaliser

from .models import AffectationRH, Agent, DisponibiliteAgent, Service

ACTION_AGENT_CREATION = 'RH_AGENT_CREATION'
ACTION_AFFECTATION = 'RH_AFFECTATION'
ACTION_INDISPO = 'RH_INDISPO'


def creer_agent(user=None, matricule='', nom='', prenom='', email='', telephone='',
                type_contrat=Agent.TypeContrat.CONTRAT, acteur=None):
    agent = Agent.objects.create(
        user=user, matricule=matricule, nom=nom, prenom=prenom,
        email=email, telephone=telephone, type_contrat=type_contrat,
    )
    journaliser(ACTION_AGENT_CREATION, objet=agent, acteur=acteur,
                commentaire=f"Création agent {agent.matricule}")
    return agent


def affecter_agent(agent, fonction, date_debut, acteur=None, date_fin=None):
    """Nouvelle affectation (l'historique des précédentes est conservé)."""
    aff = AffectationRH.objects.create(
        agent=agent, fonction=fonction, date_debut=date_debut,
        date_fin=date_fin, cree_par=acteur,
    )
    journaliser(ACTION_AFFECTATION, objet=agent, acteur=acteur,
                nouvelle_valeur=str(fonction),
                commentaire=f'Affectation depuis {date_debut}')
    return aff


def ajouter_indisponibilite(agent, type_indispo, date_debut, date_fin, acteur=None, motif=''):
    dispo = DisponibiliteAgent(
        agent=agent, type_indispo=type_indispo, motif=motif,
        date_debut=date_debut, date_fin=date_fin,
    )
    dispo.full_clean()
    dispo.save()
    journaliser(ACTION_INDISPO, objet=dispo, acteur=acteur,
                commentaire=f'{type_indispo} {date_debut} → {date_fin}')
    return dispo


def services_disponibles():
    return Service.objects.filter(actif=True)