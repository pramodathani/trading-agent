/** One event from the gateway's event bus, as the journal and the live stream carry it. */
export interface AgentEvent {
  kind: string;
  desk: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

/** One desk's state, as GET /api/desks describes it. */
export interface DeskSummary {
  name: string;
  state: string;
  paused: boolean;
  queued: number;
  mode: string;
  models: string[];
  preferred_model: string | null;
  last_model: string | null;
  session_id: string | null;
  exchanges: number;
  persona?: string | null;
}

/** The answer of GET /api/desks. */
export interface DesksDocument {
  mode: string;
  desks: DeskSummary[];
}

/** One open position in the account. */
export interface Position {
  instrument_id: string;
  symbol: string;
  segment: string;
  product: string;
  quantity: number;
  last_price: number;
  day_pnl: number | null;
}

/** A stock a desk owns in the risk ledger. */
export interface Owner {
  instrument_id: string;
  symbol: string;
  desk: string;
}

/** A halt in force, for the account or one desk. */
export interface Halt {
  scope: string;
  reason: string;
  until_date: string;
}

/** The answer of GET /api/account. */
export interface AccountDocument {
  total_balance: number;
  margin_utilized: number;
  day_pnl: number;
  week_pnl: number;
  desk_pnl: Record<string, number>;
  positions: Position[];
  holdings: Record<string, number>;
  owners: Owner[];
  halts: Halt[];
}

/** One order in the desk order book. */
export interface DeskOrder {
  record_id: string;
  desk: string;
  kind: string;
  parent_id: string | null;
  order_id: string | null;
  instrument_id: string;
  exchange: string;
  segment: string;
  symbol: string;
  transaction_type: string;
  quantity: number;
  product: string;
  price: number;
  dry_run: boolean;
  state: string;
  placed_at: string;
}

/** The answer of a journal route. */
export interface JournalDocument {
  day: string;
  events: AgentEvent[];
}

/** The answer of a tool-backed action such as flatten. */
export interface ToolActionResult {
  text: string;
  is_error: boolean;
}

/** One session in a desk's list. */
export interface SessionEntry {
  session_id: string;
  exchanges: number;
}

/** One finished turn in a session's log. */
export interface Exchange {
  trigger_text: string;
  answer: string;
  backend_name: string;
  finished_at: string;
}

/** One day's summary, written at the rollover. */
export interface DailySummary {
  date: string;
  text: string;
}

/** One of the desk's notes files. */
export interface NotesFile {
  file: string;
  text: string;
}

/** One session search hit. */
export interface SearchHit {
  day: string;
  kind: string;
  snippet: string;
}

/** One file the user may edit. */
export interface EditableFile {
  name: string;
  desk: string | null;
  exists: boolean;
  characters: number;
}

/** One proposed change to a user file, with the difference it would make. */
export interface Proposal {
  proposal_id: string;
  desk: string;
  file_name: string;
  content: string;
  reason: string;
  created_at: string;
  status: string;
  difference: string;
}

/** One scheduled job, with its next runs. */
export interface CronJob {
  job_id: string;
  name: string;
  kind: string;
  schedule: string | null;
  run_at: string | null;
  text: string;
  target: string;
  trading_days_only: boolean;
  market_hours_only: boolean;
  deliver_url: string | null;
  created_by: string;
  created_at: string;
  description: string;
  next_runs: string[];
  last_run?: string | null;
}

/** One recorded run or skip of a job. */
export interface CronRun {
  at: string;
  job_id: string;
  name: string;
  outcome: string;
  detail: string;
}

/** The body of a new job. */
export interface NewJob {
  name: string;
  schedule: string | null;
  run_at: string | null;
  instructions: string | null;
  command: string | null;
  trading_days_only: boolean;
  market_hours_only: boolean;
}

/** One price alert. */
export interface PriceAlert {
  alert_id: string;
  symbol: string;
  condition: string;
  price: number;
  note: string;
  created_at: string;
  description: string;
}

/** One skill the desk can use, with how often it was used. */
export interface SkillEntry {
  name: string;
  description: string;
  origin: string;
  uses: number;
  troubled_uses: number;
  last_used: string | null;
}

/** One skill hidden because something it needs is missing. */
export interface HiddenSkillEntry {
  name: string;
  description: string;
  origin: string;
  missing: string[];
}

/** One subagent definition. */
export interface SubagentEntry {
  name: string;
  description: string;
  tools: string[] | null;
  models: string[] | null;
  maximum_turns: number;
  timeout_seconds: number;
  path: string;
}

/** One MCP server's state. */
export interface McpServerEntry {
  name: string;
  type: string;
  state: string;
  error: string;
  tools: string[];
}

/** One installed package. */
export interface PackageEntry {
  name: string;
  version: string;
  description: string;
  skills: string[];
  agents: string[];
  mcp_servers: string[];
  hooks: string[];
  has_app: boolean;
}

/** One checkpoint of a desk's own files. */
export interface CheckpointEntry {
  checkpoint_id: string;
  created_at: string;
  reason: string;
}

/** One backend's usage today on one desk. */
export interface BackendUsage {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read_tokens: number;
  api_equivalent_cost_usd: number;
}

/** The answer of GET /api/usage. */
export interface UsageDocument {
  desks: Record<string, Record<string, BackendUsage>>;
  rate_limits: Record<string, Record<string, unknown>>;
}
