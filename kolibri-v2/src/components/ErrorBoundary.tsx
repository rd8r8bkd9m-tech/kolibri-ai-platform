import { Component, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-8 text-center">
          <AlertTriangle size={48} className="text-amber-500 mb-4" strokeWidth={1.5} />
          <h2 className="text-[18px] font-semibold text-[var(--text-primary)] mb-2">Что-то пошло не так</h2>
          <p className="text-[14px] text-[var(--text-secondary)] mb-4 max-w-md">
            {this.state.error?.message || 'Произошла непредвиденная ошибка'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="h-9 px-4 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors"
          >
            Попробовать снова
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
