# Demo video — script, timings and checklist

Target: **under 10 minutes total**, unlisted on YouTube, two parts.

- **Part 1 (0:00–4:50)** — customer presentation. Audience: the day-ahead
  procurement desk and their manager. Goal: they believe this is useful.
- **Part 2 (4:50–9:40)** — technical walkthrough. Audience: a tech lead
  reviewing the work. Goal: review is easy and knowledge transfers.

Speak to the numbers on screen. Every figure below is what the app actually
renders for the default January 2026 settings — if a number differs on the day,
read what is on screen rather than this script.

---

## Before recording

- [ ] Stack running and warm — load the dashboard once so the API cache is hot
      and the demo does not open on a spinner.
- [ ] Browser at **1920×1080**, zoom 100%, bookmarks bar hidden.
- [ ] Theme set deliberately (light reads better on compressed video).
- [ ] Controls at defaults: January 2026, cutoff 09:00, D−1, hourly mean,
      MAPE floor 100 MW.
- [ ] Vintage inspector left on its default hour (the window's largest error).
- [ ] Notifications silenced; one clean browser profile, no extra tabs beyond
      the list below.
- [ ] Editor open at `backend/app/analysis/vintage.py` with the `select`
      method visible.
- [ ] A terminal ready in `backend/`, large font, cleared.
- [ ] Microphone tested.

**Tabs, in order:**

1. The dashboard
2. `/api/docs` (OpenAPI)
3. The GitHub repository
4. Editor
5. Terminal

---

## Part 1 — Customer presentation (target 4:50)

### 0:00–0:40 — The problem, in their words

> "You buy power on the day-ahead market, and how much conventional generation
> you need depends on how much wind there's going to be. But you have to commit
> before gate closure the day before delivery — so you're committing on a
> forecast.
>
> Two questions follow. What did we actually know when we decided? And how
> wrong was it, as a number we can plan around?
>
> This is Windsight. It answers both, using Elexon's published wind data and
> nothing else."

*On screen: the dashboard at the Overview section.*

### 0:40–1:40 — The headline

Point at the hero figure.

> "Across January 2026 — that's 744 delivery hours, every single one matched —
> the day-ahead forecast was out by **2,039 megawatts** on an average hour.
> About 18% of the wind that actually turned up.
>
> But the average miss isn't the interesting part. **Look at the bias:
> plus 1,748 megawatts.** That's not noise. The forecast didn't scatter around
> the truth — it sat consistently *above* it. 632 of those 744 hours were
> over-forecast."

> "Over-forecasting wind means under-buying thermal cover. That's the direction
> that gets closed out in the balancing market, at the worst prices."

*Scroll slowly through the three Overview cards — availability, matched
periods, source status.*

> "And note the coverage: 100%. Every hour has both a real forecast and real
> outturn. Nothing here is filled in or estimated."

### 1:40–2:50 — The thing that makes this honest

Scroll to **Forecast versus actual**, then to the **vintage inspector**.

> "Now, this is the part I want to be clear about, because it's the easiest
> thing to get wrong in this kind of analysis.
>
> Wind forecasts get revised constantly. If I compare what actually happened
> against the *latest* forecast — the one that exists today — I'd be measuring
> hindsight. I'd be giving you credit for information you didn't have."

Point at the vintage inspector chart.

> "So here's a single hour. Every dot is a separate forecast publication for
> that one hour. There were **24 of them**. The dashed line is your decision
> deadline — 9am the day before delivery.
>
> Everything left of that line, you had. Everything right of it arrived too
> late. We take the last one before the line" — point at the highlighted
> point — "and we throw the rest away.
>
> On this hour, the forecast you had said 20,942 megawatts. The wind actually
> delivered 14,072. You were short by **6,870 megawatts** — and you can see the
> later forecasts, the ones you never saw, were still saying twenty-one
> thousand. The forecast didn't catch it either."

### 2:50–3:50 — What the error is made of

Scroll to **Forecast accuracy**, then the MSE decomposition card.

> "Here's why the bias matters so much. We can split the error exactly into two
> parts.
>
> **Forty-nine percent of it is systematic** — a stable offset of about 1,750
> megawatts. The other half is genuine dispersion, about 1,794 megawatts of
> spread.
>
> Those two need completely different responses. A stable offset you can
> *correct for* — allow for it in the position before the auction. The
> dispersion you can't; that's real weather uncertainty, and it has to be
> carried or hedged.
>
> Splitting them tells you how much of this is a modelling fix and how much is
> a risk-management problem."

Scroll to the **cutoff comparison** chart.

> "And this prices something you may already suspect. If you could decide at
> 5pm instead of 6am, the error drops from about 2,016 to 1,874 megawatts.
> That's what deciding later is worth, in volume. Whether it's achievable is
> your process question — but now it has a number attached."

### 3:50–4:30 — Where it stops, and what you get

Scroll to **Error analysis** briefly, then **Settlement period detail**.

> "Underneath all of it is the audit trail. Every hour, the forecast, the exact
> timestamp it was published, what actually happened, and the error. Filter it,
> and export the whole thing to CSV for your own models."

Scroll to **Using this** and point at the caution callout.

> "One thing I want to be straight about. This is built on wind data alone,
> which is the scope we agreed. There's no demand here, no prices, no costs.
> So it does **not** tell you what to buy — and I'd be suspicious of anything
> that claimed to from this data.
>
> There's also a caveat on the bias itself" — point — "Elexon doesn't document
> these two series as covering exactly the same set of wind farms. Some of that
> 1,748 megawatts could be a scope difference rather than forecast error. The
> dispersion number isn't affected by that, which is why we report both."

### 4:30–4:50 — Close

> "So: a pilot, on one month of real data, with the decision timing handled
> properly. The obvious next steps are bias correction as a feature, and
> applying this to your own contracted position rather than the national one."

---

## Part 2 — Technical walkthrough (target 4:50)

### 4:50–5:30 — Architecture

*Switch to the GitHub repo, README architecture diagram.*

> "Python and FastAPI on the back, React and TypeScript on the front, both
> containerised, deployed as a single Vercel project.
>
> The structure follows one rule: **HTTP does no data work**. `main.py`
> validates parameters, calls the service, serialises the result. Everything
> underneath — the Elexon client, normalisation, vintage selection, alignment,
> metrics — is a separate module, and every analysis function is pure and
> synchronous.
>
> That's what makes the whole pipeline testable from fixtures with no network,
> which is most of why the test suite is quick and deterministic."

### 5:30–6:30 — The Elexon integration

*Editor: `backend/app/elexon/client.py`, then `normalise.py`.*

> "Two datasets. FUELHH for actuals, filtered to `fuelType=WIND` — and I filter
> upstream, which cuts the payload by about twenty times, *and* again during
> normalisation, so the guarantee holds regardless of how the request was
> built.
>
> WINDFOR for forecasts, queried by publish-time window — which suits us,
> because the decision cutoff *is* a constraint on publish time.
>
> A few things I confirmed against the live API rather than assuming. The
> stream endpoints return a bare array, no pagination — a month is one request.
> FUELHH rejects settlement-date and publish-date filters together. And
> critically" — point — "**WINDFOR is hourly, FUELHH is half-hourly.** They
> don't share a resolution."

*Scroll to the duplicate handling in `normalise.py`.*

> "Normalisation is defensive. A row that won't parse is dropped and counted,
> never coerced to zero — bad upstream data should reduce visible coverage, not
> quietly bias a metric. Duplicate actuals are treated as revisions, later
> publish time wins. Duplicate forecast rows collapse, but **distinct vintages
> never do** — collapsing them would destroy the cutoff logic entirely."

### 6:30–7:30 — Vintage selection and time handling

*Editor: `backend/app/analysis/vintage.py`, the `select` method.*

> "This is the core. For a target hour, binary-search the sorted publication
> times for the cutoff, take the last one at or before it. Inclusive, because a
> forecast published exactly at the deadline was available.
>
> If nothing qualifies we return `None` — and the caller records the hour as
> unmatched. It is never backfilled with a later forecast. That's the single
> most important line of behaviour in the project, and there's a test named
> after it."

*Editor: `timeutils.py`.*

> "Time handling. Everything crossing a boundary is timezone-aware UTC — naive
> datetimes raise, rather than being assumed.
>
> But a *delivery day* is a London day, because that's what a settlement date
> means. And London days are 23, 24 or 25 hours long across clock changes. So
> I resolve day boundaries in London and iterate UTC hours between them.
> Transition days come out with 46 or 50 settlement periods instead of being
> padded to 48. Both 2026 transitions are tested."

*Briefly: `align.py`.*

> "The resolution mismatch is a judgement call, so I made it visible: two
> reduction modes, selectable in the UI. They differ by less than one percent
> on the headline, which is worth knowing — the result doesn't hinge on it."

### 7:30–8:15 — Metrics

*Editor: `metrics.py`.*

> "Pure standard library — no pandas, no numpy. The dataset is small and the
> dependency-free bundle starts fast on a serverless host.
>
> Sign convention is fixed everywhere: **error equals forecast minus actual**,
> so positive means over-forecast.
>
> Two decisions worth calling out. **MAPE is fragile near zero**, so it's
> restricted by a configurable floor and the included and excluded counts are
> always reported — and wMAPE sits next to it because that one's defined for
> every hour.
>
> And **undefined is returned as null, never zero**. An empty window gives you
> nulls and `matched_hours: 0`. A zero there would read as a perfect forecast,
> which is the worst possible failure mode for this product."

### 8:15–9:05 — Tests, Docker, deployment

*Terminal:*

```bash
pytest -m "not live" -q
```

> "**217 offline tests**, about ten seconds, ninety-nine percent coverage.
> Hermetic — upstream is mocked with respx, and the fixtures are verbatim
> slices of real Elexon responses."

```bash
pytest -m live -q
```

> "Four more against the live API, excluded by default. These re-check the
> upstream contract: field names, that hourly/half-hourly split, and that a D−1
> cutoff really does select a D−1 publication. Fixtures prove we parse what
> Elexon sent once; these prove the contract still holds."

> "One test I'd point you at specifically: the real feed has an **off-schedule
> publication at 12:25 on the 15th of January**. WINDFOR normally publishes on
> a fixed cadence — so there's a test asserting selection compares *instants*
> and never assumes publication slots."

*Terminal:*

```bash
docker compose up --build
```

> "Compose runs both: nginx serves the built frontend and proxies `/api` to the
> backend, so the browser sees one origin — no CORS, and it mirrors the
> deployed topology. The frontend waits on the backend's health check. Both
> containers run unprivileged."

*Tab: `/api/docs`.*

> "The API is documented by its Pydantic models, so OpenAPI is generated rather
> than written — it can't drift. Six endpoints: health, meta, the analysis, the
> vintage inspector, the cutoff sweep, and a CSV export that's served from the
> same analysis object the JSON is, so the file and the screen can't disagree."

### 9:05–9:40 — Decisions and limitations

> "Three decisions I'd defend in review.
>
> **One:** the decision cutoff is a documented assumption, not a market rule,
> and it's configurable — the brief doesn't define one, and I'd rather expose
> that than bury a guess.
>
> **Two:** no synthetic data path at all. If Elexon is unreachable the product
> says so and shows nothing. There's no fallback that could ever be mistaken
> for real data.
>
> **Three:** the scope caveat on the bias is in the product, not just the
> README. Elexon doesn't document these two series as covering the same asset
> set, and the honest thing is to report the number, flag it, and give the
> reader the bias/dispersion split so they can see what depends on it.
>
> Known limitations and the roadmap are in the README. Happy to go deeper
> anywhere."

---

## Recording notes

- Scroll slowly — compressed video loses fast motion.
- Pause after each number so it lands.
- Zoom the editor to ~16pt; the default is unreadable at 1080p.
- If a load takes a moment, say what it's doing rather than waiting silently.
- Upload as **Unlisted**, then open the link in a private window to confirm it
  plays without a sign-in.
