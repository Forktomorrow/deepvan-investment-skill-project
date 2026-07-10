# Research Skill Taxonomy

Use this reference when turning creator posts into reusable投研 skills.

## Skill Format

Each skill must be operational:

```text
Skill name:
Use when:
Inputs:
Decision rules:
Output:
Falsifiers:
Evidence examples:
```

Avoid vague labels such as "看好AI" or "价值投资". The skill should tell another agent what to do.

## Skill 1: Portfolio-First Expression

Use when a post mixes several assets, themes, or account types.

Inputs:
- portfolio version
- available instruments
- risk budget
- explicit weights or event-only changes

Decision rules:
- Represent a thesis as a basket or portfolio when single-name risk is high.
- Keep every complete table as an independent 100% portfolio.
- Treat event-only posts as deltas, not full snapshots.
- Separate sector buckets from underlying security detail.

Output:
- portfolio_id
- holdings table
- completeness flag
- unresolved items

Falsifiers:
- total weight cannot be reconciled
- asset aliases imply duplicate rows
- source only provides commentary, not position facts

## Skill 2: Dominant Variable Trigger

Use when a post explains a trade through macro, policy, or industry variables.

Inputs:
- asset/theme
- stated driver
- horizon
- market expectation

Decision rules:
- Identify the one or two variables that would change the trade.
- Classify each variable as fact, expectation, or price.
- If the variable deteriorates, reduce or hedge before waiting for price confirmation.
- If variable improves and price has not reflected it, add exposure.

Output:
- dominant_variable
- transmission_chain
- action
- validation_signal

Falsifiers:
- variable is not measurable
- no asset-level transmission path
- post only uses narrative adjectives

## Skill 3: Overseas-to-China Mapping

Use when overseas industry news is mapped to A-share, Hong Kong, or domestic fund instruments.

Inputs:
- overseas catalyst
- affected supply chain
- domestic listed substitutes
- tradability constraints

Decision rules:
- Map from overseas capex/order/price signal to domestic revenue or valuation channel.
- Distinguish direct beneficiaries, sentiment proxies, and hedge assets.
- Check whether domestic assets already priced the overseas signal.

Output:
- overseas_signal
- domestic_mapping
- asset_candidates
- confidence

Falsifiers:
- domestic company has no real exposure
- price moved before the signal
- mapping is only thematic, not causal

## Skill 4: Executable Substitution

Use when the same thesis must be expressed in different accounts.

Inputs:
- account constraints: US, Hong Kong, mainland, pure A-share, public fund only
- instrument list
- premium/discount and liquidity

Decision rules:
- Prefer closest risk exposure, not closest name.
- Flag QDII premium, FX risk, fund tracking error, and liquidity.
- Provide fallback instruments when direct exposure is not available.

Output:
- primary instrument
- substitutes
- execution caveats

Falsifiers:
- substitute has different beta or driver
- instrument cannot be bought by target account
- premium destroys expected edge

## Skill 5: Drawdown-First Risk Control

Use when event risk, valuation risk, or policy uncertainty increases.

Inputs:
- current exposure
- risk source
- hedge tools
- maximum drawdown tolerance

Decision rules:
- If thesis is falsified, sell or stop loss.
- If risk is temporary but large, reduce or hedge.
- If volatility is high but thesis intact, separate direction from volatility with options or smaller size.

Output:
- risk_type
- action
- hedge_or_cash_plan
- re-entry condition

Falsifiers:
- hedge cost exceeds protection value
- drawdown risk is not tied to portfolio exposure

## Skill 6: Evidence-Led Accountability

Use when building a credibility or backtest dataset.

Inputs:
- source URL
- publish time
- asset and action
- starting price or portfolio net value
- benchmark

Decision rules:
- Every claim needs a date, asset, direction, benchmark, and evaluation horizon.
- Mark ambiguous statements as `invalid` instead of forcing a win/loss.
- Use multiple windows: 5D, 20D, 60D, 120D.
- Separate direction success from variable validation.

Output:
- claim record
- yes/no result fields
- explanation

Falsifiers:
- no executable asset
- no date
- no clear direction
- benchmark unavailable
