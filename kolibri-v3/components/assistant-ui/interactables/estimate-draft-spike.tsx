"use client";

import { unstable_useInteractable } from "@assistant-ui/react";
import { z } from "zod";

import { Button } from "@/components/ui/button";

const estimateDraftSchema = z.object({
	title: z.string().max(160),
	region: z.string().max(160),
	areaM2: z.number().nonnegative(),
	status: z.enum(["draft", "needs_input"]),
});

/**
 * Isolated Interactables spike. It is opt-in and intentionally does not call
 * the estimate API or persistence adapters; the canonical EstimateEditor and
 * tenant-aware backend remain the only save path.
 */
export function EstimateDraftInteractableSpike() {
	const [state, controls] = unstable_useInteractable("estimate_draft", {
		id: "kolibri-estimate-draft-spike",
		description:
			"Экспериментальный черновик сметы без сохранения: название, регион и площадь.",
		stateSchema: estimateDraftSchema,
		initialState: {
			title: "Черновик сметы",
			region: "",
			areaM2: 0,
			status: "needs_input" as const,
		},
	});

	return (
		<section className="border-border bg-card w-full max-w-xl rounded-xl border p-4" aria-label="Экспериментальный черновик сметы">
			<div className="flex items-start justify-between gap-3">
				<div>
					<h2 className="font-semibold">Черновик сметы · spike</h2>
					<p className="text-muted-foreground mt-1 text-xs">
						Interactables · не сохраняется и не является расчётом
					</p>
				</div>
				<span className="rounded-full border px-2 py-0.5 text-xs">{state.status}</span>
			</div>
			<div className="mt-3 grid gap-3 sm:grid-cols-2">
				<label className="text-xs">
					<span className="mb-1 block font-medium">Название</span>
					<input
						className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
						value={state.title}
						onChange={(event) => controls.setState((current) => ({ ...current, title: event.target.value }))}
					/>
				</label>
				<label className="text-xs">
					<span className="mb-1 block font-medium">Регион</span>
					<input
						className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
						value={state.region}
						onChange={(event) => controls.setState((current) => ({ ...current, region: event.target.value, status: event.target.value ? "draft" : "needs_input" }))}
					/>
				</label>
				<label className="text-xs">
					<span className="mb-1 block font-medium">Площадь, м²</span>
					<input
						className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
						type="number"
						min={0}
						value={state.areaM2}
						onChange={(event) => controls.setState((current) => ({ ...current, areaM2: Math.max(0, Number(event.target.value) || 0) }))}
					/>
				</label>
			</div>
			<div className="mt-3 flex gap-2">
				<Button type="button" size="sm" variant="outline" onClick={() => void controls.flush()} disabled={controls.isPending}>
					Синхронизировать состояние
				</Button>
			</div>
		</section>
	);
}
