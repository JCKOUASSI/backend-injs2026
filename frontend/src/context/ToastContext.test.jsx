import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ToastProvider, useToast } from '@/context/ToastContext'

function Harness() {
  const toast = useToast()
  return (
    <div>
      <button onClick={() => toast.showToast('Opération réussie', 'success')}>succès</button>
      <button onClick={() => toast.showToast('Erreur métier', 'error')}>erreur</button>
      <button onClick={() => toast.showToast('Info')}>défaut</button>
    </div>
  )
}

// Enregistre la référence de l'objet de contexte reçu à chaque rendu d'un
// consommateur : permet de prouver que la valeur exposée reste stable quand
// l'état interne du provider change (régression §10.10).
let refs = []
function RefProbe() {
  const toast = useToast()
  refs.push(toast)
  return <button onClick={() => toast.showToast('ping')}>ping</button>
}

describe('context/ToastContext', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    refs = []
  })
  afterEach(() => vi.useRealTimers())

  it('affiche un toast de succès puis le retire après 6 s', () => {
    render(<ToastProvider><Harness /></ToastProvider>)

    fireEvent.click(screen.getByText('succès'))
    expect(screen.getByText('Opération réussie')).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(5999))
    expect(screen.getByText('Opération réussie')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(2))
    expect(screen.queryByText('Opération réussie')).not.toBeInTheDocument()
  })

  it('utilise le type success par défaut', () => {
    render(<ToastProvider><Harness /></ToastProvider>)
    fireEvent.click(screen.getByText('défaut'))
    expect(screen.getByText('Info')).toBeInTheDocument()
  })

  it('peut empiler plusieurs toasts', () => {
    render(<ToastProvider><Harness /></ToastProvider>)
    fireEvent.click(screen.getByText('succès'))
    fireEvent.click(screen.getByText('défaut'))
    expect(screen.getByText('Opération réussie')).toBeInTheDocument()
    expect(screen.getByText('Info')).toBeInTheDocument()
  })

  // Régression §10.10 : la valeur de contexte doit rester la MÊME référence
  // quand un toast apparaît puis disparaît. Sinon les écrans qui mémoïsent un
  // chargeur avec l'objet `toast` en dépendance (Jurys, Graduation, etc.)
  // voient ce chargeur recréé et leur effet rejoué à chaque toast — d'où une
  // boucle de requêtes sur un échec de chargement initial.
  it('expose une valeur de contexte stable à l’apparition et à la disparition d’un toast (§10.10)', () => {
    render(<ToastProvider><RefProbe /></ToastProvider>)
    const valeurInitiale = refs[0]

    fireEvent.click(screen.getByText('ping')) // ajout d'un toast -> rendu du provider
    expect(refs.at(-1)).toBe(valeurInitiale)

    act(() => vi.advanceTimersByTime(6000))   // disparition -> autre rendu du provider
    expect(refs.at(-1)).toBe(valeurInitiale)
  })
})
