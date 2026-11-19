import type { Estimate, Policy, PolicyTerms, Simulation } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.";
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
