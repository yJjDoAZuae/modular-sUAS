# The derivation

**Status:** written 2026-08-28 under
[IP-FC-87](../implementation/freecad_migration.md), which
[OQ-DES-D9](dimension_scheme.md#open-questions) called for. **Restructured 2026-08-29**, in two
corrections: originating requirements were separated from the level below them, and the level
below was relabeled — it had been called *derived* throughout, which in the standard sense of
that word means "traceable to no higher-level requirement" and was true of only three of the
eleven. Section 1 records what the mislabel cost. It is the document the project did not have: a statement
of what the interfaces are *meant* to be, from which the geometry that exists follows.

> **The originating requirements in [section 2](#2-originating-requirements--proposed) are
> PROPOSED, and were written without reading the requirements that already exist in the
> project wiki.** Reconciling the two is [OQ-DES-DV5](#open-questions), and it comes before
> acceptance: the reconstruction agrees with the wiki in most places, is missing three of
> its requirements, and gets the reason for the mold line backwards. Until that is settled,
> nothing below is on firmer ground than section 2 is.

---

## 1. Three kinds of statement, and they are not interchangeable

**Originating requirements** come from outside the design — from the mission, the physics, the
manufacturing process, and the people who build and fly the airframe. They are traceable to
nothing below them. That is what makes them axiomatic once accepted: they are not *right*
because something else in the project implies them, they are the thing everything else is
answerable to. An originating requirement cannot be checked by a tool. It is accepted, or it is
not.

**Level-1 system requirements** are a level down. Most are obtained by **decomposition** —
allocating an originating requirement to the system — and each of those traces to its parent.
[Section 4](#4-level-1-system-requirements) states eleven, and
[section 5](#5-the-interfaces--level-2-part-requirements) decomposes them again into part-level
interface requirements, which are the ten joints.

**Derived requirements are not the same thing, and the word has a specific meaning.** In the
sense INCOSE uses — and ARP4754A and DO-178C with it — a derived requirement is one that is
**not traceable to any higher-level requirement**: it arises from the design solution itself,
from a technology or implementation choice, rather than from decomposing something above it.
That is narrower than "obtained by decomposition", and the difference carries an obligation. A
derived requirement has **no parent to validate it against**, so it has to be reviewed and
accepted on its own, exactly as an originating requirement does.

> **This document called all of them "derived" until 2026-08-29, and then reported as its
> headline result that every one traced upward.** In the standard sense of the word that is a
> contradiction: anything that traces upward is decomposed, not derived. The structure was
> right and the label was wrong — and the label is the part that tells a reviewer what they are
> obliged to look at.

Three of the eleven **are** genuinely derived: SR-4, SR-5 and SR-6, all three of them decisions
about *where a joint's clearance goes*, which nothing above the design requires. They are
flagged, they carry their own justification in place of a parent, and `check_derivation.py`
refuses a requirement flagged derived that has a parent as readily as one that has neither.

**Derived and *inferred* are different axes**, and SR-4 is why both labels are needed: its
reason is recorded in `design_constants.json`, so it is not inferred — and it traces to no
requirement, so it is derived. A recorded rationale is not a parent.

**Implementation artifacts** are neither. They are quantities that exist because a modeling
kernel needs them — a cutting solid that has to overshoot, a union that has to overlap, a mask
that has to reach past the profile. They have no design content at all, and the project has
already been bitten once by failing to say so: the corner's panel rebate is cut by a primitive
sized `2·panel_thickness + 2·panel_tolerance`, and the interface register recorded that as the
joint's own dimension until 2026-08-28.
[Section 7](#7-what-is-neither-implementation-artifacts) lists them and gives the rule that
keeps them distinguishable.

### What each level is answerable to

| Level | Traces to | Checked by | If it is wrong |
| --- | --- | --- | --- |
| L0 originating | nothing — it is the source | review and acceptance | the design is solving the wrong problem |
| L1 system, decomposed | one or more L0 | `check_derivation.py`'s trace check | a design rule is unjustified |
| L1 system, **derived** | **nothing — and that is the finding** | its own rationale, plus review, same as an L0 | a design decision nobody agreed to is load-bearing |
| L2 part interface | one or more L1 | `check_derivation.py` on the parameters, `check_derived_geometry.py` on the faces | a part does not meet its interface |
| Implementation artifact | nothing, deliberately | the kernel, by building | a boolean fails, or nothing at all |

Rows three and five both trace to nothing, and confusing them would be the worst mistake this
table could invite. A derived requirement is a **design decision that needs accepting**; an
implementation artifact is a **number with no design content at all**. The first belongs in a
review, the second must never reach one.

### The test this document has to pass

> **Derivability: the geometry as it stands — the OpenSCAD source, together with the corrections
> the FreeCAD migration turned up — must *follow from* the L1 requirements; and every L1
> requirement must either trace to an L0 requirement or be flagged derived and carry its own
> justification. Where a link fails, one end of it is wrong, and the disagreement is visible.**

Visible is the operative word, and it is why this document ships with checkers rather than with
an argument that it is correct. [Section 9](#9-how-this-is-checked) describes them. **What they
cannot do is check section 2**, and no tool can: an originating requirement is accepted by
review. Confusing the two is exactly the failure this document was written to end.

### How to read the source labels

Every statement below is labeled with where its reason comes from:

| Label | Meaning |
| --- | --- |
| **recorded** | the reason is written down in `design_constants.json`, a design document, or a resolved open question, and is quoted or cited here |
| **generalized** | the reason is recorded for some of the cases it covers, and stating it as a rule over all of them is this document's step |
| **inferred** | no reason is recorded; the reconstruction is this document's, is marked as such wherever it is used, and is **not** design authority |

Ratifying an expression read off the geometry as design intent is the move that produced
OQ-DES-D9, so an inference is never promoted here — it is flagged, and
[OQ-DES-DV3](#open-questions) asks whether any of them may be adopted.

Millimeters and degrees throughout, which is what the OpenSCAD path uses. Where a quantity is a
print setting rather than an airframe dimension, the unit is stated with it.

---

## 2. Originating requirements — **proposed, and superseded pending reconciliation**

> **A requirements set already exists, in the project wiki, and this list was written without
> reading it.** Found 2026-08-29. `modular-sUAS.wiki` carries a Mermaid `requirementDiagram`
> on its *MAUS‑FOS Fuselage Outer Mold Line (OML) Standard* page, and an objectives list on
> *Modular Airframe Unitized System (MAUS) Architecture*. That is the authoritative source and
> this section is a reconstruction of it made in ignorance of it. **Reconciling the two is
> [OQ-DES-DV5](#open-questions), and until that is done nothing here should be accepted** — the
> reconstruction agrees with the wiki in most places, is missing three of its requirements, and
> gets one of them backwards.

**What the wiki actually says**, because the differences matter more than the agreements:

| Wiki | This section |
| --- | --- |
| Two standards in a refinement chain: **MAUS‑FOS** (the OML standard) refines *Modularity*; **MAUS‑FD1** (this printable design system) refines MAUS‑FOS *and* *Printability* *and* *Assembly*; the fuselage design *satisfies* MAUS‑FD1 | one flat list, with no FOS/FD1 distinction at all |
| *Modularity*, 8 sub-requirements — interchange and re-ordering of sections, interchange not affecting structure, flat exterior panels for system integration, simple shape for the wing interface, constant cross section for longitudinal relocation, standardized dimensions for commonality | OR-1, OR-2, OR-4, partly |
| *Printability*, 3 — FDM printable, **layer orientation aligned to structural performance needs**, **printable without support material** | OR-5 covers the first; **the other two have no counterpart here** |
| *Assembly*, 1 — **components are self-aligning during assembly** | OR-7, and the wiki's wording is the better one |
| **"dimensional tolerances are considered application dependent and therefore are not included in the standard"** | OR-6 treats clearance as originating |
| Objectives: iteration of sizing and configuration, system integration, modularity, decoupled component designs — **"optimization of aerodynamic efficiency is a secondary concern"** | **OR-3 calls the mold line aerodynamic**, which inverts this |

**The one that is backwards.** OR-3 below justifies the mold line as an aerodynamic surface. The
wiki's stated reasons for the OML are all modularity ones — flat panels for system integration,
a simple shape for the wing interface, a constant cross section so wings can move
longitudinally, standardized dimensions for commonality — and it says outright that aerodynamic
optimization is secondary. The *datum* generalization this document makes turns out to be
better supported than the reason it gave for it: "interchange or re-ordering of fuselage
sections does not affect fuselage structure" is a stronger parent for a shared, untradeable
mold line than aerodynamics ever was.

**The one that changes what is even in scope.** The OML standard excludes dimensional
tolerances deliberately, as application-dependent. If that holds, then SR-4, SR-5 and SR-6 —
this document's three derived requirements, all of them about where a joint's clearance goes —
are derived *by design*: the standard declines to parent them, and they belong to FD1. That is
a much better answer than "nobody wrote it down", and it is the wiki's, not this document's.

Nine statements follow. Each is a reading of something the project has recorded; the *source*
column says what, and the *label* says how far the reading goes beyond it. **None has been
accepted, and the label is not a substitute for acceptance** — a requirement can be faithfully
read off a recorded note and still be the wrong requirement.

**OR-1 through OR-8 originate the airframe. OR-9 originates the drawing set**, which is a
different branch of the same tree and is why `dimension_scheme.md` exists as a separate
document. Whether they should be two lists is [OQ-DES-DV4](#open-questions).

| ID | Statement | Source | Label |
| --- | --- | --- | --- |
| **OR-1** | One parametric standard produces the whole family of sizes: a fuselage *is* a set of standard lengths scaled by `U`. | `design_constants.json` `standard._about` — *"The parametric standard: what 1U means, in millimeters … These are the numbers a fuselage IS."* | recorded |
| **OR-2** | The airframe is modular: a bay is four corners and two bulkheads, and bays join end to end. | `corner.md` — *"Four of them, plus a bulkhead at each end, make one bay"*; the `end_bolt` / `end_anchor` / `interconnect` type axis | recorded |
| **OR-3** | The outer surface is an aerodynamic mold line, and it is continuous across every part that reaches it. | the OML comes from OpenVSP (`cad/modular_sUAS_nose_tail.vsp3`, UC-9); `corner_radius`'s entry — *"the mold line the panel's outer surface is flush with"* | generalized — the *continuity* clause is this document's |
| **OR-4** | Panels are designed by others inside an allocated envelope, and interchange. | stated 2026-08-22, `dimension_scheme.md` §0 — *"Panels are to be given their own OML allocation with panel shapes designed inside it, so that designs can be interchanged"*; OQ-DES-D4 | recorded |
| **OR-5** | Structural parts are FDM printed; longerons, booms, panels, fasteners and inserts are bought. | the `printer` group; `panel_variants.csv`'s supplier sizes in inches and millimeters; `threaded_insert_dimensions.csv` | recorded |
| **OR-6** | Joints are bonded or fastened, and must accommodate print variation and bond thickness. | `tolerances._about` — *"a joint built with no gap has nowhere for the bond to go and nothing to absorb print variation"* | recorded |
| **OR-7** | The airframe assembles by hand, without jigs. | `greeble_opening_angle`'s entry — *"the tube presses in sideways and snaps into the bore"*; `greeble_snap_clearance_per_u` — *"so the corner can snap in from the back side"* | recorded |
| **OR-8** | The volume the airframe encloses is usable — payload, wiring, and a hand with a nut driver. | stated 2026-08-22, `dimension_scheme.md` §1's second clause | recorded |
| **OR-9** | The drawing user is integrating with the structure, not inspecting a part. | stated 2026-08-22, `dimension_scheme.md` §0 — *"the drawing user wants to understand the impact of the part design on their integration with the structure"*; OQ-DES-D2 | recorded |

### What acceptance would have to settle

Reviewing these is not a formality, and three things in particular are underdetermined:

- **Whether OR-3's continuity clause is a requirement or a convention.** The recorded notes say
  three separate parts land on the mold line. That the mold line is a *shared datum no joint may
  trade against* is the generalization, and it is what four level-1 requirements rest on.
- **Whether OR-2 fixes the number four.** A rectangular section with four corners is what
  exists; whether the section shape is originating, or is itself derived from an aerodynamic
  requirement, is not recorded anywhere.
- **Whether OR-9 belongs in this list at all**, or is the head of a separate tree for the drawing
  set. [OQ-DES-DV4](#open-questions).

---

## 3. What is chosen

The originating requirements say *that* there is a standard, that panels are bought, that joints
carry clearance. These are the numbers that say **what**. A derivation has to bottom out
somewhere, and being on this list is a claim: that the value is a decision, not a consequence.

| Chosen | Value | Where | Instantiates | Why it is not derived |
| --- | --- | --- | --- | --- |
| `unit_width` | 100 mm at 1U | `standard` | OR-1 | the standard: what 1U *is* |
| `unit_length` | 100 mm at 1U, FX=1 | `standard` | OR-1, OR-2 | the bay length, and the only standard value FX scales |
| `corner_radius` | 10 mm at 1U | `standard` | OR-1, OR-3 | the mold line's corner |
| `longeron_radius` | 2 mm at 1U | `standard` | OR-1, OR-5 | the tube is bought at this size |
| `bolt_offset` | 8 mm at 1U | `standard` | OR-1, OR-2 | where the fastener sits in the corner |
| `panel_thickness` | 9 stock sizes | `panel_variants.csv` | OR-5 | the panel is bought; the sizes are a supplier's, in inches and millimeters both |
| `bulkhead_thickness` | 4, 5, 6, 6, 8, 10, 12, 16 | `bulkhead_size_variants.csv` | OR-1 | **tabulated per size step, and no rule relates it to U** — [OQ-DES-DV2](#open-questions) |
| `bulkhead_bolt_diameter` | 3, 3, 4, 4, 5, 6, 6, 8 | `bulkhead_size_variants.csv` | OR-5 | a standard fastener series, chosen per size step |
| `boom_diameter`, boom `y`/`z` | fractions of `unit_width` | `boom_bulkhead_type_variants.csv` | OR-1, OR-5 | the boom tube is bought; where it sits is a configuration |
| `greeble_opening_angle` | 35° | `geometry` | OR-7 | tuned by experiment; the file says explicitly not to replace it with a formula |
| `boom_key_angle` | 0° | `geometry` | OR-2 | the key does not have to be there at all |
| `extrusion_width`, `layer_height` | 0.6, 0.2 mm | `printer` | OR-5 | print settings, not airframe dimensions |
| `cowl_n_perimeters` | 1 | `slicing` | OR-5 | how many perimeters the **cowl** prints with |
| the seven clearances | 0.05 … 0.2, one negative | `tolerances` | OR-6 | **four carry no argument for their size** — [OQ-DES-DV3](#open-questions) |

Everything else in the sweep is derived below. That is not a claim about tidiness; it is the
coverage `check_derivation.py` enforces.

---

## 4. Level-1 system requirements

Eleven rules. Each states whether it is **decomposed** from an L0 parent or **derived** — with
no parent at all — and how far the reasoning is recorded. They are what
[section 5](#5-the-interfaces--level-2-part-requirements)'s interfaces are built on, and the
same ids appear in the source: `check_derivation.py` carries them as data and refuses a relation
that names one which does not exist.

### SR-1 — Airframe dimensions are proportional to U, and scale freely with it — **recorded**

*Decomposed from OR-1.* This is the general case and it covers most of the airframe: the
standard's five lengths, and every `_per_u` coefficient in the `scaling` group. `unit_length` is
multiplied by `FX` as well, because FX is the bay-length axis and nothing else responds to it.

**Scaling freely includes going below the 1U value, and most dimensions do.** Measured on a
1 mm-panel `end_bolt` at U=0.5 against U=1: `corner.radius` 5 against 10, `web.width` 1.5
against 3, `web.fillet_radius` 1 against 2, `bulkhead_flange.chamfer` 0.5 against 1,
`plate.thickness` 0.4 against 0.8, `longeron.radius` 1 against 2, `bolt.offset` 4 against 8 —
**eleven derived fields shrink and four do not**. The four that hold are SR-11's, and they are
the exception.

### SR-2 — A feature whose size the print process governs is sized in whole extrusions or whole layers — **recorded**

*Decomposed from OR-5.* `design_constants.json`'s `scaling._about` states the discipline,
including that the suffix carries the unit: *"`_extrusions` is a count of `extrusion_width`,
`_layers` a count of `layer_height`, `_per_u` a multiple of U in millimeters, and a bare `_mm`
is an absolute floor that does not scale."*

`ceil(n·U)·extrusion_width` for a wall and `ceil(n·U)·layer_height` for a skin: a wall is laid
down in whole perimeters and a skin in whole layers, so the count rounds up and the feature
takes the size that produces. **This is about quantization, not about a minimum** — the plate
is `ceil(4·U)` layers and gets thinner as U falls, 0.4 mm at U=0.5 against 0.8 at U=1.

The one feature that scales as neither a proportion nor a count is the greeble wall, and its
entry says why: *"sqrt(U) not U: the wall is a printed feature sized to survive a snap fit, so
it scales in extrusions rather than as a fraction of the airframe."*

### SR-3 — Every part reaching the outer surface lands on the mold line, and a joint's clearance is taken inboard of it — **generalized**

*Decomposed from OR-3 and OR-6.* Recorded for three joints, in the clearances' own `why` fields:
`panel_tolerance` — *"so its outer surface still lands flush with the mold line at
`corner_radius`"*; `cowl_flange_tolerance` — *"the perimeter term is the radial room the
**COWL's** wall occupies, so the cowl's outer surface still lands on the mold line"*;
`nose_flange_tolerance` — *"the offset is a function of the shell it lands on"*.

**The generalization is this document's:** stating it as a rule that also governs the corner's
panel seat and the bulkhead's outer face, neither of which has it written down. Both follow —
section 5 shows the faces landing where the rule requires — but the rule was read from three
instances and then found to hold for five.

### SR-4 — A joint's clearance appears once, on one named side; the other side is nominal — **DERIVED**, and **recorded**

**Traces to no higher-level requirement.** OR-6 requires that a joint accommodate print
variation and bond thickness; it does not say the accommodation is single-sided, and splitting
it across both halves would satisfy OR-6 equally. Putting it on one side is a design decision.

**Its reason is on record, which is exactly why this rule needs two labels.** Recorded twice in
the same words: `greeble_tolerance` — *"Carried entirely on the **CORNER** … so the joint takes
the clearance once. There is deliberately no bulkhead counterpart; 'the post is nominal' is an
invariant, not a setting"*; `corner_tolerance` — *"Carried entirely on the corner, same as the
greeble: when the bulkhead re-evaluates that shape to cut its own socket it passes 0."* So it is
**recorded** — its rationale is written down — and still **derived** — nothing above it requires
it. A recorded rationale is not a parent, and the two axes have to be tracked separately or a
rule like this looks validated when it is only explained.

**The unit is the joint, not the parameter, and `panel_tolerance` is why that has to be said.**
It is carried by *both* the corner (register row 4) and the bulkhead (row 5), which is not a
violation of this rule: those are two different joints against the same bought panel, and each
takes its own clearance once, on its own printed side. SR-3 in fact *requires* it — the panel
lies across both seats, so both must be set back by the same pocket or it cannot sit flat on
the mold line. Measured at 1U with a 3/16 in panel: the corner seats at 5.1375 corner-local and
the bulkhead at 45.1375 airframe, both the mold line less 4.8625. A rule stated over parameters
rather than over joints would forbid the geometry that is correct.

The consequence for a drawing is real and belongs to OR-9's branch rather than to this rule: a
drawing that dimensions both sides at nominal is not wrong about either part and is wrong about
the joint, and an inspector measuring the bulkhead's post against a drawing showing a clearance
would reject a good part.

### SR-5 — The bought part is nominal and the printed part carries the fit — **DERIVED**, and **inferred**

**Traces to no higher-level requirement.** OR-5 says which parts are bought and OR-6 says the
joint needs clearance; neither implies that the clearance goes on the printed side. The longeron
tube, the boom tube, the bolt, the insert and the panel are all bought, and each mating feature
in the printed parts is sized to the bought part's nominal plus a clearance. This is consistent
everywhere and written down nowhere — so unlike SR-4 it is both derived and inferred, which is
the weaker position of the two.

### SR-6 — At the corner/bulkhead interface the corner carries the clearance, so the bulkhead's dimensions stay consistent — **DERIVED**, and now **recorded**

**Rationale stated 2026-08-29, so this is no longer inferred:** *the corner is less likely to
have integrated components interfacing it than the bulkhead, so the bulkhead is the part whose
dimensions should stay consistent, and the variation is allocated to the corner.*

That is a stronger statement than "the corner carries it", and it generalizes: it is a rule
about **which part is the stable one**, so it would decide the next allocation of this kind the
same way without anyone having to re-argue it.

> **Both reconstructions this document offered were wrong.** It had proposed that the clearance
> sits on the corner because there are four corners to one bulkhead, or because the corner is
> the part that is pressed in. Neither is the reason. Both read plausibly, which is the entire
> case for [OQ-DES-DV3](#open-questions)'s refusal to promote an inference: a confident,
> well-argued reconstruction was available here, and it was not the intent.

**It stays flagged derived, pending [OQ-DES-DV5](#open-questions).** The rationale points at a
parent that plausibly exists in the wiki — *Modularity4*, "interchange or re-ordering of
fuselage sections does not affect fuselage structure", and the objective of facilitating system
integration — but which one it decomposes from is exactly what the reconciliation has to
settle, and inventing the parent here is the move this document exists to avoid.

### SR-7 — Where a joint does not exist its clearance is zero, and that zero is the absence of the joint rather than a fit set to nothing — **recorded**

*Decomposed from OR-6 and OR-9.* `panel_tolerance` is 0 on a cowling bulkhead and on the 0 mm panel
variants; `cowl_flange_tolerance` is 0 on every non-cowling type; `plate.tolerance` is 0 where
the plate is inactive.

The drawing consequence is recorded: a generated drawing must **omit** the dimension rather than
print `0.0`, because a dimensioned zero asserts a coincident fit that was designed and is
inspectable. The geometric consequence is derived here and is sharper than it looks — see
[section 6.3](#63-what-happens-when-a-feature-is-absent), where a feature turns out to vanish in
two different ways.

### SR-8 — No part may intrude on the volume swept by another part's assembly motion — **recorded**

*Decomposed from OR-7.* A clearance under SR-8 is room for a *motion*, not for a fit, which is
why it is a separate rule: it is measured along the direction of assembly and it applies even
where the assembled parts end up nowhere near each other.

### SR-9 — A drawing states which of several competing requirements produced a dimension — **recorded**

*Decomposed from OR-9.* Where two requirements bear on one feature, the feature takes the
binding one — that much is not a requirement, it is simply what a constraint does, and
`corner.md` records the instance: the corner's inboard boundary must clear the longeron bore
*and* sit outside wherever the panel interface has been pushed to, *"and whichever binds,
wins."* **The requirement is what the drawing then has to say.** The table carries the number,
and a note has to carry *which term produced it*, or an integrator takes the wrong design intent
away from a correct number.

### SR-10 — The panel envelope is fixed by the frame and stated without reference to any panel design — **recorded**

*Decomposed from OR-4.* Every boundary of the allocation is determined by the frame, and
OQ-DES-D4 made the envelope a part so a candidate panel is checked by containment rather than
against transcribed numbers.

**SR-9 and SR-10 are the two that no parameter relation enforces**, and `check_derivation.py`
says so on every run rather than letting them sit in the table looking checked. Both govern the
drawing or the envelope rather than a number the sweep produces: SR-10 is enforced by the OML
part and by section 6.1's allocation table, SR-9 by the note-binding in `check_drawing.py`.

### SR-11 — Where a feature's function is set by something that does not scale with the airframe, its size is floored — **partly recorded**

*Decomposed from OR-5 and OR-6.* This is SR-1's exception and it is a short list: four derived
quantities floor, written `max(n·U, n)` or `max(ceil(n·U)·w, n·w)` — `bolt.thickness`,
`bulkhead_flange.thickness`, `greeble.thickness` and its nub — plus the boom key's width, height
and radius, which are zero on every non-boom variant. `panel.overlap` floors too, on an absolute
4 mm rather than on a 1U value.

**The floor's reason is recorded for two of them and not for the rest.** The greeble wall:
*"The floor is the same n because a one-extrusion wall has no interior."* The panel overlap:
*"Absolute millimeters and deliberately unscaled — it is a bond-area minimum, not a proportion
of the airframe."* For the bolt boss, the bulkhead flange wall and the boom key, the floor is
stated and its reason is not — see [section 8](#8-what-could-not-be-derived).

That the floor *value* usually equals the 1U value is a consequence of writing it `max(n·U, n)`,
not the reason for it. `panel.overlap`'s floor is 4 mm, which is nothing's 1U value.

---

## 5. The interfaces — level-2 part requirements

The ten joints `dimension_scheme.md` section 2 enumerates, each stated as a requirement on
specific parts, decomposed from the level-1 rules above, and then checked. The **Evidence** line
gives what was measured on the built solid, not what the source says.

Values in the evidence lines are at **1U with a 3/16 in panel** unless stated: `corner_radius`
10, `panel_thickness` 4.7625, `panel_tolerance` 0.1, `panel_overlap` 4.7625, `panel_offset` 2.5,
`longeron_radius` 2, `longeron_tolerance` 0.05, `extrusion_width` 0.6.

### Joint 1 — longeron tube → corner bore

*Traces to SR-5, SR-8.*

**Requirement.** The tube passes through the corner for the full length of the part and is
located by it, not retained by it (`corner.md`). It is bought.

**Derivation.** SR-5: the tube is nominal, so the bore carries the whole clearance. SR-8: the
tube is pressed in sideways, so the corner's inboard boundary must leave the bore's mouth open
rather than closing around it; that boundary is derived under joint 3.

**Follows.** bore radius = `longeron_radius + longeron_tolerance` = 2.05.

### Joint 2 — bulkhead greeble post → corner socket

*Traces to SR-4, SR-6.*

**Requirement.** The greeble is the C-shaped seat that holds the longeron; it stands on the
bulkhead, and the corner has a socket it enters.

**Derivation.** The clearance goes on the corner. The socket is the greeble's own profile grown
by `greeble_tolerance`, and the post is built at nominal.

**Follows.** socket radius = `longeron_radius + longeron_tolerance + greeble_thickness +
greeble_tolerance`; the bulkhead's post is the same expression with the tolerance at 0.

**Evidence.** `greeble.tolerance` resolves to 0.05 on the corner sweep and **0 on both bulkhead
sweeps, on all 280 bulkhead variants** — the invariant, checked rather than asserted.

### Joint 3 — corner seating faces → bulkhead

*Traces to SR-4, SR-6, SR-9.*

**Requirement.** The corner plugs into a socket in the bulkhead. Its footprint there is bounded
by a flat face on each arm and a diagonal across the inboard side. The socket is cut from the
corner's own description, so the two are one shape and SR-4 puts the clearance on the corner.

**Derivation, and this is the one with real content.** Two constraints bear on the diagonal:

- **the bore branch.** The diagonal is a 45° line; where it crosses the axis it must leave
  material between itself and the bore, or the tube's opening is cut into. The standoff is
  `longeron_chamfer`, which is one `extrusion_width` — the thinnest wall that prints. So the
  crossing sits at `longeron_radius + longeron_tolerance + longeron_chamfer` from the axis.
- **the panel branch.** The diagonal may not rise above the panel seat, or it would cut into the
  seat the panel lands on. That puts a floor at
  `(panel_overlap + panel_offset) − (corner_radius − panel_thickness − panel_tolerance)`.

The binding branch wins; SR-9 makes the drawing say which. The **flat** faces then run from where the diagonal reaches them up to the
panel seat, so the seating flat's height is the amount by which the bore branch exceeds the panel
branch — and **when the panel branch governs, the flat is not small, it is gone.**

**Follows.**

```
flat_offset  = -max(longeron_radius + longeron_tolerance + longeron_chamfer,
                    (panel_overlap + panel_offset)
                      - (corner_radius - panel_thickness - panel_tolerance))
flat_x       = -(panel_overlap + panel_offset)
flat height  = max(bore branch, panel branch) - panel branch
```

Under SR-4 both faces then move inboard by `corner_tolerance` measured **normal to each**, which
is why the diagonal's intercept moves by `√2` times it and the flat's does not.

**Evidence.** At 1U/3-16 the bore branch is 2.65 and the panel branch 2.125, so the flat is 0.525
tall: the built corner has a face normal to X at −7.2625 of **52.5000 mm²**, which is 0.525 × the
100 mm part length, exactly. Across the sweep the bore branch governs on **240 of 264 corner
variants and 120 of the 132 non-cowling bulkhead variants**, and on the remaining 24 and 12 the
flat vanishes — checked by building `0.5 end_bolt 1 mm`, where `check_derived_geometry.py`
predicts the face absent and the part has none.

### Joint 4 — panel → corner

*Traces to SR-3, SR-5, SR-10.*

**Requirement.** The panel is bought flat stock. It lands on the mold line, is captured by the
corner along each edge, and is bonded there.

**Derivation.** SR-3 puts the panel's outer surface on the mold line, so the corner's seat is set
back from it by the panel and its fit, with the clearance inboard. SR-3 also says no material
stands outboard of the panel, so **the feature is a rebate and not a slot** — the panel's outer
face is exposed and *is* the airframe surface. The arm carrying the seat reaches the corner's own
mating plane at `panel_overlap + panel_offset` and stops there; stopping one clearance short would
put the end face inboard of the seat's own boundary (OQ-DES-B13, and OQ-DES-D8 for the same error
surviving in the register until 2026-08-28). The seat's inboard end is a stop the panel butts
against, placed one `panel_tolerance` beyond the panel's edge so the panel bottoms out on
clearance.

**Follows.**

| | Expression | At 1U, 3/16 in |
| --- | --- | ---: |
| seat, from the corner arc center | `corner_radius − panel_thickness − panel_tolerance` | 5.1375 |
| seat length along the arm | `panel_overlap + panel_tolerance` | 4.8625 |
| end stop, from the longeron axis | `panel_offset − panel_tolerance` | 2.4000 |
| end stop height | `panel_thickness + panel_tolerance` | 4.8625 |
| mold line surviving on the arm | `panel_offset − panel_tolerance` | 2.4000 |
| arm reach | `panel_overlap + panel_offset` | 7.2625 |

**Evidence.** Every one of those faces is where the derivation puts it on the built corner, to
1e-6 mm, with the derived area — at 1U/3-16 in, seat 486.2500 mm², stop 486.2500 mm², mold line
240.0000 mm², arm end 52.5000 mm². The same predictions hold at 4U/1-4 in and 0.5U/1 mm, and on
the 0 mm panel, where the features the derivation says are absent are absent.

> **The register said "slot `2·panel_thickness + 2·panel_tolerance` deep" until 2026-08-28.**
> That is not a wrong requirement — it is not a requirement at all. It is the size of the cutting
> primitive, which overshoots on both axes so the boolean clears the material. Recording an
> implementation artifact as a joint dimension is the failure mode
> [section 7](#7-what-is-neither-implementation-artifacts) exists to prevent, and this is the
> instance that prompted it.

### Joint 5 — panel → bulkhead flange

*Traces to SR-3, SR-10.*

**Requirement.** The panel runs the full length of a bay and is not interrupted at a station. It
has to be supported where it crosses the bulkhead.

**Derivation.** SR-3 from the other side: the panel's outer surface is on the mold line, so the
bulkhead's outer face is set back from the mold line by the panel pocket, and the panel passes
over it. The face runs the panel's exposed span, because that is the part of the panel that is
over the bulkhead rather than inside a corner.

**Follows.** outer face at `unit_width/2 − panel_thickness − panel_tolerance`, running
`unit_width − 2·(corner_radius + panel_offset) − 2·panel_overlap`.

**Evidence.** The built bulkhead's outer flat face is at **45.1375** and measures **392.8500
mm²**, which is 65.475 × 6 — the panel's exposed span times the bulkhead thickness. Checked at
0.5U, 1U and 4U and on the 0 mm panel. It is the strongest single confirmation in this document
because the span is derived from the panel allocation in [section 6.1](#61-the-panel), which
touches none of the bulkhead's own parameters.

**This is the reason a panel is not interrupted at a station: the bulkhead gives way to it.**
`unit_length − 2·bulkhead_thickness` was the alternative reading and it is wrong.

### Joint 6 — boom tube → boom bulkhead collet

*Traces to SR-1, SR-5.*

**Requirement.** A bought tube is gripped by a printed collet.

**Derivation.** SR-5: the tube is nominal, the collet's bore takes the clearance. SR-1: the
collet wall scales with the airframe like any other proportion, with no floor.

**Follows.** `collet_radius = boom_diameter/2 + boom_collet_thickness + boom_tolerance`, with
`boom_collet_thickness = 3·U`. Recorded verbatim in `boom_tolerance`'s entry.

**Residual.** The clearance is 0.2, four times the longeron's 0.05, and the constants file says
of it: *"the boom is a larger tube through a deeper bore, but the number has never been justified
in writing."* [OQ-DES-DV3](#open-questions).

### Joint 7 — cowl → cowling bulkhead flange

*Traces to SR-3, SR-7.*

**Requirement.** The cowl slides over a flange on the bulkhead and is bonded to it. The cowl's
outer surface is airframe surface.

**Derivation.** SR-3: the cowl's outer surface lands on the mold line, so the flange has to be
inboard of the mold line by the cowl's own wall — `cowl_n_perimeters · extrusion_width`, which is
a *print* quantity of the other part — plus the fit.

**Follows.** flange outer radius = `corner_radius − cowl_n_perimeters·extrusion_width −
cowl_flange_tolerance`; flange height `cowl_flange_height_per_u · U`. Recorded verbatim.

**Carried by the cowling type, not by the bulkhead.** The flange's height is zero on the end and
interconnect types, so it is not a feature those parts have — SR-7, and the reason
`dimension_scheme.md` row 7 names a type rather than a part (OQ-DES-D6).

### Joint 8 — nose closure → cowl shell

*Traces to SR-3.*

**Requirement.** The nose seats on top of the cowl's perimeter shell and is bonded to it. It is a
lap joint, and its alignment comes from the fit while its bond comes from the seating face.

**Derivation.** SR-3: the offset is the shell the nose lands on — the cowl's own wall again —
plus the fit against it. The fit is **negative**, and legitimately: a nominal interference is how
a printed joint is made to grip, and a bonded joint does not need a positive gap because the bond
line is on the seating face and not in the lap.

**Follows.** `nose.flange_inset = cowl_n_perimeters·extrusion_width + nose_flange_tolerance`
= 1 × 0.6 − 0.1 = **0.5**. Recorded verbatim, and confirmed on all 16 nose and tail variants.

Do not read the old `0.5 = 0.4 + 0.1` decomposition as provenance: 0.4 was the hand drivers'
development extrusion width, so that arithmetic is a coincidence of test numbers.

### Joint 9 — nose plate → nose closure

*Traces to SR-7.*

**Requirement.** A printed plate closes the nose tip and must print without support.

**Derivation.** SR-5 does not apply — both parts are printed — so the clearance is a fit between
two printed features and sits on the pocket. The relief angle is a print constraint:
`overhang_angle_from_bed`, one value for the project since OQ-DES-CW11.

**Follows.** pocket radius = `plate_diameter/2 + plate_tolerance`, relieved at
`overhang_angle_from_bed`. `plate.tolerance` is 0 on `tail_high_open`, where the plate is
inactive — SR-7.

### Joint 10 — bolt or insert → bulkhead

*Traces to SR-1, SR-11, SR-5.*

**Requirement.** Bays bolt together end to end. One end takes a bolt through a clearance hole,
the other a threaded insert.

**Derivation.** SR-1 places the fastener: `bolt_offset · U` from the corner arc center, on the
diagonal. SR-5 sizes the hole: a bolt gets its own nominal, an insert gets its bore from
[`threaded_insert_dimensions.csv`](../../src/Fuselage/tools/threaded_insert_dimensions.csv),
which is supplier data. SR-11 floors the boss around it: the fastener series does not shrink proportionally, so the
boss cannot either.

**Follows.** `bolt.offset = 8·U`; `bolt.radius = bolt_diameter/2`, or the insert bore for an
anchor; `bolt.thickness = max(3·U, 3)`.

**Residual.** Where the fillet between the bulkhead flange and the bolt boss lands relative to the
bolt axis is *not* determined by anything — it is the difference of four dimensions chosen
independently, and it takes whatever value they leave. That is OQ-DES-B14, deliberately measured
and reported rather than constrained, and this document does not change it.

---

## 6. What follows from the interfaces

### 6.1 The panel

The panel's own size is what a panel designer needs and no joint states it. SR-10 requires it be
stated anyway, and SR-3 does the work: the panel spans from corner to corner, its outer face on
the mold line.

| | Expression | At 1U, 3/16 in |
| --- | --- | ---: |
| width, corner to corner | `unit_width − 2·(corner_radius + panel_offset)` | 75.000 |
| exposed span between corners | `width − 2·panel_overlap` | 65.475 |
| entry into each corner | `panel_overlap` | 4.7625 |
| inner face, from the airframe axis | `unit_width/2 − panel_thickness − panel_tolerance` | 45.1375 |
| outer face | the mold line, `unit_width/2` | 50.000 |
| length along the bay | `unit_length · FX` | 100.000 |

**The width is confirmed by a clearance, not by a face.** Take the panel to be 75.000 wide and
its edge lands 0.1000 short of the corner's end stop — `panel_tolerance` exactly, and no other
width fits the rebate the corner was cut with. The exposed span is confirmed a second time, and
independently, by the bulkhead's outer face measuring 392.8500 mm² (joint 5).

### 6.2 `panel_offset`, which is the densest thing in the design

`panel_offset` is how far the panel's inboard edge stands off the longeron axis, and it is not
free: two requirements bear on it and the binding one wins, which is what SR-9 obliges
the drawing to say.

**R1 — the panel must not run into the greeble.** The greeble's outer perimeter is a circle about
the longeron axis of radius `longeron_radius + longeron_tolerance + greeble_thickness +
greeble_nub_thickness`, and `greeble_margin_extrusions` of clearance is kept outside it. The
panel's inboard corner is the point (`offset`, `seat_y`), so it is outside the circle exactly when
`offset² + seat_y² ≥ radius²`.

**R2 — the corner has to be able to snap on (SR-8).** The greeble's mouth faces the 45° diagonal
and the corner presses onto the longeron sideways, so the corner's mating plane at
`panel_overlap + panel_offset` must clear the greeble's extremity *measured along that diagonal*,
plus the margin, plus `greeble_snap_clearance_per_u · U` of room to move.

The margin is taken out of the radius before the projection and added back after. That is not an
accident of the arithmetic and the constants file already flags the three appearances as one
quantity: the margin is a clearance **normal to the plane**, and projecting it onto the diagonal
would shrink it by √2, so it would no longer be the clearance.

The result is rounded **up** to a whole `panel_offset_quantum_mm`. Rounding down would eat the
clearance the requirements just established.

**Evidence, and it is a stronger check than the formula.** `check_derivation.py` also tests R1 and
R2 directly against the offset the sweep produced — never evaluating the formula, so it cannot
fail in sympathy with it. On all **528 non-cowling variants** the built offset satisfies both
requirements, and on **all 528 one quantum less would violate at least one**. The quantized offset
is never slack. **R2 governs on 468 of them and R1 on 60**, so the requirement that usually
decides the panel's width is the assembly motion, not the static clearance.

### 6.3 What happens when a feature is absent

SR-7 says a structural zero is the absence of a joint. Deriving where the faces go makes that
concrete, and it turns out features vanish in **two different ways**, which is worth stating
because the first form of the geometry check had them behaving alike and the parts said otherwise:

- **By merging.** On a 0 mm panel variant the corner's panel seat has no depth, so it collapses
  onto the mold line, and the end stop collapses onto the bulkhead seating flat. A face is still
  found at each derived position — it belongs to the other feature. The corner has 50 faces
  instead of 54.
- **By closing up.** On the 24 corner variants where joint 3's panel branch governs, the seating
  flat's height goes to zero and the face is simply not there. Nothing takes its place.

The distinction matters for a checker and for a drawing both: "absent" cannot be tested as "no
face at this coordinate", and a dimension cannot be attached to a face that has merged into
another feature. The bulkhead's outer face is a third case again — it does *not* vanish with the
panel, it moves out onto the mold line, because its extent is the exposed span and not the pocket.

### 6.4 The enclosed spans

*Traces to OR-8 directly, which is the only place in this document that happens.* Nothing in the
model mates with the bulkhead's interior aperture, so no joint reaches it — but a battery, a loom,
a servo and a hand with a nut driver all depend on it. Its derivation is SR-3 applied twice
inward, and the last term differs by part because the ring's inner boundary is set by the flange
on a frame bulkhead and by the web on a boom bulkhead:

| Part | Enclosed span | At 1U, 3/16 in |
| --- | --- | ---: |
| frame bulkhead | `unit_width − 2·(panel_thickness + panel_tolerance) − 2·flange_thickness` | 87.875 |
| boom bulkhead | `unit_width − 2·(panel_thickness + panel_tolerance) − 2·web_width` | 78.275 |

On a boom bulkhead the span and the clear opening are two different numbers — 78.275 both ways
against 78.275 × 66.402 — because the collet intrudes from one side.

---

## 7. What is neither: implementation artifacts

A modeling kernel needs quantities the design does not have. A cutting solid has to overshoot the
material or the boolean leaves a zero-thickness sliver; a masking half-plane has to reach past the
profile; a union of stacked sections has to overlap or CGAL may not fuse them. **None of these is
a requirement at any level, and none of them belongs in a register, a drawing, or a trace.**

> **The rule: an implementation artifact must not be sized from the dimension of the feature it
> operates on.** Sized that way it is indistinguishable from a design quantity — it scales like
> one, it reads like one, and sooner or later somebody records it as one.

### The instance that prompted this section

The corner's panel rebate is cut by a rectangle whose rows are, in `freecad/corner_tree.py` and
identically in `scad/fuselage_corner_geometry.scad`:

```
slot_x = -panel_overlap * 2 - panel_offset + panel_tolerance
slot_w = panel_overlap * 2
slot_d = panel_thickness * 2 + panel_tolerance * 2
```

The feature those produce is a rebate `panel_thickness + panel_tolerance` deep and
`panel_overlap + panel_tolerance` long — measured, in [joint 4](#joint-4--panel--corner). Every
one of the doublings is overshoot: the rectangle is drawn twice the pocket tall so it clears the
mold line, and twice the overlap long so it opens through the end of the arm. **The overshoot is
the feature's own dimension, doubled**, which is why it scaled convincingly across 264 variants
and why the interface register carried `2·panel_thickness + 2·panel_tolerance` as the joint's
depth until 2026-08-28.

**It is also unnecessary in FreeCAD.** OCCT does not need CGAL's slop, and this project already
has the right idiom two rows further up the same table — `mask_reach` and `through_cut`, each a
"big enough" distance stated once, named, and commented with why it is named rather than inlined.
The panel slot should use it. That is
[IP-FC-88](../implementation/freecad_migration.md), filed rather than done here because it changes
a live generator and wants a before/after measurement.

### The others, and why they are already handled correctly

| Artifact | What it is | How it stays visible |
| --- | --- | --- |
| `mask_reach = 2·corner_radius` | how far a masking half-plane must extend to cover the profile | named, with a comment recording that it had to be renamed from `far` once it shared a sheet with the bulkhead's different "big enough" distance |
| `through_cut = 3·bulkhead_thickness` | length for a centered cutting solid that must pass entirely through | named, with a docstring saying exactly that |
| `eps = 0.01` section overlap | the corner's three z-sections overlap so CGAL fuses them | measured under IP-FC-55: forcing all three flush moves the assembled corner by −0.0006 mm³ and changes no face. **OCCT does not need it; it stays for the OpenSCAD path**, and the measurement is why that is a decision rather than an assumption |
| masking polygon trailing vertices | points that only have to sit off the part | `corner_tree.py` says so in as many words |

Three of those four are artifacts done right: named, commented, and sized from something other
than the feature they act on. The panel slot is the one that is not.

---

## 8. What could not be derived

Everything here is a place where the implementation is correct, self-consistent, and rests on
something nobody wrote down.

1. **Four of the seven clearances carry no argument.** `boom_tolerance` 0.2 is four times the
   longeron's 0.05 and its own entry says the number has never been justified in writing.
   `longeron_tolerance` 0.05, `greeble_tolerance` 0.05 and `panel_tolerance` 0.1 are recorded as
   values with a description of where they apply, not with a reason for their size.
   [OQ-DES-DV3](#open-questions).

2. **`bulkhead_thickness` and `bulkhead_bolt_diameter` are tabulated with no rule**, so OR-1 does
   not currently reach them. Eight rows each, and neither follows `n·U`: 4·U reproduces the
   thickness for U ≥ 1.5 and misses all three of the smaller sizes. Several derived quantities
   depend on the thickness — the panel seat's area, the greeble nub's height — so the table is
   load-bearing. [OQ-DES-DV2](#open-questions).

3. **`longeron_chamfer` is not a chamfer.** It is set to `extrusion_width` and appears in exactly
   one place: the bore branch of `flat_offset`. Nothing chamfers by it. What it actually is,
   derived in joint 3, is a *standoff* — the material left between the bore and the corner's
   inboard boundary where that boundary crosses the axis. `corner.md` already marks the "smallest
   chamfer worth printing" reading as an inference; the name is the part that misleads.

4. **`panel_offset`'s upper clamp is unexercised and is not a bound.** The offset is clamped to
   `√2 · corner_radius` and then rounded up, so the rounding can carry the result back over the
   clamp. It also never binds: measured across all **528 non-cowling variants, zero reach it**.
   [OQ-DES-DV1](#open-questions).

5. **SR-4, SR-5 and SR-6 are derived — they trace to no requirement at all.** SR-6 gained its
   rationale on 2026-08-29 and SR-4 always had one; **SR-5 has neither a parent nor a recorded
   reason** and is now the most exposed statement in the set. The wiki may resolve all three at
   once: the OML standard excludes dimensional tolerances as application-dependent, which would
   make them derived by design rather than by omission. [OQ-DES-DV5](#open-questions).

6. **`panel_overlap = max(panel_thickness, 4 mm)` ties a bond length to a stock thickness.** The
   floor is recorded as a bond-area minimum, deliberately unscaled. Why the lap should otherwise
   be exactly one panel thickness is not.

7. **`greeble_opening_angle` and the boom key's dimensions are declared choices, not gaps.** 35°
   is tuned by experiment and the file says not to replace it with a formula; the key's width and
   height are recorded as independent dimensions that happen to agree. Both are in
   [section 3](#3-what-is-chosen) and neither is a defect.

8. **Four of the floors under SR-11 have a reason on record and three do not.** The greeble
   wall floors because a one-extrusion wall has no interior; the panel overlap floors on an
   absolute bond area. Why the bolt boss, the bulkhead flange wall and the boom key hold at
   their 1U size is stated as a formula and justified nowhere — and unlike the rest of the
   airframe, which shrinks freely below 1U, these are the places somebody decided it must
   not.

---

## 9. How this is checked

Three things are checked and one is not.

### The trace — `tools/check_derivation.py`, on every run

`ORIGINATING` and `DERIVED` are tables in the source, and every relation names a DR id rather than
describing its reason in prose. A DR that traces to no OR, a DR that traces to an OR that does not
exist, or a relation naming a DR that does not exist is a **failure**, not a wording problem — it
means a design decision is justified by something that is not a requirement.

```
traceability -- 11 L1 requirements: 8 decomposed from 9 L0, 3 DERIVED (SR-4, SR-5, SR-6),
                each carrying its own justification
    note: SR-10 reaches no parameter relation; it is checked elsewhere or not at all
    note: SR-9 reaches no parameter relation; it is checked elsewhere or not at all
```

The note is not a failure and is printed deliberately: a requirement nothing enforces should not
be able to sit in the table looking enforced.

### The parameters — `tools/check_derivation.py`, every variant

Runs in the project virtualenv, no FreeCAD, seconds. Every numeric field a variant carries is
either a **given** — listed with where it was chosen — or a **derived** field produced by a
relation from the givens and from values the checker has already derived. It never reads the
sweep's own answer. Coverage is enforced: a field that is neither fails, so a parameter added to
`fuselage_variants.py` cannot silently leave the derivation behind.

```
corner        -- 264 variants, every relation derives the built value
bulkhead      -- 148 variants, every relation derives the built value
boom_bulkhead -- 132 variants, every relation derives the built value
nose          --   8 variants, every relation derives the built value
tail          --   8 variants, every relation derives the built value
ok -- every parameter is a stated choice or follows from one
```

It also tests [section 6.2](#62-panel_offset-which-is-the-densest-thing-in-the-design)'s two
requirements against the built offset directly, which is the one place the derivation would
otherwise be a restatement of the implementation's own arithmetic. `--report` prints the whole
requirement tree.

### The faces — `freecad/check_derived_geometry.py`, by sample

Runs under `freecadcmd`, builds the part, about a second each. Each entry states a face the design
*requires*: its normal, position, area, whether it exists at all on this variant, and the DR it
serves. Then the solid is asked. Absence is a prediction in its own right, handled as
[section 6.3](#63-what-happens-when-a-feature-is-absent) describes.

```
freecadcmd check_derived_geometry.py --pass variant.params.json
freecadcmd check_derived_geometry.py --pass variant.params.json kind=bulkhead
```

Run 2026-08-28 on four variants chosen to reach the topology cases rather than to sample evenly —
1U/3-16 in, 1U/0 mm (features merge), 0.5U/1 mm (the seating flat closes up), 4U/1-4 in — for both
the corner and the bulkhead. All pass.

**What it does not cover.** The diagonal seating face, which is not axis-normal; the bore and
collet, which are cylindrical; the cowl and nose, which are not ported to FreeCAD yet (IP-FC-12).
Those are derived above and checked only through their parameters.

### What is checked by nothing — section 2

**No tool can validate an originating requirement**, and a checker that appeared to would be worse
than none. Section 2 is accepted by review or it is not, and until it is, a green run means only
that the implementation follows from requirements nobody has agreed to. That is still worth having
— it is the difference between a design that is internally consistent and one that is merely built
— but it is not the same claim, and this document does not let the two be read as one.

Neither does anything establish that a *clearance value* is right. A derivation shows the geometry
follows from the numbers chosen; whether 0.05 is the right gap for a printed bore is a question for
a printed part, and [section 8](#8-what-could-not-be-derived) says which of them nothing has
answered.

---

## 10. Where this document lives

[OQ-ARCH-7](../architecture/freecad_migration.md#open-questions) named this document's
prerequisite on 2026-08-07 and assigned it to `doc/architecture/overview.md`, which does not
exist. It is filed here instead, in `doc/design/`, beside `corner.md`, `bulkhead.md`, `cowl.md`
and `dimension_scheme.md`. The reason is what the other two directories hold: `doc/architecture/`
holds the migration's own structure and `doc/implementation/` holds the work items, and this is
neither — it is design intent, and it is read together with the design documents it derives.

That is a filing decision and it is cheap to reverse; the deps in IP-FC-87 record it.

---

## Open questions

| ID | Question | Blocking? |
| --- | --- | --- |
| OQ-DES-DV1 | `panel_offset`'s `√2·corner_radius` clamp never binds on any variant, has no recorded reason, and is applied before the rounding, so it does not bound the result | Not blocking — no variant reaches it, which is also why nothing would notice if it were wrong |
| OQ-DES-DV2 | `bulkhead_thickness` and `bulkhead_bolt_diameter` are tabulated per size step with no rule relating them to U, and derived geometry depends on the thickness | Not blocking — the table builds correct parts; what is missing is whether it is the design or a stand-in for one |
| OQ-DES-DV3 | Four of the seven clearances, and `longeron_chamfer`, carry no recorded argument. May a plausible reconstruction be adopted as intent, or must they stay marked as choices? | Not blocking, and it decides how much of this document can ever stop being marked *inferred* |
| OQ-DES-DV4 | Several statements could be classed as originating or as derived, and where one lands decides what may be changed without going back to review | **Blocking acceptance of section 2** — the list cannot be ratified while its membership rule is undecided |
| OQ-DES-DV5 | Section 2 was written without reading the requirements already in the project wiki, which carry a MAUS‑FOS / MAUS‑FD1 refinement structure this document does not have | **Blocking acceptance of section 2, and it comes before OQ-DES-DV4** — there is no point deciding a membership rule for a list that has to be rebuilt against an existing source |

### OQ-DES-DV1 — `panel_offset`'s upper clamp never binds, and is not a bound

`panel_offset` is the distance from the longeron axis to the panel's inboard edge, derived in
[section 6.2](#62-panel_offset-which-is-the-densest-thing-in-the-design). After the two
requirements are satisfied the value passes through two more steps:

```
offset = min(offset, sqrt(2) * corner_radius)          # the clamp
offset = quantum * ceil(offset / quantum)              # the rounding, quantum = 0.25 mm
```

Three things are true of that clamp and none of them is recorded.

**It never binds.** Measured 2026-08-28 across all 528 non-cowling variants of the three built
sweeps: the requirement-driven value exceeds `√2 · corner_radius` on **zero** of them. The margin
is not close either — at 1U the requirements produce 2.5 against a clamp at 14.14.

**It is applied before the rounding, so it is not a bound on the result.** If it ever did bind, the
`ceil` that follows could carry the value back over it. A clamp the next line can undo is not doing
what a clamp reads as doing.

**Its purpose is not written down anywhere.** `√2 · corner_radius` is the distance from the
corner's arc center to the corner of a square of side `2·corner_radius`, which makes the inferred
reading "do not let the arm reach past the diagonal that mirrors the section" — but that is a
reconstruction, and if it is the intent then the quantity it should bound is `flat_x`, not
`panel_offset`, since the arm reaches `panel_overlap + panel_offset`.

**Why it is worth asking rather than leaving.** An unexercised guard is a guard nobody has tested.
If a future panel stock or a smaller `U` ever reaches it, what happens is a clamp that the rounding
may partly undo, protecting against something nobody has stated.

**Alternatives**

1. **Remove it.** The two requirements and the rounding fully determine the offset on every variant
   the sweep produces. *Benefit:* the derivation and the code agree exactly, with no unexercised
   branch and no line whose reason is unknown. *Drawback:* if the clamp is protecting against a
   case outside the current axes — a very small `U`, a much thicker panel — removing it removes
   that protection silently. *Needs:* a statement that no such case is intended, or the axes'
   bounds treated as the design's bounds.
2. **Keep it, move it after the rounding, and record what it protects.** *Benefit:* it becomes an
   actual bound, and the reason is on record. *Drawback:* it changes behavior on any variant that
   would reach it, which is none today, so the change cannot be validated by the sweep. *Needs:*
   the reason — specifically, what goes wrong when the arm is longer than this.
3. **Keep it as is and mark it a guard.** Leave the code alone, and record in this document and in
   the source that it is an unexercised safety limit with no derivation. *Benefit:* nothing moves;
   the ambiguity stops being invisible. *Drawback:* the derivation keeps a permanent *inferred*
   entry, and the ordering defect stays.
4. **Turn it into a refusal.** Instead of clamping, fail the variant when the requirements demand
   an offset this large, the way `corner_validity_check` already refuses combinations. *Benefit:* a
   case nobody has designed for produces a refusal rather than a quietly modified part.
   *Drawback:* one more validity rule, and it fires on nothing today. *Needs:* agreement that
   reaching this bound is an error rather than a case to handle.

**Recommendation: alternative 4, with alternative 1 as the fallback if the bound turns out to be
arbitrary.** A clamp is the wrong shape for this: silently shortening the panel's reach changes the
panel's width, which is a dimension on a drawing that somebody is going to build a panel to, and it
does it at exactly the moment the design has left the range anyone reasoned about. A refusal says
what a clamp is trying to say and cannot be undone by the next line. If the answer to "what goes
wrong past this point" is that nothing does and the expression was a defensive habit, alternative 1
is right and the line should go.

### OQ-DES-DV2 — Two of the airframe's dimensions are tables, not rules

`bulkhead_thickness` and `bulkhead_bolt_diameter` are columns in
[`bulkhead_size_variants.csv`](../../src/Fuselage/variant_param/bulkhead_size_variants.csv), one
value per size step:

| U | 0.5 | 0.75 | 1 | 1.5 | 2 | 2.5 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `bulkhead_thickness` (mm) | 4 | 5 | 6 | 6 | 8 | 10 | 12 | 16 |
| `bulkhead_bolt_diameter` (mm) | 3 | 3 | 4 | 4 | 5 | 6 | 6 | 8 |

SR-1, SR-2 and SR-11 cover every other length in the airframe: proportional to `U`, or a count
of extrusions or layers, with a floor where the function does not scale. These two are none of
the three, so **OR-1 does not currently reach them** — the
parametric standard produces the family for every dimension except these. `4·U` reproduces the
thickness for U ≥ 1.5 and misses 0.5, 0.75 and 1 (giving 2, 3 and 4 against the table's 4, 5 and 6),
so the small sizes are thicker than proportion. The bolt series is a standard fastener progression
and clearly a selection rather than an arithmetic result, but the *rule* for selecting it — a
fraction of `bolt_offset`, a load, a wrench size — is not stated.

**This is not cosmetic, because things are derived from the thickness.** The bulkhead's outer face
area is the panel's exposed span times `bulkhead_thickness` (joint 5), the greeble nub's height is
`bulkhead_thickness/3`, and the corner's three z-sections are cut at multiples of it. A number that
governs geometry and comes from a table with no rule cannot be extrapolated: there is no way to add
a `U = 6` row except by choosing again.

**What is not in question.** That the table's values are right. They are what has been printed and
flown, which is the same standing `corner_tolerance = 0` has.

**Alternatives**

1. **Declare the table the design.** State in this document and in the CSV that airframe size is a
   discrete series of eight, that thickness and fastener size are selected per step by engineering
   judgment, and that adding a step means making those choices. *Benefit:* honest, costs nothing,
   and matches how `greeble_opening_angle` is already treated. *Drawback:* `U` stops being a
   continuous scale factor in the documentation even though the code accepts any value, and every
   other dimension still scales continuously. *Needs:* nothing.
2. **Derive the thickness and keep the fastener tabulated.** Find the rule the eight values
   approximate — `max(4·U, 4)` fits six of eight — and adopt it, retabulating the sizes it changes.
   *Benefit:* one fewer table, and a new size step becomes derivable. *Drawback:* it changes flown
   geometry at the small sizes to fit a formula, which is the wrong direction of authority.
   *Needs:* whether any of the eight values may move.
3. **Derive the thickness for new sizes only.** Keep the eight rows as they are, and state a rule
   for extrapolating beyond them. *Benefit:* nothing flown changes and the series is extensible.
   *Drawback:* two regimes; the rule is unvalidated exactly where it is used. *Needs:* the rule.
4. **Derive the fastener from the bolt boss instead.** `bolt_offset = 8·U` and
   `bolt_thickness = max(3·U, 3)` are derived, so the boss's size is known; state the bolt as the
   largest standard size the boss carries. *Benefit:* removes one table column. *Drawback:*
   fastener selection is a load question, not a packaging one, and this would make packaging decide
   it. *Needs:* whether the current column is in fact packaging-limited.

**Recommendation: alternative 1.** The values are flown and no rule that fits them is on record, so
deriving one now means fitting a curve to eight points and calling the fit intent — the precise
move [OQ-DES-D9](dimension_scheme.md#open-questions) identified as the source of the problem this
document exists to fix. Declaring the series discrete costs one paragraph and makes the eight steps
what they actually are: eight designs that share a parameterization. If the sweep later needs a
ninth, alternative 3 becomes the question worth asking, with the eight as evidence.

### OQ-DES-DV3 — May an inferred reason be adopted as intent?

Four of the seven clearances in `design_constants.json` carry a description of *where* they apply
and no argument for *how large they are*: `longeron_tolerance` 0.05, `greeble_tolerance` 0.05,
`panel_tolerance` 0.1, `boom_tolerance` 0.2 — the last of which says so explicitly: *"Four times
the longeron's 0.05 and nothing on record says why."* The other three carry their governing
expression and, for `nose_flange_tolerance`, a full argument resolved under OQ-DES-CW10.
`longeron_chamfer = extrusion_width` is the same kind of gap in a shape quantity rather than a
clearance.

For each of these a plausible reconstruction exists and is easy to write. 0.05 is a normal sliding
fit at these sizes; 0.1 is about one FDM layer of dimensional spread; 0.2 for a deeper bore in a
larger tube is proportionate; one extrusion is the thinnest wall that prints. Every one of those
sentences would read as design intent, and **not one of them is evidence.**

**There is now a measured case.** SR-6 — which side of the corner/bulkhead interface carries the
clearance — had two reconstructions in this document, each argued from the geometry and each
reading convincingly. The actual rationale was stated on 2026-08-29 and is **neither of them**:
the corner is less likely to have components integrating to it, so the bulkhead is the part held
consistent. Two plausible inferences, both wrong, on a question where the geometry was fully
known. That is the strongest argument in this document for alternative 1, and it is evidence
rather than caution.

**The question is a rule, not a value.** This document marks such reconstructions *inferred* and
refuses them authority. That is safe and it has a cost: two of the eleven level-1 requirements are
marked inferred, [section 8](#8-what-could-not-be-derived) carries seven entries, and a reader
looking for the reason a fit is 0.05 finds a note saying nobody knows. If that marking is
permanent, the derivation is partial by construction. If it can be lifted, there has to be a rule
for lifting it, or the marking means nothing.

**Alternatives**

1. **Keep them permanently marked.** An inferred reason is never promoted; it can only be replaced
   by a recorded one. *Benefit:* the ledger stays trustworthy — anything unmarked has a real
   source. *Drawback:* the gaps are permanent unless somebody with the original intent records it,
   and for a project reconstructed from its own implementation that may be nobody.
2. **Promote on evidence from a printed part.** An inferred fit becomes recorded when a printed and
   assembled part demonstrates it — a fit that grips, a joint that slides. *Benefit:* the evidence
   is the right kind for a clearance, which is a manufacturing question. *Drawback:* it needs
   prints and a way to record their results, which the project has no place for today. *Needs:*
   somewhere to put a test result.
3. **Promote on a stated engineering argument, marked as reasoning rather than as history.**
   Introduce a third label between *recorded* and *inferred*: a reason derived from first
   principles and dated, distinguishable from an original decision but carrying authority.
   *Benefit:* the document becomes complete and stays honest about which reasons are
   reconstructions. *Drawback:* a third label is one more thing to maintain, and the difference
   between "derived from first principles" and "sounds right" is not always visible. *Needs:* what
   makes an argument admissible.
4. **Retire the question by re-choosing.** Treat the four unexplained clearances as open design
   decisions, decide each one deliberately now with the argument written down, and accept that the
   new value may equal the old. *Benefit:* the gap closes with real intent rather than
   reconstruction. *Drawback:* re-deciding a flown value risks changing it for a reason worse than
   the reason it was chosen for, which nobody knows.

**Recommendation: alternative 3, with the label reserved for clearances and shape constants and
never used for a value read off the geometry.** Alternative 1 is the safe answer and it makes this
document permanently unable to say why any fit is what it is, which is most of what a reader wants
from it. Alternative 2 is the right kind of evidence and the project cannot act on it today. The
distinction that matters is not between recorded and reasoned — it is between a reason and a
*measurement of the part dressed as a reason*, which is what OQ-DES-D9 caught. An argument from
print physics for why 0.05 is a sliding fit is not that; an expression recovered by measuring a
face is. A third label can hold that line as long as it is never applied to the second kind.

### OQ-DES-DV4 — What makes a requirement originating rather than derived?

[Section 2](#2-originating-requirements--proposed) proposes nine originating requirements and
[section 4](#4-level-1-system-requirements) eleven level-1 ones. The split decides something concrete: **an
originating requirement cannot be changed without going back to review, and a derived one can be
re-decided on engineering grounds as long as its trace still closes.** Several statements could sit
on either side, and nothing on record says which.

**The cases, and why each is genuinely ambiguous:**

- **OR-2's number four.** The section is a rounded square with four corners. Is "four corners"
  originating, or does it follow from something above it? **The wiki asks the same question and
  has not answered it either** — its FAQ page carries the entry *"Why only square fuselage cross
  sections?"* with the body `TODO`. So this is a genuine gap in the requirements rather than an
  artifact of this reconstruction.
- **OR-3's continuity clause.** That three parts land on the mold line is recorded. That the mold
  line is a shared datum *no joint may trade against* is this document's generalization, and four
  level-1 requirements rest on it. **The parent this question said was missing turns out to
  exist, and it is not aerodynamic:** the wiki's *Modularity4* — "interchange or re-ordering of
  fuselage sections does not affect fuselage structure" — together with *Modularity8*, is a
  stronger parent for an untradeable shared datum than aerodynamics was, and the wiki says
  aerodynamic optimization is secondary. Folded into [OQ-DES-DV5](#open-questions).
- **SR-6, which side carries the clearance.** Recorded as fact, unexplained as a choice. If the
  reason is that an assembler adjusts the corner, that is an assembly requirement and belongs in
  section 2. If it is an arbitrary allocation, it is derived and may be re-decided freely. The two
  readings have opposite consequences for whether anyone may move it.
- **OR-9's scope.** It originates the drawing set, not the airframe. It sits in the same list as
  eight requirements about geometry, and **SR-7 currently traces to it** — so a rule about
  where a clearance physically sits is partly justified by who reads the drawing.

**Alternatives**

1. **Accept section 2 as it stands and treat the boundary as settled by acceptance.** Whatever is
   in the list is originating because it was accepted as originating. *Benefit:* it unblocks the
   whole structure immediately, and the list is short enough to review in one sitting. *Drawback:*
   it ratifies a generalization (OR-3's continuity) and leaves two requirements with no parent
   because the parents were never written. *Needs:* one review pass.
2. **Adopt a membership rule and re-sort against it.** State the test — *a requirement is
   originating when it comes from outside the design, and changing it changes what the airframe is
   for* — and move anything that fails it down a level, adding parents where they are missing.
   *Benefit:* the boundary stops being a judgment call, and the missing aerodynamic requirements
   get written rather than assumed. *Drawback:* it turns a review into a design exercise, and it
   may surface that the aerodynamic requirements do not exist in a form anybody can state.
   *Needs:* the rule, and someone to write the missing parents.
3. **Split into two trees: the airframe and the drawing set.** OR-1 through OR-8 head one, OR-9
   heads another, and `dimension_scheme.md` becomes the decomposition of the second. *Benefit:*
   matches what the two documents already are, and stops a drawing requirement appearing as a
   parent of geometry rules. *Drawback:* two trees means two acceptance passes, and the joints
   genuinely serve both. *Needs:* deciding whether a level-1 requirement may trace into two trees.
4. **Defer: mark section 2 provisional indefinitely and rely on the derived level.** *Benefit:* the
   checkers work regardless; the level-1 requirements are the ones with teeth. *Drawback:* the
   document never becomes the axiomatic source it was written to be, and the honest reading of a
   green run stays "consistent with requirements nobody has agreed to".

**Recommendation: alternative 3 followed by alternative 2, and specifically not alternative 1.**
Splitting first is cheap and it fixes a defect already visible in the trace: SR-7 traces to OR-9,
so a rule about whether a clearance physically exists is justified partly by who reads the
drawing. That is the wrong shape even if the rule is right. With the trees separated, the
membership rule in alternative 2 has something clean to operate on, and the two missing parents —
the section shape and the aerodynamic surface — become explicit gaps to write rather than
generalizations to accept. Alternative 1 is the tempting one, and it would ratify exactly the kind
of reading-turned-into-authority that OQ-DES-D9 was filed about.

### OQ-DES-DV5 — Section 2 duplicates a requirements set that already exists

[Section 2](#2-originating-requirements--proposed-and-superseded-pending-reconciliation)
proposes nine originating requirements, each read off `design_constants.json`, the design
documents and the architecture document. **It was written on 2026-08-28 without reading the
project wiki, which already carries a requirements set.** Found 2026-08-29.

The wiki has two pages that matter. *MAUS‑FOS Fuselage Outer Mold Line (OML) Standard* carries a
Mermaid `requirementDiagram`; *Modular Airframe Unitized System (MAUS) Architecture* carries the
objectives. Together they state something this document does not have at all: **a two-standard
refinement chain.**

- **MAUS‑FOS**, the OML standard, *refines* **Modularity** — eight functional sub-requirements
  covering a minimally constraining physical interface, interchange and re-ordering of fuselage
  sections, interchange not affecting structure, flat exterior panels for system integration, a
  simple exterior shape for the wing interface, a constant cross section allowing longitudinal
  relocation of external components, and standardized dimensions for commonality between
  implementations.
- **MAUS‑FD1**, this printable fuselage design system, *refines* MAUS‑FOS **and** **Printability**
  — FDM printable, layer orientation aligned to structural performance needs, printable without
  support material — **and** **Assembly** — components are self-aligning during assembly.
- The fuselage design *satisfies* MAUS‑FD1.

And the objectives, in priority order: facilitate iteration of aircraft sizing and configuration;
facilitate system integration; maximize modularity; decouple component designs. With the explicit
qualifier that **optimization of aerodynamic efficiency is a secondary concern.**

**Where the reconstruction and the wiki differ, and it is not uniform:**

| | Finding |
| --- | --- |
| **Agrees** | OR-1 with Modularity8 and the sizing objective; OR-2 with Modularity2, 3 and 4; OR-4 with Modularity5; OR-5 with Printability1; OR-7 with Assembly1, whose *"self-aligning"* is the better wording; OR-8 with the system-integration objective |
| **Missing here** | **Printability2** (layer orientation aligned to structural performance needs) and **Printability3** (printable without support material) have no counterpart in section 2 — and Printability3 is the parent of joint 9's `overhang_angle_from_bed`, which this document traced to SR-7 instead. **Modularity7** (constant cross section for longitudinal relocation) has none either, and it is the natural parent for FX being the only length axis |
| **Backwards here** | **OR-3** justifies the mold line as an aerodynamic surface. Every reason the wiki gives for the OML is a modularity reason, and it says aerodynamic optimization is secondary |
| **Out of scope there** | *"dimensional tolerances are considered application dependent and therefore are not included in the standard"* — so clearances are an FD1 concern, not a FOS one. OR-6 treats them as originating |
| **Open in both** | *"Why only square fuselage cross sections?"* is a wiki FAQ entry whose body is `TODO`, which is [OQ-DES-DV4](#open-questions)'s first case |

**Why this is worth deciding rather than just fixing.** The obvious response — throw section 2
away and transcribe the wiki — is not obviously right. The wiki's requirements are stated at the
standard's level and several are section headings with no body yet; this document's are stated at
the level the geometry actually needs, and each one earned its place by having something below it
that had to trace somewhere. The failure was writing them without checking, not writing them.

**What is not in question.** That the wiki is authoritative where the two disagree, and that
OR-3's aerodynamic justification is wrong.

**Alternatives**

1. **Replace section 2 with the wiki's requirements, cited not copied.** Section 2 becomes a
   pointer: MAUS‑FOS's Modularity set and MAUS‑FD1's Printability and Assembly sets are the L0,
   and every SR traces to a wiki id. *Benefit:* one authoritative source, and this document stops
   competing with it. *Drawback:* several wiki requirements are headings without bodies, so some
   traces would point at a title; and the FOS/FD1 split has to be carried here, since an SR about
   a clearance cannot trace to FOS at all. *Needs:* stable ids for the wiki's requirements —
   the diagram names them `Modularity1`…`Assembly1`, which is workable.
2. **Adopt the wiki's structure and feed the reconstruction back into it.** Same as 1, plus:
   where section 2 has something the wiki lacks — the enclosed-volume requirement, the integration
   rationale behind SR-6 — propose it as a wiki edit rather than keeping it here. *Benefit:* the
   requirements set gets better, and the gaps this exercise found (three missing, one inverted)
   are fixed at the source. *Drawback:* it is a change to the standard, which is a heavier
   decision than a change to a design document, and MAUS‑FOS is meant to outlive this
   implementation. *Needs:* whether FOS is open to amendment from FD1's experience.
3. **Keep both, and make section 2 explicitly the FD1-level restatement.** The wiki holds
   FOS-level requirements; section 2 holds the FD1-level ones this implementation needs, each
   citing its FOS parent where one exists. *Benefit:* matches the refinement chain the wiki
   already draws, and gives the three derived requirements a home — FOS excludes tolerances by
   design, so FD1 is exactly where they belong. *Drawback:* two lists to keep in step, which is
   what produced this problem once already. *Needs:* a rule for which list a new requirement
   goes in.
4. **Correct section 2 in place and cross-reference.** Fix OR-3, add the three missing
   requirements, note the FOS/FD1 split in prose, and leave the structure alone. *Benefit:*
   cheapest, and the checkers keep working untouched. *Drawback:* it keeps a second requirements
   set alive without saying which wins, which is the situation that caused the error.

**Recommendation: alternative 3, with alternative 2's feedback for the gaps it found.** The
wiki's own diagram says MAUS‑FD1 refines MAUS‑FOS, so a second list at FD1 level is not a
duplicate — it is the level the diagram already predicts, and it is where the three derived
requirements belong, since FOS excludes dimensional tolerances on purpose. That reading turns
this document's biggest weakness into a straightforward answer: SR-4, SR-5 and SR-6 are derived
because the standard deliberately declines to parent them. What alternative 3 does not excuse is
the four things the reconstruction got wrong or missed; those should go back to the wiki under
alternative 2, because Printability3 in particular is a real requirement that this design
already satisfies and no document here records.


---

## See also

- [dimension_scheme.md](dimension_scheme.md) — section 2's register, which this derives rather than
  restates; OQ-DES-D7, D8 and D9
- [corner.md](corner.md) — the cross-section, joint 3's `max`, OQ-DES-C5
- [bulkhead.md](bulkhead.md) — the greeble, the flange, OQ-DES-B13 and B14
- [corner_bulkhead_joint.md](corner_bulkhead_joint.md) — joint 3 drawn from the built solids
- [cowl.md](cowl.md) — joints 7 and 8, OQ-DES-CW9 through CW11
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-87, the work item;
  IP-FC-88, the panel slot's overshoot
- [freecad_migration.md](../architecture/freecad_migration.md) — OQ-ARCH-7, which asked for this
