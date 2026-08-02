import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { KolibriApp } from "@/app/kolibri-app";

const MOBILE_USER_AGENT =
	/(Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile)/i;

export default async function AppPage() {
	const requestHeaders = await headers();
	const userAgent = requestHeaders.get("user-agent") ?? "";
	const isMobileRequest =
		requestHeaders.get("sec-ch-ua-mobile") === "?1" ||
		MOBILE_USER_AGENT.test(userAgent);

	// The gateway normally routes mobile requests to Expo before Next sees
	// them. Keep this guard at the route boundary as well so a direct request
	// to the desktop upstream never renders the desktop app first.
	if (isMobileRequest) {
		redirect("/app?client=mobile");
	}

	return <KolibriApp />;
}
