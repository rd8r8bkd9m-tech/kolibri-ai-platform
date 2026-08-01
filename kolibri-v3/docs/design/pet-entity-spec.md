# Kolibri Pet Entity — product behavior specification

Status: normative V1 behavior contract for desktop web/PWA and Expo mobile.

## Product role

The pet is a persistent, useful companion for the active Kolibri workspace. It
expresses the real state of the current agent run, gives the user a small entry
point to the same Product Chat, and makes waiting, approval, success, failure,
and offline conditions legible without opening another surface.

The pet is not a decorative animation, a second chatbot, or a separate agent.
It never owns a runtime, conversation, model selection, message history, or
business artifact. Its composer and actions always address the already active
Product Chat scope.

## Persistent identity and personality

Each pet has one stable product id, display name, role, personality,
accessibility description, accent color, reviewed thumbnail, active artwork,
and versioned animation atlas. Changing the selected character changes its
presentation and copy, not the capabilities or behavior of the agent.

The selected pet, visibility, motion preference, and permitted placement are
user preferences. The backend user profile is the durable authority once the
preference API exists. Device storage is an offline-start cache and must never
silently replace a newer server value. Position is device/surface-specific and
must not roam between incompatible viewport classes.

## Activity and event model

### Activity states

| State | Meaning | Animation row |
| --- | --- | --- |
| `idle` | no active run; ready for the next action | `idle` |
| `thinking` | model is interpreting or planning | `running` |
| `running` | tools or a long operation are executing | `running` |
| `review` | output or artifact is being inspected/verified | `review` |
| `waiting` | the run is blocked on missing user input | `waiting` |
| `approval` | an explicit confirmation is required | `waiting` |
| `success` | the run completed successfully | `jumping` |
| `error` | the run failed or ended incompletely | `failed` |
| `offline` | Product Chat runtime or gateway is unavailable | static `failed` pose |

`thinking` and `running` may share atlas artwork in V1 but remain distinct
semantic states so copy, telemetry, and future animation can differ.
`waiting` and `approval` likewise remain distinct.

### Reactions

Reactions are short overlays that resume the underlying activity state:

- `greeting` after a deliberate tap opens the pet (`waving` row);
- `celebrate` after a user message is accepted (`jumping` row);
- directional `running-left` / `running-right` only while the user moves the
  pet, never as a substitute for agent work.

Runtime state always preempts a reaction. Reactions have deterministic expiry
and cannot hide an approval, error, or offline condition.

### Server event authority

Agent activity is driven by ordered server events, transported through the
same AG-UI run as Product Chat. The portable event envelope is:

```ts
type PetActivityEventV1 = {
  type: "kolibri.pet.activity.v1";
  threadId: string;
  runId: string;
  sequence: number;
  occurredAt: string;
  state:
    | "idle"
    | "thinking"
    | "running"
    | "review"
    | "waiting"
    | "approval"
    | "success"
    | "error";
  reason?: string;
};
```

Clients accept only events for their active thread/run and monotonically newer
sequences. Until the backend emits this event, a thin adapter may derive only
the states provable from assistant-ui (`isRunning`, completed, incomplete).
It must not invent tool progress or successful completion. `offline` is a
local connection state and yields to a newer healthy server run.

## Deterministic visual contract

The reviewed atlas is WebP/PNG, 1536×1872 pixels: eight columns, nine rows,
with 192×208 cells. Rows and frame timings are the hatch-pet contract:

1. `idle` — 6 frames;
2. `running-right` — 8 frames;
3. `running-left` — 8 frames;
4. `waving` — 4 frames;
5. `jumping` — 5 frames;
6. `failed` — 8 frames;
7. `waiting` — 6 frames;
8. `running` — 6 frames;
9. `review` — 6 frames.

Frame selection is deterministic from state entry time. Reduced-motion uses a
reviewed static frame for each semantic state; it does not replace animation
with bobbing, shaking, or scale pulses. A static active image is allowed only
as an explicit compatibility fallback while a versioned atlas is absent.

## Interaction behavior

### Tap

A tap gives light/selection feedback, plays `greeting`, and opens or closes a
compact panel. The panel contains identity, current real status, and a compact
composer bound to the current assistant-ui composer. Sending, cancelling,
attachments, permissions, and errors follow Product Chat behavior.

### Long press

Long press gives medium haptic feedback and opens concise companion controls,
starting with the reviewed character picker. Visibility, haptic, placement,
and settings actions are shown only on surfaces that expose the corresponding
durable preference. Long press must not send a message, close the just-opened
panel, or begin dragging.

### Drag

Desktop supports pointer drag plus keyboard arrows; Shift increases the step.
Mobile may move the pet only from the pet hit target after the gesture
threshold. The transparent overlay is never interactive, and vertical chat
scroll wins outside the pet target. Position is clamped to safe areas and
cannot cover the composer, primary navigation, system home indicator, or
critical dialogs.

## Placement

Desktop renders in a top-level portal independent of workspace layout. It may
be moved or collapsed to an edge and must not cause layout shift. The compact
panel chooses above/below placement by available viewport space.

Mobile renders above the composer safe area with only the visible trigger and
open panel accepting touches. The full-screen overlay is pass-through. The
panel respects keyboard avoidance, safe-area insets, and one-hand reach. It
must not intercept message-list scroll when closed.

## Haptics, accessibility, and motion preferences

- selection/light feedback: open, close, character selection;
- success/error notification feedback: real run state transition only;
- medium feedback: long-press menu and confirmed placement;
- no haptic feedback on web or unsupported devices;
- every control has a role, label, expanded/selected/disabled state, and at
  least a 44×44 point touch target;
- status changes are announced politely once, without repeating every frame;
- artwork is hidden from accessibility because the enclosing control names
  identity and state;
- keyboard users can open, close, move, collapse, restore, and reach the
  composer with predictable focus restoration;
- reduced-motion and reduced-data are respected independently.

## Reliability and boundaries

- Never create a second assistant runtime, chat thread, or transport client.
- Never issue a direct `fetch` from the pet renderer or composer.
- Never show fake progress, fake replies, or timer-based success.
- Never cover unread chat content, the main composer, navigation, approval
  controls, or system safe areas.
- Never use a full-screen touch layer when the panel is closed.
- Never derive business state from animation state.
- Never download arbitrary unreviewed pet assets in a native release; server
  selection is restricted to bundled, versioned ids.
- The pet remains useful when animation is disabled: identity, truthful status,
  current-chat action, keyboard/accessibility behavior, and offline state all
  remain available.

## Acceptance criteria

1. Desktop and mobile consume the same state/event and atlas row contract.
2. The default Koli atlas passes deterministic geometry, transparency,
   contact-sheet, and motion-preview QA.
3. Run state changes produce the matching semantic animation and one status
   announcement; tap/message reactions resume the correct state.
4. Reduced-motion uses static state poses and produces no continuous motion.
5. The pet composer sends through the active Product Chat and does not create
   another runtime.
6. Closed mobile pet overlay does not block chat scroll; desktop portal does
   not change workspace layout.
7. Selection and visibility persist; placement remains clamped and recoverable.
8. Lint, typecheck, focused contract tests, mobile scroll regression, and
   desktop keyboard/drag checks pass without DOM-prop warnings.
