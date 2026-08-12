const stats = [
	{ value: "1", label: "тариф запуска из серверного каталога" },
	{ value: "5", label: "форматов документов и экспорта" },
	{ value: "3", label: "шага контура: запрос, смета, документы" },
];

export function StatsSection() {
	return (
		<section className="klp-stats" aria-label="КолИ в цифрах">
			{stats.map((stat) => (
				<div className="klp-stat" key={stat.label}>
					<strong>{stat.value}</strong>
					<span>{stat.label}</span>
				</div>
			))}
		</section>
	);
}
