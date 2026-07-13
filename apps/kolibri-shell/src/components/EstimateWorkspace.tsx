import {
  Blocks,
  CheckCircle2,
  Download,
  Droplets,
  ExternalLink,
  FileText,
  House,
  Link2,
  MessageSquareText,
  MoreVertical,
  Pencil,
  Trash2,
  X,
} from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { EstimateLine, EstimateSummarySection, VerifiedArtifact } from '../api/types';

interface EstimateWorkspaceProps {
  artifact: VerifiedArtifact & { estimate: NonNullable<VerifiedArtifact['estimate']> };
  presentation: 'mobile' | 'desktop';
}

const rubles = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

function formatRubles(value: number): string {
  return `${rubles.format(Math.round(value))} ₽`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value);
}

function parseNumber(value: string): number {
  const parsed = Number(value.replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function sectionIcon(icon: EstimateSummarySection['icon']) {
  if (icon === 'foundation') return <Blocks aria-hidden="true" />;
  if (icon === 'engineering') return <Droplets aria-hidden="true" />;
  return <House aria-hidden="true" />;
}

interface EstimateEditorProps {
  lines: EstimateLine[];
  onChange(lines: EstimateLine[]): void;
  firstInputRef?: RefObject<HTMLInputElement | null>;
}

function EstimateEditor({ lines, onChange, firstInputRef }: EstimateEditorProps) {
  const [activeMenu, setActiveMenu] = useState<string>();

  const patchLine = (id: string, update: Partial<EstimateLine>) => {
    onChange(lines.map((line) => {
      if (line.id !== id) return line;
      const next = { ...line, ...update };
      return { ...next, amountRub: next.quantity * next.unitPriceRub };
    }));
  };

  return (
    <div className="estimate-table" role="table" aria-label="Строки сметы">
      <div className="estimate-table-head" role="row">
        <span>№</span><span>Работы и материалы</span><span>Ед. изм.</span>
        <span>Кол-во</span><span>Цена, ₽</span><span>Сумма, ₽</span><span />
      </div>
      {lines.map((line, index) => (
        <div className="estimate-table-row" role="row" key={line.id}>
          <span className="estimate-index">{index + 1}</span>
          <input
            ref={index === 0 ? firstInputRef : undefined}
            aria-label={`Работы и материалы, строка ${index + 1}`}
            type="text"
            value={line.title}
            onChange={(event) => patchLine(line.id, { title: event.target.value })}
          />
          <input
            aria-label={`Единица измерения, строка ${index + 1}`}
            type="text"
            value={line.unit}
            onChange={(event) => patchLine(line.id, { unit: event.target.value })}
          />
          <input
            aria-label={`Количество, строка ${index + 1}`}
            type="text"
            inputMode="decimal"
            value={formatNumber(line.quantity)}
            onChange={(event) => patchLine(line.id, { quantity: parseNumber(event.target.value) })}
          />
          <input
            aria-label={`Цена, строка ${index + 1}`}
            type="text"
            inputMode="decimal"
            value={formatNumber(line.unitPriceRub)}
            onChange={(event) => patchLine(line.id, { unitPriceRub: parseNumber(event.target.value) })}
          />
          <output aria-label={`Сумма, строка ${index + 1}`}>{rubles.format(line.amountRub)}</output>
          <div className="estimate-row-menu-anchor">
            <button
              type="button"
              className="estimate-row-menu-button"
              aria-label={`Действия строки ${index + 1}`}
              aria-expanded={activeMenu === line.id}
              onClick={() => setActiveMenu((current) => current === line.id ? undefined : line.id)}
            >
              <MoreVertical aria-hidden="true" />
            </button>
            {activeMenu === line.id ? (
              <div className="estimate-row-menu" role="menu">
                <button type="button" role="menuitem" onClick={() => onChange(lines.filter((item) => item.id !== line.id))}>
                  <Trash2 aria-hidden="true" /> Удалить строку
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function EstimateWorkspace({ artifact, presentation }: EstimateWorkspaceProps) {
  const estimate = artifact.estimate;
  const [lines, setLines] = useState(estimate.lines);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [mobileEditing, setMobileEditing] = useState(false);
  const firstInputRef = useRef<HTMLInputElement>(null);
  const total = useMemo(() => lines.reduce((sum, line) => sum + line.amountRub, 0), [lines]);
  const summary = estimate.summarySections?.length
    ? estimate.summarySections
    : lines.slice(0, 3).map((line, index): EstimateSummarySection => ({
        id: line.id,
        title: line.section ?? line.title,
        amountRub: line.amountRub,
        icon: index === 0 ? 'foundation' : index === 1 ? 'house' : 'engineering',
      }));

  const startEditing = () => {
    if (presentation === 'mobile') setMobileEditing(true);
    else requestAnimationFrame(() => firstInputRef.current?.focus());
  };

  const sourceVerdict = (
    <div className="estimate-source-verdict" data-status={estimate.status}>
      <CheckCircle2 aria-hidden="true" />
      <span>{estimate.sourceSummary}</span>
    </div>
  );

  if (presentation === 'mobile') {
    return (
      <>
        <section className="estimate-sheet" data-testid="estimate-workspace">
          <div className="estimate-sheet-handle" aria-hidden="true" />
          <h2>{estimate.title}</h2>
          <div className="estimate-summary-list">
            {summary.map((section) => (
              <div className="estimate-summary-row" key={section.id}>
                <span className="estimate-summary-icon">{sectionIcon(section.icon)}</span>
                <span>{section.title}</span>
                <strong>{formatRubles(section.amountRub)}</strong>
              </div>
            ))}
          </div>
          <div className="estimate-total"><strong>Итого</strong><output>{formatRubles(total)}</output></div>
          {sourceVerdict}
          {sourcesOpen ? <p className="estimate-source-detail">{estimate.sourceSummary}</p> : null}
          <div className="estimate-mobile-actions">
            <button type="button" onClick={startEditing}><Pencil aria-hidden="true" />Редактировать</button>
            <button type="button" aria-expanded={sourcesOpen} onClick={() => setSourcesOpen((value) => !value)}>
              <MessageSquareText aria-hidden="true" />Источники
            </button>
            <a href={artifact.downloadUrl} target="_blank" rel="noreferrer">
              <FileText aria-hidden="true" />PDF
            </a>
          </div>
        </section>
        {mobileEditing ? (
          <section className="estimate-mobile-editor" role="dialog" aria-modal="true" aria-label="Редактор сметы">
            <header>
              <div><small>Смета</small><h2>{estimate.title}</h2></div>
              <button type="button" aria-label="Закрыть редактор" onClick={() => setMobileEditing(false)}><X aria-hidden="true" /></button>
            </header>
            <div className="estimate-mobile-editor-scroll">
              <EstimateEditor lines={lines} onChange={setLines} firstInputRef={firstInputRef} />
              <div className="estimate-total"><strong>Итого</strong><output>{formatRubles(total)}</output></div>
            </div>
            <button className="estimate-editor-done" type="button" onClick={() => setMobileEditing(false)}>Готово</button>
          </section>
        ) : null}
      </>
    );
  }

  return (
    <section className="estimate-workspace" data-testid="estimate-workspace">
      <div className="estimate-action-rail" aria-label="Действия со сметой">
        <button type="button" onClick={startEditing}><Pencil aria-hidden="true" />Редактировать</button>
        <button type="button" aria-expanded={sourcesOpen} onClick={() => setSourcesOpen((value) => !value)}><Link2 aria-hidden="true" />Источники</button>
        <a href={artifact.downloadUrl} target="_blank" rel="noreferrer"><FileText aria-hidden="true" />PDF</a>
        <a href={artifact.downloadUrl} target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" />Открыть окном</a>
      </div>
      <header className="estimate-heading">
        <h2>{estimate.title}</h2>
        <p>{[estimate.location, estimate.pricedAt ? `цены на ${estimate.pricedAt}` : undefined].filter(Boolean).join(' · ')}</p>
      </header>
      <EstimateEditor lines={lines} onChange={setLines} firstInputRef={firstInputRef} />
      <div className="estimate-total"><strong>Итого</strong><output>{formatRubles(total)}</output></div>
      {sourceVerdict}
      {sourcesOpen ? <p className="estimate-source-detail">{estimate.sourceSummary}</p> : null}
      <a className="estimate-pdf-row" href={artifact.downloadUrl} download={artifact.name}>
        <span><FileText aria-hidden="true" />{artifact.name}</span>
        <span>PDF · {Math.max(1, Math.round(artifact.sizeBytes / 1024))} КБ <Download aria-hidden="true" /></span>
      </a>
    </section>
  );
}
