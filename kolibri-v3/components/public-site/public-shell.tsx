"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { PublicCommerceConfig } from "@/lib/server/public-commerce";
import { LandingNav } from "./landing/landing-nav";
import { PublicBrand } from "./public-brand";

function PublicNavigationLink({
	href,
	children,
	className,
}: {
	href: string;
	children: ReactNode;
	className?: string;
}) {
	const pathname = usePathname();
	const isHomeAnchor = href.startsWith("/#");
	const targetPath = href.split("#", 1)[0] || "/";
	const active = pathname === targetPath && !isHomeAnchor;

	return (
		<Link
			className={className}
			href={href}
			aria-current={active ? "page" : undefined}
			prefetch
		>
			{children}
		</Link>
	);
}

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
			<LandingNav />
			<main id="main-content">{children}</main>
			<footer className="kp-footer">
				<div className="kp-container kp-footer-grid">
					<div className="kp-footer-brand">
						<PublicBrand />
						<p>AI-рабочая среда для смет, проектов и связанных документов.</p>
						<span className="kp-footer-note">
							© {new Date().getFullYear()} КолИ
						</span>
					</div>
					<nav aria-label="Продукт">
						<strong>Продукт</strong>
						<PublicNavigationLink href="/#roles">Возможности</PublicNavigationLink>
						<PublicNavigationLink href="/#work">Как работает</PublicNavigationLink>
						<PublicNavigationLink href="/pricing">Тарифы</PublicNavigationLink>
						<PublicNavigationLink href="/app">Приложение</PublicNavigationLink>
					</nav>
					<nav aria-label="Документы и контакты">
						<strong>Компания</strong>
						<PublicNavigationLink href="/contacts">Контакты</PublicNavigationLink>
						<PublicNavigationLink href="/legal/offer">Публичная оферта</PublicNavigationLink>
						<PublicNavigationLink href="/legal/privacy">
							Конфиденциальность
						</PublicNavigationLink>
						<PublicNavigationLink href="/legal/payment-and-refund">
							Оплата и возврат
						</PublicNavigationLink>
						<PublicNavigationLink href="/contacts">Контакты</PublicNavigationLink>
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
					</div>
				</div>
			</footer>
		</div>
	);
}
