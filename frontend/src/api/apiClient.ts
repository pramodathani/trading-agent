import { tokenStore } from '../auth/tokenStore';
import type {
  AccountDocument,
  CheckpointEntry,
  CronJob,
  CronRun,
  DailySummary,
  DeskOrder,
  DesksDocument,
  DeskSummary,
  EditableFile,
  Exchange,
  HiddenSkillEntry,
  JournalDocument,
  McpServerEntry,
  NewJob,
  NotesFile,
  PackageEntry,
  PriceAlert,
  Proposal,
  SearchHit,
  SessionEntry,
  SkillEntry,
  SubagentEntry,
  ToolActionResult,
  UsageDocument,
} from './types';

/** An error answer from the gateway, with its status code and explanation. */
export class ApiError extends Error {
  readonly statusCode: number;

  /**
   * Creates the error.
   * @param statusCode The HTTP status code.
   * @param message The gateway's explanation.
   */
  constructor(statusCode: number, message: string) {
    super(message);
    this.statusCode = statusCode;
  }
}

/** Calls the gateway's API with the access token. */
export class ApiClient {
  /**
   * Checks a token by asking for the desks with it.
   * @param token The token to check.
   * @returns True when the gateway accepts it.
   */
  async isAccepted(token: string): Promise<boolean> {
    const response = await fetch('/api/desks', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    return response.ok;
  }

  /**
   * Every desk's state.
   * @returns The desks and the trading mode.
   */
  desks(): Promise<DesksDocument> {
    return this.request<DesksDocument>('GET', '/api/desks');
  }

  /**
   * Sends a message or slash command to a desk.
   * @param deskName The desk.
   * @param text The message.
   * @returns The new trigger's id.
   */
  sendMessage(deskName: string, text: string): Promise<{ trigger_id: string }> {
    return this.request('POST', `/api/desks/${deskName}/messages`, {
      text,
    });
  }

  /**
   * Pauses a desk.
   * @param deskName The desk.
   * @returns The desk's new state.
   */
  pause(deskName: string): Promise<DeskSummary> {
    return this.request('POST', `/api/desks/${deskName}/pause`);
  }

  /**
   * Resumes a desk.
   * @param deskName The desk.
   * @returns The desk's new state.
   */
  resume(deskName: string): Promise<DeskSummary> {
    return this.request('POST', `/api/desks/${deskName}/resume`);
  }

  /**
   * Cancels a desk's orders and closes its positions.
   * @param deskName The desk.
   * @param reason Why, for the journal.
   * @returns The flatten tool's report.
   */
  flatten(deskName: string, reason: string): Promise<ToolActionResult> {
    return this.request('POST', `/api/desks/${deskName}/flatten`, {
      reason,
    });
  }

  /**
   * The account's balances, positions, ownership and halts.
   * @returns The account.
   */
  account(): Promise<AccountDocument> {
    return this.request('GET', '/api/account');
  }

  /**
   * Each desk's open orders in the desk order book.
   * @returns The orders, keyed by desk.
   */
  deskOrders(): Promise<Record<string, DeskOrder[]>> {
    return this.request('GET', '/api/desk-orders');
  }

  /**
   * UBI's own order book.
   * @returns UBI's document, as UBI serves it.
   */
  brokerOrders(): Promise<{ orders?: Record<string, unknown>[] }> {
    return this.request('GET', '/api/orders?kind=orders');
  }

  /**
   * Halts every desk until tomorrow and flattens the account.
   * @param reason Why.
   * @returns The kill switch's report.
   */
  kill(reason: string): Promise<Record<string, unknown>> {
    return this.request('POST', '/api/account/kill', {
      confirm: 'FLATTEN',
      reason,
    });
  }

  /**
   * One desk's journal for a day.
   * @param deskName The desk.
   * @param limit The most events.
   * @returns The day's events, oldest first.
   */
  deskJournal(deskName: string, limit: number): Promise<JournalDocument> {
    return this.request('GET', `/api/desks/${deskName}/journal?limit=${limit}`);
  }

  /**
   * Every desk's journal for today, merged, plus the gateway's own.
   * @param deskNames The desks.
   * @param limit The most events per desk.
   * @returns The events, oldest first.
   */
  async allJournals(deskNames: string[], limit: number): Promise<JournalDocument> {
    const documents = [];
    for (const deskName of deskNames) {
      documents.push(this.deskJournal(deskName, limit));
    }
    documents.push(this.request<JournalDocument>('GET', `/api/journal?limit=${limit}`));
    const answers = await Promise.all(documents);
    const events = [];
    for (const answer of answers) {
      events.push(...answer.events);
    }
    events.sort((first, second) => first.created_at.localeCompare(second.created_at));
    return {
      day: answers[0]?.day ?? '',
      events,
    };
  }

  /**
   * One desk's sessions.
   * @param deskName The desk.
   * @returns The current session and every session with its size.
   */
  sessions(deskName: string): Promise<{ current: string | null; sessions: SessionEntry[] }> {
    return this.request('GET', `/api/desks/${deskName}/sessions`);
  }

  /**
   * One session's exchanges.
   * @param deskName The desk.
   * @param sessionId The session.
   * @returns The exchanges, oldest first.
   */
  session(deskName: string, sessionId: string): Promise<{ session_id: string; exchanges: Exchange[] }> {
    return this.request('GET', `/api/desks/${deskName}/sessions/${sessionId}`);
  }

  /**
   * One desk's daily summaries.
   * @param deskName The desk.
   * @returns The summaries, newest first.
   */
  summaries(deskName: string): Promise<{ summaries: DailySummary[] }> {
    return this.request('GET', `/api/desks/${deskName}/summaries`);
  }

  /**
   * One desk's notes files.
   * @param deskName The desk.
   * @returns The notes, newest first.
   */
  notes(deskName: string): Promise<{ notes: NotesFile[] }> {
    return this.request('GET', `/api/desks/${deskName}/notes`);
  }

  /**
   * Searches a desk's past sessions, summaries, journal and notes.
   * @param deskName The desk.
   * @param keywords The words to look for.
   * @returns The hits, and whether they hold every word.
   */
  search(deskName: string, keywords: string): Promise<{ matched_every_word: boolean; hits: SearchHit[] }> {
    return this.request('GET', `/api/desks/${deskName}/search?keywords=${encodeURIComponent(keywords)}&limit=40`);
  }

  /**
   * The files the user may edit.
   * @returns The files.
   */
  files(): Promise<{ files: EditableFile[] }> {
    return this.request('GET', '/api/files');
  }

  /**
   * One file's text.
   * @param name The file's name.
   * @param desk Its desk, or null for a shared file.
   * @returns The text.
   */
  fileText(name: string, desk: string | null): Promise<{ name: string; desk: string | null; text: string }> {
    const deskPart = desk === null ? '' : `&desk=${encodeURIComponent(desk)}`;
    return this.request('GET', `/api/files/content?name=${encodeURIComponent(name)}${deskPart}`);
  }

  /**
   * Saves one file.
   * @param name The file's name.
   * @param desk Its desk, or null for a shared file.
   * @param text The new text.
   * @returns The saved size.
   */
  saveFile(name: string, desk: string | null, text: string): Promise<{ characters: number }> {
    return this.request('PUT', '/api/files/content', {
      name,
      desk,
      text,
    });
  }

  /**
   * Every proposal, with its difference.
   * @returns The proposals, newest first.
   */
  proposals(): Promise<{ proposals: Proposal[] }> {
    return this.request('GET', '/api/proposals');
  }

  /**
   * Accepts or rejects a proposal.
   * @param proposalId The proposal.
   * @param accept True to accept, false to reject.
   * @returns The gateway's confirmation.
   */
  decideProposal(proposalId: string, accept: boolean): Promise<Record<string, unknown>> {
    return this.request('POST', `/api/proposals/${proposalId}/${accept ? 'accept' : 'reject'}`);
  }

  /**
   * One desk's jobs and recent runs.
   * @param deskName The desk.
   * @returns The jobs and runs.
   */
  jobs(deskName: string): Promise<{ jobs: CronJob[]; recent_runs: CronRun[] }> {
    return this.request('GET', `/api/desks/${deskName}/jobs`);
  }

  /**
   * Creates a job.
   * @param deskName The desk.
   * @param job The job.
   * @returns The job with its next runs.
   */
  createJob(deskName: string, job: NewJob): Promise<CronJob> {
    return this.request('POST', `/api/desks/${deskName}/jobs`, job);
  }

  /**
   * Deletes a job.
   * @param deskName The desk.
   * @param jobId The job.
   * @returns The deleted job's description.
   */
  deleteJob(deskName: string, jobId: string): Promise<{ deleted: string }> {
    return this.request('DELETE', `/api/desks/${deskName}/jobs/${jobId}`);
  }

  /**
   * Starts a job now.
   * @param deskName The desk.
   * @param jobId The job.
   * @returns A confirmation.
   */
  runJob(deskName: string, jobId: string): Promise<{ started: string }> {
    return this.request('POST', `/api/desks/${deskName}/jobs/${jobId}/run`);
  }

  /**
   * One desk's price alerts.
   * @param deskName The desk.
   * @returns The alerts.
   */
  alerts(deskName: string): Promise<{ alerts: PriceAlert[] }> {
    return this.request('GET', `/api/desks/${deskName}/alerts`);
  }

  /**
   * Removes a price alert.
   * @param deskName The desk.
   * @param alertId The alert.
   * @returns The removed alert's description.
   */
  deleteAlert(deskName: string, alertId: string): Promise<{ deleted: string }> {
    return this.request('DELETE', `/api/desks/${deskName}/alerts/${alertId}`);
  }

  /**
   * One desk's skills.
   * @param deskName The desk.
   * @returns The usable and hidden skills.
   */
  skills(deskName: string): Promise<{ available: SkillEntry[]; hidden: HiddenSkillEntry[] }> {
    return this.request('GET', `/api/desks/${deskName}/skills`);
  }

  /**
   * The subagent definitions.
   * @returns The subagents and the files that could not be read.
   */
  subagents(): Promise<{ subagents: SubagentEntry[]; broken: { path: string; error: string }[] }> {
    return this.request('GET', '/api/subagents');
  }

  /**
   * The MCP servers.
   * @returns Each server's state.
   */
  mcpServers(): Promise<{ servers: McpServerEntry[] }> {
    return this.request('GET', '/api/mcp');
  }

  /**
   * The installed packages.
   * @returns The packages.
   */
  packages(): Promise<{ packages: PackageEntry[] }> {
    return this.request('GET', '/api/packages');
  }

  /**
   * One desk's checkpoints.
   * @param deskName The desk.
   * @returns The checkpoints, newest first.
   */
  checkpoints(deskName: string): Promise<{ checkpoints: CheckpointEntry[] }> {
    return this.request('GET', `/api/desks/${deskName}/checkpoints`);
  }

  /**
   * Restores a desk's files from a checkpoint.
   * @param deskName The desk.
   * @param checkpointId The checkpoint.
   * @returns The restored checkpoint and the one that undoes the restore.
   */
  restoreCheckpoint(deskName: string, checkpointId: string): Promise<{ restored: string; undo_checkpoint_id: string }> {
    return this.request('POST', `/api/desks/${deskName}/checkpoints/${checkpointId}/restore`);
  }

  /**
   * Today's model usage.
   * @returns Usage per desk and backend, and rate-limit reports.
   */
  usage(): Promise<UsageDocument> {
    return this.request('GET', '/api/usage');
  }

  /**
   * The configuration, with secrets masked.
   * @returns trading_agent.toml as the gateway read it.
   */
  configuration(): Promise<Record<string, unknown>> {
    return this.request('GET', '/api/configuration');
  }

  /**
   * Sends one request with the token and reads its JSON answer.
   * @param method The HTTP method.
   * @param path The address under the gateway.
   * @param body The JSON body, if any.
   * @returns The answer.
   * @throws ApiError when the gateway answers with an error.
   */
  private async request<Answer>(method: string, path: string, body?: unknown): Promise<Answer> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${tokenStore.current() ?? ''}`,
    };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 401) {
      tokenStore.clear();
    }
    if (!response.ok) {
      throw new ApiError(response.status, await this.explain(response));
    }
    return (await response.json()) as Answer;
  }

  /**
   * Reads the explanation from an error answer.
   * @param response The error answer.
   * @returns FastAPI's detail text, or the status text.
   */
  private async explain(response: Response): Promise<string> {
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') {
        return body.detail;
      }
      return JSON.stringify(body.detail);
    } catch {
      return response.statusText;
    }
  }
}

export const apiClient = new ApiClient();
