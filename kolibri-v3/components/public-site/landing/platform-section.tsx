import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function PlatformSection() {
	return (
		<section className="kp-platform kp-section" aria-labelledby="platform-title">
			<div className="kp-container kp-platform-card">
				<div>
					<p className="kp-eyebrow"><span /> Универсальная платформа</p>
					<h2 id="platform-title">Строительство — первый коммерческий вертикальный контур.</h2>
				</div>
				<div>
					<p>
						КолИ строится как серверная агентная среда: интерфейс показывает доступные
						пользователю модели, инструменты и документы из динамической конфигурации.
						Та же основа может поддерживать другие отраслевые процессы без отдельного продукта с нуля.
					</p>
					<Link className="kp-button kp-button-light" href="/app">
						Перейти в приложение <ArrowRight aria-hidden="true" />
					</Link>
				</div>
			</div>
		</section>
	);
}
