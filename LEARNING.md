# Learning notes

Concepts that came up while building Tracehound, written down so the reasoning isn't lost.
Each entry says what the idea is, why we use it, and where it shows up in the code.

## Contents

- [Storing money in minor units](#storing-money-in-minor-units)

---

## Storing money in minor units

*Came up in: `supabase/migrations/20261030130318_create_plans.sql` (`plan_prices.price_minor`)*

`price_minor` stores a price as a whole number in the currency's minor unit, its smallest
unit: cents for US dollars, paise for rupees. So $19.99 is stored as `1999`, and ₹499 as
`49900`.

We do this because computers store numbers in binary. Every whole number has an exact
binary form, but most decimal fractions don't. Just as 1/3 can't be written exactly in
decimal (0.333… forever), 1/10 can't be written exactly in binary. So a float price like
19.99 is really stored as a value slightly off from 19.99:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

Each time we add tax, multiply by a quantity or apply a coupon, those tiny errors can build
up, and the total can end up off by a cent or more. Integers don't have this problem:
`1999 + 1999` is always exactly `3998`. When a calculation produces a fraction of a cent,
like a 20% discount, we round it once, on purpose, in one place. We only convert back to
"$19.99" when showing the price to a user.

**Beyond the database.** JavaScript has one number type (a float), so a JSON price of
`19.99` becomes a float in the React UI whatever the server used, while `1999` arrives
unchanged. Stripe (`unit_amount`) and Razorpay (`amount`) also use minor units, so a
payment integration can pass the value straight through.

**Edge cases.**
- Not every currency has 2 decimal places: JPY has 0 (¥500 is `500`), KWD has 3. Use
  `Intl.NumberFormat` (JS) or a currency-aware formatter instead of always dividing by 100.
- Postgres `numeric(10,2)` would also be exact inside the database. Minor units mainly
  help once the value leaves the database: in JSON, JavaScript and payment APIs.
- The column is named `price_minor`, not `price`, so nobody reads `1900` as $1,900.
