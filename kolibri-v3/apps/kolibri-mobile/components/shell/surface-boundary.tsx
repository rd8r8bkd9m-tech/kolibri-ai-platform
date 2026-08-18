import type { IconName } from "@/components/ui/icon-mappings";
import { EmptyState } from "@/components/design-system/EmptyState";

export function SurfaceBoundary({
	icon,
	title,
	body,
	note,
}: {
	icon: IconName;
	title: string;
	body: string;
	note: string;
}) {
	return <EmptyState body={body} icon={icon} note={note} title={title} />;
}
