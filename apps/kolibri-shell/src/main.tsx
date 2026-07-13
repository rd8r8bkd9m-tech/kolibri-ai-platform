import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import './styles/tokens.css';
import './styles/global.css';
import './styles/shell.css';

async function mount() {
  let fixture: Awaited<ReturnType<
    typeof import('./dev/estimateVisualFixture')['createEstimateVisualFixture']
  >> | undefined;
  if (
    import.meta.env.DEV &&
    new URLSearchParams(window.location.search).get('__fixture') === 'estimate'
  ) {
    const { createEstimateVisualFixture } = await import('./dev/estimateVisualFixture');
    fixture = createEstimateVisualFixture(window.matchMedia('(max-width: 767px)').matches);
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App client={fixture?.client} initialView={fixture?.initialView} />
    </StrictMode>,
  );
}

void mount();
