"use client";

import { Toaster as SonnerToaster, toast } from "sonner";

type ToasterProps = React.ComponentProps<typeof SonnerToaster>;

function Toaster({ ...props }: ToasterProps) {
	return (
		<SonnerToaster
			className="toaster group"
			toastOptions={{
				classNames: {
					toast:
						"group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
					description: "group-[.toast]:text-muted-foreground",
					actionButton:
						"group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
					cancelButton:
						"group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
					success: "group-[.toast]:border-emerald-500/30",
					error: "group-[.toast]:border-destructive/30",
					warning: "group-[.toast]:border-amber-500/30",
					info: "group-[.toast]:border-sky-500/30",
				},
			}}
			position="bottom-right"
			expand={false}
			richColors
			closeButton
			{...props}
		/>
	);
}

export { Toaster, toast };
