# Life Ledger Consistency Design

## Goal

Make Alicer's chat, Moments, life simulation, photos, and memory share one consistent fictional reality.

The core problem is not text quality. It is authority. If chat, Moments, life simulation, and memory each let the LLM invent facts independently, Alicer will contradict herself. A statement like "I have a flight to Guangzhou tomorrow" must become a durable planned fact that later schedule generation, Moments, and chat all obey.

This design introduces a canonical Life Ledger as the source of truth for time-bound life facts, commitments, current state, and relationship promises. LLMs may propose and express details, but the backend decides what becomes canonical.

## Current State

First phase implementation has started the ledger foundation:

- `life_facts` persistence exists for factual items with lifecycle status.
- Chat injects bounded world context through `ContextComposer`.
- Chat can schedule asynchronous fact extraction after a response.
- Life simulation and Moments can read ledger constraints.
- Default prompt modules now read from the unified context package: world facts, companion life state, user timeline, chat photo rules, split chat history, and long-term memory.

Important limitation: this is still the first strong-consistency pass. The ledger now guides prompts, life simulation, Moments, and photo decisions, but not every lifecycle loop is closed yet.

## Design Principles

1. One factual authority
   - The ledger owns canonical time-bound reality.
   - Chat, Moments, photos, and life simulation read from it.
   - They do not independently commit new reality without passing through ledger validation.

2. LLM proposes, backend validates
   - LLM output is treated as a proposal.
   - Backend validates type, time, confidence, source, conflict priority, and TTL before writing.

3. Extract selectively
   - Do not run expensive fact extraction on every message.
   - Use a cheap heuristic trigger first.
   - Only run LLM extraction for high-signal turns.

4. Facts must exit
   - Temporary plans expire.
   - Current states decay quickly.
   - Completed/cancelled/superseded facts leave the prompt.
   - Only durable, repeated, or explicitly important facts can become long-term memory.

5. Prompt sees a context package, not the database
   - Do not dump the ledger into prompts.
   - Build a compact, task-specific world context for each generation.

## Ledger Fact Types

`profile_fact`

Stable Alicer facts: occupation, home city, work style, common places, habits, identity constraints.

Typical source:

- explicit settings
- long-term memory
- repeated confirmed behavior

Prompt lifetime: long-lived, but only top relevant facts are included.

`schedule_commitment`

Future or planned arrangements: flights, overtime, appointments, travel, tomorrow's plan, promised activity.

Examples:

- "明天有一趟飞广州的航班"
- "今晚要加班"
- "周末想去看展"

Prompt lifetime: from creation until completed, cancelled, expired, or superseded.

`current_state`

Short-lived current activity/location/mood/availability.

Examples:

- "现在在机场候机"
- "刚到家，有点累"

Prompt lifetime: hours, not days.

`life_event`

Occurred trajectory event generated or confirmed by simulation.

Examples:

- "07:30 出门去机场"
- "12:20 到达广州"

Prompt lifetime: recent trajectory only. Older events can be archived or summarized.

`relationship_commitment`

Promises or commitments made to the user.

Examples:

- "下班后给你拍一张照片"
- "明天落地后告诉你"
- "今晚陪你聊天"

Prompt lifetime: until fulfilled, cancelled, expired, or explicitly corrected.

`memory_candidate`

Potential long-term memory candidate.

This is not long-term memory yet. It needs later promotion.

Examples:

- repeated preference
- explicit "记住"
- durable relationship fact

## Lifecycle

Allowed statuses:

- `candidate`
- `planned`
- `active`
- `completed`
- `cancelled`
- `superseded`
- `expired`
- `archived`

Lifecycle rules:

- New LLM-extracted facts normally enter as `candidate` or `planned`.
- Time-window facts become `active` when `startsAt <= now < endsAt`.
- Planned facts become `completed` after successful related life events or explicit confirmation.
- Planned facts become `expired` if their time window passes without confirmation.
- Conflicting older facts become `superseded`.
- Low-confidence unused candidate facts become `archived`.
- Completed/expired/superseded facts are not shown in normal prompt context unless needed for recent continuity.

## Fact Fields

Minimum fields:

- `id`
- `type`
- `status`
- `title`
- `summary`
- `startsAt`
- `endsAt`
- `expiresAt`
- `confidence`
- `importance`
- `source`
- `sourceMessageId`
- `related`
- `metadata`
- `supersedesId`
- `createdAt`
- `updatedAt`

Recommended metadata:

- `actor`: `alicer`, `user`, or `relationship`
- `place`
- `city`
- `activity`
- `hardConstraint`: whether generation must obey it
- `extractionReason`
- `rawProposal`
- `validationWarnings`

## Conflict Priority

When facts conflict, higher priority wins:

1. User explicit correction
2. User explicit setting
3. Alicer promise or commitment to user
4. External signals: time, location, calendar-like events if available
5. Life simulation output
6. LLM free improvisation

Examples:

- If Alicer said she flies to Guangzhou tomorrow, the daily plan cannot place her in a normal office day unless the flight is cancelled or superseded.
- If user corrects "不是广州，是深圳", the Guangzhou fact is superseded.
- If a generated life event says she is at home while an active flight commitment says she should be at the airport, the life event should be rejected or regenerated.

## Extraction Strategy

Do not extract every message.

Step 1: Cheap trigger

Run synchronous heuristics on the current user message and final assistant reply.

High-signal triggers:

- future time words: 明天, 后天, 今晚, 周末, 下周, 等会儿
- schedule words: 航班, 飞, 出差, 上班, 加班, 约会, 会议, 旅行
- promise words: 我会, 等我, 到时候, 给你发, 拍给你
- durable memory words: 记住, 以后, 一直, 通常, 我喜欢, 你喜欢
- correction words: 不对, 不是, 改成, 其实, 应该是

Step 2: LLM proposal extraction

Only if triggered, call a small extraction prompt with:

- current user message
- assistant reply
- current active/planned facts
- current life state
- current date/time

Do not include full chat history.

Step 3: Validation

Validate:

- JSON shape
- fact type
- time parsing
- confidence threshold
- whether the statement is literal vs joke/roleplay/metaphor
- whether actor is Alicer or user
- conflict priority
- TTL

Step 4: Write

Insert, update, supersede, or reject.

Step 5: Cleanup

On reads and scheduled maintenance:

- expire old facts
- archive stale candidates
- complete facts that are matched by life events
- remove archived facts from prompt context

## Prompt Organization Target

Current implementation adds `world.context` as one extra module. That is useful but insufficient.

Second phase should introduce a Context Composer that builds one bounded prompt package from all context sources:

1. Role and expression rules
2. Current world state
3. Active and upcoming ledger commitments
4. Recent Alicer life trajectory
5. User timeline context
6. Chat photo pending/availability context
7. Long-term memory
8. Recent chat history
9. Contradiction guardrails

The prompt modules should become views over this composed package, not independent context builders.

Recommended prompt variables:

- `{{world.current}}`
- `{{world.commitments}}`
- `{{world.trajectory}}`
- `{{world.user}}`
- `{{world.photos}}`
- `{{world.memory}}`
- `{{history.recent_20}}`
- `{{history.older}}`
- `{{world.guardrails}}`

Compatibility path:

- Keep existing `{{life.current}}`, `{{user.current}}`, and `{{chat.photo}}` temporarily.
- Internally generate them from the same Context Composer.
- Later migrate default prompt modules to the new `world.*` variables.

## Prompt Budget Rules

Each generation receives a bounded context package:

- unfinished commitments: max 10
- today/tomorrow plan items: max 20
- recent life events: max 12
- recent Moments: max 3
- long-term memories: max 10
- latest chat messages: 20
- older chat: summarized or budget-limited

The ledger itself can grow, but prompt context cannot.

## Life Simulation Integration

Life simulation should become:

1. Plan Compiler
2. Hourly Simulator

Plan Compiler input:

- stable profile facts
- active/planned schedule commitments
- relationship commitments
- recent life trajectory
- weather/time/day type
- selected long-term memories

Plan Compiler output:

- daily plan skeleton
- hard constraints
- possible surprises
- allowed deviations

Hourly Simulator input:

- compiled plan
- current state
- active hard constraints
- recent events

Hourly Simulator output:

- one life event
- updated current state
- optional memory candidate

Rules:

- Randomness may fill details, not violate commitments.
- If a hard commitment exists, generated events must route toward it.
- Disallowed or contradictory locations should trigger regeneration/fallback.

## Moments Integration

Moments should come from life reality.

Generation flow:

1. Advance life simulation to now.
2. Select a source life event or ledger fact.
3. Build a moment prompt around that source.
4. Generate content/image prompt.
5. Save Moment with `sourceLifeEventId` and/or `sourceFactId`.
6. Write back a ledger event such as `moment_posted`.

Rules:

- Do not turn user itinerary into Alicer's first-person experience.
- Do not invent a conflicting location or schedule.
- If no good source event exists, create a quiet text-only Moment or skip.

## Chat Integration

Before LLM reply:

- Build Context Composer package.
- Include active commitments and guardrails.
- Include pending relationship commitments naturally.

After LLM reply:

- Run cheap extraction trigger.
- If triggered, schedule async extraction.
- Store proposed facts only after validation.
- Schedule chat photo decision separately but with ledger context.

The user-facing assistant should not mention internal mechanisms like quota, ledger, extraction, tasks, or APIs.

## Memory Integration

Memory is not the same as ledger.

Ledger:

- time-bound
- operational
- may expire
- controls consistency

Memory:

- durable
- curated
- slow-changing
- used for identity, preferences, relationship facts

Promotion rules:

- Explicit "remember this" can create `memory_candidate`.
- Repeated facts can become candidates.
- Completed one-off schedules usually do not become long-term memory.
- Relationship-significant events may be summarized into memory after completion.

## APIs and UI

Backend API needed:

- `GET /api/life/facts`
- `POST /api/life/facts`
- `PATCH /api/life/facts/{id}`
- `POST /api/life/facts/{id}/cancel`
- `POST /api/life/facts/{id}/complete`
- `POST /api/life/facts/{id}/supersede`
- `POST /api/life/facts/cleanup`
- `GET /api/life/world-context`

Settings/admin UI should show:

- active facts
- upcoming commitments
- candidates waiting for review
- expired/superseded facts
- source message
- confidence
- conflict warnings
- manual cancel/complete/delete

Default mode can be automatic, but the UI must make correction possible.

## Implementation Plan

Phase 1: Ledger foundation

- Add `life_facts` schema and helpers.
- Add ledger service with extraction trigger, validation, TTL, and context builder.
- Inject `world.context` into prompt.
- Feed ledger constraints into life planning and Moments.

Status: implemented.

Phase 2: Management and Prompt Composer

- Add fact management APIs.
- Add cleanup/audit lifecycle jobs.
- Add conflict detection report.
- Build `ContextComposer`.
- Make `life.current`, `user.current`, `chat.photo`, and `world.context` come from the same context package.
- Update default prompt modules to match the new organization.

Status: implemented. The API, cleanup/audit foundation, `ContextComposer`, default prompt variable migration, chat photo world-context read, Moment writeback, and settings UI panel for reviewing/editing facts are in place.

Phase 3: Strong consistency loops

- Life event completion updates facts.
- Moments write back posted facts.
- Chat photo tasks bind to relationship commitments.
- Memory promotion consumes `memory_candidate` facts.
- Add smoke tests for cross-surface consistency.

Phase 4: UI polish

- Add fact ledger panel in settings.
- Show current/upcoming reality in a compact, editable view.
- Add manual correction flow for wrong commitments.

Status: first usable version implemented in Settings under the life simulation section.

## Test Cases

Flight continuity:

1. User asks about tomorrow.
2. Alicer replies: "明天我有一趟飞广州的航班。"
3. Ledger stores planned flight.
4. Tomorrow's daily plan includes preparation, commute, airport, flight, arrival/rest.
5. Moments use airport/flight/travel context if posting.
6. Chat answers "你在哪" based on the active plan/event.

Correction:

1. Alicer says Guangzhou.
2. User says "不是广州，是深圳。"
3. Guangzhou fact becomes superseded.
4. Shenzhen fact becomes planned.
5. Future generation follows Shenzhen.

Photo promise:

1. Alicer says "下班后拍给你看。"
2. Ledger stores relationship commitment.
3. Chat photo service sees pending commitment.
4. If photo sends successfully, commitment becomes completed.
5. If it expires, future prompt can naturally apologize or avoid pretending it happened.

Moment binding:

1. Life event says Alicer is waiting at airport.
2. Moment posts an airport selfie.
3. Moment metadata binds source event/fact.
4. Later chat can reference the posted Moment consistently.

## Non-Goals For Now

- Perfect natural language time parsing for every phrase.
- Full calendar integration.
- User-visible guarantee that every assistant sentence becomes canonical.
- Permanent storage of all extracted candidates.
- Replacing long-term memory with ledger.
- Heavy extraction on every message.

## Open Questions

- Should candidate facts require user review when confidence is low?
- What confidence threshold should create a planned fact automatically?
- How aggressively should Alicer treat her own casual statements as commitments?
- Should settings expose a "strict consistency" slider?
- Should completed facts remain queryable in UI for 7 days, 30 days, or indefinitely archived?
