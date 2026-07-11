import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

function newEstimateLine(index = 1) {
  return { id: `line-${index}`, section: "Основные работы", description: "", category: "labor", unit: "шт", quantity: "1", price: "0", provenance: { source: "manual" } };
}

function editableLine(line, index, minorUnit) {
  return {
    ...newEstimateLine(index + 1),
    ...line,
    quantity: String(line.quantity ?? "1"),
    price: String((Number(line.unit_price_minor ?? 0) / (10 ** minorUnit)).toFixed(minorUnit)),
    provenance: line.provenance || { source: "manual" },
  };
}

function textList(value) {
  return String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
}

function formatRubles(minor) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format((Number(minor) || 0) / 100);
}

export function EstimateWorkspace({ payload, onCalculate }) {
  const minorUnit = payload.minor_unit ?? 2;
  const [title, setTitle] = useState(payload.title || "Новая смета");
  const [lines, setLines] = useState(() => payload.lines?.map((line, index) => editableLine(line, index, minorUnit)) || [newEstimateLine()]);
  const [overhead, setOverhead] = useState(String((payload.overhead_rate_bps || 0) / 100));
  const [tax, setTax] = useState(String((payload.tax_rate_bps || 0) / 100));
  const [assumptions, setAssumptions] = useState((payload.assumptions || []).join("\n"));
  const [questions, setQuestions] = useState((payload.questions || []).join("\n"));
  const task = payload.task;
  const calculation = task?.result?.calculation;
  const busy = payload.status === "running";

  const patchLine = (id, patch) => {
    setLines((current) => current.map((line) => line.id === id ? { ...line, ...patch } : line));
  };
  const removeLine = (id) => {
    setLines((current) => current.length > 1 ? current.filter((line) => line.id !== id) : current);
  };
  const submit = () => {
    const usable = lines.filter((line) => line.description.trim());
    if (!usable.length) return;
    onCalculate({
      title: title.trim() || "Новая смета",
      currency: "RUB",
      minor_unit: minorUnit,
      region: payload.metadata?.region || payload.region || "Не указан",
      client_name: payload.client_name || null,
      object_name: payload.object_name || null,
      object_address: payload.object_address || null,
      source_summary: payload.metadata?.provenance || payload.source_summary || "Цены требуют проверки",
      assumptions: textList(assumptions),
      questions: textList(questions),
      lines: usable.map((line, index) => ({
        id: line.id || `line-${index + 1}`,
        section: line.section.trim() || "Основные работы",
        description: line.description.trim(),
        category: line.category,
        unit: line.unit.trim() || "шт",
        quantity: String(Math.max(Number(line.quantity) || 0, 0.000001)),
        unit_price_minor: Math.round(Math.max(Number(line.price) || 0, 0) * (10 ** minorUnit)),
        provenance: line.provenance || { source: "manual" },
      })),
      overhead_rate_bps: Math.round(Math.max(Number(overhead) || 0, 0) * 100),
      tax_rate_bps: Math.round(Math.max(Number(tax) || 0, 0) * 100),
      estimate_id: payload.persistence?.estimate_id || null,
      estimate_base_version: payload.persistence?.version || null,
    });
  };

  return (
    <div className="estimate-workspace">
      <div className="estimate-heading">
        <div>
          <span>{payload.persistence?.state === "saved" ? `Версия ${payload.persistence.version} сохранена` : "Детерминированный расчёт"}</span>
          <input aria-label="Название сметы" onChange={(event) => setTitle(event.target.value)} value={title} />
        </div>
        <div><small>Итого</small><strong>{formatRubles(calculation?.totals?.grand_total_minor)}</strong></div>
      </div>
      <div className="estimate-table">
        <div className="estimate-row estimate-row-head">
          <span>Тип</span><span>Раздел и позиция</span><span>Ед.</span><span>Кол-во</span><span>Цена, ₽</span><span />
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
            </span>
            <input aria-label="Единица" onChange={(event) => patchLine(line.id, { unit: event.target.value })} value={line.unit} />
            <input aria-label="Количество" min="0.000001" onChange={(event) => patchLine(line.id, { quantity: event.target.value })} step="0.01" type="number" value={line.quantity} />
            <input aria-label="Цена" min="0" onChange={(event) => patchLine(line.id, { price: event.target.value, provenance: { source: "manual", source_ref: "Изменено пользователем" } })} step="0.01" type="number" value={line.price} />
            <button aria-label="Удалить позицию" onClick={() => removeLine(line.id)} type="button"><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
      <div className="estimate-controls">
        <button onClick={() => setLines((current) => [...current, newEstimateLine(current.length + 1)])} type="button">
          <Plus size={17} /> Добавить позицию
        </button>
        <label>Накладные, %<input min="0" onChange={(event) => setOverhead(event.target.value)} step="0.01" type="number" value={overhead} /></label>
        <label>Налог, %<input min="0" onChange={(event) => setTax(event.target.value)} step="0.01" type="number" value={tax} /></label>
        <button className="primary-action" disabled={busy || !lines.some((line) => line.description.trim())} onClick={submit} type="button">
          {busy ? "Сохраняю…" : "Сохранить и PDF"}
        </button>
      </div>
      {calculation && (
        <div className="estimate-summary">
          <span>Работы и материалы <strong>{formatRubles(calculation.totals.subtotal_minor)}</strong></span>
          <span>Накладные <strong>{formatRubles(calculation.totals.overhead_minor)}</strong></span>
          <span>Налог <strong>{formatRubles(calculation.totals.tax_minor)}</strong></span>
          <span>Итого <strong>{formatRubles(calculation.totals.grand_total_minor)}</strong></span>
        </div>
      )}
      <details className="estimate-notes">
        <summary>Допущения и вопросы</summary>
        <div>
          <label>Допущения<textarea onChange={(event) => setAssumptions(event.target.value)} placeholder="По одному допущению в строке" value={assumptions} /></label>
          <label>Нужно уточнить<textarea onChange={(event) => setQuestions(event.target.value)} placeholder="По одному вопросу в строке" value={questions} /></label>
        </div>
      </details>
      {payload.error && <div className="inline-error">{payload.error}</div>}
    </div>
  );
}
