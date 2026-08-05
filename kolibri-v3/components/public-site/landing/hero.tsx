import Link from "next/link";
import { ArrowRight, Check, Globe, ShieldCheck, Smartphone } from "lucide-react";
import { ProductPreview } from "./product-preview";

export function LandingHero() {
	return (
		<section className="kp-hero kp-section" aria-labelledby="hero-title">
			<div className="kp-container kp-hero-grid">
				<div className="kp-hero-copy">
					<p className="kp-eyebrow"><span /> AI для сметного дела и строительства</p>
					<h1 id="hero-title">
						От описания объекта — к <em>смете и документам.</em>
					</h1>
					<p className="kp-hero-lead">
						КолИ собирает исходные данные, формирует версионную смету
						и помогает подготовить КП, договор и акты в одном проекте.
					</p>
					<div className="kp-hero-metrics" role="list" aria-label="Ключевые возможности текущего рабочего контура">
						<p role="listitem"><Globe aria-hidden="true" /> Работа на kolibriai.ru</p>
						<p role="listitem"><ShieldCheck aria-hidden="true" /> Платежи через Т-Банк</p>
						<p role="listitem"><Smartphone aria-hidden="true" /> Процесс в одном экране</p>
					</div>
					<div className="kp-hero-actions">
						<Link className="kp-button kp-button-primary" href="/app">
							Открыть КолИ <ArrowRight aria-hidden="true" />
						</Link>
						<Link className="kp-button kp-button-secondary" href="/pricing#plans">
							Посмотреть тариф
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
