import type { AccountDocument } from '../api/types';
import { formatter } from '../utilities/formatter';
import { SideCard, SideRow } from './SideCard';

/** What the funds card shows. */
interface FundsCardProperties {
  account: AccountDocument | null;
  error: string | null;
}

/**
 * The account's balance and the margin in use.
 * @param properties The account, and the latest error.
 * @returns The card.
 */
export function FundsCard(properties: FundsCardProperties) {
  const account = properties.account;
  if (account === null) {
    return (
      <SideCard cardId="funds" title="Funds">
        <p className={properties.error !== null ? 'side-empty error-text' : 'side-empty'}>{properties.error ?? 'Loading…'}</p>
      </SideCard>
    );
  }
  const marginShare = account.total_balance > 0 ? Math.min(1, account.margin_utilized / account.total_balance) : 0;
  return (
    <SideCard cardId="funds" title="Funds">
      <SideRow label="Balance" value={formatter.money(account.total_balance)} />
      <SideRow label="Margin in use" value={formatter.money(account.margin_utilized)} />
      <div className="meter" role="img" aria-label={`${Math.round(marginShare * 100)}% of the balance in use as margin`}>
        <span style={{ width: `${marginShare * 100}%` }} />
      </div>
      <p className="side-note">{formatter.share(account.margin_utilized, account.total_balance)} of the balance is in use as margin.</p>
    </SideCard>
  );
}
