import "server-only";

import type {
  AgentRun,
  Claim,
  ClaimEvent,
  DocumentMeta,
  JobStats,
  Overview,
  Party,
  Policy,
  PolicyIssued,
  Premium,
  Review,
} from "./types";

export const CORE_API_URL = process.env.CORE_API_URL ?? "http://localhost:8000";

export class CoreApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`core API ${status}: ${detail}`);
  }
}

function describe(detail: unknown): string {
  // FastAPI request validation returns a list of {loc, msg}; domain errors return a string.
  if (Array.isArray(detail)) {
    return detail
      .map((d) => `${(d.loc ?? []).filter((p: unknown) => p !== "body").join(".")}: ${d.msg}`)
      .join("; ");
  }
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${CORE_API_URL}${path}`, {
    cache: "no-store", // claims change constantly; never serve a stale case to a handler
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = describe(body.detail ?? body);
    } catch {
      // keep statusText
    }
    throw new CoreApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function request<T>(path: string, init?: RequestInit): Promise<T> {
  return send<T>(path, { ...init, headers: { "content-type": "application/json", ...init?.headers } });
}

function post<T>(path: string, body: object): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const api = {
  overview: () => request<Overview>("/metrics/overview"),
  claims: (status?: string) =>
    request<Claim[]>(`/claims?limit=500${status ? `&status=${status}` : ""}`),
  claim: (id: string) => request<Claim>(`/claims/${id}`),
  policy: (id: string) => request<Policy>(`/policies/${id}`),
  documents: (claimId: string) => request<DocumentMeta[]>(`/claims/${claimId}/documents`),
  events: (claimId: string) => request<ClaimEvent[]>(`/claims/${claimId}/events`),
  runs: (claimId: string) => request<AgentRun[]>(`/claims/${claimId}/agent-runs`),
  reviews: (claimId: string) => request<Review[]>(`/claims/${claimId}/reviews`),
  jobStats: () => request<JobStats>("/jobs/stats"),
  transition: (claimId: string, body: object) => post<Claim>(`/claims/${claimId}/transitions`, body),
  review: (claimId: string, body: object) => post<Review>(`/claims/${claimId}/reviews`, body),

  // Customer portal
  quote: (body: object) => post<Premium>("/quotes", body),
  createParty: (body: object) => post<Party>("/parties", body),
  issuePolicy: (body: object) => post<PolicyIssued>("/policies", body),
  policyClaims: (policyId: string) => request<Claim[]>(`/policies/${policyId}/claims`),
  reportClaim: (body: object) => post<Claim>("/claims", body),
  uploadDocument: (claimId: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return send<DocumentMeta>(`/claims/${claimId}/documents`, { method: "POST", body: form });
  },
};
