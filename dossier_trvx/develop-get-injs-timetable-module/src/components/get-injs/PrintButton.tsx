"use client";

export function PrintButton({ label = "Imprimer" }: { label?: string }) {
  return (
    <button type="button" className="btn-ghost no-print" onClick={() => window.print()}>
      {label}
    </button>
  );
}
