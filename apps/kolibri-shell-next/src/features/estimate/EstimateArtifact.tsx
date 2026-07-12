import { OverlayDialog } from "@components/OverlayDialog";
import {
  estimateGroups,
  estimateTotal,
  formatMoney,
  lineTotal,
  type EstimateArtifact as EstimateArtifactModel,
} from "@domain/shell";
import {
  Blocks,
  CheckCircle2,
  Download,
  Droplet,
  ExternalLink,
  FileText,
  House,
  Link,
  MessageSquareText,
  MoreVertical,
  Pencil,
} from "lucide-react";
import { useState } from "react";

interface EstimateArtifactProps {
  estimate: EstimateArtifactModel;
  onLineChange: (lineId: string, field: "quantity" | "unitPrice", value: number) => void;
  onNotice: (message: string) => void;
}

interface EstimateBodyProps extends EstimateArtifactProps {
  editing: boolean;
  onToggleEditing: () => void;
  onOpenSources: () => void;
  onPdf: () => void;
  onFullscreen: () => void;
  fullscreen: boolean;
}

const groupIcons = {
  foundation: Blocks,
  house: House,
  systems: Droplet,
} as const;

function decimalValue(value: string): number | null {
  const normalized = value.trim().replace(",", ".").replace(/\s+/g, "");
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function EstimateBody({
  estimate,
  onLineChange,
  onNotice,
  editing,
  onToggleEditing,
  onOpenSources,
  onPdf,
  onFullscreen,
  fullscreen,
}: EstimateBodyProps) {
  const groups = estimateGroups(estimate);
  const total = estimateTotal(estimate);

  return (
    <div className={`estimate-body ${fullscreen && editing ? "is-mobile-editing" : ""}`}>
      <button className="sheet-handle" type="button" onClick={onFullscreen} aria-label="Развернуть смету">
        <span />
      </button>

      <div className="estimate-toolbar desktop-only">
        <button type="button" onClick={onToggleEditing} aria-pressed={editing}>
          <Pencil aria-hidden="true" />
          {editing ? "Готово" : "Редактировать"}
        </button>
        <button type="button" onClick={onOpenSources}>
          <Link aria-hidden="true" />
          Источники
        </button>
        <button type="button" onClick={onPdf}>
          <FileText aria-hidden="true" />
          PDF
        </button>
        {!fullscreen ? (
          <button type="button" onClick={onFullscreen}>
            <ExternalLink aria-hidden="true" />
            Открыть окном
          </button>
        ) : null}
      </div>

      <header className="estimate-heading">
        <h2>
          <span className="desktop-only">{estimate.title}</span>
          <span className="mobile-only">Предварительная смета</span>
        </h2>
        <p>{estimate.location} · цены на {estimate.pricedAt}</p>
      </header>

      <div className="estimate-table desktop-only" role="table" aria-label={estimate.title}>
        <div className="estimate-table-head" role="row">
          <span role="columnheader">№</span>
          <span role="columnheader">Работы и материалы</span>
          <span role="columnheader">Ед. изм.</span>
          <span role="columnheader">Кол-во</span>
          <span role="columnheader">Цена, ₽</span>
          <span role="columnheader">Сумма, ₽</span>
          <span aria-hidden="true" />
        </div>
        {estimate.lines.map((line, index) => (
          <div className="estimate-table-row" role="row" key={line.id}>
            <span role="cell">{index + 1}</span>
            <span className="table-field table-label" role="cell">{line.label}</span>
            <span className="table-field centered" role="cell">{line.unit}</span>
            <span className="table-field centered" role="cell">
              {editing ? (
                <input
                  aria-label={`Количество: ${line.label}`}
                  type="text"
                  inputMode="decimal"
                  value={line.quantity}
                  onChange={(event) => {
                    const value = decimalValue(event.currentTarget.value);
                    if (value !== null) onLineChange(line.id, "quantity", value);
                  }}
                />
              ) : line.quantity}
            </span>
            <span className="table-field numeric" role="cell">
              {editing ? (
                <input
                  aria-label={`Цена: ${line.label}`}
                  type="text"
                  inputMode="decimal"
                  value={line.unitPrice}
                  onChange={(event) => {
                    const value = decimalValue(event.currentTarget.value);
                    if (value !== null) onLineChange(line.id, "unitPrice", value);
                  }}
                />
              ) : formatMoney(line.unitPrice)}
            </span>
            <span className="table-field numeric" role="cell">{formatMoney(lineTotal(line))}</span>
            <button
              type="button"
              className="row-menu"
              aria-label={`Действия: ${line.label}`}
              onClick={() => onNotice(`Строка «${line.label}»: ${formatMoney(lineTotal(line))} ₽`)}
            >
              <MoreVertical aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>

      <div className="mobile-estimate-groups">
        {groups.map((group) => {
          const Icon = groupIcons[group.kind];
          return (
            <div className="mobile-estimate-row" key={group.id}>
              <span className="mobile-category-icon"><Icon aria-hidden="true" /></span>
              <span>{group.label}</span>
              <strong>{formatMoney(group.total)} ₽</strong>
            </div>
          );
        })}
      </div>

      {fullscreen && editing ? (
        <div className="mobile-estimate-editor" aria-label="Редактор строк сметы">
          {estimate.lines.map((line, index) => (
            <section className="mobile-estimate-edit-row" key={line.id}>
              <header>
                <span>{index + 1}</span>
                <strong>{line.label}</strong>
                <small>{line.unit}</small>
              </header>
              <label>
                <span>Количество</span>
                <input
                  aria-label={`Количество: ${line.label}`}
                  type="text"
                  inputMode="decimal"
                  value={line.quantity}
                  onChange={(event) => {
                    const value = decimalValue(event.currentTarget.value);
                    if (value !== null) onLineChange(line.id, "quantity", value);
                  }}
                />
              </label>
              <label>
                <span>Цена, ₽</span>
                <input
                  aria-label={`Цена: ${line.label}`}
                  type="text"
                  inputMode="decimal"
                  value={line.unitPrice}
                  onChange={(event) => {
                    const value = decimalValue(event.currentTarget.value);
                    if (value !== null) onLineChange(line.id, "unitPrice", value);
                  }}
                />
              </label>
              <p>Сумма <strong>{formatMoney(lineTotal(line))} ₽</strong></p>
            </section>
          ))}
        </div>
      ) : null}

      <div className="estimate-total">
        <strong>Итого</strong>
        <strong>{formatMoney(total)} ₽</strong>
      </div>

      <p className="estimate-source-note">
        <CheckCircle2 aria-hidden="true" />
        <span className="desktop-only">Источники: {estimate.sourceSummary}</span>
        <span className="mobile-only">Источники: проверены и актуальны</span>
      </p>

      <button className="estimate-file desktop-only" type="button" onClick={onPdf}>
        <FileText aria-hidden="true" />
        <span>{estimate.fileName}</span>
        <small>{estimate.fileSizeLabel}</small>
        <Download aria-hidden="true" />
      </button>

      <div className="mobile-estimate-actions">
        <button
          type="button"
          onClick={() => {
            if (!fullscreen && !editing) {
              onToggleEditing();
              onFullscreen();
              return;
            }
            onToggleEditing();
          }}
          aria-pressed={editing}
        >
          <Pencil aria-hidden="true" />
          <span>{editing ? "Готово" : "Редактировать"}</span>
        </button>
        <button type="button" onClick={onOpenSources}>
          <MessageSquareText aria-hidden="true" />
          <span>Источники</span>
        </button>
        <button className="pdf-action" type="button" onClick={onPdf}>
          <FileText aria-hidden="true" />
          <span>PDF</span>
        </button>
      </div>
    </div>
  );
}

export function EstimateArtifact({ estimate, onLineChange, onNotice }: EstimateArtifactProps) {
  const [editing, setEditing] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

  const handlePdf = () => {
    onNotice("Открываю системный диалог печати — выберите «Сохранить как PDF».");
    window.print();
  };

  const bodyProps: EstimateBodyProps = {
    estimate,
    onLineChange,
    onNotice,
    editing,
    onToggleEditing: () => setEditing((value) => !value),
    onOpenSources: () => setSourcesOpen(true),
    onPdf: handlePdf,
    onFullscreen: () => setFullscreenOpen(true),
    fullscreen: false,
  };

  return (
    <>
      <section className="estimate-artifact" aria-label="Смета">
        <EstimateBody {...bodyProps} />
      </section>

      <OverlayDialog
        open={sourcesOpen}
        title="Источники сметы"
        onClose={() => setSourcesOpen(false)}
        className="sources-dialog"
      >
        <p className="source-lead">Цены проверены на {estimate.pricedAt}.</p>
        <div className="source-record">
          <CheckCircle2 aria-hidden="true" />
          <span>{estimate.sourceSummary}</span>
        </div>
        <p className="source-caveat">Перед закупкой запросите финальные коммерческие предложения у поставщиков.</p>
      </OverlayDialog>

      <OverlayDialog
        open={fullscreenOpen}
        title="Предварительная смета"
        onClose={() => setFullscreenOpen(false)}
        className="artifact-dialog"
      >
        <EstimateBody {...bodyProps} fullscreen onFullscreen={() => setFullscreenOpen(false)} />
      </OverlayDialog>
    </>
  );
}
