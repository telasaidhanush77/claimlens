"use client";

import { useRef, useState } from "react";

type Props = { busy: boolean; onUpload: (f: File) => void; onSample: () => void };

export function PolicyStep({ busy, onUpload, onSample }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const pick = (files: FileList | null) => {
    const f = files?.[0];
    if (f) onUpload(f);
  };

  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-stretch">
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}
        className={`rounded-xl border-2 border-dashed px-6 py-8 text-left transition-colors disabled:opacity-60 ${
          drag ? "border-teal bg-teal-soft" : "border-line bg-card hover:border-teal"
        }`}
      >
        <span className="block font-medium">Upload your policy wording (PDF)</span>
        <span className="mt-1 block text-sm text-muted">
          The long terms-and-conditions document, not the one-page schedule. Drop it here or click.
        </span>
      </button>
      <input ref={input} type="file" accept="application/pdf" hidden onChange={(e) => pick(e.target.files)} />
      <button
        type="button"
        disabled={busy}
        onClick={onSample}
        className="rounded-xl bg-ink px-6 py-4 font-medium text-paper transition hover:bg-teal disabled:opacity-60"
      >
        Try the sample policy
      </button>
    </div>
  );
}
