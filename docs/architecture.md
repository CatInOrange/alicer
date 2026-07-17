# Alicer Architecture Notes

## Purpose

Alicer is a companion app built around one fictional but consistent life.
The backend should not let chat, Moments, photos, memories, and the life simulator invent separate versions of Alicer.

The current architecture is best described as:

1. A canonical persistence layer.
2. Several context sources that describe reality.
3. A context composer that turns reality into bounded prompt input.
4. Generation surfaces that produce chat, Moments, photos, diary, and proactive actions.
5. Schedulers that advance background state.

## Shared Vocabulary

Use these terms consistently:

- **Fact Ledger**: durable or time-bound facts in `life_facts`. This is the authority for commitments, hard schedules, current states, stable profile facts, and recent posted Moments.
- **Life Simulation**: Alicer's own hourly/daily simulated life in `life_state` and `life_events`.
- **Future Timeline**: prompt-facing view of the remaining day, hard blocks, upcoming facts, conflicts, and routine inference. It is built by the context composer from life state plus the fact ledger.
- **User Timeline**: authorized reality cues from the user's device, such as location, motion, music, and attention state.
- **Context Package**: the structured prompt payload produced by `compose_prompt_context()`.
- **Generation Surface**: a user-visible output channel: chat, streamed chat, Moments, chat photos, diary, or proactive outreach.
- **Proactive Engine**: the candidate/score/decision layer that decides whether Alicer should initiate contact or post a Moment.
- **Delivery**: the final act of writing a message, Moment, photo, or event to persistence.

## Target Engine Boundaries

The long-term architecture should be engine-oriented, with explicit inputs and outputs. The goal is not to create many classes for their own sake. The goal is to prevent chat, Moments, diary, photos, and proactive behavior from each inventing their own version of Alicer's life.

### Fact Ledger Engine

Owns canonical reality.

Responsibilities:

- Extract proposed facts and commitments from chat and generated outputs.
- Validate actor, type, time window, confidence, priority, and conflicts.
- Store lifecycle state in `life_facts`.
- Mark facts completed, cancelled, expired, superseded, or archived.
- Publish fact projections for life planning and prompt context.

It should answer:

- What is true?
- What is planned?
- What is forbidden because it conflicts with a hard fact?
- Which older fact was replaced by a newer correction?

It should not:

- Generate chat copy.
- Generate Moments.
- Invent life texture beyond fact normalization.

### Life Simulation Engine

Owns Alicer's simulated daily continuity.

Responsibilities:

- Build today's plan from profile, routine, and Fact Ledger constraints.
- Advance current life state and hourly life events.
- Produce Moment-worthy life events.
- Produce the Future Timeline projection used by prompts.

It should answer:

- What is Alicer doing now?
- What is she likely doing later today?
- Which future blocks are hard commitments?
- Which parts are soft routine or LLM-filled texture?

It should not:

- Override ledger facts.
- Treat routine inference as a commitment.
- Commit new durable facts without passing through the Fact Ledger Engine.

### User Timeline Engine

Owns the user's authorized reality cues.

Responsibilities:

- Ingest device/location/music/motion/attention signals.
- Summarize current user state with confidence and staleness.
- Expose weak context and interruption-risk signals.

It should answer:

- Is the user probably busy, moving, resting, or available?
- Has the user's city/place/attention state changed?
- How stale or uncertain is this signal?

It should not:

- Be phrased directly as surveillance text.
- Override explicit user messages.
- Decide proactive delivery by itself.

### Memory Engine

Owns long-term semantic memory.

Responsibilities:

- Extract reusable preferences, relationship facts, and stable context.
- Keep review/active/archive lifecycle separate from near-term schedule facts.
- Recall relevant memories for a generation request.

It should answer:

- What durable context matters for this interaction?
- What does the user explicitly want remembered?

It should not:

- Be the authority for near-term schedule consistency.
- Store every transient plan as long-term memory.

### Context Engine

Owns the unified projection from all context sources into generation-ready input.

Responsibilities:

- Read Fact Ledger, Life Simulation, User Timeline, Memory, chat history, environment, and photo state.
- Apply authority ordering.
- Produce a bounded `Context Package`.
- Expose task-specific projections for chat, Moments, photos, diary, and proactive decisions.

It should answer:

- What should this generation surface know?
- Which source wins if two sources conflict?
- What should be omitted because it is stale, low-confidence, or private?

It should not:

- Generate final user-visible text.
- Mutate canonical facts as a side effect.
- Call an LLM on the synchronous chat path.

The Context Engine is a deterministic resolver. It should use rules, timestamps, confidence, status, and authority order to build a resolved context package. If semantic extraction or summarization needs an LLM, that work belongs in asynchronous extraction, memory processing, life planning, or generation jobs before or after the chat response.

### Prompt Engine

Owns prompt module rendering, not domain truth.

Responsibilities:

- Render system prompts from prompt modules and Context Package variables.
- Enforce prompt ordering, module enablement, and prompt size budgets.
- Provide prompt debug metadata.

It should answer:

- How should the model be instructed for this surface?
- Which context variables were rendered?

It should not:

- Decide whether facts are true.
- Decide whether a proactive action should happen.
- Build separate hidden realities for different surfaces.

Important distinction: the Prompt Engine can serve chat, Moments, diary, photos, and proactive chat, but it should not be the only shared layer. Shared consistency must come from the Context Engine and Fact Ledger before prompt rendering.

Normal chat latency rule:

```text
read data -> deterministic Context Engine -> Prompt Engine -> one chat LLM call
```

No extra Context Engine LLM call is allowed in the normal request/response path.

### Generation Engines

Own surface-specific generation.

Examples:

- Chat Generation
- Moment Generation
- Photo Generation
- Diary Generation
- Rift Generation

Responsibilities:

- Ask the Context Engine for the right projection.
- Ask the Prompt Engine to render the right prompt when text generation is needed.
- Call the LLM or image service.
- Return a proposed output plus metadata.

They should not:

- Bypass the Fact Ledger when creating new commitments.
- Rebuild context ad hoc from raw tables.
- Each define their own consistency priority.

### Proactive Engine

Owns decision-making for initiating contact.

Responsibilities:

- Build outreach candidates from life state, future timeline, user timeline, recent chat, Moments, and prior proactive events.
- Score candidates for relevance, emotional value, freshness, and interruption risk.
- Apply quiet hours, cooldowns, daily caps, duplicate suppression, and user coldness.
- Select a generation surface such as chat or Moment.
- Record skipped, delivered, and failed decisions in `proactive_events`.

It should answer:

- Should Alicer initiate anything now?
- Why this action, why now, and why not silence?

It should not:

- Write its own Moment strategy.
- Invent separate chat context.
- Directly override life plans.

### Delivery and Audit Layer

Owns durable side effects.

Responsibilities:

- Persist messages, Moments, photo tasks, diary entries, proactive events, and debug metadata.
- Link generated outputs back to source facts, life events, candidates, and prompts.
- Provide "why did this happen?" observability.

It should answer:

- What was delivered?
- What source/candidate/context caused it?
- Which generated output fulfilled or contradicted a commitment?

## Backend Shape

The backend is a FastAPI single-process application:

- `backend/app/main.py` wires the database, LLM service, routers, static uploads, health endpoint, and background tasks.
- `backend/app/db.py` is the SQLite persistence gateway. It owns schema creation and row-to-dict normalization.
- `backend/app/routers/*` expose API surfaces and perform request-level orchestration.
- `backend/app/services/*` hold most domain logic: prompt composition, memory extraction, fact extraction, life simulation, user timeline summarization, photo decisions, and proactive decisions.
- `backend/app/defaults.py` defines feature settings and prompt modules.

Startup launches these background tasks:

- `run_diary_scheduler()`
- `run_life_scheduler()`
- `run_moments_scheduler()`
- `run_proactive_scheduler()`

## Persistence Model

Primary tables:

- `messages`: chat history and assistant outputs, including streamed placeholders and proactive messages.
- `memories`, `memory_queue`, `memory_events`: long-term memory extraction, review, recall, and audit.
- `life_facts`: the Fact Ledger.
- `life_state`: current life profile, current state, daily plan, and plan date.
- `life_events`: hourly simulated trajectory; can be marked as used for a Moment.
- `user_timeline_state`, `user_timeline_events`: summarized and raw-ish user device signals.
- `moments`, `moment_likes`, `moment_comments`: Moments feed and engagement.
- `chat_photo_tasks`: lifecycle for requested or proactive chat photos.
- `proactive_events`: decisions and deliveries made by the Proactive Engine.
- `scheduled_jobs`: lightweight idempotency and scheduler bookkeeping.

SQLite is currently treated as the system of record. Schema migration lives inside `Database.ensure_schema()`.

## Consistency Model

Alicer cannot get strong consistency from prompt wording alone. The consistency model must be backend-led:

1. User-visible text may propose new reality.
2. The Fact Ledger decides whether that reality is accepted.
3. Accepted facts invalidate affected plans and projections.
4. The Context Engine rebuilds a fresh Context Package.
5. Every generation surface consumes that package or a documented subset.
6. Delivery metadata records which facts, life events, prompts, and candidates influenced the output.

The consistency path may use LLMs only outside the synchronous context-resolution step. For example, post-chat fact extraction may call an LLM, and refreshing a daily life plan may call an LLM, but those calls happen after the user-visible chat reply or in background scheduler work. Context resolution itself stays deterministic.

### Authority Order

When sources conflict, use this order:

1. User explicit correction.
2. User explicit settings.
3. Alicer's explicit commitment or promise to the user.
4. Active hard facts and schedules in the Fact Ledger.
5. External/user timeline signals, with confidence and staleness.
6. Current life simulation state.
7. Today's remaining plan and future timeline.
8. Long-term routine/profile/memory.
9. LLM improvisation and atmosphere.

The lower layers can add color, but they cannot rewrite higher layers.

### Example: Planned A, Then Chat Decides B

Scenario:

- Before chat, Alicer's plan says she will do A this afternoon.
- During chat, user and Alicer decide she will go do B instead.

Expected consistency flow:

1. Chat Generation replies naturally.
2. Post-generation extraction detects the new commitment B.
3. Fact Ledger validates actor/time/conflict and writes B as a planned or active fact.
4. Affected A fact or soft plan is marked superseded, cancelled, or conflict-suppressed.
5. Life Simulation invalidates or refreshes the affected daily plan window.
6. Future Timeline is rebuilt from the updated ledger and plan.
7. Later chat, proactive messages, Moments, diary, and photos all see B through the Context Package.
8. If a later generation mentions A, that is a bug in either projection freshness or prompt consumption, not a valid creative choice.

This is the critical maintenance rule: a changed plan is not "remembered" because one prompt saw it. It is remembered because the change was committed to the ledger and all surfaces read the updated projection.

### Plan Invalidation

Any accepted fact should declare which projections it invalidates.

Examples:

- New `schedule_commitment` with a time window: invalidate today's life plan for overlapping windows and rebuild Future Timeline.
- Cancelled hard fact: remove locked block and regenerate affected soft plan.
- New `current_state`: refresh `world.current` and possibly current life state.
- New `relationship_commitment`: refresh `world.commitments` and proactive follow-up candidates.
- New `profile_fact`: refresh effective profile, routine, and future plan generation.
- New `moment_posted`: refresh recent trajectory and Moment repetition suppression.

The implementation can begin with coarse invalidation, such as "refresh today's plan after hard fact changes", and later become more precise.

### Freshness Contract

Every generation surface should know whether its context is fresh enough.

Minimum freshness metadata:

- `contextGeneratedAt`
- `ledgerVersion` or latest ledger `updatedAt`
- `lifePlanGeneratedAt`
- `lifePlanDate`
- `futureTimelineSource`
- `userTimelineUpdatedAt`
- `memoryRecallGeneratedAt`

If a surface uses stale context after a new hard fact was accepted, that should be observable in debug metadata.

### Surfaces Must Share Reality

Chat, Moments, photos, diary, and proactive actions may have different style prompts, but they must share the same authority model.

Good pattern:

```text
Fact Ledger + Life + User Timeline + Memory
        -> Context Engine
        -> Context Package / surface projection
        -> Prompt Engine
        -> Generation Engine
        -> Delivery + Audit
        -> Fact extraction / fulfillment checks
```

Bad pattern:

```text
Moment prompt reads life tables directly.
Chat prompt reads ledger directly.
Photo director reads its own summary.
Proactive service invents its own state.
Diary uses a separate timeline.
```

The bad pattern works temporarily, but it creates contradiction bugs because each surface has a different reality.

## Fact Ledger

Implemented in `life_fact_service.py`, the Fact Ledger extracts and normalizes facts from chat turns.

Fact types currently include:

- `schedule_commitment`
- `relationship_commitment`
- `current_state`
- `profile_fact`
- `life_event_hint`
- `moment_posted`

The ledger does four jobs:

1. Extract high-signal facts from chat, using cheap triggers before LLM extraction.
2. Normalize relative dates against the message `createdAt` in Asia/Shanghai, using a 04:00 user-day boundary.
3. Clean up expired, completed, duplicate, and superseded facts.
4. Produce compact prompt/life constraints through `build_world_context()`, `fact_constraints_for_life()`, and `resolve_life_constraints_for_day()`.

Hard schedules are resolved before the daily plan is generated. Flights and similar hard commitments become locked blocks and can suppress or flag conflicting soft facts.

## Life Simulation

Implemented in `life_service.py`.

Life simulation owns Alicer's internal daily continuity:

- `refresh_life_plan()` generates a daily plan from profile, recent events, facts, and hard constraints.
- `advance_life_until_now()` advances due hourly slots.
- `_generate_life_event()` creates one life event for a time slot, unless a hard block deterministically supplies the event.
- `build_life_context()` returns the prompt-facing life state: profile, current state, plan, recent events, fact constraints, daily constraints, and routine.
- `choose_moment_life_event()` exposes candidate life events for Moments.

The intended priority is:

1. Hard facts and explicit commitments.
2. Current life state.
3. Today's remaining plan.
4. Long-term routine/profile.
5. Mood, atmosphere, and LLM variation.

This means the life simulator may add texture, but it should not rewrite schedule commitments, job identity, home base, or other stable facts.

## Context Composer

Implemented in `context_composer.py` and called by `prompt_service.render_prompt()`.

This is the main consistency boundary.

Input sources:

- settings and prompt modules
- selected chat history
- recalled long-term memories
- environment/weather
- Fact Ledger world context
- life simulation context
- user timeline context
- chat photo context

Output:

- prompt variables such as `context.brief`, `world.current`, `world.future`, `world.commitments`, `world.user`, `world.photos`, `life.current`, and history/memory variables
- a structured `contextPackage` stored in prompt debug metadata
- one system prompt assembled from enabled prompt modules

The most important prompt variable is `context.brief`. It orders context by authority:

1. Consistency guardrails.
2. Alicer current state.
3. Alicer future timeline.
4. Unfinished commitments, plans, and stable facts.
5. User reality cues.
6. Photo/selfie continuity.
7. Recent Alicer trajectory.
8. Recent chat.
9. Earlier chat.
10. Long-term memory.

## Chat Flow

Implemented in `routers/chat.py`.

Non-streaming flow:

1. Save the user message.
2. Merge settings.
3. Enrich environment/weather.
4. Load recent messages excluding the new user message.
5. Recall memories.
6. Build life, user, world, and photo contexts.
7. Render prompt.
8. Call LLM.
9. Save assistant message with `promptDebug`.
10. Queue memory extraction, fact extraction, and chat-photo decision.

Streaming flow is similar, but it first saves a placeholder assistant message with `streamStatus=streaming`, updates it during generation, and then runs the same post-processing after completion.

## Moments Flow

Implemented in `routers/moments.py`.

Moments can be created manually, by the noon scheduler, or by the Proactive Engine.

Generation flow:

1. Advance life.
2. Optionally choose an unused life event.
3. Build a Moment strategy from relationship stage, engagement, visibility, special event, environment cue, and life event.
4. Prompt the LLM to write a Moment and image prompt as Alicer.
5. Optionally generate an image.
6. Save the Moment.
7. Mark the life event as used.
8. Write a short-lived `moment_posted` fact into the ledger.

Moments should primarily grow from life events, not from random broadcast.

## Chat Photos

Implemented in `chat_photo_service.py`.

Chat photos are a separate delivery lifecycle:

1. Build quota and active-task context.
2. After chat generation, ask a photo director prompt whether to create a photo task.
3. Enforce daily quota, requested/proactive permission, and minimum interval.
4. Generate the image.
5. Send it as an assistant chat message with image metadata.

The normal chat prompt sees photo continuity through `world.photos`, so Alicer can remember whether she promised or is waiting on a photo.

## Memory

Implemented in `memory_service.py`.

Memory is long-term, reusable companion context, not a schedule authority.

Flow:

1. Chat messages are queued after each assistant reply.
2. Explicit memory requests are processed quickly; batch extraction runs only when due.
3. LLM or heuristic extraction creates memory candidates.
4. Candidates may enter `active` or `pending` depending on settings and confidence.
5. `recall_memories()` scores active memories by pinned status, importance, confidence, lexical match, and recency.

Use memory for stable preferences, relationship context, and durable facts. Use the Fact Ledger for near-term life consistency and commitments.

## User Timeline

Implemented in `user_timeline_service.py` and exposed by `routers/user_timeline.py`.

The user timeline ingests Android/device events and produces a compact state:

- scene and semantic location label
- city/district and place changes
- motion and availability
- music/headset context
- attention state
- recent high-value events

This data is prompt context, not surveillance text. The prompt explicitly says to use it naturally, avoid exact coordinates, and treat stale or low-confidence signals as weak cues.

## Proactive Engine

Implemented in `proactive_service.py` and exposed by `routers/proactive.py`.

The Proactive Engine is a restraint-first decision layer.

It currently supports:

- long-idle chat check-ins
- support follow-up after pressure or discomfort signals
- follow-up for user schedules that look like the user's own plan
- Alicer life-state sharing
- life-event-based Moments

Decision flow:

1. Merge settings.
2. Respect `proactive.enabled`.
3. Load recent messages, Moments, and proactive events.
4. Advance/build life context.
5. Build user and world contexts.
6. Generate candidates.
7. Suppress duplicates.
8. Pick the highest score.
9. Compare against chat or Moment threshold.
10. Record skipped or delivered `proactive_events`.

Delivery rules:

- Chat delivery reuses normal prompt rendering, then appends a small proactive instruction and saves an assistant message with `metadata.source = "proactive"`.
- Moment delivery reuses `generate_life_moment()`.

This is important: the proactive layer should decide *whether* and *why* to act; it should not become a separate prompt universe.

## Settings

Settings are stored in `app_settings` and merged with `DEFAULT_SETTINGS`.

Backend setting groups:

- `companion`
- `environment`
- `memory`
- `chatContext`
- `moments`
- `life`
- `userTimeline`
- `chatPhotos`
- `proactive`
- `model`
- `promptModules`

`merge_settings()` is currently the compatibility boundary for adding nested setting groups.

The Settings UI should be reorganized by engine boundary rather than by the order features were added. Target groups:

- Companion Identity: persona, relationship tone, avatar, model-facing identity.
- Model and Prompt Engine: model provider, prompt modules, prompt preview/debug.
- Fact Ledger and Memory: memories, life facts, extraction, review, cleanup, reconciliation status.
- Life Simulation and Future Timeline: profile, routine, current state, daily plan, hard blocks, conflicts, projection freshness.
- User Timeline: authorized device/user context signals, freshness, privacy controls.
- Generation Surfaces: chat behavior, Moments, photos, diary, and surface-specific generation controls.
- Proactive Engine: enablement, quiet hours, thresholds, cooldowns, daily caps, recent decisions, candidate debug.
- Delivery and Audit: sent messages, posted Moments, proactive events, prompt debug, "why did this happen?" views.

This UI shape should make the backend architecture visible to the user. Each settings section should own both controls and the most useful debug/status view for that engine.

## Current Refactor Progress

This section is the working map for the architecture cleanup. Keep it updated when a refactor step lands, otherwise the engine boundaries will drift back into ad hoc service calls.

### Phase 0: Architecture Map

Status: mostly done.

Completed:

- Defined shared vocabulary for Fact Ledger, Life Simulation, Future Timeline, User Timeline, Context Package, Generation Surface, Proactive Engine, and Delivery.
- Documented the target engine boundaries and which layer owns truth, planning, projection, prompt rendering, generation, proactive decisions, and audit.
- Documented the consistency model: accepted facts must invalidate affected plans and projections before later surfaces generate text.
- Documented the synchronous chat latency rule: deterministic Context Engine, then Prompt Engine, then one chat LLM call.

Still open:

- Keep this document synchronized with code as services are extracted.
- Add diagrams only if the text starts becoming hard to scan.

### Phase 1: Fact Ledger To Life Projection Reconciliation

Status: first clean boundary landed.

Completed:

- Added `consistency_service.py` as the first explicit consistency boundary.
- Added `reconcile_after_life_facts_changed()` to detect plan-affecting facts and refresh today's life plan when needed.
- Connected reconciliation after asynchronous chat fact extraction.
- Connected reconciliation after recent-chat fact refresh.
- Connected reconciliation to manual `/api/life/facts` create, update, cancel, complete, and supersede routes.
- Persisted the last reconciliation result in `scheduled_jobs` under `consistency:life_projection:last` so the latest projection refresh is inspectable.
- Added regression coverage proving a newly extracted schedule fact refreshes today's plan and appears in hard blocks.
- Moved manual life fact mutations behind `life_fact_app_service.py`, so routers no longer directly know reconciliation details.
- Added Context Package freshness metadata from life state, plan generation, latest fact update, and latest reconciliation result.

Current limitations:

- Reconciliation is coarse. It refreshes today's plan for today-affecting facts, rather than doing precise per-window invalidation.
- Future-day facts are recorded but do not yet schedule future plan regeneration.
- The reconciliation audit is stored as one latest scheduled-job record, not a full history.
- Fact extraction is still asynchronous after chat, so the immediate reply may not yet reflect the newly extracted fact. Later turns should.

Next step:

- Use the freshness contract in more surface-specific debug views, especially proactive and Moment generation.

### Phase 2: Context Package As The Standard Surface Input

Status: started.

Goal:

- Every user-visible generation surface should consume `Context Package` or a named projection derived from it.

Work items:

- Define surface projections for chat, Moments, photos, diary, proactive chat, and proactive Moments.
- Keep `context.brief`, `world.future`, `world.commitments`, `world.user`, and `world.photos` as shared source concepts rather than chat-only conveniences.
- Add tests that prove hard facts and Future Timeline appear in non-chat surface prompts where relevant.

Current limitation:

- Chat uses the strongest Context Package path. Moments, photos, and diary still have custom prompts with partial context gathering.
- The Context Package now carries a `freshness` object and a `context.freshness` rendered variable. This is ready for reuse by non-chat surfaces.

### Phase 3: Moment Generation Extraction

Status: first clean boundary landed.

Goal:

- Move Moment generation out of `routers/moments.py` into a `MomentService` or `MomentEngine`.

Work items:

- Keep the router as HTTP-only orchestration.
- Move strategy building, life-event selection, prompt rendering, image generation, Moment persistence, and `moment_posted` fact writing behind a service boundary.
- Let proactive Moment delivery call the same Moment engine instead of reaching through router helpers.
- Make the Moment engine consume a Context Package projection or a documented life-event projection.

Completed:

- Added `moment_service.py` as the Moment Generation boundary.
- Moved scheduled Moment generation, manual generation, life-event strategy, image prompt generation, Moment persistence, and `moment_posted` fact writing out of `routers/moments.py`.
- Updated app startup and proactive routes to import `run_moments_scheduler()` and `generate_life_moment()` from the service layer.
- Kept `routers/moments.py` focused on HTTP endpoints for list/generate/reference-image upload/likes/comments.

Current limitations:

- Moment prompts still consume a documented life-event projection, not the full Context Package projection.
- Comment replies remain lightweight and do not yet use the full Prompt Engine.

### Phase 4: Proactive Engine Split

Status: started.

Goal:

- Keep proactive behavior as a decision engine, not a generation universe.

Work items:

- Split candidate building, decision policy/scoring, delivery, and audit into separate units.
- Use User Timeline signals more directly for interruption risk.
- Route proactive chat through Chat Generation and proactive Moments through Moment Generation once those engines exist.
- Keep `proactive_events` as the durable answer to "why did she contact me?"

Completed:

- Split `proactive_service.py` into orchestration plus `proactive_candidates.py`, `proactive_policy.py`, `proactive_delivery.py`, and `proactive_types.py`.
- Kept public entrypoints stable: `run_proactive_scheduler()`, `run_proactive_once()`, `debug_candidates()`, and the current router/API behavior.
- Kept compatibility exports for existing tests while moving implementation out of the monolithic service.

Current limitations:

- Proactive chat still renders through the chat prompt directly instead of a dedicated Chat Generation engine.
- Proactive Moments still call the router-level Moment helper until Moment Generation is extracted.
- User Timeline is available to candidate building but interruption-risk scoring is still light.

### Phase 5: Typed Settings And Repository Boundaries

Status: deferred.

Goal:

- Reduce accidental behavior changes from untyped dict access and a large all-domain `Database` class.

Work items:

- Add per-domain settings normalizers or Pydantic models for `life`, `moments`, `proactive`, and `chatPhotos`.
- Split `Database` into domain repositories only after the engine boundaries are clearer.
- Preserve one SQLite system of record unless deployment requirements change.

### Phase 6: Engine-Oriented Settings UI

Status: not started.

Goal:

- Make the configuration page match the backend engine model, so controls, debug state, and audit views are discoverable by subsystem.

Work items:

- Reorganize the Settings screen into engine sections: Companion Identity, Model/Prompt Engine, Fact Ledger/Memory, Life Simulation/Future Timeline, User Timeline, Generation Surfaces, Proactive Engine, and Delivery/Audit.
- Keep advanced/debug panels collapsed by default, but show freshness/conflict/status badges at the section level.
- Move current scattered life, prompt, proactive, photo, and Moment controls under their owning engine.
- Surface the new Context Package freshness contract and latest consistency reconciliation result in the Life/Context debug area.
- Add a Proactive Engine panel for current thresholds, cooldowns, today's delivered/skipped counts, latest candidates, and recent `proactive_events`.
- Avoid exposing raw implementation names when a user-facing label is clearer, but keep developer debug fields available in advanced panels.

## Current Architecture Issues

These are not all bugs. They are places where the architecture is showing pressure.

### 1. `db.py` Is Too Large

`Database` owns all schema, migrations, and methods for unrelated domains: chat, photos, memories, life, facts, user timeline, Moments, rifts, proactive events.

This is convenient, but it makes domain boundaries fuzzy. A future cleanup could split repositories by domain while keeping one SQLite connection helper.

### 2. Scheduler Ownership Is Centralized But Thin

`main.py` starts all background loops directly. That is readable, but scheduler behavior is spread across routers and services.

Potential cleanup: introduce a small `scheduler.py` that registers background jobs, names them, handles cancellation, and records failures consistently.

### 3. Moment Generation Is Extracted But Not Fully Context-Packaged

`moment_service.py` now owns Moment generation and `routers/moments.py` is HTTP-focused.

The next cleanup is to make the Moment engine consume a Context Package projection rather than assembling life/chat/fact context directly.

### 4. Proactive Scoring Uses User Timeline Too Lightly

The proactive engine builds `user_context`, but current candidate scoring mostly relies on messages, life state, Moments, and prior proactive events.

Next cleanup: let user availability, place changes, city changes, music/motion, and stale-location confidence directly influence interruption risk and candidate choice.

### 5. Fact Commit Loop Is Not Fully Closed

Chat can extract facts after replies, and Moments write `moment_posted` facts. But assistant replies that create future promises are still only partially captured by the current extraction loop, and new facts do not always trigger immediate replanning.

Target behavior: new hard facts or commitments should invalidate affected daily plans and refresh the future timeline before later generation.

### 6. Context Composition Is Strong For Chat, Less Universal Elsewhere

Chat uses the full context package. Moments use a custom prompt. Photos use a custom director prompt. Proactive chat reuses chat context, while proactive Moments reuse Moment generation.

This is acceptable for now, but all generation surfaces should share the same authority model and future timeline rules. The docs and APIs should keep calling this the `Context Package` even when a surface only consumes a subset.

### 7. Settings Have No Typed Schema Boundary

Settings are plain nested dictionaries. `merge_settings()` fills defaults, but there is no typed validation layer for backend consumers.

As features grow, consider Pydantic settings models or small per-domain normalizers, especially for proactive thresholds, quiet hours, and life schedule settings.

The frontend settings page also mirrors the old feature-by-feature growth pattern. It should be reorganized by engine ownership so users and developers can understand which subsystem a control affects.

### 8. Debug Surfaces Are Useful But Fragmented

There is prompt debug metadata, life debug state, proactive candidate/event endpoints, and settings panels. They are not yet presented as one coherent observability model.

Target language:

- "Why did she say this?" -> prompt debug/context package.
- "Why is she doing this today?" -> life plan/fact constraints.
- "Why did she contact me?" -> proactive event decision.
- "Why did she post this Moment?" -> Moment metadata/life event.

## Suggested Near-Term Cleanup Order

1. Close the consistency loop: accepted hard facts and commitments should invalidate affected life plans and refresh the Future Timeline before later generation.
2. Define Context Package projections for every generation surface: chat, Moments, photos, diary, proactive chat, and proactive Moments.
3. Move Moment generation from `routers/moments.py` into a `MomentService` or `MomentEngine`.
4. Split Proactive Engine internals into candidate building, policy/scoring, delivery, and audit.
5. Teach proactive scoring to use user timeline interruption risk directly.
6. Reorganize the Settings UI by engine boundary, with status/debug panels beside the controls.
7. Add a typed settings normalization layer for proactive/life/moments.
8. Split `Database` into domain repositories if schema churn continues.

## Design Rule Of Thumb

When adding a new behavior, ask:

1. Does this create or modify reality? If yes, it must go through the Fact Ledger or a domain table with explicit metadata.
2. Does this change today's plan or future commitments? If yes, it must invalidate and rebuild the affected projections.
3. Does this generate user-visible text? If yes, it should consume the Context Package or a clearly documented subset of it.
4. Does this initiate contact? If yes, it should pass through the Proactive Engine.
5. Does this publish a Moment? If yes, it should be grounded in a life event or an explicit strategy source.
6. Does this use user reality cues? If yes, it should preserve uncertainty and avoid surveillance-like phrasing.
