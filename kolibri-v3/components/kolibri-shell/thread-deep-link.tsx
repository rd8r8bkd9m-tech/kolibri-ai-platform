"use client";

import { useAui, useAuiState } from "@assistant-ui/react";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

/**
 * Deep-link: открывает тред по /app/c/:threadId и синхронизирует URL
 * при переключении диалогов. Живёт вне DesktopWorkspace, чтобы не
 * смешивать навигацию с рабочим состоянием приложения.
 */
export function ThreadDeepLink({
	initialThreadId,
}: {
	initialThreadId?: string;
}) {
	const aui = useAui();
	const router = useRouter();
	const activeThreadId = useAuiState((state) => state.threads.mainThreadId);
	const threadItems = useAuiState((state) => state.threads.threadItems);
	const initialRef = useRef(initialThreadId);
	const openedRef = useRef(false);

	useEffect(() => {
		const targetId = initialRef.current;
		if (!targetId || openedRef.current) return;
		if (!threadItems.some((thread) => thread.id === targetId)) return;
		openedRef.current = true;
		if (activeThreadId !== targetId) {
			void aui.threads().switchToThread(targetId);
		}
	}, [activeThreadId, aui, threadItems]);

	useEffect(() => {
		if (!activeThreadId || activeThreadId === initialRef.current) return;
		router.replace(`/app/c/${activeThreadId}`);
	}, [activeThreadId, router]);

	return null;
}
