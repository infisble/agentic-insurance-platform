// Shapes returned by the core API (src/aip/api/schemas.py).

export type ClaimStatus =
  | "RECEIVED"
  | "EXTRACTED"
  | "TRIAGED"
  | "COVERAGE_CHECKED"
  | "AWAITING_REVIEW"
  | "NEEDS_INFO"
  | "APPROVED"
  | "REJECTED"
  | "PAID";

export interface CoverageReason {
  code: string;
  clause: string;
  message: string;
}

export interface Coverage {
  decision: "COVERED" | "NOT_COVERED" | "REFER";
  payable_amount: string;
  reasons: CoverageReason[];
}

export interface Issue {
  code: string;
  field: string;
  severity: "error" | "warning";
  message: string;
}

export interface Evidence {
  field: string;
  quote: string;
  confidence: "high" | "medium" | "low";
}

export interface ExtractedDocument {
  doc_type: string;
  language: string;
  policy_number: string | null;
  claimant_name: string | null;
  event_date: string | null;
  issue_date: string | null;
  vendor_name: string | null;
  document_number: string | null;
  currency: string | null;
  total_amount: string | null;
  iban: string | null;
  line_items: { description: string; amount: string }[];
  damage_description: string | null;
  evidence: Evidence[];
}

export interface ExtractionDraft {
  documents: {
    document_id: string;
    filename: string;
    data: ExtractedDocument;
    issues: Issue[];
  }[];
  _by: string;
}

export interface TriageDraft {
  peril: string;
  peril_matches_reported: boolean;
  complexity: string;
  queue: string;
  fraud_signals: string[];
  missing_information: string[];
  rationale: string;
  proposed_queue: string;
  final_queue: string;
  routing_overrides: string[];
  _by: string;
}

export interface SummaryDraft {
  summary_sk: string;
  key_facts: string[];
  open_questions: string[];
  recommendation: "approve" | "reject" | "request_information" | "refer_senior";
  recommendation_rationale: string;
  draft_customer_message: string;
  _by: string;
}

export interface Claim {
  id: string;
  number: string;
  policy_id: string;
  status: ClaimStatus;
  peril: string;
  event_date: string;
  reported_at: string;
  channel: string;
  description: string;
  claimed_amount: string;
  payable_amount: string | null;
  approved_amount: string | null;
  coverage: Coverage | null;
  queue: string | null;
  extraction: ExtractionDraft | null;
  triage: TriageDraft | null;
  summary: SummaryDraft | null;
  version: number;
}

export interface Policy {
  id: string;
  number: string;
  product_code: "MOTOR_TPL" | "HOUSEHOLD";
  status: string;
  start_date: string;
  end_date: string;
  conditions_version: string;
  risk: Record<string, unknown>;
  gross_premium: string;
}

export interface DocumentMeta {
  id: string;
  filename: string;
  content_type: string;
  page_count: number | null;
}

export interface ClaimEvent {
  seq: number;
  from_status: string | null;
  to_status: string;
  actor_type: string;
  actor_id: string;
  reason: string | null;
  at: string;
}

export interface AgentRun {
  id: string;
  agent: string;
  agent_version: string;
  model: string;
  status: "ok" | "failed";
  turns: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  latency_ms: number;
  cache_hit: boolean;
  error: string | null;
  created_at: string;
}

export interface Review {
  id: string;
  kind: "extraction" | "triage" | "summary";
  agent: string;
  verdict: "accept" | "edit" | "reject";
  corrections: Record<string, { from: unknown; to: unknown }>;
  comment: string | null;
  reviewer: string;
  at: string;
}

export interface AgentMetrics {
  agent: string;
  runs: number;
  failed: number;
  cache_hits: number;
  cost_usd: string;
  avg_cost_usd: string;
  avg_latency_ms: number;
  reviewed: number;
  accepted: number;
  edited: number;
  rejected: number;
  override_rate: number | null;
}

export interface Overview {
  claims_by_status: Record<string, number>;
  review_queue: Record<string, number>;
  agents: AgentMetrics[];
  most_corrected_fields: [string, number][];
  total_agent_cost_usd: string;
}

export type JobStats = Record<"queued" | "running" | "done" | "dead", number>;

export interface Factor {
  name: string;
  value: string;
  explanation: string;
}

export interface Premium {
  product: string;
  tariff_version: string;
  base: string;
  factors: Factor[];
  net_premium: string;
  tax: string;
  gross_premium: string;
}

export interface Party {
  id: string;
  first_name: string | null;
  last_name: string;
  email: string | null;
  country: string;
  language: string;
}

export interface PolicyIssued {
  policy: Policy;
  premium: Premium;
}
