import "server-only";

import { cookies } from "next/headers";

// Development identity: the handler picks a name in the header. Production replaces this
// with Entra ID (ADR 0013); the core API then derives the actor from the token.
export const HANDLERS = ["handler.novak", "handler.horvathova", "senior.kovac"] as const;
const COOKIE = "aip_handler";

export async function currentHandler(): Promise<string> {
  const value = (await cookies()).get(COOKIE)?.value;
  return HANDLERS.includes(value as (typeof HANDLERS)[number]) ? value! : HANDLERS[0];
}

export async function setHandlerCookie(name: string): Promise<void> {
  if (!HANDLERS.includes(name as (typeof HANDLERS)[number])) return;
  (await cookies()).set(COOKIE, name, { httpOnly: true, sameSite: "lax", path: "/" });
}
