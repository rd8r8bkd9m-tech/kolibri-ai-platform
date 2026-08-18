"use client";

import { useEffect, useRef, useState } from "react";

const stats = [
	{ value: 2, label: "источника цен и нормативов: ФСНБ-2024 и ФГИС ЦС" },
	{ value: 4, label: "документа в контуре: смета, КП, счёт, ведомость" },
	{ value: 3, label: "формата экспорта: XLSX, PDF и DOCX" },
];

function CountStat({ label, value }: { label: string; value: number }) {
	const root = useRef<HTMLDivElement>(null);
	const [display, setDisplay] = useState(0);

	useEffect(() => {
		const node = root.current;
		if (!node) return;
		const observer = new IntersectionObserver(
			([entry]) => {
				if (!entry.isIntersecting) return;
				observer.disconnect();
				const startedAt = performance.now();
				const duration = 900;
				const tick = (now: number) => {
					const progress = Math.min(1, (now - startedAt) / duration);
					setDisplay(Math.round(value * (1 - Math.pow(1 - progress, 3))));
					if (progress < 1) requestAnimationFrame(tick);
				};
				requestAnimationFrame(tick);
			},
			{ threshold: 0.4 },
		);
		observer.observe(node);
		return () => observer.disconnect();
	}, [value]);

	return (
		<div className="klp-stat" ref={root}>
			<strong>{display}</strong>
			<span>{label}</span>
		</div>
	);
}

export function StatsSection() {
	return (
		<section className="klp-stats" aria-label="КолИ в цифрах">
			{stats.map((stat) => (
				<CountStat key={stat.label} label={stat.label} value={stat.value} />
			))}
		</section>
	);
}
