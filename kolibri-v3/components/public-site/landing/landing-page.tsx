import { CommerceSection } from "./commerce";
import { FaqSection } from "./faq";
import { FeatureGrid } from "./features";
import { LandingHero } from "./hero";
import { PlatformSection } from "./platform-section";
import { WorkflowSection } from "./workflow";

export function LandingPage() {
	return (
		<>
			<LandingHero />
			<div className="kp-principle-bar" aria-label="Процесс работы">
				<span>Исходные данные</span><i />
				<span>Смета</span><i />
				<span>Версии</span><i />
				<span>Документы</span><i />
				<span>Результат</span>
			</div>
			<FeatureGrid />
			<WorkflowSection />
			<CommerceSection />
			<FaqSection />
			<PlatformSection />
		</>
	);
}
