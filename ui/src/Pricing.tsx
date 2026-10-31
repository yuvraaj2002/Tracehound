import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useAuth } from './auth/context'
import { useGetStarted } from './auth/useGetStarted'
import { listPlans, type BillingInterval, type PlanPrice, type PlanSummary } from './lib/api'
import './Pricing.css'

/** The plan given the "Most popular" badge, by code. Ignored when no such plan is listed. */
const FEATURED_PLAN = 'pro'

/** Who each plan is for, by code. Unlisted plans fall back to a line built from their credits. */
const descriptions: Record<string, string> = {
  free: 'Try Tracehound on a real incident and see how the team investigates, before you commit to anything.',
  pro: 'For engineers on call every week. Enough investigations to open a case on the alerts that matter.',
  max: 'For teams that investigate every page. Room to open a case on every alert, not only the big ones.',
}

/** Only what every plan does today. Plans differ in how many investigations they include. */
const features = [
  'All six specialists on every case',
  'Cited evidence behind every finding',
  'Ranked hypotheses, with uncertainty shown',
  'Loki log integration',
  'REST API and keys for your alerting tools',
]

type Load = { status: 'loading' } | { status: 'error', message: string } | { status: 'ready', plans: PlanSummary[] }

/** Formats a minor-unit amount, dropping the decimals from whole amounts ($19, not $19.00). */
function money(minor: number, currency: string) {
  const digits = new Intl.NumberFormat(undefined, { style: 'currency', currency }).resolvedOptions().maximumFractionDigits ?? 2
  const major = minor / 10 ** digits
  const fraction = Number.isInteger(major) ? 0 : digits
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, minimumFractionDigits: fraction, maximumFractionDigits: fraction }).format(major)
}

const priceOf = (plan: PlanSummary, currency: string, interval: BillingInterval) =>
  plan.prices.find((price) => price.currency === currency && price.billing_interval === interval)

/** How much a year costs less than twelve months, as a fraction; null without both prices. */
function yearlySaving(plan: PlanSummary, currency: string) {
  const month = priceOf(plan, currency, 'month')
  const year = priceOf(plan, currency, 'year')
  if (!month || !year || month.amount_minor === 0) return null
  return 1 - year.amount_minor / (12 * month.amount_minor)
}

/** USD when offered, otherwise the first currency listed. One currency is shown at a time. */
function displayCurrency(plans: PlanSummary[]) {
  const currencies = plans.flatMap((plan) => plan.prices.map((price) => price.currency))
  return currencies.includes('USD') ? 'USD' : currencies[0] ?? 'USD'
}

function readRequest(search: string): { plan: string | null, interval: BillingInterval | null } {
  const params = new URLSearchParams(search)
  const billing = params.get('billing')
  return { plan: params.get('plan'), interval: billing === 'month' || billing === 'year' ? billing : null }
}

export default function Pricing() {
  const { session } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  // A visitor sent to sign in from Subscribe comes back with ?plan=&billing= to pick up where they were.
  const [request] = useState(() => readRequest(location.search))
  const [interval, setBillingInterval] = useState<BillingInterval>(request.interval ?? 'year')
  const [picked, setPicked] = useState<string | null>(null)
  // The session restores after first render, so a returning visitor's plan is read once it has.
  const pending = picked ?? (session ? request.plan : null)

  const fetchPlans = useCallback(() => listPlans()
    .then(({ items }) => setLoad({ status: 'ready', plans: items }))
    .catch((err: unknown) => setLoad({ status: 'error', message: err instanceof Error ? err.message : 'Could not load the plans.' })), [])

  useEffect(() => { void fetchPlans() }, [fetchPlans])

  const retry = () => { setLoad({ status: 'loading' }); void fetchPlans() }

  // Router navigation (e.g. back from sign-in) doesn't scroll to the hash the way a page load does.
  useEffect(() => {
    if (location.hash === '#pricing') document.getElementById('pricing')?.scrollIntoView({ block: 'start' })
  }, [location.hash])

  const plans = load.status === 'ready' ? load.plans : []
  const currency = displayCurrency(plans)
  const intervals = new Set(plans.flatMap((plan) => plan.prices.filter((price) => price.currency === currency).map((price) => price.billing_interval)))
  const bestSaving = Math.max(0, ...plans.map((plan) => yearlySaving(plan, currency) ?? 0))
  // With only one interval on offer there is nothing to toggle.
  const shownInterval: BillingInterval = intervals.size === 1 ? [...intervals][0]! : interval

  const subscribe = (plan: PlanSummary) => {
    if (!session) {
      navigate('/signin', { state: { from: `/?${new URLSearchParams({ plan: plan.code, billing: shownInterval })}#pricing` } })
      return
    }
    // Payments aren't live yet. Checkout for (plan.code, shownInterval, currency) starts here.
    setPicked(plan.code)
  }

  return (
    <section id="pricing" className="pricing" aria-labelledby="pricing-title">
      <div className="section-heading">
        <div><p className="eyebrow">Pricing</p><h2 id="pricing-title">Pay for investigations,<br />not for seats.</h2></div>
        <p>Every plan gets the whole team. Pick how many investigations you need each month, and change plans as you grow.</p>
      </div>

      {intervals.size > 1 && <fieldset className="billing-toggle">
        <legend className="sr-only">Billing period</legend>
        {(['month', 'year'] as const).map((value) => <label key={value}>
          <input type="radio" name="billing" value={value} checked={interval === value} onChange={() => setBillingInterval(value)} />
          <span>{value === 'month' ? 'Monthly' : 'Yearly'}{value === 'year' && bestSaving >= 0.01 && <em>Save up to {Math.round(bestSaving * 100)}%</em>}</span>
        </label>)}
      </fieldset>}

      {load.status === 'loading' && <ul className="plan-grid" aria-busy="true" aria-label="Loading plans">
        {[0, 1, 2].map((index) => <li key={index} className="plan-card is-skeleton" aria-hidden="true"><span /><span /><span /><span /></li>)}
      </ul>}

      {load.status === 'error' && <div className="pricing-notice" role="alert">
        <p>Pricing couldn’t be loaded. {load.message}</p>
        <button type="button" className="pricing-retry" onClick={retry}>Try again</button>
      </div>}

      {load.status === 'ready' && plans.length === 0 && <div className="pricing-notice"><p>Plans are on their way. Check back soon.</p></div>}

      {plans.length > 0 && <ul className="plan-grid" style={{ '--plan-count': plans.length } as CSSProperties}>
        {plans.map((plan) => <PlanCard
          key={plan.code}
          plan={plan}
          price={priceOf(plan, currency, shownInterval)}
          monthly={priceOf(plan, currency, 'month')}
          interval={shownInterval}
          featured={plan.code === FEATURED_PLAN && plans.length > 1}
          signedIn={Boolean(session)}
          pending={pending === plan.code}
          onSubscribe={() => subscribe(plan)}
        />)}
      </ul>}

      {plans.length > 0 && <p className="plan-footnote">One credit runs one investigation. Credits are granted every month, on yearly plans too.</p>}
    </section>
  )
}

type PlanCardProps = {
  plan: PlanSummary
  price: PlanPrice | undefined
  monthly: PlanPrice | undefined
  interval: BillingInterval
  featured: boolean
  signedIn: boolean
  pending: boolean
  onSubscribe: () => void
}

function PlanCard({ plan, price, monthly, interval, featured, signedIn, pending, onSubscribe }: PlanCardProps) {
  const free = plan.prices.length === 0 || price?.amount_minor === 0
  const titleId = `plan-${plan.code}`
  const currency = price?.currency ?? monthly?.currency ?? 'USD'
  const yearly = interval === 'year' && price
  // What a month costs on this billing period, in minor units.
  const perMonth = price ? (yearly ? Math.round(price.amount_minor / 12) : price.amount_minor) : null
  const saving = yearly && monthly && monthly.amount_minor > 0 ? Math.round((1 - price.amount_minor / (12 * monthly.amount_minor)) * 100) : 0

  let detail: string
  if (free) detail = 'Free forever'
  else if (!price) detail = `Not offered ${interval === 'year' ? 'yearly' : 'monthly'}`
  else detail = yearly ? `Billed ${money(price.amount_minor, currency)} yearly` : 'Billed monthly'

  return (
    <li className={`plan-card ${featured ? 'is-featured' : ''}`} aria-labelledby={titleId}>
      <div className="plan-head">
        <h3 id={titleId}>{plan.display_name}</h3>
        {featured && <span className="plan-badge">Most popular</span>}
      </div>
      <p className="plan-description">{descriptions[plan.code] ?? `${plan.credits.toLocaleString()} investigations a month, with all six specialists on every case.`}</p>

      <p className="plan-price">
        {saving > 0 && monthly && <span className="plan-was"><span className="sr-only">Was </span>{money(monthly.amount_minor, currency)}</span>}
        <span className="plan-amount">{free ? money(0, currency) : perMonth === null ? '—' : money(perMonth, currency)}</span>
        {!free && perMonth !== null && <span className="plan-unit">/ month</span>}
      </p>
      <p className="plan-detail">{detail}{saving > 0 && <span className="plan-save">Save {saving}%</span>}</p>
      <p className="plan-rate">{perMonth !== null && !free && plan.credits > 0 ? `About ${money(Math.round(perMonth / plan.credits), currency)} per investigation` : ''}</p>

      {free
        ? <StartFree signedIn={signedIn} />
        : <button type="button" className="plan-action" onClick={onSubscribe} disabled={!price} aria-describedby={pending ? `${titleId}-pending` : undefined}>Subscribe <span aria-hidden="true">→</span></button>}
      <p className="plan-pending" id={`${titleId}-pending`} role="status">{pending && 'Checkout opens here soon. We’re finishing payments now.'}</p>

      <p className="plan-features-label">What’s included</p>
      <ul className="plan-features">
        <li><CheckIcon /><span><strong>{plan.credits.toLocaleString()}</strong> investigation{plan.credits === 1 ? '' : 's'} a month</span></li>
        {features.map((item) => <li key={item}><CheckIcon /><span>{item}</span></li>)}
      </ul>
    </li>
  )
}

function StartFree({ signedIn }: { signedIn: boolean }) {
  const getStarted = useGetStarted()
  return <Link className="plan-action" to={getStarted.to} onClick={getStarted.start} aria-busy={getStarted.checking || undefined}>{signedIn ? 'Go to your workspace' : 'Start for free'} <span aria-hidden="true">→</span></Link>
}

function CheckIcon() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
}
