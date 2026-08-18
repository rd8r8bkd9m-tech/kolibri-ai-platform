import { AgentTraceSection } from "./agent-trace";
import { CasesSection } from "./cases";
import { FaqSection } from "./faq";
import { FinalCtaSection } from "./final-cta";
import { LandingHero } from "./hero";
import { IntegrationsSection } from "./platform-section";
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
			<AgentTraceSection />
			<IntegrationsSection />
			<PricingSection />
			<StatsSection />
			<FaqSection />
			<CasesSection />
			<FinalCtaSection />
		</>
	);
}
