import type { Metadata, Viewport } from "next";

import "katex/dist/katex.min.css";
import "./globals.css";
import "@/components/public-site/styles/tokens.css";
import "@/components/public-site/styles/shell.css";
import "@/components/public-site/styles/landing.css";
import "@/components/public-site/styles/landing-sections.css";
import "@/components/public-site/styles/landing-copy.css";
import "@/components/public-site/styles/public-pages.css";

export const metadata: Metadata = {
	title: {
		default: "Kolibri AI — сметы и документы строительного проекта",
		template: "%s · Kolibri AI",
	},
	description:
		"AI-рабочая среда для версионных смет, проектов, коммерческих предложений, договоров и актов.",
	applicationName: "Kolibri",
	appleWebApp: {
		capable: true,
		statusBarStyle: "black-translucent",
		title: "Kolibri",
	},
};

export const viewport: Viewport = {
	width: "device-width",
	initialScale: 1,
	viewportFit: "cover",
	interactiveWidget: "resizes-content",
	themeColor: [
		{ media: "(prefers-color-scheme: light)", color: "#ffffff" },
		{ media: "(prefers-color-scheme: dark)", color: "#000000" },
	],
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html lang="ru" className="min-h-full" suppressHydrationWarning>
			<body className="min-h-full font-sans">{children}</body>
		</html>
	);
}
