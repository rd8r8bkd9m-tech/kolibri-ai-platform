const toNumber = (value: number): number =>
	Number.isFinite(value) ? value : 0;

export function fmtMoney(value: number): string {
	const amount = toNumber(value);
	const hasFraction = !Number.isInteger(amount);
	return new Intl.NumberFormat("ru-RU", {
		currency: "RUB",
		minimumFractionDigits: 0,
		maximumFractionDigits: hasFraction ? 2 : 0,
	}).format(amount);
}

export function fmtQty(value: number): string {
	const amount = toNumber(value);
	return Number.isInteger(amount)
		? String(amount)
		: String(Number.parseFloat(amount.toFixed(4)));
}

export function lineTotal(qty: number, price: number): number {
	return toNumber(qty) * toNumber(price);
}
