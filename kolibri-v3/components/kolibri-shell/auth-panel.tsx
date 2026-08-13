"use client";

import type { FormEvent, KeyboardEvent } from "react";
import { useId, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useIdentity } from "@/lib/identity/provider";
import { cn } from "@/lib/utils";

export function AuthPanel({
	onAuthenticated,
}: {
	onAuthenticated?: () => void;
}) {
	const identity = useIdentity();
	const [mode, setMode] = useState<"login" | "register">("login");
	const [name, setName] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(identity.error);
	const authTabPrefix = useId().replace(/:/g, "");
	const authTabRefs = useRef<Array<HTMLButtonElement | null>>([]);

	const loginTabId = `${authTabPrefix}-account-login-tab`;
	const registerTabId = `${authTabPrefix}-account-register-tab`;
	const loginPanelId = `${authTabPrefix}-account-auth-login-panel`;
	const registerPanelId = `${authTabPrefix}-account-auth-register-panel`;

	const switchMode = (nextMode: "login" | "register") => {
		setMode(nextMode);
		setError(null);
	};

	const focusModeTab = (nextMode: "login" | "register", nextIndex: number) => {
		switchMode(nextMode);
		window.requestAnimationFrame(() => {
			authTabRefs.current[nextIndex]?.focus();
		});
	};

	const handleModeKeyDown = (
		event: KeyboardEvent<HTMLButtonElement>,
		index: number,
	) => {
		let nextIndex: number | null = null;
		if (event.key === "ArrowRight") {
			nextIndex = (index + 1) % 2;
		} else if (event.key === "ArrowLeft") {
			nextIndex = (index - 1 + 2) % 2;
		} else if (event.key === "Home") {
			nextIndex = 0;
		} else if (event.key === "End") {
			nextIndex = 1;
		}

		if (nextIndex === null) {
			return;
		}

		event.preventDefault();
		const nextMode = nextIndex === 0 ? "login" : "register";
		focusModeTab(nextMode, nextIndex);
	};

	const submit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setSubmitting(true);
		setError(null);
		try {
			if (mode === "login") {
				await identity.login({ email, password });
			} else {
				await identity.register({ email, name, password });
			}
			setPassword("");
			onAuthenticated?.();
		} catch (requestError) {
			setError(
				requestError instanceof Error
					? requestError.message
					: "Не удалось подтвердить аккаунт.",
			);
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<div className="w-full">
			<div
				role="tablist"
				aria-label="Способ входа"
				aria-orientation="horizontal"
				className="grid grid-cols-2 rounded-xl bg-muted p-1"
			>
				<button
					type="button"
					role="tab"
					ref={(node) => {
						authTabRefs.current[0] = node;
					}}
					id={loginTabId}
					aria-controls={loginPanelId}
					aria-selected={mode === "login"}
					tabIndex={mode === "login" ? 0 : -1}
					onClick={() => switchMode("login")}
					onKeyDown={(event) => handleModeKeyDown(event, 0)}
					className={cn(
						"h-9 rounded-lg text-sm font-medium",
						mode === "login"
							? "bg-background shadow-sm"
							: "text-muted-foreground",
					)}
				>
					Вход
				</button>
				<button
					type="button"
					role="tab"
					ref={(node) => {
						authTabRefs.current[1] = node;
					}}
					id={registerTabId}
					aria-controls={registerPanelId}
					aria-selected={mode === "register"}
					tabIndex={mode === "register" ? 0 : -1}
					onClick={() => switchMode("register")}
					onKeyDown={(event) => handleModeKeyDown(event, 1)}
					className={cn(
						"h-9 rounded-lg text-sm font-medium",
						mode === "register"
							? "bg-background shadow-sm"
							: "text-muted-foreground",
					)}
				>
					Регистрация
				</button>
			</div>

			{mode === "login" ? (
				<form
					id={loginPanelId}
					role="tabpanel"
					aria-labelledby={loginTabId}
					tabIndex={0}
					className="mt-5 space-y-4"
					onSubmit={submit}
				>
					<h2 className="sr-only">Вход</h2>
					<label className="block text-[13px] font-medium">
						Email
						<Input
							type="email"
							value={email}
							onChange={(event) => setEmail(event.target.value)}
							autoComplete="email"
							required
							maxLength={320}
							className="mt-2 h-10 rounded-lg shadow-none"
						/>
					</label>
					<label className="block text-[13px] font-medium">
						Пароль
						<Input
							type="password"
							value={password}
							onChange={(event) => setPassword(event.target.value)}
							autoComplete="current-password"
							required
							minLength={12}
							maxLength={256}
							className="mt-2 h-10 rounded-lg shadow-none"
						/>
					</label>
					{error ? (
						<p
							className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] leading-5 text-destructive"
							role="alert"
						>
							{error}
						</p>
					) : null}
					<Button
						type="submit"
						disabled={submitting}
						className="h-10 w-full rounded-lg"
					>
						{submitting ? (
							<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
						) : null}
						Войти
					</Button>
				</form>
			) : (
				<form
					id={registerPanelId}
					role="tabpanel"
					aria-labelledby={registerTabId}
					tabIndex={0}
					className="mt-5 space-y-4"
					onSubmit={submit}
				>
					<h2 className="sr-only">Регистрация</h2>
					<label className="block text-[13px] font-medium">
						Имя
						<Input
							value={name}
							onChange={(event) => setName(event.target.value)}
							autoComplete="name"
							required
							minLength={2}
							maxLength={160}
							className="mt-2 h-10 rounded-lg shadow-none"
						/>
					</label>
					<label className="block text-[13px] font-medium">
						Email
						<Input
							type="email"
							value={email}
							onChange={(event) => setEmail(event.target.value)}
							autoComplete="email"
							required
							maxLength={320}
							className="mt-2 h-10 rounded-lg shadow-none"
						/>
					</label>
					<label className="block text-[13px] font-medium">
						Пароль
						<Input
							type="password"
							value={password}
							onChange={(event) => setPassword(event.target.value)}
							autoComplete="new-password"
							required
							minLength={12}
							maxLength={256}
							className="mt-2 h-10 rounded-lg shadow-none"
						/>
					</label>
					{error ? (
						<p
							className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[12px] leading-5 text-destructive"
							role="alert"
						>
							{error}
						</p>
					) : null}
					<Button
						type="submit"
						disabled={submitting}
						className="h-10 w-full rounded-lg"
					>
						{submitting ? (
							<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
						) : null}
						Создать аккаунт
					</Button>
				</form>
			)}
		</div>
	);
}

export function DesktopAuthScreen() {
	return (
		<div className="bg-background flex h-dvh min-h-0 items-center justify-center px-4">
			<div className="w-full max-w-sm">
				<AuthPanel />
			</div>
		</div>
	);
}
