import type { Metadata } from "next";
import { MyRuntimeProvider } from "@/app/MyRuntimeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { IdentityProvider } from "@/lib/identity/provider";
import { ModelCatalogProvider } from "@/lib/models/provider";

import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Колибри — проектная рабочая среда",
  description:
    "Chat + Canvas для смет, проектов, документов и проверяемых результатов.",
};

export const dynamic = "force-dynamic";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className="h-dvh" suppressHydrationWarning>
      <body className="h-dvh overflow-hidden font-sans">
        <IdentityProvider>
          <ModelCatalogProvider>
            <MyRuntimeProvider>
              <TooltipProvider delayDuration={350}>
                {children}
              </TooltipProvider>
            </MyRuntimeProvider>
          </ModelCatalogProvider>
        </IdentityProvider>
      </body>
    </html>
  );
}
