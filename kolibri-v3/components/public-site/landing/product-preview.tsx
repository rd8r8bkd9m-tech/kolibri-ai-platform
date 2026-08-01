import {
	Check,
	FileCheck2,
	FileText,
	FolderKanban,
	MessageSquareText,
} from "lucide-react";

const estimateRows = [
	["Подготовка основания", "м²", "38"],
	["Возведение стен", "м³", "12,4"],
	["Устройство кровли", "м²", "54"],
] as const;

export function ProductPreview() {
	return (
		<div className="kp-product-stage" aria-label="Интерфейс строительного проекта Kolibri AI">
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
						<span className="is-active"><MessageSquareText /></span>
						<span><FolderKanban /></span>
						<span><FileText /></span>
					</aside>
					<div className="kp-product-content">
						<div className="kp-product-heading">
							<div>
								<p>СМЕТА · ВЕРСИЯ 3</p>
								<h2>Строительство одноэтажного дома</h2>
							</div>
							<span><Check /> проверено</span>
						</div>
						<div className="kp-estimate-card">
							<div className="kp-estimate-head">
								<strong>Работы и материалы</strong>
								<small>основания сохранены</small>
							</div>
							{estimateRows.map(([name, unit, quantity]) => (
								<div className="kp-estimate-row" key={name}>
									<span>{name}</span>
									<small>{quantity} {unit}</small>
								</div>
							))}
							<div className="kp-estimate-total">
								<span>Итог проекта</span>
								<strong>рассчитан по версии</strong>
							</div>
						</div>
						<div className="kp-document-flow" aria-label="Связанные документы">
							<span><FileText /> КП</span>
							<i aria-hidden="true" />
							<span><FileText /> Договор</span>
							<i aria-hidden="true" />
							<span><FileCheck2 /> Акт</span>
						</div>
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
