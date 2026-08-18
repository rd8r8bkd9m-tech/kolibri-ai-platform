import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Reveal } from "./reveal";

export function FinalCtaSection() {
	return (
		<section className="klp-final-cta" aria-labelledby="final-cta-title">
			<div className="klp-final-cta-inner">
				<Reveal>
					<h2 id="final-cta-title">Попробуйте агента на своей задаче</h2>
					<p>
						Опишите объект или загрузите файл — первая смета и документы
						соберутся в чате без карты.
					</p>
					<div className="klp-hero-cta-row">
						<Link className="klp-cta-pill" href="/app">
							Попробовать бесплатно <ArrowRight aria-hidden="true" />
						</Link>
						<Link className="klp-hero-link" href="/contacts">
							Записаться на демо
						</Link>
					</div>
				</Reveal>
			</div>
		</section>
	);
}
