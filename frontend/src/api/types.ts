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
