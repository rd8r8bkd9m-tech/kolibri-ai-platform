"use client";

import {
	Check,
	CircleHelp,
	FileCheck2,
	FileText,
	FolderKanban,
	MessageSquareText,
	Send,
	ShoppingBag,
	UserRound,
	Wrench,
} from "lucide-react";
import { useState } from "react";

type EstimateRow = {
	name: string;
	unit: string;
	quantity: string;
};

type DocumentItem = {
	label: string;
	statusLabel: string;
	statusKey: "ready" | "draft" | "working";
	icon: typeof FileText | typeof FileCheck2;
};

type PreviewView = "chat" | "estimate" | "documents" | "payment";

const baseEstimateRows: EstimateRow[] = [
	{ name: "Подготовка основания", unit: "м²", quantity: "38" },
	{ name: "Возведение стен", unit: "м³", quantity: "12,4" },
	{ name: "Устройство кровли", unit: "м²", quantity: "54" },
];

const initialDocumentCards: readonly DocumentItem[] = [
	{ label: "Коммерческое предложение", statusLabel: "готово", statusKey: "ready", icon: FileText },
	{ label: "Договор", statusLabel: "черновик", statusKey: "draft", icon: FileText },
	{ label: "Акт выполненных работ", statusLabel: "в работе", statusKey: "working", icon: FileCheck2 },
];

const views: { id: PreviewView; label: string; icon: typeof MessageSquareText }[] = [
	{
		id: "chat",
		label: "Чат проекта",
		icon: MessageSquareText,
	},
	{
		id: "estimate",
		label: "Смета",
		icon: FolderKanban,
	},
	{
		id: "documents",
		label: "Документы",
		icon: FileText,
	},
	{
		id: "payment",
		label: "Платеж",
		icon: ShoppingBag,
	},
];

const conversation = [
	{ from: "Клиент", text: "Проект дома 1 этажа, площадь 38 м², каркасный вариант." },
	{ from: "КолИ", text: "Принято. Уточните регион, этажность и требования к отоплению." },
	{ from: "Клиент", text: "Москва, высота 5,8 м, тёплое покрытие пола и тёплая кровля." },
];

export function ProductPreview() {
	const [view, setView] = useState<PreviewView>("chat");
	const [rows, setRows] = useState<EstimateRow[]>(baseEstimateRows);
	const [documents, setDocuments] = useState<DocumentItem[]>([...initialDocumentCards]);
	const [chatInput, setChatInput] = useState("Добавьте требования по электрике");
	const [paymentState, setPaymentState] = useState<"idle" | "initiated" | "confirmed">("idle");
	const [flow, setFlow] = useState(26);

	const ActiveIcon = views.find((item) => item.id === view)?.icon ?? MessageSquareText;
	const statusText = paymentState === "idle" ? "ожидает инициирования" : paymentState === "initiated" ? "переход в банк" : "CONFIRMED";

	const updateFlow = (next: number) => setFlow(Math.max(0, Math.min(100, next)));

	function submitChatPrompt() {
		if (!chatInput.trim()) {
			return;
		}
		setFlow(44);
		setChatInput("");
	}

	function addEstimateRow() {
		setRows((current) => [
			...current,
			{ name: `Доп. позиция ${current.length - baseEstimateRows.length + 1}`, unit: "п.м.", quantity: "8" },
		]);
		setFlow((current) => Math.min(100, current + 8));
	}

	function finalizeDocuments() {
		setDocuments((current) =>
			current.map((item) => ({
				...item,
				statusLabel: "готово",
				statusKey: "ready",
			})),
		);
		setFlow((current) => Math.min(100, current + 18));
	}

	function togglePaymentDemo() {
		if (paymentState === "idle") {
			setPaymentState("initiated");
			updateFlow(56);
			return;
		}
		if (paymentState === "initiated") {
			setPaymentState("confirmed");
			updateFlow(100);
			return;
		}
		setPaymentState("idle");
		updateFlow(26);
	}

	return (
		<div className="kp-product-stage" aria-label="Интерфейс строительного проекта КолИ">
			<div className="kp-product-glow" aria-hidden="true" />
			<article className="kp-product-window">
				<header className="kp-window-bar">
					<div className="kp-window-dots" aria-hidden="true">
						<i />
						<i />
						<i />
					</div>
					<span>Дом · 38 м²</span>
					<span className="kp-live-status">
						<i /> проект активен
					</span>
				</header>
				<div className="kp-product-body">
					<aside className="kp-product-rail" aria-hidden="true">
						<div className="kp-product-tabbar" role="tablist" aria-label="Переключение блоков проекта">
							{views.map(({ id, icon: Icon, label }) => (
								<button
									className={`kp-product-tab ${view === id ? "is-active" : ""}`}
									type="button"
									key={id}
									role="tab"
									aria-selected={view === id}
									onClick={() => setView(id)}
								>
									<Icon aria-hidden="true" />
									<span>{label}</span>
								</button>
							))}
						</div>
					</aside>
					<div className="kp-product-content">
						<div className="kp-product-heading">
							<div>
								<p>СЛОЖНЫЙ ПРОЕКТ · {view === "chat" ? "ДИАЛОГ" : view === "estimate" ? "ВЕРСИЯ 3" : "ДОКУМЕНТЫ"}</p>
								<h2>Строительство одноэтажного дома</h2>
							</div>
							<span><ActiveIcon aria-hidden="true" /> {view === "chat" ? "вопрос/ответ" : view === "payment" ? "платеж" : "проверено"}</span>
						</div>
						<div className="kp-product-panel">
							{view === "chat" ? (
								<>
									<div className="kp-chat-log">
										{conversation.map((message) => (
											<div key={`${message.from}:${message.text}`} className="kp-chat-row">
												<small>{message.from}</small>
												<p>{message.text}</p>
											</div>
										))}
									</div>
									<div className="kp-chat-input">
										<input value={chatInput} onChange={(event) => setChatInput(event.currentTarget.value)} aria-label="Черновик следующего ввода" />
										<button type="button" aria-label="Отправить ввод" onClick={submitChatPrompt}>
											<Send />
										</button>
									</div>
								</>
							) : view === "estimate" ? (
								<div className="kp-estimate-card">
									<div className="kp-estimate-head">
										<strong>Работы и материалы</strong>
										<small>основания сохранены</small>
									</div>
									{rows.map((item) => (
										<div className="kp-estimate-row" key={item.name}>
											<span>
												<CircleHelp aria-hidden="true" />
												{item.name}
											</span>
											<small>{item.quantity} {item.unit}</small>
										</div>
									))}
									<div className="kp-estimate-total">
										<span>Итог проекта</span>
										<strong>рассчитан по версии</strong>
									</div>
									<button className="kp-estimate-row kp-row-add" type="button" onClick={addEstimateRow}>
										<span><Wrench aria-hidden="true" /> добавить позицию</span>
										<small>черновик</small>
									</button>
								</div>
							) : view === "documents" ? (
								<div className="kp-document-list">
									{documents.map((doc) => (
										<div className="kp-document-item" key={doc.label}>
											<span><doc.icon aria-hidden="true" /> {doc.label}</span>
											<span className={`kp-document-state is-${doc.statusKey}`}>
												<UserRound aria-hidden="true" /> {doc.statusLabel}
											</span>
										</div>
									))}
									<button type="button" className="kp-document-export" aria-label="Сформировать все документы" onClick={finalizeDocuments}>
										<FileCheck2 aria-hidden="true" />
										Сформировать пакет
									</button>
								</div>
							) : (
								<div className="kp-payment-preview">
									<div className="kp-payment-head">
										<p><Check aria-hidden="true" /> Сбор платежа в Т‑Банк</p>
										<span>Переход на защищенную форму банка</span>
									</div>
									<div className="kp-payment-grid">
										<p><strong>Счёт:</strong> Доступ на 30 дней</p>
										<p><strong>Сумма:</strong> 4 990 ₽</p>
										<p><strong>Статус:</strong> {statusText}</p>
										<p><strong>Методы:</strong> Карта, СБП, T‑Pay</p>
									</div>
									<button
										type="button"
										className="kp-document-export kp-document-export-wide"
										aria-label="Симулировать платёж"
										onClick={togglePaymentDemo}
									>
										<FileCheck2 aria-hidden="true" />
										{paymentState === "idle" ? "Открыть страницу банка" : paymentState === "initiated" ? "Подтвердить оплату" : "Сбросить симуляцию"}
									</button>
									<p className="kp-panel-hint is-muted">
										<Check aria-hidden="true" /> Доступ включится после статуса CONFIRMED.
									</p>
								</div>
							)}
						</div>
						<div className="kp-document-flow" aria-label="Связанные документы">
							{view === "documents" ? (
								<>
									<span><Check /> Сформировано</span>
									<i aria-hidden="true" />
									<span><Check /> Проверено</span>
								</>
							) : (
								<>
									<span><FileText /> КП</span>
									<i aria-hidden="true" />
									<span><FileText /> Договор</span>
									<i aria-hidden="true" />
									<span><FileCheck2 /> Акт</span>
								</>
							)}
						</div>
						<div className="kp-preview-progress" aria-label="Прогресс контура">
							<span>Прогресс сборки</span>
							<div className="kp-progress-track">
								<div className="kp-progress-value" style={{ width: `${flow}%` }} />
							</div>
						</div>
						<p className="kp-panel-hint">
							<Check aria-hidden="true" />
							{view === "chat"
								? "Данные зафиксированы и можно переходить к смете."
								: view === "payment"
									? "Переход в банк не меняет проект и не требует повторного ввода данных."
									: "Операция выполнена без переключения контекста."}
						</p>
					</div>
				</div>
			</article>
			<div className="kp-floating-note kp-note-version">
				<span>V3</span>
				<p><strong>Пересчёт готов</strong><small>изменения учтены</small></p>
			</div>
			<div className="kp-floating-note kp-note-proof">
				<span><Check /></span>
				<p><strong>Основание сохранено</strong><small>источник связан со строкой</small></p>
			</div>
		</div>
	);
}
