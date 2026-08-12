"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

export function Reveal({
	children,
	className = "",
	delay = 0,
}: {
	children: ReactNode;
	className?: string;
	delay?: number;
}) {
	const root = useRef<HTMLDivElement>(null);
	const [visible, setVisible] = useState(false);

	useEffect(() => {
		const node = root.current;
		if (!node) return;
		if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
			setVisible(true);
			return;
		}
		const observer = new IntersectionObserver(
			([entry]) => {
				if (!entry.isIntersecting) return;
				setVisible(true);
				observer.disconnect();
			},
			{ threshold: 0.12 },
		);
		observer.observe(node);
		return () => observer.disconnect();
	}, []);

	return (
		<div
			className={`klp-reveal${visible ? " is-visible" : ""}${className ? ` ${className}` : ""}`}
			ref={root}
			style={delay ? { transitionDelay: `${delay}ms` } : undefined}
		>
			{children}
		</div>
	);
}
