import { Component } from "react"
import { KolibriBird } from "./KolibriBird"

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <KolibriBird size={64} state="error" />
          <h2>Что-то пошло не так</h2>
          <p>{this.state.error.message}</p>
          <button className="upload-btn" onClick={() => { this.setState({ error: null }); window.location.reload() }}>
            Перезагрузить
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
