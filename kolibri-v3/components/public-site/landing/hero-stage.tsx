"use client";

import {
	ClipboardList,
	FileCheck2,
	FileText,
	Send,
} from "lucide-react";

const chips = ["ФСНБ-2022", "ГЭСН", "ФГИС ЦС"];

export function HeroStage() {
	return (
		<div className="klp-hero-stage" aria-label="Демонстрация работы агента КолИ">
			<div className="klp-stage">
				<div className="klp-stage-content">
					<div className="klp-stage-topbar">
						<div className="klp-stage-dots" aria-hidden="true">
							<i />
							<i />
							<i />
						</div>
						<span className="klp-stage-status">
							<i /> агент в сети
						</span>
					</div>
					<div className="klp-chat">
						<div className="klp-msg klp-msg-user">
							<div className="klp-bubble">
								Загляни в{" "}
								{chips.map((chip) => (
									<span className="klp-chip" key={chip}>
										<span className="klp-chip-dot" aria-hidden="true" />
										{chip}
									</span>
								))}{" "}
								и собери смету на каркасный дом 38 м² в Москве
							</div>
						</div>
						<div className="klp-msg">
							<div className="klp-ai-body">
								<strong>
									Смета готова — 2 840 000 ₽. Это версия 3, предыдущие расчёты сохранены.
								</strong>
								<ul>
									<li><strong>Работы</strong> — 1 420 000 ₽</li>
									<li><strong>Материалы</strong> — 1 130 000 ₽</li>
									<li><strong>Накладные и резерв</strong> — 290 000 ₽</li>
								</ul>
								<p>Полный расчёт приложил. Разложить по разделам?</p>
								<div className="klp-file-card" style={{ marginTop: "0.8rem" }}>
									<span className="klp-file-icon"><FileText aria-hidden="true" /></span>
									<span className="klp-file-meta">
										<strong>Смета · версия 3</strong>
										<span>Документ · XLSX</span>
									</span>
								</div>
							</div>
						</div>
					</div>
					<div className="klp-composer">
						<input aria-label="Вопрос агенту" placeholder="Уточните электрику и тёплые полы…" />
						<button className="klp-send" type="button" aria-label="Отправить">
							<Send aria-hidden="true" />
						</button>
					</div>
				</div>
			</div>
			<div className="klp-float-pill klp-pill-a">
				<span><ClipboardList aria-hidden="true" /></span>
				<p>Смета создана<small>каждое изменение — версия</small></p>
			</div>
			<div className="klp-float-pill klp-pill-b">
				<span><FileText aria-hidden="true" /></span>
				<p>КП готов<small>черновик договора</small></p>
			</div>
			<div className="klp-float-pill klp-pill-c">
				<span><FileCheck2 aria-hidden="true" /></span>
				<p>Акт выполненных работ<small>в работе</small></p>
			</div>
		</div>
	);
}
