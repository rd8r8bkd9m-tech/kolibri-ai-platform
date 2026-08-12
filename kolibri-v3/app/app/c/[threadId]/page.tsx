import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { KolibriApp } from "@/app/kolibri-app";

const MOBILE_USER_AGENT =
	/(Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile)/i;

export default async function ThreadPage({
	params,
}: {
	params: Promise<{ threadId: string }>;
}) {
	const { threadId } = await params;
	const requestHeaders = await headers();
	const userAgent = requestHeaders.get("user-agent") ?? "";
	const isMobileRequest =
		requestHeaders.get("sec-ch-ua-mobile") === "?1" ||
		MOBILE_USER_AGENT.test(userAgent);

	if (isMobileRequest) {
		redirect(`/app?client=mobile&threadId=${encodeURIComponent(threadId)}`);
	}

	return <KolibriApp initialThreadId={threadId} />;
}
