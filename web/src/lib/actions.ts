"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, CoreApiError } from "./api";
import { currentHandler, setHandlerCookie } from "./handler";

// Every action goes through the core API, which enforces the same rules for handlers as for
// agents (state machine, actor permissions, validation). The UI never decides on its own.

function back(claimId: string, params: Record<string, string>): never {
  const qs = new URLSearchParams(params).toString();
  redirect(`/claims/${claimId}?${qs}`);
}

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

export async function decide(form: FormData) {
  const claimId = text(form, "claimId");
  const decision = text(form, "decision");
  const handler = await currentHandler();
  const body: Record<string, unknown> = {
    target: decision,
    actor: { type: "human", id: handler },
    reason: text(form, "reason") || null,
  };
  if (decision === "APPROVED") body.approved_amount = text(form, "amount");
  try {
    await api.transition(claimId, body);
  } catch (e) {
    if (e instanceof CoreApiError) back(claimId, { error: e.detail });
    throw e;
  }
  revalidatePath("/", "layout");
  back(claimId, { notice: `Claim moved to ${decision} by ${handler}` });
}

export async function review(form: FormData) {
  const claimId = text(form, "claimId");
  const kind = text(form, "kind");
  const handler = await currentHandler();

  // Fields are rendered as `field:<name>` with the agent's value in `orig:<name>`;
  // only the ones the handler actually changed become corrections.
  const corrections: Record<string, { from: string; to: string }> = {};
  for (const [key, value] of form.entries()) {
    if (!key.startsWith("field:")) continue;
    const name = key.slice("field:".length);
    const from = text(form, `orig:${name}`);
    const to = String(value).trim();
    if (to !== from) corrections[name] = { from, to };
  }
  let verdict = text(form, "verdict");
  if (verdict === "accept" && Object.keys(corrections).length > 0) verdict = "edit";

  try {
    await api.review(claimId, {
      kind,
      verdict,
      corrections,
      comment: text(form, "comment") || null,
      actor: { type: "human", id: handler },
    });
  } catch (e) {
    if (e instanceof CoreApiError) back(claimId, { error: e.detail });
    throw e;
  }
  revalidatePath("/", "layout");
  back(claimId, { notice: `Feedback on ${kind} saved (${verdict})` });
}

export async function switchHandler(form: FormData) {
  await setHandlerCookie(text(form, "handler"));
  revalidatePath("/", "layout");
}
