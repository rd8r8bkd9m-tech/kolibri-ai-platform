import { useMemo, useState } from "react";
import { CheckCircle2, FileText, Plus, Save, ShieldAlert, Trash2 } from "lucide-react";
import { EstimateLineEvidence } from "../estimate/EstimateLineEvidence";
import { EstimateTotals } from "../estimate/EstimateTotals";
import { estimateArtifactDisplayName, estimateTitleFromPayload } from "../estimate/estimateTitle";
import {
  calculateEstimateTotals,
  formatEstimateMoney,
  normalizeEstimatePayload,
  priceInputToMinor,
  validEstimateQuantity,
} from "../estimate/estimateModel";
import { submitEstimateFeedback } from "../runtime/kolibriApi";
import { materializedArtifacts } from "../shell/projectModel";

function newEstimateLine(index = 1) {
  return {
    id: `line-${index}`,
    section: "Основные работы",
    description: "",
    category: "labor",
    unit: "шт",
    quantity: "1",
    price: "0",
    provenance: { source: "manual", source_ref: "Ручной ввод", validation_status: "unverified" },
    evidence: { status: "unverified", sourceRef: "Ручной ввод", priceMinMinor: null, priceMaxMinor: null },
  };
}

function editableLine(line, index, minorUnit) {
  return {
    ...newEstimateLine(index + 1),
    ...line,
    quantity: String(line.quantity ?? "1"),
    price: String(line.price ?? (Number(line.unit_price_minor ?? 0) / (10 ** minorUnit)).toFixed(minorUnit)),
    provenance: line.provenance || { source: "manual" },
  };
}

function textList(value) {
  return String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
}

function EstimateNumberInput(props) {
  return (
    <input
      {...props}
      autoComplete="off"
      className="estimate-number-input"
      inputMode="decimal"
      pattern="[0-9]*[.,]?[0-9]*"
      spellCheck="false"
      type="text"
    />
  );
}

const SELECT_LABELS = {
  "resource-index": "Ресурсно-индексный",
  resource: "Ресурсный",
  "base-index": "Базисно-индексный",
  contract: "Договорный",
  commercial: "Коммерческий",
  project: "По проекту",
  measurement: "По замерам",
  manual: "Ручной ввод",
};

function EstimateReadinessWorkspace({ payload, readiness, onOpenArtifact, onUpdate }) {
  const fields = readiness.editor?.fields || [];
  const existingDraft = payload.readinessDraft || {};
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [
    field.id,
    existingDraft[field.id] ?? field.value ?? "",
  ])));
  const [savedAt, setSavedAt] = useState(payload.readinessDraftSavedAt || "");
  const artifacts = materializedArtifacts(payload.artifacts || payload.task?.artifacts);
  const checklist = artifacts.find((artifact) => artifact.document_role === "estimate_input_checklist")
    || artifacts.find((artifact) => artifact.deliverable_type === "pdf");
  const completed = fields.filter((field) => String(values[field.id] || "").trim()).length;
  const total = fields.length;
  const percent = total ? Math.round((completed / total) * 100) : 0;
  const facts = readiness.known_facts || {};
  const displayTitle = estimateTitleFromPayload({ ...payload, readiness });

  const patchField = (fieldId, value) => {
    setValues((current) => {
      const next = { ...current, [fieldId]: value };
      onUpdate?.({ readinessDraft: next, readinessDraftSavedAt: "" });
      return next;
    });
    setSavedAt("");
  };
  const saveDraft = () => {
    const timestamp = new Date().toISOString();
    setSavedAt(timestamp);
    onUpdate?.({ readinessDraft: values, readinessDraftSavedAt: timestamp });
  };

  return (
    <div className="estimate-readiness-workspace">
      <section className="readiness-alert" aria-label="Статус готовности сметы">
        <ShieldAlert aria-hidden="true" size={22} />
        <div>
          <span>Нужны исходные данные</span>
          <h3>Денежный итог не рассчитан</h3>
          <p>Kolibri не подставляет цены, объёмы, индексы или налоги без проверяемого документа-основания.</p>
        </div>
        {checklist && (
          <button onClick={() => onOpenArtifact?.({ ...checklist, display_name: estimateArtifactDisplayName(checklist, displayTitle) })} type="button">
            <FileText size={16} /> Открыть PDF-чеклист
          </button>
        )}
      </section>

      <section className="readiness-facts" aria-label="Известные факты">
        <div><small>Объект</small><strong>{facts.object_type_label || "Требует подтверждения"}</strong></div>
        {facts.gross_area_m2 && <div><small>Площадь</small><strong>{facts.gross_area_m2} м²</strong></div>}
        <div><small>Место</small><strong>{[facts.region, facts.locality].filter(Boolean).join(", ") || "Требует подтверждения"}</strong></div>
        <div><small>Нормативная проверка</small><strong>Не пройдена</strong></div>
      </section>

      <section className="readiness-progress" aria-label={`Заполнено ${completed} из ${total}`}>
        <div><span>Комплектность черновика</span><strong>{completed} из {total}</strong></div>
        <div aria-hidden="true"><span style={{ width: `${percent}%` }} /></div>
        <small>Заполненное поле ещё не считается проверенным: потребуется сверка самого документа.</small>
      </section>

      <div className="readiness-groups">
        {(readiness.required_inputs || []).map((group) => {
          const groupFields = fields.filter((field) => field.group_id === group.id);
          const groupComplete = groupFields.length > 0 && groupFields.every((field) => String(values[field.id] || "").trim());
          return (
            <section className="readiness-group" key={group.id}>
              <header>
                <div>
                  {groupComplete ? <CheckCircle2 aria-hidden="true" size={18} /> : <span aria-hidden="true">{groupFields.filter((field) => String(values[field.id] || "").trim()).length}/{groupFields.length}</span>}
                  <h4>{group.label}</h4>
                </div>
                <small>{groupComplete ? "Заполнено, не проверено" : "Нужно заполнить"}</small>
              </header>
              <p>{group.evidence}</p>
              <div className="readiness-field-grid">
                {groupFields.map((field) => {
                  const common = {
                    id: `readiness-${field.id}`,
                    onChange: (event) => patchField(field.id, event.target.value),
                    value: values[field.id] || "",
                  };
                  return (
                    <label key={field.id}>
                      <span>{field.label}</span>
                      {field.input_type === "select" ? (
                        <select {...common}>
                          <option value="">Выберите…</option>
                          {(field.options || []).map((option) => <option key={option} value={option}>{SELECT_LABELS[option] || option}</option>)}
                        </select>
                      ) : field.input_type === "textarea" ? (
                        <textarea {...common} placeholder={field.placeholder || "Укажите документ и реквизиты"} rows={3} />
                      ) : (
                        <input {...common} placeholder={field.suggested_value ? `Подтвердите: ${field.suggested_value}` : field.placeholder || "Укажите значение"} type={field.input_type === "date" ? "date" : "text"} />
                      )}
                    </label>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>

      <section className="readiness-sections">
        <h4>Разделы будущей сметы</h4>
        <p>Позиции и суммы появятся только после подтверждения состава работ и источников.</p>
        <div>{(readiness.draft_sections || []).map((section) => <span key={section.id}>{section.label}</span>)}</div>
      </section>

      <footer className="readiness-actions">
        <div>
          <strong>{savedAt ? "Черновик сохранён в проекте" : "Есть несохранённые данные"}</strong>
          <small>{savedAt ? new Date(savedAt).toLocaleString("ru-RU") : "Сохранение не подтверждает достоверность документов"}</small>
        </div>
        <button className="primary-action" onClick={saveDraft} type="button"><Save size={16} /> Сохранить черновик</button>
      </footer>
      {payload.error && <div className="inline-error">{payload.error}</div>}
    </div>
  );
}

function EditableEstimateWorkspace({ model, onCalculate, onOpenArtifact, payload }) {
  const minorUnit = model.minorUnit;
  const [title, setTitle] = useState(model.title);
  const [lines, setLines] = useState(() => model.lines.length
    ? model.lines.map((line, index) => editableLine(line, index, minorUnit))
    : [newEstimateLine()]);
  const [overhead, setOverhead] = useState(String(model.overheadRateBps / 100));
  const [tax, setTax] = useState(String(model.taxRateBps / 100));
  const [assumptions, setAssumptions] = useState(model.assumptions.join("\n"));
  const [questions, setQuestions] = useState(model.questions.join("\n"));
  const estimateStatus = model.status;
  const busy = payload.status === "running";
  const [reviewState, setReviewState] = useState("");
  const overheadRateBps = Math.round(Math.max(Number(overhead) || 0, 0) * 100);
  const taxRateBps = Math.round(Math.max(Number(tax) || 0, 0) * 100);
  const totals = useMemo(() => calculateEstimateTotals(lines, {
    minorUnit,
    overheadRateBps,
    taxRateBps,
  }), [lines, minorUnit, overheadRateBps, taxRateBps]);
  const hasInvalidLine = lines.some((line) => (
    !line.description.trim()
      || !validEstimateQuantity(line.quantity)
      || priceInputToMinor(line.price, minorUnit) === null
  ));

  const review = async (action) => {
    const estimateId = payload.persistence?.estimate_id;
    const baseVersion = payload.persistence?.version;
    if (!estimateId || !baseVersion || reviewState === "saving") return;
    setReviewState("saving");
    try {
      const receipt = await submitEstimateFeedback({
        estimateId,
        baseVersion,
        action,
        reason: action === "reject" ? "Отклонено владельцем в редакторе; требуется корректировка." : "",
      });
      setReviewState(receipt.status === "queued" ? action : "rejected");
    } catch {
      setReviewState("error");
    }
  };

  const patchLine = (id, patch) => {
    setLines((current) => current.map((line) => line.id === id ? { ...line, ...patch } : line));
  };
  const removeLine = (id) => {
    setLines((current) => current.length > 1 ? current.filter((line) => line.id !== id) : current);
  };
  const submit = () => {
    const usable = lines.filter((line) => line.description.trim());
    if (!usable.length || hasInvalidLine) return;
    onCalculate({
      title: title.trim() || "Новая смета",
      currency: model.currency,
      minor_unit: minorUnit,
      region: model.region,
      client_name: model.clientName,
      object_name: model.objectName,
      object_address: model.objectAddress,
      source_summary: model.sourceSummary,
      assumptions: textList(assumptions),
      questions: textList(questions),
      lines: usable.map((line, index) => ({
        id: line.id || `line-${index + 1}`,
        section: line.section.trim() || "Основные работы",
        description: line.description.trim(),
        category: line.category,
        unit: line.unit.trim() || "шт",
        quantity: String(line.quantity).trim(),
        unit_price_minor: priceInputToMinor(line.price, minorUnit),
        provenance: line.provenance || { source: "manual" },
      })),
      overhead_rate_bps: overheadRateBps,
      tax_rate_bps: taxRateBps,
      normative_basis: model.normativeBasis,
      estimate_id: payload.persistence?.estimate_id || null,
      estimate_base_version: payload.persistence?.version || null,
    });
  };

  return (
    <div className="estimate-workspace">
      <section className={`estimate-verification-banner is-${estimateStatus}`} aria-label="Статус достоверности сметы">
        {estimateStatus === "verified" ? <CheckCircle2 aria-hidden="true" size={19} /> : <ShieldAlert aria-hidden="true" size={19} />}
        <div>
          <strong>{estimateStatus === "verified" ? "Проверенная смета" : "Предварительная смета"}</strong>
          <span>
            {estimateStatus === "verified"
              ? "Источники, исходные документы и расчётная база прошли контроль."
              : "Итог пересчитан движком, но источники ещё не прошли независимую проверку."}
          </span>
        </div>
        <small>{model.confidenceLabel}</small>
      </section>
      <div className="estimate-heading">
        <div>
          <span>{payload.persistence?.state === "saved" ? `Версия ${payload.persistence.version} сохранена` : "Детерминированный расчёт"}</span>
          <input aria-label="Название сметы" onChange={(event) => setTitle(event.target.value)} value={title} />
        </div>
        <div><small>Итого сейчас</small><strong>{formatEstimateMoney(totals.grandTotalMinor, minorUnit, model.currency)}</strong></div>
      </div>
      <div className="estimate-table">
        <div className="estimate-row estimate-row-head">
          <span>Тип</span><span>Раздел, позиция и источник</span><span>Ед.</span><span>Кол-во</span><span>Цена, ₽</span><span>Сумма</span><span />
        </div>
        {lines.map((line) => (
          <div className="estimate-row" key={line.id}>
            <select aria-label="Раздел" onChange={(event) => patchLine(line.id, { category: event.target.value })} value={line.category}>
              <option value="labor">Работы</option>
              <option value="material">Материалы</option>
              <option value="equipment">Оборудование</option>
              <option value="service">Услуги</option>
              <option value="other">Другое</option>
            </select>
            <span className="estimate-position-cell">
              <input aria-label="Раздел" onChange={(event) => patchLine(line.id, { section: event.target.value })} placeholder="Раздел" value={line.section} />
              <input aria-label="Позиция" onChange={(event) => patchLine(line.id, { description: event.target.value })} placeholder="Например, монтаж перегородки" value={line.description} />
              <EstimateLineEvidence currency={model.currency} line={line} minorUnit={minorUnit} />
            </span>
            <input aria-label="Единица" onChange={(event) => patchLine(line.id, { unit: event.target.value })} value={line.unit} />
            <EstimateNumberInput aria-label="Количество" min="0.000001" onChange={(event) => patchLine(line.id, { quantity: event.target.value })} step="0.01" value={line.quantity} />
            <EstimateNumberInput aria-label="Цена" min="0" onChange={(event) => patchLine(line.id, {
              price: event.target.value,
              provenance: { source: "manual", source_ref: "Изменено пользователем", validation_status: "unverified" },
              evidence: { status: "unverified", sourceRef: "Изменено пользователем", priceMinMinor: null, priceMaxMinor: null },
            })} step="0.01" value={line.price} />
            <strong className="estimate-line-total">{formatEstimateMoney(totals.lineTotals.get(line.id), minorUnit, model.currency)}</strong>
            <button aria-label="Удалить позицию" onClick={() => removeLine(line.id)} type="button"><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
      <div className="estimate-controls">
        <button onClick={() => setLines((current) => [...current, newEstimateLine(current.length + 1)])} type="button">
          <Plus size={17} /> Добавить позицию
        </button>
        <label>Накладные, %<EstimateNumberInput min="0" onChange={(event) => setOverhead(event.target.value)} step="0.01" value={overhead} /></label>
        <label>Налог, %<EstimateNumberInput min="0" onChange={(event) => setTax(event.target.value)} step="0.01" value={tax} /></label>
        {model.pdfArtifact && (
          <button className="estimate-pdf-action" onClick={() => onOpenArtifact?.({ ...model.pdfArtifact, display_name: estimateArtifactDisplayName(model.pdfArtifact, title) })} type="button">
            <FileText size={17} /> Открыть PDF-снимок
          </button>
        )}
        <button className="primary-action" disabled={busy || hasInvalidLine} onClick={submit} type="button">
          {busy ? "Сохраняю…" : model.pdfArtifact ? "Сохранить новую версию PDF" : "Пересчитать и создать PDF"}
        </button>
      </div>
      {hasInvalidLine && <p className="estimate-validation-note">Заполните название, положительное количество и корректную цену каждой позиции.</p>}
      <EstimateTotals currency={model.currency} minorUnit={minorUnit} totals={totals} />
      <details className="estimate-notes">
        <summary>Допущения и вопросы · {textList(assumptions).length + textList(questions).length}</summary>
        <div>
          <label>Допущения<textarea onChange={(event) => setAssumptions(event.target.value)} placeholder="По одному допущению в строке" value={assumptions} /></label>
          <label>Нужно уточнить<textarea onChange={(event) => setQuestions(event.target.value)} placeholder="По одному вопросу в строке" value={questions} /></label>
        </div>
      </details>
      {payload.persistence?.estimate_id && (
        <div className="estimate-review-actions" aria-label="Рецензирование сметы">
          <span>{reviewState === "accept" ? "Принято и отправлено в FormulaLM" : reviewState === "reject" ? "Возвращено на исправление" : reviewState === "error" || reviewState === "rejected" ? "Отзыв не принят политикой данных" : "Оцените предварительную смету"}</span>
          <button disabled={reviewState === "saving"} onClick={() => review("reject")} type="button">Вернуть</button>
          <button className="primary-action" disabled={reviewState === "saving"} onClick={() => review("accept")} type="button">Принять</button>
        </div>
      )}
      {payload.error && <div className="inline-error">{payload.error}</div>}
    </div>
  );
}

export function EstimateWorkspace({ payload, onCalculate, onOpenArtifact, onUpdate }) {
  const readiness = payload.readiness || (payload.task?.result?.type === "estimate_readiness" ? payload.task.result.readiness : null);
  const model = normalizeEstimatePayload(payload);
  const revisionKey = payload.task?.result?.calculation?.calculation_sha256
    || payload.persistence?.version
    || `${payload.status || "draft"}:${model.lines.length}:${model.pricedLineCount}`;
  return readiness
    ? <EstimateReadinessWorkspace onOpenArtifact={onOpenArtifact} onUpdate={onUpdate} payload={payload} readiness={readiness} />
    : <EditableEstimateWorkspace key={revisionKey} model={model} onCalculate={onCalculate} onOpenArtifact={onOpenArtifact} payload={payload} />;
}
