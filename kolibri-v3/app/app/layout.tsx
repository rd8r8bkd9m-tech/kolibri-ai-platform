import type { ReactNode } from "react";
import { MyRuntimeProvider } from "@/app/MyRuntimeProvider";
import { MobileEnvironment } from "@/components/kolibri-shell/mobile-environment";
import { KolibriThemeProvider } from "@/components/theme/kolibri-theme-provider";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { IdentityProvider } from "@/lib/identity/provider";
import { ModelCatalogProvider } from "@/lib/models/provider";

export default function ProductAppLayout({ children }: { children: ReactNode }) {
	return (
		<div className="h-dvh overflow-hidden overscroll-none">
			<MobileEnvironment />
			<KolibriThemeProvider>
				<Toaster />
				<IdentityProvider>
					<ModelCatalogProvider>
						<MyRuntimeProvider>
							<TooltipProvider delayDuration={350}>{children}</TooltipProvider>
						</MyRuntimeProvider>
					</ModelCatalogProvider>
				</IdentityProvider>
			</KolibriThemeProvider>
		</div>
	);
}
