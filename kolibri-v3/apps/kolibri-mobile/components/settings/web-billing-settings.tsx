export type WebBillingSettingsProps = {
	authorizedFetch: typeof fetch;
	refreshProfile: () => Promise<unknown>;
	returnedIntent?: string;
};

/** Native storefronts use StoreKit / Google Play, never the web acquiring UI. */
export function WebBillingSettings(_props: WebBillingSettingsProps) {
	return null;
}
