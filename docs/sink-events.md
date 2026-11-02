# The 0x4xxx message ids are ADK sink events, and they all have names

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

**2026-09-30.** This project has spent a long time working out what
`0x4003`, `0x4008`, `0x4012` and friends mean, by suppressing them and
listening to what changed. They did not need to be worked out. They are
the ADK sink application's **event enum**, and `sink_events.h` names all
488 of them.

```c
#define EVENTS_MESSAGE_BASE      (0x4000)
#define EVENTS_USR_MESSAGE_BASE  (EVENTS_MESSAGE_BASE)
#define EVENTS_SYS_MESSAGE_BASE  (EVENTS_USR_MESSAGE_BASE + 0x0700)
```

This follows from `docs/library-matching.md` (not in this export): Bose's application is the
ADK sink app, so it inherits the sink app's event numbering.

**Bose uses 196 distinct values in 0x4000-0x47FF, and 184 of them have an
ADK 4.3.1 name.** Full table with load/compare counts:
`build/analysis/sink-events.txt` (not in this export).

> **Not to be confused with the prompt ids.** `docs/request-id-catalog.md` (not in this export)
> catalogues values 0x00-0x3F, which are indices into the speaker's sound
> corpus. These 0x4xxx values are *events* — the messages that, among many
> other things, cause a prompt to be played. Different space, different
> meaning.

## What it confirms, and what it corrects

| id | ADK name | what this project believed |
|---|---|---|
| 0x4001 | `EventUsrPowerOn` | "VA start" — **wrong**, and already retracted |
| 0x4002 | `EventUsrPowerOff` | "VA stop" — **wrong**, same |
| **0x4003** | **`EventUsrEnterPairing`** | "the Bluetooth hold" — **right**, proven by probe27 |
| 0x4008 | `EventUsrAnswer` | one of the dispatcher's outputs |
| 0x4009 | `EventUsrReject` | " |
| 0x400A | `EventUsrCancelEnd` | " |
| 0x400B | `EventUsrTransferToggle` | " |
| 0x400C | `EventUsrMicrophoneMuteToggle` | " |
| 0x4012 | `EventUsrThreeWayAcceptWaitingHoldActive` | " |
| 0x400D / 0x400E | `EventUsrMainOutVolumeUp` / `Down` | the volume buttons |

**probe27 was right and is now independently confirmed.** Holding the
Bluetooth button makes the speaker enter pairing, and 0x4003 is literally
`EventUsrEnterPairing`. That was established the hard way — suppress the
sound, hear which button went quiet — and the ADK header agrees.

It also explains the shape of the dispatcher at 0x1063F
(`docs/centre-button-hook.md` (not in this export)): it emits `Answer`, `Reject`, `CancelEnd`,
`TransferToggle` and the three-way call events, choosing among them by
call state. That is a **call-control** dispatcher, which is why one
physical button produces different ids in different states.

## The centre button: 0x4004 is the candidate

The obvious modern answer would be `EventUsrVoiceAssistantStart` (0x40CE)
or `EventUsrInitateVoiceRecognition` (0x40CC). **Neither appears anywhere
in Bose's image** — zero loads, zero compares. They postdate the ADK
version Bose built from (VM 19.0; these are present in 4.3.1's header but
unused here).

What Bose does use is **`EventUsrInitateVoiceDial` (0x4004): 8 loads and
2 compares**, and `docs/centre-button-hook.md` already recorded that
`fn 0x846` dispatches 0x4004 to 0xE1A as part of its hold family.

`EventUsrInitateVoiceDial` is the HFP mechanism for asking the *phone* to
open its voice assistant — which is exactly what a centre button on a
speaker of this era does, and it matches the owner's own description of a
centre-button long-press: a beep and an LED flash, a session opening.

> **Hypothesis, not a finding: the centre button's long-press is
> `EventUsrInitateVoiceDial` = 0x4004, handled at 0xE1A.**

It is testable with the method that settled 0x4003: hook or suppress it
and have the owner press one button. That is a cheap experiment, and it
is the next one to run **after** the audio question is answered, not
before — a trigger is worth nothing until there is something worth
triggering.

## How to regenerate

```sh
grep -oE '/\*0x4[0-9A-Fa-f]{3}\*/\s+Event[A-Za-z0-9_]+' \
    adk/4.3.1/app/apps/sink/sink_events.h
```

and the cross-reference against Bose's image is what produced
`build/analysis/sink-events.txt`.
