# FreeCAD workflows — what to expect as a user

**Status.** Written 2026-08-08. This describes the workflows the FreeCAD migration is being
built to deliver, and it is deliberately written before all of them exist — the point is
that the design was chosen to serve them. Each section states what works today. The
decisions behind it are in
[doc/architecture/freecad_migration.md](../architecture/freecad_migration.md); the
measurements are in
[doc/implementation/freecad_migration.md](../implementation/freecad_migration.md).

---

## The shape of the system

The generator produces parts from a **parameter set**. It does not produce one corner; it
produces the corner at every size and configuration the parameter tables describe — 576
variants at the time of writing.

Two things follow from that, and most of this guide is their consequences:

1. **Generated files are outputs, not documents you own.** The sweep rewrites them. Anything
   you put in a generated file is lost the next time it runs.
2. **Geometry is driven by parameters, not by dragging.** A dimension is an expression over
   a parameter table. Typing a number over one does not do what it appears to do — see
   [Rules that will bite you](#rules-that-will-bite-you).

So the workflows below are all built around *not* editing generated files in place.

---

## What the generator gives you

| You want | Output | Works today |
| --- | --- | --- |
| Printable meshes | `*.stl`, millimetres | **Yes** — this is the current system |
| Native editable models | `*.FCStd` | Planned (IP-FC-14) |
| Neutral solid models | `*.step` | Planned (IP-FC-15) |
| Assemblies with joints | `*.FCStd` assembly | Planned (IP-FC-19) |
| Dimensioned drawings | TechDraw pages | Planned (IP-FC-21, IP-FC-22) |
| Mass properties, FEM | analysis models | Planned (IP-FC-20, IP-FC-23, IP-FC-24) |
| Blender scenes, exploded views | `*.blend` | Partly — `blender/splode.blend` exists |

Exported meshes and solids are **millimetres**, whatever the internal units.

---

## Workflow A — a derived part

**Use this when you want a modified version of a generated part.** It is the only workflow
that lets you change the original's parameters *and* add your own geometry.

Examples this is for: opening up a tolerance, changing a bolt diameter, adding a bracket to
attach a component, cutting a clearance notch for something that has to pass through.

### How it works

Your document owns everything: a parameter sheet, the generated geometry nodes, and your own
features. The generator is run **into your document** rather than referenced from it. That is
what puts the parameters within your reach.

```
Your document
├── Params            <- spreadsheet: U, tolerances, bolt diameter, ...   you edit this
├── Outer, Bore, ...  <- generated nodes, each dimension an expression over Params
├── Tip               <- stable end of the generated tree
├── UserBracket ──┐
├── UserFuse   <──┘   Base = Tip
├── UserNotch ────┐
└── UserCut    <──┘   Base = UserFuse                                     your geometry
```

### Steps

1. **Create your document and save it.** Do this first — some references refuse to resolve
   from an unsaved document.
2. **Run the generator into it**, naming the variant you are starting from. It creates the
   parameter sheet and the geometry nodes.
3. **Edit the parameter sheet** for anything the original already parameterises — a
   tolerance, a bolt diameter, the size multiplier `U`. The geometry follows.
4. **Add your own features downstream of `Tip`.** Fuse a bracket on, cut a notch out.
   Reference `Tip` and nothing else inside the generated tree.
5. **Bind your own features to the parameter sheet** wherever their position or size
   depends on the part's size. See the last rule below for why.

### Re-running the generator

Safe, and it is how you pick up improvements to the generator. It updates only the nodes it
owns — they carry a `Generator` tag — and leaves alone:

- your parameter values, including every override you made;
- your own geometry nodes and the references between them;
- your features' link to `Tip`.

Measured: re-running produced no duplicate nodes, preserved all overridden parameters, and
left every user node connected.

### Why `Tip` and nothing else

The generated tree's internals change shape as parameters change — the corner's face count
moves from 52 to 32 between `U` 1 and 4 as features merge. Anything bound to an internal node
or to a face name will eventually break. `Tip` is guaranteed stable and exists for exactly
this purpose.

**This is also why drawings dimension expressions rather than faces**, and why assembly joints
are asserted against placements computed from parameters.

---

## Workflow B — linking a generated part

**Use this when you want to *use* generated parts without modifying them**, and you want them
to update automatically when the sweep re-runs. Assemblies are the main case.

A link references the generated file. The geometry follows the source whenever it changes,
and you can fuse or cut your own geometry onto the link locally.

**What a link cannot do is change the source's parameters.** There is no route from your
document into the generated file's parameter table. If you need a different tolerance, you
need Workflow A.

Your document must be saved to disk before a link to another document will resolve.

| | Derived part (A) | Link (B) |
| --- | --- | --- |
| Change the original's parameters | **Yes** | No |
| Add or subtract your own geometry | Yes | Yes |
| Follows the sweep automatically | No — re-run the generator | **Yes** |
| Good for | modified variants of a part | assemblies, reuse at scale |

---

## Rules that will bite you

These are FreeCAD behaviours, not project choices. Each was measured; each fails quietly.

**Do not type over a dimension that is driven by an expression.** The edit appears to work —
the field accepts it and reads back your value — and the next recompute silently reverts it.
Change the parameter, not the dimension.

**Unbinding an expression is permanent and invisible.** If you clear an expression to set a
value by hand, that dimension stops tracking the parameter table for good, with nothing to
distinguish it from one that was never bound. Two dimensions that used to move together will
quietly stop. If you do it deliberately, write down that you did.

**Bind your own geometry to the parameter table.** A feature drawn with fixed numbers stays
valid at other sizes and stops meaning anything. In testing, a hand-placed bracket removed
248 mm³ at one size and exactly 0 mm³ at the next size up — still valid, still present,
doing nothing. Nothing warns you.

**Never edit a generated file in place.** It is an output. The sweep rewrites it.

---

## Which workflow for which use case

| Use case | Workflow |
| --- | --- |
| Print a standard part | Take the `.stl`. No FreeCAD needed |
| Print a part with one dimension changed | **A** — derived part |
| Attach something to a part (bracket, mount) | **A** — derived part |
| Clearance for something passing through | **A** — derived part |
| Build a fuselage unit, nose, tail, full assembly | **B** — link the generated parts |
| Drawings of standard parts | Generated from the sweep; nothing to do by hand |
| Drawings of a modified part | Generate from your derived document |
| Analysis of a standard configuration | Generated assembly, then the analysis ladder |
| A genuinely new component | Author it directly; `PartDesign::` sketches are the right tool for new design work, and it can consume generated parts as references |

---

## Getting help from the model itself

The parameter sheet is the documentation of what is adjustable. If something you want to
change is not in it, that is a signal: either the parameter exists upstream and should be
exposed, or the change is new design work rather than re-parameterisation. Both are fine —
they are just different jobs.
