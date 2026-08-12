import type { Metadata } from "next";
import { LandingPage } from "@/components/public-site/landing/landing-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = {
	title: "КолИ — ИИ-сметчик, документы и нормативы строительного проекта",
	description:
		"КолИ — агент для строительных смет: соберите версионную смету из описания объекта, подготовьте КП, договор и акты и экспортируйте в XLSX, PDF, DOCX.",
	keywords: [
		"ИИ сметчик",
		"строительная смета",
		"смета онлайн",
		"ФСНБ-2022",
		"ГЭСН",
		"ФГИС ЦС",
		"КП договор акт",
	],
	openGraph: {
		title: "КолИ — ИИ-сметчик строительного проекта",
		description:
			"Один агент на смету, документы и рутину: версии, основания и экспорт XLSX, PDF, DOCX.",
		type: "website",
		locale: "ru_RU",
		siteName: "КолИ",
	},
	twitter: {
		card: "summary_large_image",
		title: "КолИ — ИИ-сметчик строительного проекта",
		description:
			"Один агент на смету, документы и рутину: версии, основания и экспорт XLSX, PDF, DOCX.",
	},
};

const structuredData = {
	"@context": "https://schema.org",
	"@graph": [
		{
			"@type": "SoftwareApplication",
			name: "КолИ",
			applicationCategory: "BusinessApplication",
			operatingSystem: "Web",
			description:
				"AI-агент для строительных смет: версионные расчёты, КП, договоры и акты, экспорт XLSX, PDF, DOCX.",
			inLanguage: "ru",
			offers: {
				"@type": "Offer",
				price: "99",
				priceCurrency: "RUB",
				availability: "https://schema.org/InStock",
			},
		},
		{
			"@type": "FAQPage",
			mainEntity: [
				{
					"@type": "Question",
					name: "Чем КолИ отличается от обычного чат-бота?",
					acceptedAnswer: {
						"@type": "Answer",
						text:
							"КолИ — агентная среда для сметного дела: он структурирует исходные данные в версионную смету, связывает строки с основаниями и выпускает КП, договоры и акты из согласованных данных проекта.",
					},
				},
				{
					"@type": "Question",
					name: "Какие документы поддерживаются?",
					acceptedAnswer: {
						"@type": "Answer",
						text:
							"Версионные сметы, коммерческие предложения, договоры, акты выполненных работ и экспорт в XLSX, PDF и DOCX.",
					},
				},
			],
		},
	],
};

export default function HomePage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<script
				type="application/ld+json"
				dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
			/>
			<LandingPage />
		</PublicShell>
	);
}
