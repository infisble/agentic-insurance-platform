// What the portal offers. Prices, limits and rules come from the core API; this is only the
// labelling the forms need.

export type ProductCode = "MOTOR_TPL" | "HOUSEHOLD";

export const PRODUCTS: Record<
  ProductCode,
  { name: string; tagline: string; perils: [string, string][] }
> = {
  MOTOR_TPL: {
    name: "Motor third-party liability",
    tagline: "Mandatory cover for damage and injury you cause to others while driving.",
    perils: [
      ["MOTOR_TP_PROPERTY", "Damage to someone else's property"],
      ["MOTOR_TP_INJURY", "Injury to another person"],
    ],
  },
  HOUSEHOLD: {
    name: "Household",
    tagline: "Your belongings at home against fire, water, flood, storm and theft.",
    perils: [
      ["FIRE", "Fire"],
      ["WATER_LEAK", "Water leak"],
      ["FLOOD", "Flood"],
      ["STORM", "Storm"],
      ["THEFT", "Theft or burglary"],
    ],
  },
};

export const REGIONS: [string, string][] = [
  ["BA", "Bratislava"],
  ["TT", "Trnava"],
  ["TN", "Trenčín"],
  ["NR", "Nitra"],
  ["ZA", "Žilina"],
  ["BB", "Banská Bystrica"],
  ["PO", "Prešov"],
  ["KE", "Košice"],
];

export const DEDUCTIBLES = ["50", "100", "200"];

export function isProduct(value: unknown): value is ProductCode {
  return value === "MOTOR_TPL" || value === "HOUSEHOLD";
}

export function perilLabel(code: string): string {
  for (const p of Object.values(PRODUCTS)) {
    const hit = p.perils.find(([c]) => c === code);
    if (hit) return hit[1];
  }
  return code;
}

// Customer-facing wording for claim statuses: no internal queues or agent names.
export const CUSTOMER_STATUS: Record<string, { label: string; text: string }> = {
  RECEIVED: { label: "Received", text: "We have your claim and are checking the documents." },
  EXTRACTED: { label: "Being checked", text: "We are reading your documents." },
  TRIAGED: { label: "Being checked", text: "We are checking your policy and the claim details." },
  COVERAGE_CHECKED: { label: "Being checked", text: "We are checking your cover." },
  AWAITING_REVIEW: {
    label: "With a claims handler",
    text: "A claims handler is reviewing your claim. Every decision is made by a person.",
  },
  NEEDS_INFO: { label: "We need more information", text: "Please send what we asked for below." },
  APPROVED: { label: "Approved", text: "Your claim is approved; the payment is on its way." },
  PAID: { label: "Paid", text: "The payment has been sent." },
  REJECTED: { label: "Not covered", text: "Unfortunately we cannot pay this claim." },
};

export const PROCESSING = new Set(["RECEIVED", "EXTRACTED", "TRIAGED", "COVERAGE_CHECKED"]);
