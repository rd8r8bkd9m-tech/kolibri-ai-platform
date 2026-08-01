import type { ReactNode } from "react";
import type { PublicCommerceConfig } from "@/lib/server/public-commerce";

export function LegalPage({
	children,
	commerce,
	eyebrow,
	lead,
	title,
}: {
	children: ReactNode;
	commerce: PublicCommerceConfig;
	eyebrow: string;
	lead: string;
	title: string;
}) {
	return (
		<article className="kp-legal-page kp-section">
			<div className="kp-container kp-legal-layout">
				<header className="kp-legal-header">
					<p className="kp-eyebrow kp-eyebrow-dark"><span /> {eyebrow}</p>
					<h1>{title}</h1>
					<p>{lead}</p>
				</header>
				{commerce.ready ? (
					<div className="kp-legal-status is-ready" role="status">
						<strong>Реквизиты продавца опубликованы</strong>
						<span>{commerce.legalName} · ИНН {commerce.inn}</span>
					</div>
				) : (
					<div className="kp-legal-status is-warning" role="status">
						<strong>Документ ещё не готов к публикации</strong>
						<span>В серверной конфигурации отсутствуют: {commerce.missing.join(", ")}.</span>
					</div>
				)}
				<div className="kp-legal-content">{children}</div>
			</div>
		</article>
	);
}

export function LegalSection({
	children,
	title,
}: {
	children: ReactNode;
	title: string;
}) {
	return (
		<section>
			<h2>{title}</h2>
			{children}
		</section>
	);
}

export function LegalFacts({
	items,
}: {
	items: Array<{ label: string; value: string | null }>;
}) {
	return (
		<dl className="kp-legal-facts">
			{items.map(({ label, value }) => (
				<div key={label}>
					<dt>{label}</dt>
					<dd>{value ?? "Не настроено"}</dd>
				</div>
			))}
		</dl>
	);
}
