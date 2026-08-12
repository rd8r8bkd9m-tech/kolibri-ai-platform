import Link from "next/link";
import { ArrowRight, Check, FileStack, ShieldCheck, Smartphone } from "lucide-react";
import { ProductPreview } from "./product-preview";

export function LandingHero() {
	return (
		<section className="kp-hero kp-section" aria-labelledby="hero-title">
			<div className="kp-container kp-hero-grid">
				<div className="kp-hero-copy">
					<p className="kp-eyebrow"><span /> AI-сметчик для строительства</p>
					<h1 id="hero-title">
						Один агент на <em>смету, документы и рутину.</em>
					</h1>
					<p className="kp-hero-lead">
						Опишите объект обычным языком — КолИ соберёт версионную смету,
						подготовит КП, договор и акты по вашим данным и не потеряет
						ни одной редакции расчёта.
					</p>
					<div className="kp-hero-metrics" role="list" aria-label="Ключевые возможности текущего рабочего контура">
						<p role="listitem"><FileStack aria-hidden="true" /> Сметы и документы в одном проекте</p>
						<p role="listitem"><ShieldCheck aria-hidden="true" /> Платежи через Т-Банк</p>
						<p role="listitem"><Smartphone aria-hidden="true" /> Процесс в одном экране</p>
					</div>
					<div className="kp-hero-actions">
						<Link className="kp-button kp-button-primary" href="/app">
							Попробовать бесплатно <ArrowRight aria-hidden="true" />
						</Link>
						<Link className="kp-button kp-button-secondary" href="/pricing#plans">
							Посмотреть тарифы
						</Link>
					</div>
					<ul className="kp-hero-claims" aria-label="Ключевые возможности">
						<li><Check /> Смета по исходным данным</li>
						<li><Check /> Связанные документы</li>
						<li><Check /> Версии и основания</li>
					</ul>
				</div>
				<ProductPreview />
			</div>
		</section>
	);
}
