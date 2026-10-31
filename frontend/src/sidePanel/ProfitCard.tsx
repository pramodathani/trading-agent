import type { AccountDocument } from '../api/types';
import { formatter } from '../utilities/formatter';
import { SideCard, SideRow } from './SideCard';

/** What the profit card shows. */
interface ProfitCardProperties {
  traderName: string;
  account: AccountDocument | null;
}

/**
 * Profit and loss for this trader and for the whole account, and any halt in force.
 * @param properties The trader's name and the account.
 * @returns The card, or nothing while the account loads.
 */
export function ProfitCard(properties: ProfitCardProperties) {
  const account = properties.account;
  if (account === null) {
    return null;
  }
  const traderPnl = account.trader_pnl[properties.traderName] ?? 0;
  const halts = account.halts.filter((halt) => halt.scope === properties.traderName || halt.scope === 'account');
  return (
    <SideCard cardId="pnl" title="Profit and loss">
      <SideRow label="This trader today" value={formatter.signedMoney(traderPnl)} valueClassName={formatter.pnlClass(traderPnl)} />
      <SideRow label="Account today" value={formatter.signedMoney(account.day_pnl)} valueClassName={formatter.pnlClass(account.day_pnl)} />
      <SideRow label="Account this week" value={formatter.signedMoney(account.week_pnl)} valueClassName={formatter.pnlClass(account.week_pnl)} />
      {halts.map((halt) => (
        <p key={`${halt.scope}-${halt.until_date}`} className="halt-line">
          {halt.scope === 'account' ? 'Account' : 'Trader'} halted until {halt.until_date}: {halt.reason}
        </p>
      ))}
    </SideCard>
  );
}
