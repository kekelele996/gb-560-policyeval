/** 6 个核心实体的前端类型（与 backend/src/schemas 对应）。 */

export type Role = 'admin' | 'engineer' | 'owner';
export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type ViolationStatus = 'open' | 'exception' | 'fixed';
export type RunStatus = 'running' | 'done' | 'failed';
export type ExemptionStatus = 'pending' | 'approved' | 'rejected' | 'expired';
export type RuleKind = 'Pod' | 'Deployment' | 'Namespace' | 'LimitRange';

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  role_label: string;
  scope_namespaces: string[] | null;
  is_active: boolean;
}

export interface BundleDoc {
  kind: string;
  name: string;
  namespace: string;
  replicas?: number | null;
  container_count?: number;
  images?: string[];
  spec_keys?: string[];
}

export interface Bundle {
  id: string;
  name: string;
  source: string;
  cluster: string;
  k8s_version: string;
  file_count: number;
  doc_count: number;
  namespace_count: number;
  imported_by: string;
  imported_at: string;
  warnings: string[];
  parsed_tree?: BundleDoc[];
  raw_yaml?: string;
}

export interface BundleDetail {
  bundle: Bundle;
  tree_groups: { namespace: string; docs: BundleDoc[]; doc_count: number }[];
  doc_count: number;
  namespace_count: number;
}

export interface ParseError {
  message: string;
  line: number;
  column: number;
  expected: string[];
  token: string;
  offset: number;
  snippet: string;
}

export interface Policy {
  id: string;
  code: string;
  title: string;
  severity: Severity;
  kind: RuleKind;
  dsl_text: string;
  enabled: boolean;
  version: number;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  parse_error: ParseError | null;
  parsed: boolean;
  ast_json?: unknown;
  ast_summary: string | null;
}

export interface ValidateResult {
  ok: boolean;
  error: ParseError | null;
  predicate_count?: number;
  path_count?: number;
  max_depth?: number;
  summary?: string;
  ast?: unknown;
}

export interface DryRunPreview {
  resource_kind: string;
  resource_name: string;
  namespace: string;
  evidence: Evidence;
}

export interface DryRunResult {
  policy_code: string;
  bundle_id: string;
  bundle_name: string;
  evaluated_docs: number;
  matched_docs: number;
  violated_docs: number;
  violation_count: number;
  violations_preview: DryRunPreview[];
}

export interface Run {
  id: string;
  run_key: string | null;
  bundle_id: string;
  status: RunStatus;
  status_label: string;
  rules_evaluated: number;
  rules_passed: number;
  rules_failed: number;
  docs_evaluated: number;
  violation_count: number;
  triggered_by: string;
  scope: string[];
  error_message: string;
  started_at: string;
  finished_at: string | null;
}

export interface RuleResult {
  policy_id: string | null;
  code: string;
  title: string;
  severity: Severity;
  violation_count: number;
  status: 'pass' | 'fail';
}

export interface RunDetail {
  rules: RuleResult[];
  severity_counts: Record<Severity, number>;
  status_counts: Record<ViolationStatus, number>;
  namespace_counts: Record<string, number>;
}

export interface RunPayload {
  run: Run;
  detail: RunDetail;
}

export interface LeafResult {
  template: string;
  path: string;
  actual: unknown;
  exists: boolean;
  expected: unknown;
  op: string;
  passed: boolean;
  note: string | null;
  negated: boolean;
}

export interface EvidenceResource {
  kind: string;
  namespace: string;
  name: string;
  replicas?: number;
  containers: { name: string; image: string; has_limits: boolean }[];
  labels?: string[];
}

export interface Evidence {
  algorithm: string;
  policy_code?: string;
  dsl?: string;
  ast_summary?: string;
  matched?: boolean;
  evaluated_leaves?: number;
  failed_leaves?: number;
  leaf_results?: LeafResult[];
  leaf_results_truncated?: boolean;
  warnings?: string[];
  resource?: EvidenceResource;
  metric?: string;
  used?: { value: number; milli?: number; gib?: number; display: string };
  threshold?: { value: number; milli?: number; gib?: number; display: string };
  threshold_source?: string;
  threshold_raw?: string;
  ratio?: number | null;
  over_pct?: number;
  formula?: string;
  workload_count?: number;
  pod_count?: number;
  container?: string;
  replicas?: number;
  requests?: Record<string, unknown>;
}

export interface Violation {
  id: string;
  run_id: string;
  policy_id: string | null;
  rule_code: string;
  source: 'dsl' | 'quota';
  policy_code?: string;
  policy_title?: string;
  resource_kind: string;
  resource_name: string;
  namespace: string;
  severity: Severity;
  severity_label: string;
  status: ViolationStatus;
  status_label: string;
  owner_team: string;
  created_at: string;
  rule_title?: string;
}

export interface Advice {
  id: string;
  violation_id: string;
  patch_yaml: string;
  impact: Record<string, unknown>;
  effort_level: 'S' | 'M' | 'L';
  generated_by: string;
  created_at: string;
}

export interface ViolationDetail extends Violation {
  evidence: Evidence;
  policy: {
    id: string;
    code: string;
    title: string;
    severity: Severity;
    kind: RuleKind;
    dsl_text: string;
  } | null;
  advice: Advice | null;
  exemption: {
    id: string;
    status: ExemptionStatus;
    reason: string;
    requested_by: string;
    expires_at: string | null;
  } | null;
}

export interface Exemption {
  id: string;
  policy_id: string;
  policy_code: string | null;
  policy_title: string | null;
  severity: Severity | null;
  namespace: string;
  resource_name: string;
  reason: string;
  requested_by: string;
  approved_by: string;
  status: ExemptionStatus;
  status_label: string;
  expires_at: string | null;
  decided_at: string | null;
  decision_note: string;
  created_at: string;
  violation_id?: string;
  violation_status?: ViolationStatus;
}

export interface QuotaHotspot {
  namespace: string;
  metric: string;
  used: { display: string } | null;
  threshold: { display: string } | null;
  threshold_source: string;
  over_pct: number;
  ratio?: number | null;
  severity: Severity;
  violation_id?: string;
}

export interface ViolationSummary {
  run_id: string | null;
  total: number;
  open_total: number;
  severity_counts: Record<Severity, number>;
  status_counts: Record<ViolationStatus, number>;
  source_counts: Record<string, number>;
  namespaces: { namespace: string; total: number; open: number; exception: number; fixed: number }[];
  policies: { rule_code: string; policy_id: string | null; total: number; open: number; severity: Severity }[];
  quota_hotspots: QuotaHotspot[];
}

export interface ComplianceReport {
  run: {
    id: string;
    bundle_id: string;
    bundle_name: string;
    status: RunStatus;
    rules_evaluated: number;
    rules_passed: number;
    docs_evaluated: number;
    violation_count: number;
    finished_at: string | null;
  };
  generated_at: string;
  generated_by: string;
  compliance_score: number;
  score_formula: string;
  totals: { violations: number; open: number; exception: number; fixed: number };
  severity: Record<Severity, { count: number; label: string }>;
  status: Record<ViolationStatus, { count: number; label: string }>;
  policies: { code: string; title: string; severity: Severity; total: number; open: number; exception: number; fixed: number }[];
  namespaces: { namespace: string; total: number; open: number; exception: number; fixed: number }[];
  exemptions: { total: number; by_status: Record<ExemptionStatus, { count: number; label: string }> };
  quota_hotspots: QuotaHotspot[];
  critical_samples: { code: string; namespace: string; resource: string; evidence_path: string; actual: unknown; expected: unknown }[];
}

export interface MetaSummary {
  customer: string;
  bundle: {
    id: string | null;
    name: string | null;
    doc_count: number;
    file_count: number;
    namespace_count: number;
    cluster: string;
  };
  namespaces: string[];
  policies: { total: number; enabled: number; broken: number };
  runs: {
    total: number;
    latest: {
      id: string;
      status: RunStatus;
      violation_count: number;
      rules_evaluated: number;
      rules_passed: number;
      started_at: string;
    } | null;
  };
  open_violations: {
    total: number;
    severity: Record<Severity, number>;
    by_namespace: { namespace: string; count: number }[];
  };
  exemptions: { pending: number; approved: number };
  role: Role;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
