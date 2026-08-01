import type { Metadata } from "next";
import { LandingPage } from "@/components/public-site/landing/landing-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = {
	title: "Сметы и документы строительного проекта",
};

export default function HomePage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<LandingPage />
		</PublicShell>
	);
}
