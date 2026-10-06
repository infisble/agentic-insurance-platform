"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, CoreApiError } from "./api";
import { ownsPolicy, rememberPolicy } from "./portal";

// Customer actions. Like the handler actions, they only call the core API: the customer gets
// exactly the rights the state machine gives the `customer` actor, nothing more.

const CUSTOMER = { type: "customer", id: "portal" };

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function to(path: string, params: Record<string, string>): never {
  const qs = new URLSearchParams(params).toString();
  redirect(qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path);
}

function files(form: FormData): File[] {
  return form.getAll("file").filter((f): f is File => f instanceof File && f.size > 0);
}

export async function buyPolicy(form: FormData) {
  const back = `/portal/quote?${text(form, "quote")}`;
  let policyId: string;
  try {
    const party = await api.createParty({
      kind: "person",
      first_name: text(form, "first_name"),
      last_name: text(form, "last_name"),
      birth_date: text(form, "birth_date") || null,
      email: text(form, "email") || null,
      phone: text(form, "phone") || null,
      street: text(form, "street") || null,
      city: text(form, "city") || null,
      postal_code: text(form, "postal_code") || null,
      country: text(form, "country"),
      language: text(form, "language"),
    });
    const issued = await api.issuePolicy({
      holder_id: party.id,
      risk: JSON.parse(text(form, "risk")),
      start_date: text(form, "start_date"),
    });
    policyId = issued.policy.id;
  } catch (e) {
    if (e instanceof CoreApiError) to(back, { error: e.detail });
    throw e;
  }
  await rememberPolicy(policyId);
  revalidatePath("/portal");
  to(`/portal/policies/${policyId}`, { notice: "Your policy is active. Welcome!" });
}

export async function reportClaim(form: FormData) {
  const policyId = text(form, "policyId");
  if (!(await ownsPolicy(policyId))) redirect("/portal");
  let claimId: string;
  try {
    const claim = await api.reportClaim({
      data: {
        policy_id: policyId,
        peril: text(form, "peril"),
        event_date: text(form, "event_date"),
        description: text(form, "description"),
        claimed_amount: text(form, "claimed_amount"),
        channel: "portal",
      },
      actor: CUSTOMER,
    });
    claimId = claim.id;
  } catch (e) {
    if (e instanceof CoreApiError) to(`/portal/policies/${policyId}`, { error: e.detail });
    throw e;
  }
  try {
    // Each upload enqueues the claim for the agents (debounced), in the same transaction.
    for (const file of files(form)) await api.uploadDocument(claimId, file);
  } catch (e) {
    if (e instanceof CoreApiError) to(`/portal/claims/${claimId}`, { error: e.detail });
    throw e;
  }
  revalidatePath("/", "layout");
  to(`/portal/claims/${claimId}`, { notice: "Thank you. Your claim was submitted." });
}

export async function addDocuments(form: FormData) {
  const claimId = text(form, "claimId");
  const claim = await api.claim(claimId);
  if (!(await ownsPolicy(claim.policy_id))) redirect("/portal");
  const uploads = files(form);
  if (uploads.length === 0) to(`/portal/claims/${claimId}`, { error: "Choose a file to upload" });
  try {
    for (const file of uploads) await api.uploadDocument(claimId, file);
    if (claim.status === "NEEDS_INFO") {
      // The customer answered: the claim goes back into processing (and onto the job queue).
      await api.transition(claimId, {
        target: "RECEIVED",
        actor: CUSTOMER,
        reason: text(form, "comment") || "Customer sent additional documents",
      });
    }
  } catch (e) {
    if (e instanceof CoreApiError) to(`/portal/claims/${claimId}`, { error: e.detail });
    throw e;
  }
  revalidatePath("/", "layout");
  to(`/portal/claims/${claimId}`, { notice: "Documents received, thank you." });
}
