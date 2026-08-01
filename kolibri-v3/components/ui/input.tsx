import * as React from "react";

import { cn } from "@/lib/utils";
import { uiClassTokens } from "@/components/ui/class-names";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
	return (
		<input
			type={type}
			data-slot="input"
			className={cn(
				uiClassTokens.inputBase,
				uiClassTokens.inputFocusState,
				uiClassTokens.inputInvalidState,
				className,
			)}
			{...props}
		/>
	);
}

export { Input };
