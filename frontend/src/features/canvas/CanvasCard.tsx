import { motion } from 'framer-motion';
import type { CanvasCard as CanvasCardType } from '../../shared/types';

interface CanvasCardProps {
  card: CanvasCardType;
  onAction?: (action: string, card: CanvasCardType) => void;
}

const cardIcons: Record<string, string> = {
  estimate: 'M9 7h6m-6 4h6m-3-8v12M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z',
  document: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6',
  table: 'M3 3h18v18H3z M3 9h18 M3 15h18 M9 3v18',
  code: 'M16 18l6-6-6-6 M8 6l-6 6 6 6',
  plan: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2 M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
  checklist: 'M9 11l3 3L22 4 M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11',
  memory: 'M12 2a10 10 0 100 20 10 10 0 000-20z M12 6v6l4 2',
  action: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
};

export function CanvasCard({ card, onAction }: CanvasCardProps) {
  const iconPath = cardIcons[card.type] || cardIcons.action;
  const isClickable = card.type === 'estimate';

  const handleCardClick = () => {
    if (isClickable) onAction?.('edit', card);
  };

  return (
    <motion.div
      className={`canvas-card${isClickable ? ' canvas-card--clickable' : ''}`}
      onClick={handleCardClick}
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, type: 'spring', stiffness: 200 }}
      whileHover={isClickable ? { scale: 1.01, y: -2 } : undefined}
    >
      <div className="canvas-card__header">
        <div className="canvas-card__icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={iconPath} />
          </svg>
        </div>
        <div>
          <div className="canvas-card__eyebrow">{card.type.toUpperCase()}</div>
          <div className="canvas-card__title">{card.title}</div>
        </div>
      </div>

      <div className="canvas-card__body">
        {card.type === 'estimate' && <EstimatePreview data={card.data} />}
        {card.type === 'document' && <DocumentPreview data={card.data} />}
        {card.type === 'checklist' && <ChecklistPreview data={card.data} />}
        {card.type === 'plan' && <PlanPreview data={card.data} />}
        {card.type === 'code' && <CodePreview data={card.data} />}
        {card.type === 'memory' && <MemoryPreview data={card.data} />}
        {card.type === 'table' && <TablePreview data={card.data} />}
        {card.type === 'action' && <ActionPreview data={card.data} />}
      </div>

      <div className="canvas-card__footer">
        {card.status && (
          <span className={`trace-badge trace-badge--${card.status === 'ready' ? 'green' : 'yellow'}`}>
            {card.status}
          </span>
        )}
        <button className="canvas-card__export" onClick={() => onAction?.('export', card)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M7 10l5 5 5-5 M12 15V3" />
          </svg>
          Экспорт
        </button>
      </div>
    </motion.div>
  );
}

function EstimatePreview({ data }: { data: any }) {
  if (!data?.items) return <div className="canvas-block">Нет данных сметы</div>;
  
  const total = data.totals?.grand_total || data.items.reduce((s: number, i: any) => s + (i.total || 0), 0);
  
  return (
    <>
      <div className="canvas-block canvas-block--heading">{data.title || 'Смета'}</div>
      {data.client?.name && (
        <div className="canvas-block">
          <strong>Клиент:</strong> {data.client.name}
        </div>
      )}
      <div className="canvas-block">
        <table style={{ width: '100%', fontSize: '0.82rem', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(var(--foreground), 0.1)' }}>
              <th style={{ textAlign: 'left', padding: '4px 8px', fontWeight: 600 }}>Работа</th>
              <th style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600 }}>Кол-во</th>
              <th style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600 }}>Цена</th>
              <th style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600 }}>Сумма</th>
            </tr>
          </thead>
          <tbody>
            {data.items.slice(0, 5).map((item: any, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid rgba(var(--foreground), 0.05)' }}>
                <td style={{ padding: '4px 8px' }}>{item.name}</td>
                <td style={{ textAlign: 'right', padding: '4px 8px' }}>{item.quantity} {item.unit}</td>
                <td style={{ textAlign: 'right', padding: '4px 8px' }}>{item.unit_price?.toLocaleString()} ₽</td>
                <td style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600 }}>{item.total?.toLocaleString()} ₽</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.items.length > 5 && (
          <div style={{ textAlign: 'center', padding: '4px', color: 'rgb(var(--muted))', fontSize: '0.78rem' }}>
            +{data.items.length - 5} позиций
          </div>
        )}
      </div>
      <div className="canvas-block" style={{ fontWeight: 700, fontSize: '1rem' }}>
        Итого: {total.toLocaleString()} ₽
      </div>
    </>
  );
}

function DocumentPreview({ data }: { data: any }) {
  return (
    <>
      <div className="canvas-block canvas-block--heading">{data?.title || 'Документ'}</div>
      {data?.content && (
        <div className="canvas-block" style={{ maxHeight: '120px', overflow: 'hidden' }}>
          {typeof data.content === 'string' ? data.content.slice(0, 200) : JSON.stringify(data.content).slice(0, 200)}...
        </div>
      )}
    </>
  );
}

function ChecklistPreview({ data }: { data: any }) {
  const items = data?.items || [];
  return (
    <div className="canvas-block canvas-block--checklist">
      {items.map((item: any, i: number) => (
        <li key={i}>
          <div className="canvas-check-dot" />
          <span>{typeof item === 'string' ? item : item.text}</span>
        </li>
      ))}
    </div>
  );
}

function PlanPreview({ data }: { data: any }) {
  const steps = data?.steps || [];
  return (
    <>
      {steps.map((step: any, i: number) => (
        <div key={i} className="canvas-block">
          <strong>{i + 1}.</strong> {typeof step === 'string' ? step : step.title}
        </div>
      ))}
    </>
  );
}

function CodePreview({ data }: { data: any }) {
  return (
    <div className="canvas-block canvas-block--code">
      <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
        {data?.code || data?.content || '// Код'}
      </pre>
    </div>
  );
}

function MemoryPreview({ data }: { data: any }) {
  return (
    <div className="memory-card">
      <div className="memory-card__label">ПАМЯТЬ</div>
      <div className="memory-card__text">{data?.content || data?.text}</div>
      {data?.reason && <div className="memory-card__reason">{data.reason}</div>}
    </div>
  );
}

function TablePreview({ data }: { data: any }) {
  if (!data?.columns || !data?.rows) return <div className="canvas-block">Нет данных таблицы</div>;
  return (
    <div className="canvas-block" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', fontSize: '0.82rem', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {data.columns.map((col: string, i: number) => (
              <th key={i} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '2px solid rgba(var(--foreground), 0.1)', fontWeight: 600 }}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row: any[], i: number) => (
            <tr key={i}>
              {row.map((cell: any, j: number) => (
                <td key={j} style={{ padding: '4px 8px', borderBottom: '1px solid rgba(var(--foreground), 0.05)' }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActionPreview({ data }: { data: any }) {
  return (
    <div className="canvas-block">
      {data?.description || data?.text || 'Действие'}
    </div>
  );
}
