import { CasesSection } from "./cases";
import { FaqSection } from "./faq";
import { LandingHero } from "./hero";
import { PillarsSection } from "./pillars";
import { PricingSection } from "./pricing";
import { RolesSection } from "./roles";
import { StatsSection } from "./stats";

export function LandingPage() {
	return (
		<>
			<LandingHero />
			<PillarsSection />
			<RolesSection />
			<PricingSection />
			<StatsSection />
			<FaqSection />
			<CasesSection />
		</>
	);
}
