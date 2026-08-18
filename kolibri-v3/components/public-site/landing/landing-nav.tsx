"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { LandingPet } from "./landing-pet";

type NavLink = {
	label: string;
	href: string;
	hint: string;
};

type NavGroup = {
	label: string;
	links: NavLink[];
};

const groups: NavGroup[] = [
	{
		label: "Продукт",
		links: [
			{ label: "О продукте", href: "/", hint: "Что умеет агент" },
			{ label: "Все возможности", href: "/#roles", hint: "Сметы, документы, нормативы" },
			{ label: "Как работает", href: "/#work", hint: "Запрос, расчёт, результат" },
						{ label: "Приложение", href: "/app", hint: "Работа в браузере и на телефоне" },
		],
	},
	{
		label: "Решения",
		links: [
			{ label: "Сметы", href: "/#roles", hint: "Работы, материалы, цены" },
			{ label: "Документы", href: "/#roles", hint: "КП, счёт, ведомость" },
			{ label: "Цены и нормативы", href: "/#roles", hint: "ФСНБ-2024, ФГИС ЦС" },
			{ label: "Экспорт", href: "/#roles", hint: "XLSX, PDF, DOCX" },
			{ label: "Поддержка", href: "/contacts", hint: "Помощь по проекту" },
		],
	},
	{
		label: "Для бизнеса",
		links: [
			{ label: "КолИ для команд", href: "/pricing", hint: "Общий каталог и доступы" },
			{ label: "Записаться на демо", href: "/contacts", hint: "Покажем на ваших задачах" },
			{ label: "Безопасность", href: "/legal/privacy", hint: "Данные и конфиденциальность" },
			{ label: "Оферта и возврат", href: "/legal/payment-and-refund", hint: "Правила оплаты" },
		],
	},
];

const resources: NavLink[] = [
	{ label: "Вопросы и ответы", href: "/#faq", hint: "Частые вопросы" },
	{ label: "Контакты", href: "/contacts", hint: "Почта и телефон" },
	{ label: "Конфиденциальность", href: "/legal/privacy", hint: "Обработка данных" },
	{ label: "Публичная оферта", href: "/legal/offer", hint: "Условия сервиса" },
];

function NavDropdown({ group }: { group: NavGroup }) {
	const [open, setOpen] = useState(false);
	const root = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const close = (event: PointerEvent) => {
			if (root.current && !root.current.contains(event.target as Node)) {
				setOpen(false);
			}
		};
		window.addEventListener("pointerdown", close);
		return () => window.removeEventListener("pointerdown", close);
	}, [open]);

	return (
		<div
			className={`klp-nav-item${open ? " is-open" : ""}`}
			ref={root}
			onMouseEnter={() => setOpen(true)}
			onMouseLeave={() => setOpen(false)}
			onFocus={(event) => {
				if (root.current?.contains(event.target as Node)) {
					setOpen(true);
				}
			}}
			onBlur={(event) => {
				if (!root.current?.contains(event.relatedTarget as Node)) {
					setOpen(false);
				}
			}}
			onKeyDown={(event) => {
				if (event.key === "Escape") {
					setOpen(false);
					root.current?.querySelector<HTMLButtonElement>(".klp-nav-btn")?.focus();
				}
			}}
		>
			<button
				type="button"
				className="klp-nav-btn"
				aria-expanded={open}
				onFocus={() => setOpen(true)}
				onClick={() => setOpen((value) => !value)}
			>
				{group.label} <ChevronDown aria-hidden="true" />
			</button>
			{open ? (
				<div className="klp-nav-panel">
					{group.links.map((item) => (
						<Link className="klp-nav-link" href={item.href} key={item.label} onClick={() => setOpen(false)}>
							<strong>{item.label}</strong>
							<span>{item.hint}</span>
						</Link>
					))}
				</div>
			) : null}
		</div>
	);
}

function MobileLinks() {
	return (
		<>
			<Link href="/#work">Что умеет агент</Link>
			<Link href="/#roles">Сценарии</Link>
			<Link href="/#agent">Как работает агент</Link>
			<Link href="/#integrations">Интеграции</Link>
			<Link href="/pricing">Тарифы</Link>
			<Link href="/#faq">Вопросы</Link>
			<Link href="/contacts">Контакты</Link>
			<Link href="/app">Войти</Link>
			<Link className="klp-mobile-cta" href="/app">Попробовать бесплатно</Link>
		</>
	);
}

export function LandingNav() {
	const [scrolled, setScrolled] = useState(false);
	const [progress, setProgress] = useState(0);
	const pathname = usePathname();

	useEffect(() => {
		const update = () => {
			setScrolled(window.scrollY > 8);
			const max = document.documentElement.scrollHeight - window.innerHeight;
			setProgress(max > 0 ? Math.min(100, (window.scrollY / max) * 100) : 0);
		};
		update();
		window.addEventListener("scroll", update, { passive: true });
		window.addEventListener("resize", update);
		return () => {
			window.removeEventListener("scroll", update);
			window.removeEventListener("resize", update);
		};
	}, []);

	return (
		<nav className={`klp-nav${scrolled ? " is-scrolled" : ""}`} aria-label="Основная навигация">
			<div className="klp-scroll-progress" aria-hidden="true">
				<i style={{ width: `${progress}%` }} />
			</div>
			<div className="klp-nav-inner">
				<Link className="klp-nav-logo" href="/" aria-label="КолИ — на главную">
					<LandingPet interactive width={30} />
					<span className="klp-logo-pixel">колИ</span>
				</Link>
				<div className="klp-nav-center">
					{groups.map((group) => <NavDropdown group={group} key={group.label} />)}
					<Link
						className={`klp-nav-btn${pathname === "/pricing" ? " is-active" : ""}`}
						href="/pricing"
						aria-current={pathname === "/pricing" ? "page" : undefined}
					>
						Тарифы
					</Link>
					<NavDropdown group={{ label: "Ресурсы", links: resources }} />
				</div>
				<div className="klp-nav-actions">
					<details className="klp-mobile-menu">
						<summary aria-label="Открыть меню сайта">
							<span />
							<span />
							<span />
						</summary>
						<div className="klp-mobile-panel">
							<MobileLinks />
						</div>
					</details>
					<Link className="klp-nav-login" href="/app">Войти</Link>
					<Link className="klp-cta-pill klp-nav-cta" href="/app">
						Попробовать бесплатно
					</Link>
				</div>
			</div>
		</nav>
	);
}
