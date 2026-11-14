// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (types).
// شکل داده‌های API داشبورد مالی (فقط type).

export type View =
  | "overview"
  | "management"
  | "sales"
  | "users"
  | "customers"
  | "cheques"
  | "receivedCheques"
  | "issuedCheques"
  | "liquidity"
  | "inventoryPricing"
  | "purchaseDocs"
  | "pnl"
  | "payables"
  | "cashBank"
  | "companyPayments"
  | "collections"
  | "distribution"
  | "representatives"
  | "alerts"
  | "history"
  | "performance"
  | "settings"
  | "whatsapp";
export type AgentContent =
  string | number | Record<string, unknown> | null | undefined;
export type Analysis = {
  headline?: AgentContent;
  summary?: AgentContent;
  human_summary?: AgentContent;
  management_status?: string;
  good_signals?: AgentContent[];
  risks?: AgentContent[];
  bad_signals?: AgentContent[];
  future_outlook?: AgentContent;
  prediction?: any;
  scenarios?: any;
  recommended_actions?: Action[];
  decisions_today?: AgentContent[];
  seven_day_plan?: AgentContent[];
  next_best_action?: AgentContent;
  cheque_portfolio?: any;
  report_context?: any;
  alarms?: Array<{
    level?: string; code?: string; title?: string; message?: string; impact?: string;
    owner?: string; deadline?: string; agent?: string; priority?: number; evidence?: Array<{label?: string; value?: any}>;
  }>;
  alarm_summary?: { critical?: number; high?: number; total?: number };
  future_outlook?: any;
  agent_requests?: Array<{agent?: string; required?: string[]}>;
  data_quality?: any;
  drilldowns?: Record<string,string>;
  executive_kpis?: Array<{
    label: string;
    value?: number | null;
    value_rial?: number | null;
    format: string;
    tone?: string;
    available?: boolean;
    group?: string;
    note?: string;
  }>;
};
export type Action = {
  action?: string;
  why?: string;
  expected_effect?: string;
  owner?: string;
  priority?: string;
  deadline?: string;
};
export type CustomerAudit = Customer & {
  counterpart_code?: string;
  source_row_count?: number;
  distinct_cheque_count?: number;
  repeated_source_row_count?: number;
  historical_cheque_count?: number;
  overdue_open_cheque_count?: number;
  other_state_cheque_count?: number;
  other_state_cheque_amount?: number;
};
export type AgentResult = {
  metadata?: {
    agent_name?: string;
    mode?: string;
    agent_mode?: string;
    model?: string;
    fallback_used?: boolean;
  };
  analysis?: Analysis;
  rule_output?: any;
  data_context?: any;
};
export type Customer = {
  counterpart_ref?: number;
  counterpart_name?: string;
  customer_name?: string;
  risk_score?: number;
  risk_level?: string;
  current_overdue_open_ratio_percent?: number;
  open_exposure?: number;
  overdue_open_amount?: number;
  over_policy_count?: number;
  outside_policy_count?: number;
  historical_total_cheque_amount?: number;
  historical_average_cheque_amount?: number;
  historical_cheque_count?: number;
  collected_cheque_amount?: number;
  collected_cheque_count?: number;
  returned_cheque_amount?: number;
  returned_cheque_count?: number;
  open_cheque_count?: number;
  future_open_cheque_count?: number;
  future_open_cheque_amount?: number;
  open_cheques?: Cheque[];
  returned_cheques?: Cheque[];
  all_cheques?: Cheque[];
  b2b_remittances?: any;
  b2b_behavior?: any;
  b2b_risk_adjustment?: number;
  account_position?: any;
  collection_position?: any;
  late_payment_risk?: { value?: number; reasons?: string[] };
  cheque_return_probability?: { value?: number };
  collection_forecast?: { expected_collection_amount?: number };
  customer_behavior?: {
    reliability_score?: number;
    behavior_level?: string;
    historical_collection_rate_percent?: number;
    historical_return_rate_percent?: number;
    resolved_cheque_count?: number;
    open_overdue_ratio_percent?: number;
    history_confidence?: string;
  };
  credit_decision?: {
    policy?: string;
    recommended_reliance_percent?: number;
    recommended_max_new_cheque_amount_rial?: number;
    requires_human_approval?: boolean;
    reasons?: string[];
  };
  evidence?: string[];
  data_source?: "rahkaran" | "karamad";
  karamad_activity?: {
    branches?: string[];
    movement_count?: number;
    inflow_rial?: number;
    outflow_rial?: number;
    received_cheque_count?: number;
    received_cheque_amount_rial?: number;
    received_cheque_future_count?: number;
    received_cheque_future_amount_rial?: number;
    received_cheque_returned_count?: number;
    received_cheque_returned_amount_rial?: number;
    issued_cheque_count?: number;
    issued_cheque_amount_rial?: number;
    received_transfer_count?: number;
    received_transfer_amount_rial?: number;
    paid_transfer_count?: number;
    paid_transfer_amount_rial?: number;
    selected_branch?: string;
    dl_refs?: number[];
    detail?: any;
  };
};
export type Cheque = {
  cheque_id?: number;
  serial_number?: string;
  sayad_number?: string;
  document_number?: number | string;
  counterpart_name?: string;
  amount?: number;
  receipt_date_jalali?: string;
  receipt_date?: string;
  due_date_jalali?: string;
  due_date?: string;
  term_days?: number;
  days_to_due?: number;
  days_overdue?: number;
  due_status?: string;
  state_label?: string;
  state_code?: number;
  is_posted?: boolean;
  cashflow_open?: boolean;
  estimated_return_probability_percent?: number;
  risk_level?: string;
  reasons?: string[];
};
export type CashDay = {
  date?: string;
  date_jalali?: string;
  reliable_received_cheques?: number;
  reliable_received_cheque_count?: number;
  issued_cheques_due?: number;
  salary_reserve?: number;
  historical_other_expenses?: number;
  projected_inflow?: number;
  projected_outflow?: number;
  daily_net_change?: number;
  cumulative_net_change?: number;
  projected_cash?: number | null;
  cash_shortage?: boolean;
};
export type Rep = {
  representative_id?: string;
  representative_name?: string;
  customer_count?: number;
  high_risk_customer_count?: number;
  open_exposure?: number;
  overdue_open_amount?: number;
  average_risk_score?: number;
  status?: string;
  human_analysis?: string;
};
export type Alert = {
  alert_id: string;
  level?: string;
  title?: string;
  status?: string;
  assignee?: string;
  payload?: {
    description?: string;
    reason?: string;
    recommended_action?: string;
  };
};
export type TreasuryCheque = Cheque & {
  document_date?: string;
  document_date_jalali?: string;
  registration_date?: string;
  registration_date_jalali?: string;
  transfer_date?: string;
  transfer_date_jalali?: string;
  transfer_number?: string;
  bank_name?: string;
  description?: string;
  counterpart_ref?: number;
  cheque_item_id?: number;
  source_system?: "rahkaran" | "karamad";
  source_label?: string;
  branch?: string;
  branch_name?: string;
  bank_branch_name?: string;
  cheque_status?: string;
  cheque_location?: string;
  last_operation_account?: string;
  last_operation_level4?: string;
  assignment_date_jalali?: string;
  collection_date_jalali?: string;
  return_reason?: string;
  master_state_code?: number;
  current_status_description?: string;
  current_status_date_jalali?: string;
  current_status_document_date_jalali?: string;
  current_status_transaction_id?: number;
  status_source?: string;
};
export type Case = {
  case_id: string;
  counterpart_ref?: number;
  counterpart_name: string;
  status: string;
  priority: string;
  assignee?: string;
  due_at?: string;
  followups?: any[];
  promises?: any[];
};
export type Pack = {
  report_id?: string;
  status?: string;
  generated_at?: string;
  agents?: Record<string, AgentResult>;
  management_summary?: AgentResult;
  data_hub?: any;
  data?: {
    customer?: { customers?: Customer[] };
    cheques?: { cheques?: Cheque[] };
    cashflow?: {
      timeline?: CashDay[];
      negative_cash_pressure_days?: number;
      first_predicted_shortage_date_jalali?: string;
    };
    collections?: any;
    representatives?: {
      representatives?: Rep[];
      unmapped_customer_count?: number;
    };
  };
  policies?: Record<string, any>;
};
export type InsightRecord = {
  name: string;
  number: string;
  amount: string;
  due: string;
  timing: string;
};
export type InsightPayload = {
  title: string;
  subtitle?: string;
  stats: { label: string; value: string }[];
  notes?: string[];
  records?: InsightRecord[];
  tone?: string;
};
