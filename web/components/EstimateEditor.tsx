"use client";

import { CATEGORIES, CATEGORY_LABEL, type Category, type Estimate, type LineItem, type RoomOption } from "@/lib/types";

// Rows carry a client-only key so React keeps inputs attached to the right row.
export type Row = LineItem & { key: string };
export type Draft = { procedure: string; items: Row[]; rooms: (RoomOption & { key: string })[] };

const newKey = () => Math.random().toString(36).slice(2);
const STAYS: Category[] = ["room", "icu"];

export function draftFrom(est: Estimate): Draft {
  return {
    procedure: est.procedure ?? "",
    items: est.items.map((i) => ({ ...i, key: newKey() })),
    rooms: est.room_options.map((r) => ({ ...r, key: newKey() })),
  };
}

export function estimateFrom(d: Draft): Estimate {
  return {
    procedure: d.procedure.trim() || null,
    items: d.items.map(({ key: _k, ...i }) => ({ ...i, days: STAYS.includes(i.category) ? i.days || 1 : null })),
    room_options: d.rooms.filter((r) => r.name && Number(r.rate_per_day) > 0).map(({ key: _k, ...r }) => r),
  };
}

const cell = "w-full rounded border border-line px-2 py-1.5 text-sm";

type Props = { draft: Draft; onChange: (d: Draft) => void };

export function EstimateEditor({ draft, onChange }: Props) {
  const setItem = (key: string, patch: Partial<LineItem>) =>
    onChange({ ...draft, items: draft.items.map((i) => (i.key === key ? { ...i, ...patch } : i)) });
  const setRoom = (key: string, patch: Partial<RoomOption>) =>
    onChange({ ...draft, rooms: draft.rooms.map((r) => (r.key === key ? { ...r, ...patch } : r)) });

  return (
    <div className="space-y-5">
      <label className="block text-sm">
        <span className="font-medium">Procedure</span>
        <span className="ml-2 text-muted">(matches the policy&apos;s sub-limits, e.g. &quot;Knee replacement&quot;)</span>
        <input className={`${cell} mt-1 max-w-sm`} value={draft.procedure} onChange={(e) => onChange({ ...draft, procedure: e.target.value })} />
      </label>

      <div className="relative overflow-x-auto rounded-xl border border-line bg-card">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr><th className="p-3">Item</th><th className="p-3">Type</th><th className="p-3">Amount ₹</th><th className="p-3">Days</th><th className="p-3"><span className="sr-only">Remove</span></th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {draft.items.map((i) => (
              <tr key={i.key}>
                <td className="p-2"><input aria-label="Item" className={cell} value={i.description} onChange={(e) => setItem(i.key, { description: e.target.value })} /></td>
                <td className="p-2">
                  <select aria-label="Type" className={cell} value={i.category} onChange={(e) => setItem(i.key, { category: e.target.value as Category })}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
                  </select>
                </td>
                <td className="p-2"><input aria-label="Amount" inputMode="decimal" className={`${cell} num w-28`} value={String(i.amount)} onChange={(e) => setItem(i.key, { amount: e.target.value.replace(/[^\d.]/g, "") })} /></td>
                <td className="p-2">
                  {STAYS.includes(i.category) && (
                    <input aria-label="Days" inputMode="numeric" className={`${cell} num w-16`} value={i.days ?? ""} onChange={(e) => setItem(i.key, { days: Number(e.target.value.replace(/\D/g, "")) || null })} />
                  )}
                </td>
                <td className="p-2 text-right">
                  <button type="button" aria-label={`Remove ${i.description || "row"}`} onClick={() => onChange({ ...draft, items: draft.items.filter((x) => x.key !== i.key) })} className="rounded px-2 text-muted hover:text-loss">✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" onClick={() => onChange({ ...draft, items: [...draft.items, { key: newKey(), description: "", category: "other", amount: "", days: null }] })} className="m-2 rounded px-3 py-1.5 text-sm font-medium text-teal hover:bg-teal-soft">
          + Add item
        </button>
      </div>

      <div>
        <p className="text-sm font-medium">Room types the hospital offers <span className="font-normal text-muted">(optional, to compare)</span></p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {draft.rooms.map((r) => (
            <div key={r.key} className="flex gap-2">
              <input aria-label="Room type" className={cell} value={r.name} onChange={(e) => setRoom(r.key, { name: e.target.value })} />
              <input aria-label="Rate per day" inputMode="decimal" className={`${cell} num w-28`} value={String(r.rate_per_day)} onChange={(e) => setRoom(r.key, { rate_per_day: e.target.value.replace(/[^\d.]/g, "") })} />
              <button type="button" aria-label={`Remove ${r.name || "room"}`} onClick={() => onChange({ ...draft, rooms: draft.rooms.filter((x) => x.key !== r.key) })} className="px-1 text-muted hover:text-loss">✕</button>
            </div>
          ))}
        </div>
        <button type="button" onClick={() => onChange({ ...draft, rooms: [...draft.rooms, { key: newKey(), name: "", rate_per_day: "" }] })} className="mt-2 rounded px-3 py-1.5 text-sm font-medium text-teal hover:bg-teal-soft">
          + Add room type
        </button>
      </div>
    </div>
  );
}
