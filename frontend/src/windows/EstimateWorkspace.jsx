import { useState } from "react";
import { CheckCircle2, FileText, Save, ShieldAlert } from "lucide-react";
import { estimateArtifactDisplayName, estimateTitleFromPayload } from "../estimate/estimateTitle";
import { normalizeEstimatePayload } from "../estimate/estimateModel";
import { materializedArtifacts } from "../shell/projectModel";
import { EstimateEditor } from "./EstimateEditor";

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

export function EstimateWorkspace({ payload, onCalculate, onOpenArtifact, onUpdate }) {
  const readiness = payload.readiness || (payload.task?.result?.type === "estimate_readiness" ? payload.task.result.readiness : null);
  const model = normalizeEstimatePayload(payload);
  const revisionKey = payload.task?.result?.calculation?.calculation_sha256
    || payload.persistence?.version
    || `${payload.status || "draft"}:${model.lines.length}:${model.pricedLineCount}`;
  return readiness
    ? <EstimateReadinessWorkspace onOpenArtifact={onOpenArtifact} onUpdate={onUpdate} payload={payload} readiness={readiness} />
    : <EstimateEditor key={revisionKey} model={model} onCalculate={onCalculate} onOpenArtifact={onOpenArtifact} onUpdate={onUpdate} payload={payload} />;
}
