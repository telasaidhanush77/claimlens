import type { Estimate, Policy, PolicyTerms, Simulation } from "./types";

type FieldError = { loc?: (string | number)[]; msg?: string };

const FIELD: Record<string, string> = {
  description: "item name", amount: "amount", days: "days", category: "type",
  rate_per_day: "rate per day", name: "room type",
};

// FastAPI validation errors (422) arrive as a list; turn the first into "Row 3: amount …".
function describe(errors: FieldError[]): string {
  const e = errors[0] ?? {};
  const loc = e.loc ?? [];
  const i = loc.findIndex((p) => p === "items" || p === "room_options");
  const msg = (e.msg ?? "is invalid").replace(/^Value error, /, "");
  if (i >= 0 && typeof loc[i + 1] === "number") {
    const what = loc[i] === "items" ? "Estimate row" : "Room type";
    const field = FIELD[String(loc[i + 2])] ?? "";
    return `${what} ${Number(loc[i + 1]) + 1}: ${field} ${msg.charAt(0).toLowerCase()}${msg.slice(1)}`.replace(/\s+/g, " ");
  }
  return `Please check your input: ${msg}`;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail
      : Array.isArray(body.detail) ? describe(body.detail)
      : "Something went wrong. Please try again.";
    throw new Error(detail);
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

export const api = {
  uploadPolicy(file: File) {
    const form = new FormData();
    form.append("file", file);
    return call<Policy>("/api/policies", { method: "POST", body: form });
  },
  samplePolicy: () => call<Policy>("/api/policies/sample", { method: "POST" }),
  saveTerms: (id: string, terms: PolicyTerms) => call<Policy>(`/api/policies/${id}/terms`, json("PUT", terms)),
  sampleEstimate: () => call<Estimate>("/api/sample-estimate"),
  simulate: (policy_id: string, estimate: Estimate) =>
    call<Simulation>("/api/simulate", json("POST", { policy_id, estimate })),
};

export const rupees = (x: number | string | null | undefined) =>
  x === null || x === undefined || x === "" ? "—" : `₹${Math.round(Number(x)).toLocaleString("en-IN")}`;
