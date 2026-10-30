import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import {
  RadialGaugeCard,
  TeachingLoadBarChart,
  VectorDonutChart,
  VectorSplineAreaChart,
} from '@/components/dashboard/Charts'
import {
  FinancialSituationCard,
  RecentActivityTimeline,
} from '@/components/dashboard/ExecutiveWidgets'

/**
 * Garde-fou « aucune donnée inventée ».
 *
 * Ces composants affichaient, sans qu'on leur passe quoi que ce soit, des
 * chiffres présentés comme les données réelles de l'INJS : 75 % de réussite,
 * 1 248 étudiants, 248 500 000 FCFA de recettes, une évolution 2021-2026, des
 * noms d'étudiants et des horodatages. Une interface ne doit jamais fabriquer
 * une donnée officielle, même « pour faire joli ».
 */
describe('dashboard/Charts — aucune valeur inventée par défaut', () => {
  it('la jauge n’affiche ni 75 % ni de comparaison imaginaire', () => {
    render(<RadialGaugeCard title="Taux de réussite" />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('75%')).not.toBeInTheDocument()
    expect(screen.queryByText(/\+5\s*%/)).not.toBeInTheDocument()
    expect(screen.queryByText(/vs 2025/)).not.toBeInTheDocument()
  })

  it('la jauge affiche une valeur réellement fournie', () => {
    render(<RadialGaugeCard title="Taux de réussite" value={64} />)
    expect(screen.getByText('64%')).toBeInTheDocument()
  })

  it('la courbe d’évolution est vide et le dit, sans série 2021-2026', () => {
    render(<VectorSplineAreaChart title="Évolution des effectifs" />)
    expect(
      screen.getByText(/Aucun historique d’effectifs n’est enregistré/i),
    ).toBeInTheDocument()
    expect(screen.queryByText('2021')).not.toBeInTheDocument()
    expect(screen.queryByText('1248')).not.toBeInTheDocument()
  })

  it('la courbe affiche les séries réellement transmises', () => {
    render(
      <VectorSplineAreaChart
        title="Évolution des effectifs"
        years={['2024', '2025']}
        series={[{ name: 'Étudiants', color: '#1267D6', data: [10, 20] }]}
      />,
    )
    expect(screen.getByText('2024')).toBeInTheDocument()
    expect(
      screen.queryByText(/Aucun historique d’effectifs/i),
    ).not.toBeInTheDocument()
  })

  it('le donut sans données ne prétend pas à une répartition', () => {
    render(<VectorDonutChart title="Répartition par sexe" data={[]} />)
    expect(
      screen.getByText(/Aucune donnée enregistrée pour cette répartition/i),
    ).toBeInTheDocument()
  })

  it('la charge d’enseignement n’affiche aucun volume horaire inventé', () => {
    render(<TeachingLoadBarChart title="Charge d'enseignement" />)
    expect(screen.getByText(/Aucun volume horaire enregistré/i)).toBeInTheDocument()
    expect(screen.queryByText('340')).not.toBeInTheDocument()
  })

  it('la situation financière n’affiche aucun montant inventé', () => {
    render(<FinancialSituationCard title="Situation financière" />)
    expect(screen.queryByText(/248 500 000/)).not.toBeInTheDocument()
    expect(screen.queryByText(/215 780 000/)).not.toBeInTheDocument()
    expect(screen.queryByText(/32 720 000/)).not.toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3)
  })

  it('le flux d’activité ne relate aucune activité fictive', () => {
    // RecentActivityTimeline contient un lien « Voir tout » vers /scolarite.
    render(
      <MemoryRouter>
        <RecentActivityTimeline title="Activité récente" />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Aucune activité enregistrée/i)).toBeInTheDocument()
    expect(screen.queryByText(/M\. Sarr/)).not.toBeInTheDocument()
    expect(screen.queryByText(/A\. Traoré/)).not.toBeInTheDocument()
  })
})
