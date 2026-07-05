type StatusCardProps = { label: string; value: string | number };

export function StatusCard({ label, value }: StatusCardProps) {
  return (
    <article className="card">
      <div>{label}</div>
      <strong>{value}</strong>
    </article>
  );
}
