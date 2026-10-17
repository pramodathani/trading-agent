import { tokenStore } from '../auth/tokenStore';
import type {
  AccountDocument,
  DeskOrder,
  DesksDocument,
  DeskSummary,
  JournalDocument,
  ToolActionResult,
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
