import { useState } from "react"
import { motion } from "framer-motion"

export function EstimateEditor({ estimate, onClose, onSave }) {
  const [data, setData] = useState(estimate || {
    title: "Новая смета",
    client: { name: "", phone: "", address: "" },
    object: { type: "", area: 0, location: "" },
    items: [],
    totals: { works: 0, materials: 0, delivery: 0, discount: 0, grand_total: 0 },
    version: 1,
  })

  const [editingItem, setEditingItem] = useState(null)
  const [exporting, setExporting] = useState(false)

  const recalculate = (items) => {
    const works = items.filter(i => i.section === "Работы").reduce((s, i) => s + (i.total || 0), 0)
    const materials = items.filter(i => i.section === "Материалы").reduce((s, i) => s + (i.total || 0), 0)
    const delivery = data.totals?.delivery || 0
    const discount = data.totals?.discount || 0
    const grand_total = works + materials + delivery - discount
    return { works, materials, delivery, discount, grand_total }
  }

  const updateItem = (index, field, value) => {
    const newItems = [...data.items]
    newItems[index] = { ...newItems[index], [field]: value }
    if (field === "quantity" || field === "unit_price") {
      newItems[index].total = (newItems[index].quantity || 0) * (newItems[index].unit_price || 0)
    }
    setData({ ...data, items: newItems, totals: recalculate(newItems) })
  }

  const addItem = (section = "Работы") => {
    const newItem = {
      id: `item_${Date.now()}`,
      section,
      name: "",
      unit: "м2",
      quantity: 0,
      unit_price: 0,
      total: 0,
      note: "",
    }
    const newItems = [...data.items, newItem]
    setData({ ...data, items: newItems, totals: recalculate(newItems) })
    setEditingItem(newItems.length - 1)
  }

  const removeItem = (index) => {
    const newItems = data.items.filter((_, i) => i !== index)
    setData({ ...data, items: newItems, totals: recalculate(newItems) })
    setEditingItem(null)
  }

  const handleSave = () => {
    if (onSave) onSave(data)
    if (onClose) onClose()
  }

  const handleExport = async (format) => {
    setExporting(true)
    try {
      const endpoint = format === "docx" ? "/api/documents/estimate/docx" : "/api/documents/estimate/pdf"
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
      const result = await r.json()
      if (result.filename) {
        window.open(`/api/documents/file/${result.filename}`, "_blank")
      }
    } catch (e) {
      console.error("Export failed:", e)
    }
    setExporting(false)
  }

  const formatNum = (n) => (n || 0).toLocaleString("ru-RU")

  return (
    <div className="estimate-editor">
      <div className="estimate-editor-header">
        <div>
          <h2 className="estimate-editor-title">{data.title || "Смета"}</h2>
          <div className="estimate-editor-meta">
            {data.client?.name && <span>Клиент: {data.client.name}</span>}
            {data.object?.area > 0 && <span>Площадь: {data.object.area} м²</span>}
            <span>v{data.version || 1}</span>
          </div>
        </div>
        <div className="estimate-editor-actions">
          <button className="estimate-btn" onClick={() => handleExport("pdf")} disabled={exporting}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/>
            </svg>
            PDF
          </button>
          <button className="estimate-btn" onClick={() => handleExport("docx")} disabled={exporting}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/>
            </svg>
            DOCX
          </button>
          <button className="estimate-btn estimate-btn-save" onClick={handleSave}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17,21 17,13 7,13 7,21"/><polyline points="7,3 7,8 15,8"/>
            </svg>
            Сохранить
          </button>
        </div>
      </div>

      <div className="estimate-editor-body">
        <div className="estimate-editor-toolbar">
          <button className="estimate-btn" onClick={() => addItem("Работы")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Добавить работу
          </button>
          <button className="estimate-btn" onClick={() => addItem("Материалы")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Добавить материал
          </button>
        </div>

        <div className="estimate-table-wrapper">
          <table className="estimate-table">
            <thead>
              <tr>
                <th className="estimate-th-num">№</th>
                <th className="estimate-th-name">Наименование</th>
                <th className="estimate-th-unit">Ед.</th>
                <th className="estimate-th-qty">Кол-во</th>
                <th className="estimate-th-price">Цена</th>
                <th className="estimate-th-total">Сумма</th>
                <th className="estimate-th-actions"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item, i) => (
                <motion.tr
                  key={item.id || i}
                  className={`estimate-row ${editingItem === i ? "editing" : ""}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.02 }}
                >
                  <td className="estimate-td-num">{i + 1}</td>
                  <td className="estimate-td-name">
                    {editingItem === i ? (
                      <input
                        className="estimate-input"
                        value={item.name}
                        onChange={e => updateItem(i, "name", e.target.value)}
                        placeholder="Наименование"
                        autoFocus
                      />
                    ) : (
                      <span onClick={() => setEditingItem(i)}>{item.name || "—"}</span>
                    )}
                  </td>
                  <td className="estimate-td-unit">
                    {editingItem === i ? (
                      <select className="estimate-input estimate-select" value={item.unit} onChange={e => updateItem(i, "unit", e.target.value)}>
                        {["м2", "м3", "м.п", "шт", "кг", "л", "упак", "час", "компл"].map(u => (
                          <option key={u} value={u}>{u}</option>
                        ))}
                      </select>
                    ) : (
                      <span onClick={() => setEditingItem(i)}>{item.unit}</span>
                    )}
                  </td>
                  <td className="estimate-td-qty">
                    {editingItem === i ? (
                      <input
                        className="estimate-input estimate-input-num"
                        type="number"
                        value={item.quantity}
                        onChange={e => updateItem(i, "quantity", parseFloat(e.target.value) || 0)}
                      />
                    ) : (
                      <span onClick={() => setEditingItem(i)}>{item.quantity}</span>
                    )}
                  </td>
                  <td className="estimate-td-price">
                    {editingItem === i ? (
                      <input
                        className="estimate-input estimate-input-num"
                        type="number"
                        value={item.unit_price}
                        onChange={e => updateItem(i, "unit_price", parseFloat(e.target.value) || 0)}
                      />
                    ) : (
                      <span onClick={() => setEditingItem(i)}>{formatNum(item.unit_price)} ₽</span>
                    )}
                  </td>
                  <td className="estimate-td-total">{formatNum(item.total)} ₽</td>
                  <td className="estimate-td-actions">
                    <button className="estimate-btn-icon" onClick={() => removeItem(i)}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                      </svg>
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>

        {data.items.length === 0 && (
          <div className="estimate-empty">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.3 }}>
              <path d="M9 7h6m-6 4h6m-3-8v12M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z"/>
            </svg>
            <p>Нет позиций</p>
            <p className="estimate-empty-hint">Добавьте работы или материалы</p>
          </div>
        )}

        <div className="estimate-totals">
          <div className="estimate-total-row">
            <span>Работы</span>
            <span>{formatNum(data.totals?.works)} ₽</span>
          </div>
          <div className="estimate-total-row">
            <span>Материалы</span>
            <span>{formatNum(data.totals?.materials)} ₽</span>
          </div>
          {data.totals?.delivery > 0 && (
            <div className="estimate-total-row">
              <span>Доставка</span>
              <span>{formatNum(data.totals?.delivery)} ₽</span>
            </div>
          )}
          {data.totals?.discount > 0 && (
            <div className="estimate-total-row discount">
              <span>Скидка</span>
              <span>-{formatNum(data.totals?.discount)} ₽</span>
            </div>
          )}
          <div className="estimate-total-row grand">
            <span>ИТОГО</span>
            <span>{formatNum(data.totals?.grand_total)} ₽</span>
          </div>
        </div>
      </div>
    </div>
  )
}
