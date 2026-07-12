import { Component } from "react";
import { RotateCcw } from "lucide-react";
import { KolibriBird } from "./KolibriBird";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="fatal">
        <KolibriBird size={78} state="error" />
        <h1>Kolibri остановилась</h1>
        <p>Интерфейс не смог безопасно продолжить работу. Перезапустите приложение; сохранённые проекты останутся в истории.</p>
        <button onClick={() => globalThis.location.reload()} type="button">
          <RotateCcw size={18} /> Перезапустить
        </button>
      </main>
    );
  }
}
