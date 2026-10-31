import { tokenStore } from '../auth/tokenStore';
import { gatewayAddress } from './gatewayAddress';
import type {
  AccountDocument,
  AppEntry,
  Attachment,
  CheckpointEntry,
  CommandsDocument,
  ContextDocument,
  CronJob,
  CronRun,
  DailySummary,
  TraderOrder,
  TraderSummary,
  TradersDocument,
  DevicesDocument,
  EditableFile,
  Exchange,
  HiddenSkillEntry,
  JournalDocument,
  McpServerEntry,
  NewJob,
  NotesFile,
  PackageEntry,
  PermissionGrant,
  PhoneDevice,
  PriceAlert,
  Proposal,
  QuestionAnswer,
  SearchHit,
  SessionEntry,
  SkillEntry,
  SubagentEntry,
  TelegramStatus,
  ToolActionResult,
  UsageDocument,
  UserRequest,
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
   * Checks a token by asking for the traders with it.
   * @param token The token to check.
   * @param address The gateway to ask, or the saved one when left out.
   * @returns True when the gateway accepts it.
   */
  async isAccepted(token: string, address?: string): Promise<boolean> {
    const response = await fetch(gatewayAddress.url('/api/traders', address), {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    return response.ok;
  }

  /**
   * Every trader's state.
   * @returns The traders and the trading mode.
   */
  traders(): Promise<TradersDocument> {
    return this.request<TradersDocument>('GET', '/api/traders');
  }

  /**
   * The traders' questions, plans and permission requests.
   * @param status "pending" for those waiting, or "all".
   * @returns The requests, oldest first.
   */
  async requests(status: 'pending' | 'all' = 'pending'): Promise<UserRequest[]> {
    const document = await this.request<{ requests: UserRequest[] }>('GET', `/api/requests?status=${status}`);
    return document.requests;
  }

  /**
   * Answers a trader's questions.
   * @param requestId The request.
   * @param answers One answer per question, in order.
   * @returns The answered request.
   */
  answerQuestions(requestId: string, answers: QuestionAnswer[]): Promise<UserRequest> {
    return this.request<UserRequest>('POST', `/api/requests/${requestId}/answer`, {
      answers,
    });
  }

  /**
   * Approves a trader's plan, or asks for changes.
   * @param requestId The request.
   * @param decision "approve" or "revise".
   * @param feedback What should change, or a note with an approval.
   * @returns The decided request.
   */
  decidePlan(requestId: string, decision: 'approve' | 'revise', feedback: string): Promise<UserRequest> {
    return this.request<UserRequest>('POST', `/api/requests/${requestId}/plan`, {
      decision,
      feedback,
    });
  }

  /**
   * Allows a held call once or always, which runs it, or denies it.
   * @param requestId The request.
   * @param decision "allow_once", "always_allow" or "deny".
   * @param reason Why it was denied, or a note; may be empty.
   * @returns The decided request, with the call's result when it ran.
   */
  decidePermission(requestId: string, decision: 'allow_once' | 'always_allow' | 'deny', reason: string): Promise<UserRequest> {
    return this.request<UserRequest>('POST', `/api/requests/${requestId}/permission`, {
      decision,
      reason,
    });
  }

  /**
   * The standing "Always allow" permissions.
   * @returns The grants, oldest first.
   */
  async permissionGrants(): Promise<PermissionGrant[]> {
    const document = await this.request<{ grants: PermissionGrant[] }>('GET', '/api/permissions');
    return document.grants;
  }

  /**
   * Makes a trader ask again before using a tool.
   * @param trader The trader.
   * @param toolName The tool.
   * @returns Whether a grant was removed.
   */
  revokePermission(trader: string, toolName: string): Promise<{ revoked: boolean }> {
    return this.request('POST', '/api/permissions/revoke', {
      trader,
      tool_name: toolName,
    });
  }

  /**
   * Closes a trader's request without answering it.
   * @param requestId The request.
   * @returns The dismissed request.
   */
  dismissRequest(requestId: string): Promise<UserRequest> {
    return this.request<UserRequest>('POST', `/api/requests/${requestId}/dismiss`);
  }

  /**
   * Tries one backend first from now on, optionally with another of its provider's models, or returns to the configured order.
   * @param traderName The trader.
   * @param backendName The backend, or null for the configured order.
   * @param model Another model the backend offers, or null for its configured one.
   * @returns The trader's state afterwards.
   */
  chooseModel(traderName: string, backendName: string | null, model: string | null = null): Promise<TraderSummary> {
    return this.request<TraderSummary>('POST', `/api/traders/${traderName}/model`, {
      backend: backendName,
      model,
    });
  }

  /**
   * How full a trader's context window is, and which tools it has.
   * @param traderName The trader.
   * @returns The latest snapshot, or null usage before the first turn, and the tool names.
   */
  traderContext(traderName: string): Promise<ContextDocument> {
    return this.request<ContextDocument>('GET', `/api/traders/${traderName}/context`);
  }

  /**
   * A trader's slash commands and usable skills, as /help lists them.
   * @param traderName The trader.
   * @returns The trader and its command entries.
   */
  traderCommands(traderName: string): Promise<CommandsDocument> {
    return this.request<CommandsDocument>('GET', `/api/traders/${traderName}/commands`);
  }

  /**
   * Sends a message or slash command to a trader, with files uploaded beforehand.
   * @param traderName The trader.
   * @param text The message; may be empty when files are attached.
   * @param attachmentIds The uploads to send with it.
   * @returns The new trigger's id.
   */
  sendMessage(traderName: string, text: string, attachmentIds: string[] = []): Promise<{ trigger_id: string }> {
    return this.request('POST', `/api/traders/${traderName}/messages`, {
      text,
      attachment_ids: attachmentIds,
    });
  }

  /**
   * Uploads one file for a trader, to send with a message.
   * @param traderName The trader.
   * @param file The file.
   * @returns The stored attachment.
   */
  uploadAttachment(traderName: string, file: File): Promise<Attachment> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.request('POST', `/api/traders/${traderName}/attachments`, form);
  }

  /**
   * Fetches an uploaded file, to show a picture or open a document.
   * @param traderName The trader.
   * @param attachmentId The upload.
   * @returns The file's contents.
   */
  async attachmentFile(traderName: string, attachmentId: string): Promise<Blob> {
    const response = await fetch(gatewayAddress.url(`/api/traders/${traderName}/attachments/${attachmentId}`), {
      headers: {
        Authorization: `Bearer ${tokenStore.current() ?? ''}`,
      },
    });
    if (!response.ok) {
      throw new ApiError(response.status, await this.explain(response));
    }
    return response.blob();
  }

  /**
   * Fetches a picture in a trader's folder, such as a screenshot shown in a tool's card.
   * @param traderName The trader.
   * @param picturePath The picture's path relative to the trader folder.
   * @returns The picture.
   */
  async traderPicture(traderName: string, picturePath: string): Promise<Blob> {
    const encodedPath = picturePath.split('/').map(encodeURIComponent).join('/');
    const response = await fetch(gatewayAddress.url(`/api/traders/${traderName}/pictures/${encodedPath}`), {
      headers: {
        Authorization: `Bearer ${tokenStore.current() ?? ''}`,
      },
    });
    if (!response.ok) {
      throw new ApiError(response.status, await this.explain(response));
    }
    return response.blob();
  }

  /**
   * Pauses a trader.
   * @param traderName The trader.
   * @returns The trader's new state.
   */
  pause(traderName: string): Promise<TraderSummary> {
    return this.request('POST', `/api/traders/${traderName}/pause`);
  }

  /**
   * Resumes a trader.
   * @param traderName The trader.
   * @returns The trader's new state.
   */
  resume(traderName: string): Promise<TraderSummary> {
    return this.request('POST', `/api/traders/${traderName}/resume`);
  }

  /**
   * Cancels a trader's orders and closes its positions.
   * @param traderName The trader.
   * @param reason Why, for the journal.
   * @returns The flatten tool's report.
   */
  flatten(traderName: string, reason: string): Promise<ToolActionResult> {
    return this.request('POST', `/api/traders/${traderName}/flatten`, {
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
   * Each trader's open orders in the trader order book.
   * @returns The orders, keyed by trader.
   */
  traderOrders(): Promise<Record<string, TraderOrder[]>> {
    return this.request('GET', '/api/trader-orders');
  }

  /**
   * UBI's own order book.
   * @returns UBI's document, as UBI serves it.
   */
  brokerOrders(): Promise<{ orders?: Record<string, unknown>[] }> {
    return this.request('GET', '/api/orders?kind=orders');
  }

  /**
   * Halts every trader until tomorrow and flattens the account.
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
   * One trader's journal for a day.
   * @param traderName The trader.
   * @param limit The most events.
   * @returns The day's events, oldest first.
   */
  traderJournal(traderName: string, limit: number): Promise<JournalDocument> {
    return this.request('GET', `/api/traders/${traderName}/journal?limit=${limit}`);
  }

  /**
   * Every trader's journal for today, merged, plus the gateway's own.
   * @param traderNames The traders.
   * @param limit The most events per trader.
   * @returns The events, oldest first.
   */
  async allJournals(traderNames: string[], limit: number): Promise<JournalDocument> {
    const documents = [];
    for (const traderName of traderNames) {
      documents.push(this.traderJournal(traderName, limit));
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
   * One trader's sessions.
   * @param traderName The trader.
   * @returns The current session and every session with its size.
   */
  sessions(traderName: string): Promise<{ current: string | null; sessions: SessionEntry[] }> {
    return this.request('GET', `/api/traders/${traderName}/sessions`);
  }

  /**
   * One session's exchanges.
   * @param traderName The trader.
   * @param sessionId The session.
   * @returns The exchanges, oldest first.
   */
  session(traderName: string, sessionId: string): Promise<{ session_id: string; exchanges: Exchange[] }> {
    return this.request('GET', `/api/traders/${traderName}/sessions/${sessionId}`);
  }

  /**
   * One trader's daily summaries.
   * @param traderName The trader.
   * @returns The summaries, newest first.
   */
  summaries(traderName: string): Promise<{ summaries: DailySummary[] }> {
    return this.request('GET', `/api/traders/${traderName}/summaries`);
  }

  /**
   * One trader's notes files.
   * @param traderName The trader.
   * @returns The notes, newest first.
   */
  notes(traderName: string): Promise<{ notes: NotesFile[] }> {
    return this.request('GET', `/api/traders/${traderName}/notes`);
  }

  /**
   * Searches a trader's past sessions, summaries, journal and notes.
   * @param traderName The trader.
   * @param keywords The words to look for.
   * @returns The hits, and whether they hold every word.
   */
  search(traderName: string, keywords: string): Promise<{ matched_every_word: boolean; hits: SearchHit[] }> {
    return this.request('GET', `/api/traders/${traderName}/search?keywords=${encodeURIComponent(keywords)}&limit=40`);
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
   * @param trader Its trader, or null for a shared file.
   * @returns The text.
   */
  fileText(name: string, trader: string | null): Promise<{ name: string; trader: string | null; text: string }> {
    const traderPart = trader === null ? '' : `&trader=${encodeURIComponent(trader)}`;
    return this.request('GET', `/api/files/content?name=${encodeURIComponent(name)}${traderPart}`);
  }

  /**
   * Saves one file.
   * @param name The file's name.
   * @param trader Its trader, or null for a shared file.
   * @param text The new text.
   * @returns The saved size.
   */
  saveFile(name: string, trader: string | null, text: string): Promise<{ characters: number }> {
    return this.request('PUT', '/api/files/content', {
      name,
      trader,
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
   * One trader's jobs and recent runs.
   * @param traderName The trader.
   * @returns The jobs and runs.
   */
  jobs(traderName: string): Promise<{ jobs: CronJob[]; recent_runs: CronRun[] }> {
    return this.request('GET', `/api/traders/${traderName}/jobs`);
  }

  /**
   * Creates a job.
   * @param traderName The trader.
   * @param job The job.
   * @returns The job with its next runs.
   */
  createJob(traderName: string, job: NewJob): Promise<CronJob> {
    return this.request('POST', `/api/traders/${traderName}/jobs`, job);
  }

  /**
   * Deletes a job.
   * @param traderName The trader.
   * @param jobId The job.
   * @returns The deleted job's description.
   */
  deleteJob(traderName: string, jobId: string): Promise<{ deleted: string }> {
    return this.request('DELETE', `/api/traders/${traderName}/jobs/${jobId}`);
  }

  /**
   * Starts a job now.
   * @param traderName The trader.
   * @param jobId The job.
   * @returns A confirmation.
   */
  runJob(traderName: string, jobId: string): Promise<{ started: string }> {
    return this.request('POST', `/api/traders/${traderName}/jobs/${jobId}/run`);
  }

  /**
   * One trader's price alerts.
   * @param traderName The trader.
   * @returns The alerts.
   */
  alerts(traderName: string): Promise<{ alerts: PriceAlert[] }> {
    return this.request('GET', `/api/traders/${traderName}/alerts`);
  }

  /**
   * Removes a price alert.
   * @param traderName The trader.
   * @param alertId The alert.
   * @returns The removed alert's description.
   */
  deleteAlert(traderName: string, alertId: string): Promise<{ deleted: string }> {
    return this.request('DELETE', `/api/traders/${traderName}/alerts/${alertId}`);
  }

  /**
   * One trader's skills.
   * @param traderName The trader.
   * @returns The usable and hidden skills.
   */
  skills(traderName: string): Promise<{ available: SkillEntry[]; hidden: HiddenSkillEntry[] }> {
    return this.request('GET', `/api/traders/${traderName}/skills`);
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
   * One trader's checkpoints.
   * @param traderName The trader.
   * @returns The checkpoints, newest first.
   */
  checkpoints(traderName: string): Promise<{ checkpoints: CheckpointEntry[] }> {
    return this.request('GET', `/api/traders/${traderName}/checkpoints`);
  }

  /**
   * Restores a trader's files from a checkpoint.
   * @param traderName The trader.
   * @param checkpointId The checkpoint.
   * @returns The restored checkpoint and the one that undoes the restore.
   */
  restoreCheckpoint(traderName: string, checkpointId: string): Promise<{ restored: string; undo_checkpoint_id: string }> {
    return this.request('POST', `/api/traders/${traderName}/checkpoints/${checkpointId}/restore`);
  }

  /**
   * Today's model usage.
   * @returns Usage per trader and backend, and rate-limit reports.
   */
  usage(): Promise<UsageDocument> {
    return this.request('GET', '/api/usage');
  }

  /**
   * The packages' web apps.
   * @returns Each app and its state.
   */
  async apps(): Promise<AppEntry[]> {
    const document = await this.request<{ apps: AppEntry[] }>('GET', '/api/apps');
    return document.apps;
  }

  /**
   * Starts, stops or restarts an app's systemd unit.
   * @param packageName The package.
   * @param action "start", "stop" or "restart".
   * @returns The app and its state afterwards.
   */
  appAction(packageName: string, action: 'start' | 'stop' | 'restart'): Promise<AppEntry> {
    return this.request('POST', `/api/apps/${encodeURIComponent(packageName)}/${action}`);
  }

  /**
   * Telegram's state, paired chats and waiting codes.
   * @returns The Telegram status.
   */
  async telegram(): Promise<TelegramStatus> {
    const document = await this.request<{ telegram: TelegramStatus }>('GET', '/api/channels');
    return document.telegram;
  }

  /**
   * Pairs the Telegram chat that was given a code.
   * @param code The code the bot sent.
   * @returns The paired chat.
   */
  approvePairing(code: string): Promise<Record<string, unknown>> {
    return this.request('POST', `/api/channels/telegram/pairings/${encodeURIComponent(code)}/approve`);
  }

  /**
   * Unpairs a Telegram chat.
   * @param chatId The chat.
   * @returns The removed chat.
   */
  revokePairing(chatId: number): Promise<Record<string, unknown>> {
    return this.request('DELETE', `/api/channels/telegram/chats/${chatId}`);
  }

  /**
   * Whether push notifications are on, and the phones that receive them.
   * @returns The phones, without their Firebase tokens.
   */
  devices(): Promise<DevicesDocument> {
    return this.request('GET', '/api/devices');
  }

  /**
   * Registers this phone for push notifications.
   * @param token The phone's Firebase Cloud Messaging token.
   * @param name The phone's name.
   * @returns The registered phone.
   */
  registerDevice(token: string, name: string): Promise<PhoneDevice> {
    return this.request('POST', '/api/devices', {
      token,
      name,
    });
  }

  /**
   * Removes a phone, so it gets no more notifications.
   * @param deviceId The phone's id.
   * @returns The removed phone.
   */
  removeDevice(deviceId: string): Promise<PhoneDevice> {
    return this.request('DELETE', `/api/devices/${encodeURIComponent(deviceId)}`);
  }

  /**
   * Sends a test notification to one phone.
   * @param deviceId The phone's id.
   * @returns Whether Firebase accepted it.
   */
  testDevice(deviceId: string): Promise<{ sent: boolean }> {
    return this.request('POST', `/api/devices/${encodeURIComponent(deviceId)}/test`);
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
    let encoded: BodyInit | undefined;
    if (body instanceof FormData) {
      encoded = body;
    } else if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      encoded = JSON.stringify(body);
    }
    const response = await fetch(gatewayAddress.url(path), {
      method,
      headers,
      body: encoded,
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
