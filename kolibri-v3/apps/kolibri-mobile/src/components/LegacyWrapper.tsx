import type { PropsWithChildren } from "react";

/**
 * Marks a surface whose data source is not yet determined. Per the refactor
 * contract, such screens keep their old behavior and are not restyled.
 */
export function LegacyWrapper({ children }: PropsWithChildren) {
	return <>{children}</>;
}
