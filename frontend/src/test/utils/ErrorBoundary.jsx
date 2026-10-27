import { Component } from 'react'

/**
 * Attrape les erreurs de rendu des tests smoke pour les faire échouer
 * explicitement (avec le message), plutôt que de les laisser noyées dans
 * console.error.
 */
export default class TestErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  componentDidCatch(error) {
    if (this.props.onError) this.props.onError(error)
    this.setState({ error })
  }

  render() {
    if (this.state.error) {
      return (
        <div data-testid="render-crash">
          {String(this.state.error?.message || this.state.error)}
        </div>
      )
    }
    return this.props.children
  }
}
