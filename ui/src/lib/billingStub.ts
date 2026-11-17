/**
 * Stub billing data for the Billing page, until the billing API exists.
 *
 * `BillingOverview` is the shape the page expects from a future `GET /v1/billing`. Dates are
 * built relative to now, so the preview always shows a period in progress. To switch to the real
 * API, replace `getBillingOverview` with an `apiFetch<BillingOverview>('/v1/billing')` call.
 */
import type { BillingInterval } from './api'

export type SubscriptionStatus = 'active' | 'trialing' | 'past_due' | 'canceled'
export type InvoiceStatus = 'paid' | 'open' | 'failed' | 'refunded'

export type Money = { amount_minor: number, currency: string }

export type BillingOverview = {
  plan: { code: string, display_name: string, price: Money, billing_interval: BillingInterval }
  subscription: {
    status: SubscriptionStatus
    current_period_start: string
    current_period_end: string
    /** True when the plan ends at `current_period_end` instead of renewing. */
    cancel_at_period_end: boolean
  }
  /** One credit = one investigation run. Credits reset at the start of each period. */
  credits: { granted: number, used: number, resets_at: string }
  payment_method: { brand: string, last4: string, exp_month: number, exp_year: number } | null
  last_payment: { amount: Money, paid_at: string } | null
  invoices: { id: string, number: string, issued_at: string, description: string, amount: Money, status: InvoiceStatus }[]
}

const day = 24 * 60 * 60 * 1000
const at = (offsetDays: number) => new Date(Date.now() + offsetDays * day).toISOString()
const pro: Money = { amount_minor: 1900, currency: 'USD' }

const stub: BillingOverview = {
  plan: { code: 'pro', display_name: 'Pro', price: pro, billing_interval: 'month' },
  subscription: { status: 'active', current_period_start: at(-12), current_period_end: at(18), cancel_at_period_end: false },
  credits: { granted: 200, used: 137, resets_at: at(18) },
  payment_method: { brand: 'Visa', last4: '4242', exp_month: 8, exp_year: 2028 },
  last_payment: { amount: pro, paid_at: at(-12) },
  invoices: [
    { id: 'inv_3', number: 'TH-0003', issued_at: at(-12), description: 'Pro, monthly', amount: pro, status: 'paid' },
    { id: 'inv_2', number: 'TH-0002', issued_at: at(-42), description: 'Pro, monthly', amount: pro, status: 'paid' },
    { id: 'inv_1', number: 'TH-0001', issued_at: at(-72), description: 'Pro, monthly', amount: pro, status: 'paid' },
  ],
}

/** Resolves like a network call so the page's loading state is exercised too. */
export const getBillingOverview = (): Promise<BillingOverview> =>
  new Promise((resolve) => setTimeout(() => resolve(stub), 350))
