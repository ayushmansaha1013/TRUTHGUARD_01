# Hick's Law applied to TruthGuard AI
### Interaction-design rationale — paste-ready for the project report

---

## 1. The law

**Hick's Law (Hick–Hyman):** the time to make a decision grows with the number and complexity of the choices, approximately

> **RT = a + b · log₂(n + 1)**

where `n` is the number of equally-plausible options. Two consequences drive every decision below:

1. **The curve is logarithmic, so the first few options are the expensive ones.** Going 1 → 2 options costs far more than 8 → 9. Removing *any* option from a small set is a large win.
2. **Options must be *distinguishable* to count as separate.** If a user has to read three similar buttons to find the right one, the effective `n` is higher than the visible count. Visual hierarchy therefore *reduces* `n` without removing features.

The design goal for TruthGuard AI: **at every point in the flow, the user should be making at most one real decision, and it should be obvious which one.**

---

## 2. Screen-by-screen audit

| Screen | Before (n) | After (n) | What changed |
|---|---|---|---|
| **Landing (signed out)** | 3 equal CTAs | **1 primary + 1 secondary** | "Create free account" is solid, magnetic and sheened; "I already have one" is a ghost link. One obvious path. |
| **Signup** | **4 decisions** (email, password, confirm password, role) | **2 decisions** (email, role) | Confirm-password **removed** and replaced by a Show/Hide toggle + live strength meter. Role is **pre-selected as Student**, so the modal case needs zero interaction. |
| **Login** | 2 | **1** | Deliberately *not* extended with OAuth buttons or "remember me" — each would multiply decision time without helping a student reach the scanner faster. |
| **Image Scanner** | 2 competing buttons in the header ("Analyse" + "New scan") | **1** | "Scan another image" moved *inside* the result card, where it only exists once there is a result to discard. It never competes with "Analyse". |
| **Scanner result** | 5 simultaneous metrics | **1 focal + 4 collapsed** | The confidence ring is the single focal number; `raw_label`, `fake_probability`, `is_fake`, `analyzed_in_ms` moved behind a closed `<details>`. |
| **Fact Checker composer** | 3 example chips | **2** | Both from clearly different domains (health vs. history), so neither forces a comparison. |
| **Fact-check verdict bubble** | verdict + explanation + sources + retrieved context, all at once | **1 badge, then layered** | `retrieved_context` (the noisiest data on the page) is behind a closed disclosure. Sources stay visible — they are the pedagogical point. |
| **Educator Dashboard header** | 5 controls (7d / 30d / Refresh / Generate Quiz / implicit "show all") | **1 primary + 1 binary + 1 quiet icon** | "Generate Quiz" is the only solid button. Range is a 2-state segmented control (log₂2 = 1 bit — the theoretical minimum). Refresh became a low-weight icon button: same affordance, far less visual competition. |
| **Dashboard table filtering** | would have needed 4 new filter buttons | **0 new controls** | The four stat cards **are** the filters. Clicking "Deepfakes detected" narrows the table. This is *direct manipulation*: capability went up while the visible control count stayed the same. |

---

## 3. The signup change in detail (the largest single win)

**Removed:** the "Confirm password" field.
**Added:** a Show/Hide visibility toggle and a live strength meter.

Why this is a genuine usability improvement rather than a shortcut:

* The confirm field exists **only because the field is masked**. Give the user visibility and the reason for duplication disappears. This is precisely why Google, GitHub and Supabase's own dashboard dropped it.
* Error prevention beats error recovery. A strength meter gives *continuous* feedback while typing; a confirm field gives a single failure **after** the user has typed the password twice.
* Masked retyping is the highest-friction field in any signup form, and its failure mode (mismatch) is 100% recoverable later — you simply have to remember the password.
* **Nothing about password security is weakened.** Supabase still enforces the minimum length server-side, still hashes with bcrypt, and the password still travels only over TLS to the auth endpoint. Removing a *duplicate input* removes no control.

The trade-off is guarded by a **regression test** (`src/pages/Signup.test.jsx`) that fails if anyone re-adds the field, re-adds a third role option, or un-selects the least-privileged default:

```
✓ asks for exactly TWO pieces of text input: email and password
✓ has NO confirm-password field (visibility toggle replaces duplication)
✓ offers exactly TWO role options, with the least-privileged one pre-selected
✓ has exactly ONE submit control
```

---

## 4. Techniques used to lower *effective* n without removing features

Hick's Law is about **plausible** options, so hierarchy is a legitimate tool:

1. **One solid button per view.** Everything else is ghost/outline. The eye resolves the primary action pre-attentively, before any reading happens.
2. **Segmented controls instead of dropdowns** for 2–3 mutually exclusive values (the 7-day / 30-day range). All options are visible, so there is no "open the menu to discover the choices" step.
3. **Progressive disclosure** (`<details>`) for secondary data. It is present and one click away, but it does not enter the initial decision set.
4. **Direct manipulation over menus.** The stat cards filter the table, so no filter menu exists at all.
5. **Status, not options.** The backend health pill and the character counter report state; they never ask anything. The counter states *one* next action ("4 more characters needed"), never a list of possible problems.
6. **A single, always-available escape.** Every filter has one obvious way to clear it (the active chip, or "All submissions"), so the user never has to reason about how they got into a state.

---

## 5. Interaction design beyond Hick's Law

The same pass added the feedback loops that make the reduced choice set feel *responsive* rather than sparse:

| Technique | Where | Why |
|---|---|---|
| **Immediate inline validation** | both forms, dropzone, composer | Feedback in <16 ms beats a 300 ms server round-trip; the user never has to decide whether the form was accepted. |
| **Live state in the button label** | Analyse / "Analysing… 3s" / "Please wait 7s…" | The control reports its own state, so there is nothing to re-read or infer. |
| **Physical press feedback** (`.press`) | every button, link, chip | A 1px translate + scale on `:active` is a *non-colour* confirmation, so it works for colour-blind users. |
| **Magnetic CTAs** | primary actions only | The button responds before the click is committed — but translation is capped at 12 px so it can never move out from under the cursor (which would *violate* Fitts's Law). |
| **Count-up numbers** | dashboard stat cards | Motion ties the number to its change, so a range switch reads as a transition rather than a jump. |
| **3D verdict flip** | scanner | The card turning over is an unambiguous "the answer has arrived" event — stronger than a fade, and it gives the ~3 s wait a visible payoff. |
| **Threat pulse** | scanner → WebGL scene | A red shockwave through the 3D shield when `is_fake` is true: redundant coding of the verdict (colour + shape + motion + text). |
| **Scroll progress bar** | global | Peripheral awareness of "how much is left", which reduces the urge to scroll-search. |

---

## 6. Accessibility guarantees (the part that usually breaks)

Every effect above is **additive**, never load-bearing:

* `prefers-reduced-motion: reduce` disables all animation in one CSS block (`src/styles/3d.css` §12) and is re-checked live, because users can toggle it mid-session. The WebGL hero is replaced by a static composition; the flip card cross-fades instead of rotating; `CountUp` jumps straight to the final value.
* Coarse pointers (touch) get no hover-only effects — tilt, spotlight and magnetism are disabled, because there is no hover to respond to and tilt-on-drag fights page scrolling.
* No WebGL / software rasteriser → CSS 3D fallback. There is no state in which the hero is an empty box.
* Colour is never the only signal: every verdict badge carries its text label, and press feedback is geometric.
* All decorative layers are `aria-hidden="true"` and `pointer-events: none`, so they can neither be announced nor intercept a click.
* Every hover affordance has a matching `:focus-visible` ring (2 px teal, 3 px offset), so keyboard users get the same information as mouse users.
* Filter chips and clickable stat cards expose `aria-pressed`; the range control is a labelled `role="group"`.

---

## 7. One-line summary for the conclusion

> Applying Hick's Law, the signup flow was reduced from four decisions to two by replacing password duplication with password visibility, the dashboard header from five competing controls to one primary action plus a two-state range, and the scanner result from five simultaneous metrics to one focal number with the rest behind progressive disclosure — while *adding* capability, because the four stat cards became direct-manipulation filters for the table below them. Every reduction is locked in by a regression test, and every added motion effect degrades to a static, fully usable interface under `prefers-reduced-motion`, on touch devices, and where WebGL is unavailable.
