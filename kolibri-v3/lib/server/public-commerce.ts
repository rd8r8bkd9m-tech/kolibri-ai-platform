import "server-only";

export type PublicCommerceConfig = {
	legalName: string | null;
	inn: string | null;
	taxStatus: string | null;
	email: string | null;
	phone: string | null;
	address: string | null;
	ready: boolean;
	missing: string[];
};

const fields = [
	["legalName", "KOLIBRI_PUBLIC_LEGAL_NAME", "наименование продавца"],
	["inn", "KOLIBRI_PUBLIC_LEGAL_INN", "ИНН"],
	["taxStatus", "KOLIBRI_PUBLIC_TAX_STATUS", "налоговый статус"],
	["email", "KOLIBRI_PUBLIC_CONTACT_EMAIL", "электронная почта"],
	["phone", "KOLIBRI_PUBLIC_CONTACT_PHONE", "телефон"],
	["address", "KOLIBRI_PUBLIC_LEGAL_ADDRESS", "адрес"],
] as const;

function configuredValue(name: string) {
	const value = process.env[name]?.trim();
	return value && value.length <= 500 ? value : null;
}

export function getPublicCommerceConfig(): PublicCommerceConfig {
	const values = Object.fromEntries(
		fields.map(([key, environmentName]) => [key, configuredValue(environmentName)]),
	) as Record<(typeof fields)[number][0], string | null>;
	const missing = fields
		.filter(([key]) => values[key] === null)
		.map(([, , label]) => label);

	return {
		legalName: values.legalName,
		inn: values.inn,
		taxStatus: values.taxStatus,
		email: values.email,
		phone: values.phone,
		address: values.address,
		ready: missing.length === 0,
		missing,
	};
}
