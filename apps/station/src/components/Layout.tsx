import type { ReactNode } from "react";

type LayoutProps = {
  title: string;
  children: ReactNode;
};

export function Layout({ title, children }: LayoutProps) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
