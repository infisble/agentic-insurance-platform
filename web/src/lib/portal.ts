import "server-only";

import { cookies } from "next/headers";

// Development stand-in for customer identity: the policies bought in this browser are kept in
// an httpOnly cookie, and portal pages only show those. Production uses Entra External ID
// (ADR 0013) and the core API scopes every read to the signed-in customer.
const COOKIE = "aip_portal_policies";
const MAX_POLICIES = 20;

export async function myPolicyIds(): Promise<string[]> {
  const raw = (await cookies()).get(COOKIE)?.value ?? "";
  return raw.split(".").filter((id) => /^[0-9a-f-]{36}$/.test(id));
}

export async function ownsPolicy(policyId: string): Promise<boolean> {
  return (await myPolicyIds()).includes(policyId);
}

export async function rememberPolicy(policyId: string): Promise<void> {
  const ids = [policyId, ...(await myPolicyIds()).filter((id) => id !== policyId)];
  (await cookies()).set(COOKIE, ids.slice(0, MAX_POLICIES).join("."), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
}
