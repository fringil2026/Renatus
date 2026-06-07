---
incident-id: WS-INC-<SLUG-OR-STUDIO>-NNN
scope: <slug | studio>
reported: <YYYY-MM-DD>
status: OPEN            # OPEN | BLOCKED | RESOLVED  (the filename IS the state)
links: <edit NNN / decision NNN / prior incident NNN, if any>
---

## SYMPTOM
<The human's words VERBATIM> — where observed: <URL / screen / command>.

## DIAGNOSTIC
Evidence gathered BEFORE any fix — reproduce the failure FIRST. State what was checked and what each
check showed:
- Reproduction: <the exact steps/route/command that triggers it; the observed failure>
- Build output: <npm run build result, errors>
- status.json log / audit log: <relevant lines>
- Browser-visible behavior / failing request or route: <network, console, HTTP status>
<If it could NOT be reproduced, say so honestly and state what's needed to reproduce.>

## ROOT CAUSE
<ONE falsifiable sentence naming the actual cause, traced to the evidence above.>
<"Probably X" is NOT a root cause — keep diagnosing, or list the competing hypotheses and how the
fix will DISCRIMINATE between them.>

## FIX PLAN
Smallest change that addresses the root cause. Every file to touch + why:
- <path> — <why>
<Reimplementation is allowed when the diagnostic shows the implementation itself is unsound — say so
explicitly rather than patching rot.>

## VERIFICATION
How we'll PROVE it's fixed:
- Re-run the reproduction — it must now PASS (with evidence).
- Re-run every parity-checklist row the touched files could disturb (the verification-loop rule applies).

## RESOLUTION
<Filled at close.> What changed · commit(s) · the evidence the symptom is gone (reproduction now passes).
