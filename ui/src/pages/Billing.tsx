import { useEffect, useState, type CSSProperties } from 'react'
import { Link } from 'react-router'
import { getBillingOverview, type BillingOverview, type InvoiceStatus, type Money, type SubscriptionStatus } from '../lib/billingStub'
import SignedInHeader from '../SignedInHeader'
import '../auth.css'

const day = 24 * 60 * 60 * 1000
const formatMoney = ({ amount_minor, currency }: Money) =>
  new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount_minor / 100)
const formatDate = (iso: string) =>
  `${new Date(iso).toLocaleDateString(undefined, { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' })}`
const daysUntil = (iso: string) => Math.max(0, Math.ceil((Date.parse(iso) - Date.now()) / day))
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

const statusLabel: Record<SubscriptionStatus, string> = { active: 'Active', trialing: 'Trial', past_due: 'Payment due', canceled: 'Canceled' }
const invoiceLabel: Record<InvoiceStatus, string> = { paid: 'Paid', open: 'Open', failed: 'Failed', refunded: 'Refunded' }

type Load = { status: 'loading' } | { status: 'ready', billing: BillingOverview }

export default function Billing() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })

  useEffect(() => {
    let active = true
    void getBillingOverview().then((billing) => { if (active) setLoad({ status: 'ready', billing }) })
    return () => { active = false }
  }, [])

  return (
    <div className="auth-page">
      <SignedInHeader />
      <main className="workspace">
        <Link className="back-link" to="/app"><span aria-hidden="true">←</span> Home</Link>
        <div className="workspace-heading">
          <div><p className="eyebrow"><span /> Account</p><h1>Billing & subscription</h1><p className="heading-note">Your plan, the credits left this period, and what you’ve paid. One credit runs one investigation.</p></div>
          <button type="button" className="button-primary" disabled title="Plan changes are coming soon">Change plan</button>
        </div>

        <p className="billing-preview" role="note"><span aria-hidden="true">●</span> Preview: these figures are sample data until billing goes live.</p>

        {load.status === 'loading'
          ? <div className="billing-grid" aria-busy="true"><p className="sr-only" role="status">Loading billing</p>{[0, 1, 2].map((i) => <div key={i} className="billing-card"><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></div>)}</div>
          : <BillingDetails billing={load.billing} />}
      </main>
    </div>
  )
}

function BillingDetails({ billing }: { billing: BillingOverview }) {
  const { plan, subscription, credits, payment_method: card, last_payment: lastPayment, invoices } = billing
  const periodDays = Math.max(1, Math.round((Date.parse(subscription.current_period_end) - Date.parse(subscription.current_period_start)) / day))
  const daysLeft = daysUntil(subscription.current_period_end)
  const remaining = Math.max(0, credits.granted - credits.used)
  const creditShare = credits.granted ? remaining / credits.granted : 0
  const low = creditShare < 0.2

  return (
    <>
      <div className="billing-grid">
        <section className="billing-card" aria-labelledby="plan-title">
          <p className="billing-label" id="plan-title">Current plan</p>
          <div className="billing-plan">
            <h2>{plan.display_name}</h2>
            <span className={`billing-status is-${subscription.status}`}>{statusLabel[subscription.status]}</span>
          </div>
          <p className="billing-figure">{formatMoney(plan.price)}<span> / {plan.billing_interval}</span></p>
          <Meter value={(periodDays - daysLeft) / periodDays} label="Billing period elapsed" />
          <p className="billing-note"><strong>{plural(daysLeft, 'day')}</strong> left · {subscription.cancel_at_period_end ? 'ends' : 'renews'} {formatDate(subscription.current_period_end)}</p>
        </section>

        <section className="billing-card" aria-labelledby="credits-title">
          <p className="billing-label" id="credits-title">Credits remaining</p>
          <p className="billing-figure billing-figure-large">{remaining}<span> of {credits.granted}</span></p>
          <Meter value={creditShare} label="Credits remaining" tone={low ? 'low' : undefined} />
          <p className="billing-note">{credits.used} used this period · resets {formatDate(credits.resets_at)}</p>
          {low && <p className="billing-warning">Running low. Investigations stop when credits reach zero.</p>}
        </section>

        <section className="billing-card" aria-labelledby="payment-title">
          <p className="billing-label" id="payment-title">Last payment</p>
          {lastPayment
            ? <><p className="billing-figure">{formatMoney(lastPayment.amount)}</p><p className="billing-note">Paid {formatDate(lastPayment.paid_at)}</p></>
            : <p className="billing-note">No payments yet.</p>}
          <dl className="billing-facts">
            <div><dt>Payment method</dt><dd>{card ? <>{card.brand} ···· {card.last4} <span>exp {String(card.exp_month).padStart(2, '0')}/{String(card.exp_year).slice(-2)}</span></> : 'None on file'}</dd></div>
            <div><dt>Next charge</dt><dd>{subscription.cancel_at_period_end ? 'None' : `${formatMoney(plan.price)} on ${formatDate(subscription.current_period_end)}`}</dd></div>
          </dl>
          <button type="button" className="button-quiet" disabled title="Coming soon">Update payment method</button>
        </section>
      </div>

      <section className="billing-invoices" aria-labelledby="invoices-title">
        <h2 id="invoices-title">Invoices</h2>
        {invoices.length === 0
          ? <p className="billing-note">No invoices yet.</p>
          : <table className="key-table billing-table">
            <thead><tr><th scope="col">Invoice</th><th scope="col">Date (UTC)</th><th scope="col">Description</th><th scope="col">Amount</th><th scope="col">Status</th></tr></thead>
            <tbody>{invoices.map((invoice) => <tr key={invoice.id}>
              <td data-label="Invoice"><code>{invoice.number}</code></td>
              <td data-label="Date (UTC)">{formatDate(invoice.issued_at)}</td>
              <td data-label="Description" className="key-name">{invoice.description}</td>
              <td data-label="Amount">{formatMoney(invoice.amount)}</td>
              <td data-label="Status"><span className={`billing-status is-${invoice.status}`}>{invoiceLabel[invoice.status]}</span></td>
            </tr>)}</tbody>
          </table>}
      </section>
    </>
  )
}

function Meter({ value, label, tone }: { value: number, label: string, tone?: 'low' }) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100)
  return (
    <div className={`billing-meter${tone ? ` is-${tone}` : ''}`} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
      <span style={{ '--meter': `${percent}%` } as CSSProperties} />
    </div>
  )
}
