"use client";

import { useAuiState } from "@assistant-ui/react";
import { useEffect, useRef, useState } from "react";

const THINKING_PHRASES = [
	"Изучаю контекст",
	"Анализирую вводные",
	"Собираю мысли",
	"Собираю картину",
	"Свожу воедино",
	"Соединяю точки",
	"Сопоставляю факты",
	"Раскладываю выводы",
	"Смотрю под другим углом",
	"Держу нить рассуждения",
	"Уточняю детали",
	"Формулирую ответ",
	"Структурирую ответ",
	"Уточняю формулировку",
	"Довожу мысль",
	"Готовлю ответ",
] as const;

export function ThinkingStatus() {
	const isRunning = useAuiState((state) => state.thread.isRunning);
	const startedAt = useRef<number | null>(null);
	const [seconds, setSeconds] = useState(0);
	const [phraseIndex, setPhraseIndex] = useState(0);

	useEffect(() => {
		if (!isRunning) {
			startedAt.current = null;
			return;
		}
		if (startedAt.current === null) {
			startedAt.current = Date.now();
			setSeconds(0);
		}
		const phraseTimer = window.setInterval(() => {
			setPhraseIndex((index) => (index + 1) % THINKING_PHRASES.length);
		}, 900);
		const secondTimer = window.setInterval(() => {
			const base = startedAt.current ?? Date.now();
			setSeconds(Math.floor((Date.now() - base) / 1000));
		}, 1000);
		return () => {
			window.clearInterval(phraseTimer);
			window.clearInterval(secondTimer);
		};
	}, [isRunning]);

	if (!isRunning) return null;

	const elapsed = seconds < 1 ? "<1 сек" : `${seconds} сек`;

	return (
		<div
			role="status"
			aria-live="polite"
			className="flex w-full items-center justify-between gap-3 text-xs"
		>
			<span className="font-medium text-secondary">Работаю {elapsed}</span>
			<span className="text-muted-foreground">{THINKING_PHRASES[phraseIndex]}</span>
		</div>
	);
}
