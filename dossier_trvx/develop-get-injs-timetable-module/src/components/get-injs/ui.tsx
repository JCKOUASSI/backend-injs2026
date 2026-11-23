import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`card p-4 ${accent ? "border-[color:var(--inj-green)] bg-[color:var(--inj-green)] text-[#f7f3e8]" : ""}`}
    >
      <p className={`label ${accent ? "!text-[#bfd6c9]" : ""}`}>{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      {hint ? (
        <p className={`mt-1 text-xs ${accent ? "text-[#bfd6c9]" : "text-slate-500"}`}>{hint}</p>
      ) : null}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "green" | "orange" | "red" | "blue";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-[#efe9dc] text-[#4e5b53] border-[#e0d8c7]",
    green: "bg-[#e3efe7] text-[#1c5c45] border-[#c5e0d1]",
    orange: "bg-[#fbe9d8] text-[#9b4d11] border-[#f2d3b5]",
    red: "bg-[#fbe3df] text-[#9d2f22] border-[#f3c6bf]",
    blue: "bg-[#e5eef6] text-[#245b80] border-[#c9dced]",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[0.68rem] font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 border-b border-[color:var(--inj-line)] pb-5 md:flex-row md:items-end md:justify-between">
      <div>
        <p className="label text-[color:var(--inj-orange)]">{eyebrow}</p>
        <h1 className="font-display mt-1 text-3xl font-semibold text-[color:var(--inj-green)] md:text-4xl">
          {title}
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function ProgressBar({ value, tone = "green" }: { value: number; tone?: "green" | "orange" }) {
  const couleur = tone === "green" ? "var(--inj-green-soft)" : "var(--inj-orange)";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-[#eae4d7]">
      <div
        className="h-full rounded-full"
        style={{ width: `${Math.max(0, Math.min(100, value))}%`, backgroundColor: couleur }}
      />
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-[#efe9dc] text-xl">🗓️</div>
      <h3 className="font-display text-xl font-semibold text-[color:var(--inj-green)]">{title}</h3>
      <p className="max-w-md text-sm text-slate-600">{description}</p>
      {action}
    </div>
  );
}

export function Section({
  title,
  subtitle,
  children,
  actions,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--inj-line)] px-4 py-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-[color:var(--inj-green)]">{title}</h2>
          {subtitle ? <p className="text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        {actions}
      </div>
      <div className="overflow-x-auto">{children}</div>
    </section>
  );
}
