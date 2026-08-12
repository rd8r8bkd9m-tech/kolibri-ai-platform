import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { HeroStage } from "./hero-stage";

function HeroWord({ word, delay }: { word: string; delay: number }) {
	return (
		<span className="klp-hero-word" aria-label={word}>
			{word.split("").map((letter, index) => (
				<span
					className="klp-hero-letter"
					key={`${word}-${index}`}
					style={{ animationDelay: `${delay + index * 0.035}s` }}
				>
					{letter}
				</span>
			))}
		</span>
	);
}

export function LandingHero() {
	return (
		<section className="klp-hero" aria-labelledby="hero-title">
			<div className="klp-hero-inner">
				<h1 className="klp-hero-title" id="hero-title">
					Один агент на{" "}
					<HeroWord word="смету" delay={0.15} />,{" "}
					<HeroWord word="документы" delay={0.42} /> и{" "}
					<HeroWord word="рутину" delay={0.9} />
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
