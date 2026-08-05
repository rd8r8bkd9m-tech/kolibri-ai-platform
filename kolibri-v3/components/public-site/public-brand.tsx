import Link from "next/link";

export function PublicBrand() {
	return (
		<Link className="kp-brand" href="/" aria-label="КолИ — на главную">
			<span className="kp-brand-mark" aria-hidden="true">
				<i />
				<i />
				<b />
			</span>
			<span>КолИ</span>
		</Link>
	);
}
