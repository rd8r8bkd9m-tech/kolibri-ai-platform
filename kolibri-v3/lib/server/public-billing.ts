import "server-only";
import type { BillingPlan } from "@/lib/billing/client";
import { v3BackendUrl } from "@/lib/server/v3-backend";

type PublicPlanResult =
	| { plan: BillingPlan; error: null }
	| { plan: null; error: string };

function validPlan(value: unknown): value is BillingPlan {
	if (!value || typeof value !== "object" || Array.isArray(value)) return false;
	const plan = value as Record<string, unknown>;
	return (
		typeof plan.code === "string" &&
		typeof plan.name === "string" &&
		Number.isSafeInteger(plan.amountMinor) &&
		(plan.amountMinor as number) > 0 &&
		plan.currency === "RUB" &&
		Number.isSafeInteger(plan.durationSeconds) &&
		(plan.durationSeconds as number) >= 3_600 &&
		typeof plan.entitlement === "string" &&
		Number.isSafeInteger(plan.revision)
	);
}

export async function getPublicLaunchPlan(): Promise<PublicPlanResult> {
	try {
		const response = await fetch(v3BackendUrl("/v1/billing/plans"), {
			headers: { Accept: "application/json" },
			cache: "no-store",
			signal: AbortSignal.timeout(3_000),
		});
		if (!response.ok) {
			return { plan: null, error: "Серверный каталог тарифов временно недоступен." };
		}
		const payload = (await response.json()) as { items?: unknown };
		if (!Array.isArray(payload.items) || payload.items.length === 0) {
			return {
				plan: null,
				error: "В серверном каталоге пока нет активных тарифов.",
			};
		}
		const launchPlan = payload.items.find(validPlan) as BillingPlan | null;
		if (launchPlan === null) {
			return {
				plan: null,
				error: "В серверном каталоге есть ошибка данных тарифа.",
			};
		}
		return { plan: launchPlan, error: null };
	} catch {
		return { plan: null, error: "Серверный каталог тарифов временно недоступен." };
	}
}
