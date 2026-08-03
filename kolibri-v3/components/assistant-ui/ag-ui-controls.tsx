"use client";

import {
	useAgUiInterrupts,
	useAgUiSteerAway,
	useAgUiSubmitInterruptResponses,
	type AgUiInterrupt,
} from "@assistant-ui/react-ag-ui";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * Shared AG-UI human-in-the-loop surface. It is intentionally local to the
 * runtime: resolving an interrupt only sends the typed resume entry and does
 * not create or persist a product chat message.
 */
export function AgUiInterruptSurface() {
	const interrupts = useAgUiInterrupts();
	const submit = useAgUiSubmitInterruptResponses();
	const steerAway = useAgUiSteerAway();
	const [busyId, setBusyId] = useState<string | null>(null);
	const [responses, setResponses] = useState<Record<string, string>>({});

	if (interrupts.length === 0) return null;

	const resolve = async (interrupt: AgUiInterrupt, approved: boolean) => {
		setBusyId(interrupt.id);
		try {
			await submit([
				{
					interruptId: interrupt.id,
					status: approved ? "resolved" : "cancelled",
					payload: approved
						? responses[interrupt.id]?.trim() || true
						: undefined,
				},
			]);
		} finally {
			setBusyId(null);
		}
	};

	const steer = async () => {
		setBusyId("steer");
		try {
			await steerAway("Продолжите после уточнения пользователя.", [
				...interrupts.map((interrupt) => ({
					interruptId: interrupt.id,
					status: "cancelled" as const,
				})),
			]);
		} finally {
			setBusyId(null);
		}
	};

	return (
		<section
			className="border-amber-500/40 bg-amber-500/10 mx-auto mb-3 w-full max-w-3xl rounded-xl border p-3 text-sm"
			aria-label="Требуется подтверждение"
			role="alert"
		>
			<div className="font-medium">Нужно ваше решение</div>
			<div className="mt-2 space-y-2">
				{interrupts.map((interrupt) => (
					<div key={interrupt.id} className="rounded-lg border border-amber-500/30 bg-background/70 p-2">
						<p>{interrupt.message ?? "Агент ожидает подтверждения."}</p>
						{interrupt.responseSchema ? (
							<input
								className="border-input bg-background mt-2 h-8 w-full rounded-md border px-2 text-sm"
								value={responses[interrupt.id] ?? ""}
								onChange={(event) =>
									setResponses((current) => ({
										...current,
										[interrupt.id]: event.target.value,
									}))
								}
								aria-label="Ответ на запрос агента"
							/>
						) : null}
						<div className="mt-2 flex flex-wrap gap-2">
							<Button
								type="button"
								size="sm"
								onClick={() => void resolve(interrupt, true)}
								disabled={busyId !== null}
							>
								Подтвердить
							</Button>
							<Button
								type="button"
								size="sm"
								variant="outline"
								onClick={() => void resolve(interrupt, false)}
								disabled={busyId !== null}
							>
								Отклонить
							</Button>
						</div>
					</div>
				))}
			</div>
			<Button type="button" size="sm" variant="ghost" className="mt-2" onClick={() => void steer()} disabled={busyId !== null}>
				Продолжить после уточнения
			</Button>
		</section>
	);
}
