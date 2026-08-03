"use client";

import { createContext, useContext } from "react";

export type AcceptedProductChatRun = {
	readonly acceptedAt: number;
	readonly runId: string;
	readonly threadId: string;
};

export const AcceptedProductChatRunContext =
	createContext<AcceptedProductChatRun | null>(null);

export const useAcceptedProductChatRun = () =>
	useContext(AcceptedProductChatRunContext);
