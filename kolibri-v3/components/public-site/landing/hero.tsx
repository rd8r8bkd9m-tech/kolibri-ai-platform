import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
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
						Kolibri AI собирает исходные данные, формирует версионную смету
						и помогает подготовить КП, договор и акты в одном проекте.
					</p>
					<div className="kp-hero-actions">
						<Link className="kp-button kp-button-primary" href="/app">
							Открыть Kolibri <ArrowRight aria-hidden="true" />
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
