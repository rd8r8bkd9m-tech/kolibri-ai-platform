import Link from "next/link";
import type { ReactNode } from "react";
import type { PublicCommerceConfig } from "@/lib/server/public-commerce";
import { PublicBrand } from "./public-brand";

export function PublicShell({
	children,
	commerce,
}: {
	children: ReactNode;
	commerce: PublicCommerceConfig;
}) {
	return (
		<div className="kp-public-shell">
			<a className="kp-skip-link" href="#main-content">
				Перейти к содержанию
			</a>
			<header className="kp-header">
				<div className="kp-container kp-header-inner">
					<PublicBrand />
					<nav className="kp-main-nav" aria-label="Основная навигация">
						<Link href="/#features">Возможности</Link>
						<Link href="/#workflow">Как работает</Link>
						<Link href="/pricing">Тарифы</Link>
					</nav>
					<div className="kp-header-actions">
						<Link className="kp-login-link" href="/app">
							Войти
						</Link>
						<Link className="kp-button kp-button-small kp-button-primary" href="/app">
							Открыть Kolibri
						</Link>
					</div>
				</div>
			</header>
			<main id="main-content">{children}</main>
			<footer className="kp-footer">
				<div className="kp-container kp-footer-grid">
					<div className="kp-footer-brand">
						<PublicBrand />
						<p>AI-рабочая среда для смет, проектов и связанных документов.</p>
					</div>
					<nav aria-label="Документы и контакты">
						<Link href="/legal/offer">Публичная оферта</Link>
						<Link href="/legal/privacy">Конфиденциальность</Link>
						<Link href="/legal/payment-and-refund">Оплата и возврат</Link>
						<Link href="/contacts">Контакты</Link>
					</nav>
					<div className="kp-footer-legal">
						{commerce.ready ? (
							<>
								<strong>{commerce.legalName}</strong>
								<span>ИНН {commerce.inn}</span>
							</>
						) : (
							<span className="kp-config-warning">
								Реквизиты готовятся к публикации
							</span>
						)}
						<span>© {new Date().getFullYear()} Kolibri AI</span>
					</div>
				</div>
			</footer>
		</div>
	);
}
