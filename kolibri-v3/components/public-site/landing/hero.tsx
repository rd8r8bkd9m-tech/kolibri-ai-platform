import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { HeroStage } from "./hero-stage";

export function LandingHero() {
	return (
		<section className="klp-hero" aria-labelledby="hero-title">
			<div className="klp-hero-inner">
				<h1 className="klp-hero-title" id="hero-title">
					Один агент на{" "}
					<span className="klp-hero-word">смету</span>,{" "}
					<span className="klp-hero-word">документы</span> и{" "}
					<span className="klp-hero-word">рутину</span>
				</h1>
				<div className="klp-hero-cta-row">
					<Link className="klp-cta-pill" href="/app">
						Попробовать бесплатно <ArrowRight aria-hidden="true" />
					</Link>
					<Link className="klp-hero-link" href="/pricing">
						Посмотреть тарифы
					</Link>
				</div>
				<HeroStage />
			</div>
		</section>
	);
}
