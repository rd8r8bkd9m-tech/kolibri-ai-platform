"use client";

import {
	createContext,
	useContext,
	type ReactNode,
} from "react";

const CAPABILITY_ID = /^[a-z0-9][a-z0-9._-]{1,95}$/;
const RUNTIME_ID = /^[a-z0-9][a-z0-9._-]{1,95}$/;
const MAX_CAPABILITIES = 64;
const MAX_RUNTIMES = 32;

export type ProductCapability = {
	readonly id: string;
	readonly displayName: string;
	readonly available: boolean;
	readonly source: string;
	readonly reason?: string;
};

export type ProductRuntimeCapability = {
	readonly profileId: string;
	readonly runtimeId: string;
	readonly displayName: string;
	readonly connected: boolean;
	readonly startError: string | null;
	readonly modes: readonly string[];
	readonly capabilityIds: readonly string[];
};

export type ProductCapabilityManifest = {
	readonly schemaId: "kolibri.product.capability-manifest";
	readonly schemaVersion: "1.0";
	readonly capabilities: readonly ProductCapability[];
	readonly runtimes: readonly ProductRuntimeCapability[];
};

export class ProductCapabilityContractError extends Error {
	constructor(message = "Product capabilities returned an incompatible response.") {
		super(message);
		this.name = "ProductCapabilityContractError";
	}
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const isBoundedText = (value: unknown, maximum: number): value is string =>
	typeof value === "string" && value.trim().length > 0 && value.length <= maximum;

const parseCapability = (value: unknown): ProductCapability => {
	if (
		!isRecord(value) ||
		!CAPABILITY_ID.test(String(value.id ?? "")) ||
		!isBoundedText(value.displayName, 120) ||
		typeof value.available !== "boolean" ||
		!isBoundedText(value.source, 80) ||
		(value.reason !== undefined &&
			(value.reason === null || !isBoundedText(value.reason, 500)))
	) {
		throw new ProductCapabilityContractError("Invalid capability descriptor.");
	}
	return {
		id: String(value.id),
		displayName: value.displayName,
		available: value.available,
		source: value.source,
		...(value.reason === undefined ? {} : { reason: value.reason as string }),
	};
};

const parseRuntime = (value: unknown): ProductRuntimeCapability => {
	if (
		!isRecord(value) ||
		!RUNTIME_ID.test(String(value.profileId ?? "")) ||
		!RUNTIME_ID.test(String(value.runtimeId ?? "")) ||
		!isBoundedText(value.displayName, 120) ||
		typeof value.connected !== "boolean" ||
		(value.startError !== null &&
			(value.startError === undefined || !isBoundedText(value.startError, 120))) ||
		!Array.isArray(value.modes) ||
		value.modes.length > 8 ||
		value.modes.some((mode) => !isBoundedText(mode, 40)) ||
		!Array.isArray(value.capabilityIds) ||
		value.capabilityIds.length > MAX_CAPABILITIES ||
		value.capabilityIds.some(
			(capabilityId) =>
				typeof capabilityId !== "string" || !CAPABILITY_ID.test(capabilityId),
		)
	) {
		throw new ProductCapabilityContractError("Invalid runtime descriptor.");
	}
	return {
		profileId: String(value.profileId),
		runtimeId: String(value.runtimeId),
		displayName: value.displayName,
		connected: value.connected,
		startError: value.startError as string | null,
		modes: value.modes as string[],
		capabilityIds: value.capabilityIds as string[],
	};
};

export const parseProductCapabilityManifest = (
	value: unknown,
): ProductCapabilityManifest => {
	if (
		!isRecord(value) ||
		value.schemaId !== "kolibri.product.capability-manifest" ||
		value.schemaVersion !== "1.0" ||
		!Array.isArray(value.capabilities) ||
		value.capabilities.length > MAX_CAPABILITIES ||
		!Array.isArray(value.runtimes) ||
		value.runtimes.length > MAX_RUNTIMES
	) {
		throw new ProductCapabilityContractError();
	}
	const capabilities = value.capabilities.map(parseCapability);
	const ids = new Set(capabilities.map((item) => item.id));
	if (ids.size !== capabilities.length) {
		throw new ProductCapabilityContractError("Duplicate capability descriptor.");
	}
	const runtimes = value.runtimes.map(parseRuntime);
	const profileIds = new Set(runtimes.map((item) => item.profileId));
	if (profileIds.size !== runtimes.length) {
		throw new ProductCapabilityContractError("Duplicate runtime descriptor.");
	}
	return { schemaId: value.schemaId, schemaVersion: value.schemaVersion, capabilities, runtimes };
};

export const fetchProductCapabilityManifest = async (
	fetchImpl: typeof fetch = globalThis.fetch,
): Promise<ProductCapabilityManifest> => {
	const response = await fetchImpl("/api/v3/capabilities", {
		credentials: "same-origin",
		headers: { Accept: "application/json" },
		cache: "no-store",
	});
	if (!response.ok) {
		throw new ProductCapabilityContractError(
			`Capability manifest request failed (HTTP ${response.status}).`,
		);
	}
	return parseProductCapabilityManifest(await response.json());
};

export const capabilityIsAvailable = (
	manifest: ProductCapabilityManifest | null,
	capabilityId: string,
) =>
	manifest?.capabilities.some(
		(capability) => capability.id === capabilityId && capability.available,
	) === true;

export const ProductCapabilityManifestContext =
	createContext<ProductCapabilityManifest | null>(null);

export function ProductCapabilityManifestProvider({
	manifest,
	children,
}: Readonly<{
	manifest: ProductCapabilityManifest | null;
	children: ReactNode;
}>) {
	return (
		<ProductCapabilityManifestContext.Provider value={manifest}>
			{children}
		</ProductCapabilityManifestContext.Provider>
	);
}

export const useProductCapabilityManifest = () =>
	useContext(ProductCapabilityManifestContext);
