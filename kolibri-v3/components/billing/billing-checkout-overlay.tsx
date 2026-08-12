"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, ExternalLink, LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogTitle,
} from "@/components/ui/dialog";

type BillingCheckoutOverlayProps = {
	paymentUrl: string;
	onClose: () => void;
	open: boolean;
};

const FALLBACK_DELAY_MS = 4500;

function openInNewTab(url: string) {
	const popup = window.open(url, "_blank", "noopener,noreferrer");
	if (!popup) {
		throw new Error(
			"Браузер блокировал открытие новой вкладки. Закройте окно и попробуйте снова.",
		);
	}
	popup.focus();
}

export function BillingCheckoutOverlay({
	open,
	onClose,
	paymentUrl,
}: BillingCheckoutOverlayProps) {
	const [iframeState, setIframeState] = useState<"loading" | "ready" | "blocked">(
		"loading",
	);
	const [showFallback, setShowFallback] = useState(false);
	const [fallbackError, setFallbackError] = useState<string | null>(null);
	const loadingRef = useRef(false);

	useEffect(() => {
		if (!open) {
			setIframeState("loading");
			setShowFallback(false);
			setFallbackError(null);
			loadingRef.current = false;
			return;
		}

		loadingRef.current = true;
		setIframeState("loading");
		setShowFallback(false);
		setFallbackError(null);
		const timer = window.setTimeout(() => {
			if (loadingRef.current) {
				setIframeState("blocked");
				setShowFallback(true);
			}
		}, FALLBACK_DELAY_MS);
		return () => {
			loadingRef.current = false;
			window.clearTimeout(timer);
		};
	}, [open, paymentUrl]);

	const markLoaded = () => {
		loadingRef.current = false;
		setIframeState("ready");
		setShowFallback(false);
	};

	const markBlocked = () => {
		loadingRef.current = false;
		setIframeState("blocked");
		setShowFallback(true);
	};

	const tryPopup = () => {
		try {
			openInNewTab(paymentUrl);
			onClose();
		} catch (error) {
			setFallbackError(
				error instanceof Error
					? error.message
					: "Не удалось открыть платёжную страницу.",
			);
		}
	};

	return (
		<Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
			<DialogContent className="w-[min(980px,calc(100%-1.5rem))] max-w-[calc(100%-1.5rem)] gap-0 overflow-hidden p-0 sm:max-w-[min(980px,calc(100%-1.5rem))]">
				<div className="p-4 pb-3">
					<DialogTitle>Оплата через T‑Банк</DialogTitle>
					<DialogDescription>
						Форма банка открыта внутри приложения. Если встраивание заблокировано,
						переключитесь на новую вкладку.
					</DialogDescription>
				</div>
				<div className="border-y border-border/60">
					{showFallback ? null : (
						<div className="relative h-[min(68vh,620px)] w-full">
							<iframe
								className="h-full w-full border-0 bg-white"
								src={paymentUrl}
								title="Форма оплаты"
								onLoad={markLoaded}
								onError={markBlocked}
							/>
							{iframeState === "loading" ? (
								<div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/95">
									<LoaderCircle
										className="size-4 animate-spin text-muted-foreground"
										aria-hidden="true"
									/>
									<p className="text-sm text-muted-foreground">Загрузка формы оплаты…</p>
								</div>
							) : null}
						</div>
					)}
					{showFallback ? (
						<div className="flex min-h-[20rem] flex-col items-center justify-center gap-3 px-5 py-8 text-center">
							<AlertCircle className="size-10 text-amber-500" aria-hidden="true" />
							<p className="max-w-md text-sm leading-6">
								Платежную форму нельзя открыть внутри страницы прямо сейчас.
								Откройте её в новой вкладке банка.
							</p>
							<div className="flex flex-col gap-2 sm:flex-row">
								<Button type="button" onClick={tryPopup}>
									<ExternalLink className="size-4" aria-hidden="true" />
									Открыть в новой вкладке
								</Button>
							</div>
							{fallbackError ? (
								<p className="max-w-md text-xs leading-6 text-destructive">
									{fallbackError}
								</p>
							) : null}
						</div>
					) : null}
				</div>
				<div className="flex items-center justify-between gap-2 px-4 py-3 text-xs text-muted-foreground">
					<span>Состояние платежа синхронизируется через webhook банка.</span>
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={tryPopup}
							className="h-8"
						>
							<ExternalLink className="size-3.5" aria-hidden="true" />
							Открыть в новой вкладке
						</Button>
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={onClose}
							className="h-8"
						>
							<X className="size-3.5" aria-hidden="true" />
							Закрыть
						</Button>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}
