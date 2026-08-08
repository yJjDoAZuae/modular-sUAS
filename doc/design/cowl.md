# Cowl — Design

**Status:** Reconstructed from the implementation, 2026-08-07 (IP-FC-7). The cowls had no
design authority; this document creates one by reading
[`cowl_geometry.scad`](../../src/Fuselage/scad/cowl_geometry.scad),
[`derived_cowl_parameters()`](../../src/Fuselage/tools/fuselage_variants.py), and the two
committed parameter files.

**How to read it.** Statements about *what the geometry does* are derived from the code and
are reliable — the transform algebra below was worked out from the source rather than
described from memory. Statements about *why* are marked as inference where they are
inference. Where intent could not be recovered there is an open question rather than a
guess.

**Millimetres and metres both appear here, deliberately.** The cowl is the one part of the
system where the existing millimetre-throughout rule meets metre-valued data, and getting
that boundary wrong is silent. Every quantity below is marked.

---

## What a cowl is

A cowl closes one end of the fuselage against the outer mould line. There are two, and they
are the same construction with different parameters:

- The **nose** assembly — a tip (`nose`), a removable **nose plate**, and the **nose cowl**
  that carries the tip back to the cowling bulkhead.
- The **tail** assembly — a single **tail cowl** from the aft OML to the cowling bulkhead.

Unlike every other part in the system, a cowl's outer surface is **not** parametric
geometry. It is a fixed aerodynamic shape authored in OpenVSP, imported, and then cut. All
the parameters do is decide *where to cut it* and *what to hollow out of it*.

That single fact drives everything else in this document, including the two things that are
currently wrong with it.

---

## 1. The OpenVSP shape representation — where the surface comes from

The cowl's outer surface is authored in OpenVSP and lives in
[`cad/modular_sUAS_nose_tail.vsp3`](../../src/Fuselage/cad/modular_sUAS_nose_tail.vsp3).
**That file, not the exported mesh, is the definition of the shape.** Everything in §2
onward operates on a tessellation of it.

### 1.1 What the model actually contains

Read from the committed `.vsp3` (41 MB, of which nearly all is one embedded `MeshGeom` —
the parametric definition is tiny):

| `FuselageGeom` | Stations | `Length` [m] | Section types |
| --- | --- | --- | --- |
| `Nose` | 6 | 0.1 | POINT · CIRCLE · CIRCLE · **RR** · **RR** · POINT |
| `Midbody` | 2 | 0.1 | **RR** · **RR** |
| `Tail` | 4 | 0.1 | POINT · **RR** · **RR** · POINT |
| `FuselageGeom` | 4 | 0.5 | CIRCLE · **RR** · **RR** · **RR** |

**RR** = `ROUNDED_RECTANGLE`. The Vehicle also holds two `MeshGeom` components, `Nose Mesh`
and `Tail Mesh`, which are imported tessellations rather than parametric geometry.

The rounded-rectangle dimensions, in metres:

| Where | `RoundedRect_Width` | `RoundedRect_Height` |
| --- | --- | --- |
| `Nose` stations 3–4, `Midbody` both, `Tail` station 1 | 0.100 | 0.100 |
| `Tail` station 2 — the open aft end | **0.030** | **0.060** |
| `FuselageGeom` station 3 | 0.035 | 0.050 |

**A 0.1 × 0.1 m section is exactly `unit_width` at U = 1.** The OML is square where it meets
the structure, by construction — the rounded rectangle is not an approximation of the
fuselage cross-section, it *is* the fuselage cross-section. `Tail` station 2 is where the
section collapses to 30 × 60 mm on the way to the tail point, which is the open end of the
tail cowl.

> **Reading these out of the XML has a trap that cost two wrong answers.** Each `XSec`
> carries two `<Type>` elements whose values are in **element text**, not in a `Value`
> attribute — `<Type>4</Type>`, not `<Type Value="4"/>` — unlike every Parm in the file. The
> first is the XSec type, the second the XSecCurve shape enum.
>
> Worse, the `XSecCurve`'s `ParmContainer` `<Name>` is a **stale label that does not track
> the active type**: nine `ROUNDED_RECTANGLE` stations are labeled `Ellipse`, and one is
> labeled `Point`. Trusting that name reports the wrong section type on 10 of 16 stations.
> Read `<Type>`; never the label. Better still, read it through the API — see IP-FC-30.

So the whole outer mould line is defined by **four lofted fuselage components with four to
six cross-sections each** — a handful of numbers. The 12 MB and 24 MB STL files in `oml/`
are a *sampling* of that, at a density nobody chose deliberately.

### 1.2 The representation: sections, skinning, loft

An OpenVSP `FuselageGeom` is a **skinned loft**. Its shape is determined by three things:

**(a) A sequence of cross-section curves** $C_i$, each placed at a station along the spine
and each of a declared type. This model uses **POINT**, **CIRCLE** and
**ROUNDED_RECTANGLE**; the available set also includes `ELLIPSE`, `SUPER_ELLIPSE`,
`GENERAL_FUSE`, `FILE_FUSE` and `EDIT_CURVE`. Types per station are in §1.1.

The rounded rectangle is the load-bearing choice. It is what lets the OML meet a square
fuselage *exactly* rather than approximately — at 0.1 × 0.1 m it is `unit_width` at U = 1 —
and it means the cowl's section and the bulkhead's outer profile are the same shape by
construction, not by tolerance. The circles appear only in the nose forebody, where the
section is still round.

**(b) Per-station tangent controls, on each of four sides** (top, bottom, left, right). For
each side the model stores an **angle**, a **strength**, a **curvature** and a **slew**,
each with a `*Set` flag, plus `*LRAngleEq`-style flags tying the left and right halves
together. These are the boundary conditions of the loft, not decoration.

**(c) A continuity order per side** — `ContinuityTop`, `ContinuityBottom`, etc. — where
`0`, `1`, `2` request $G^0$, $G^1$, $G^2$ across the section.

The actual values in this model, which are the design:

| Component | Station | Section | Top angle | Top strength | Continuity |
| --- | --- | --- | --- | --- | --- |
| Nose | 0 | POINT | 90° | 1.00 | $G^0$ |
| Nose | 1 | ELLIPSE | 90° | 0.75 | $G^2$ |
| Nose | 2 | ELLIPSE | 30° | 1.25 | $G^2$ |
| Nose | 3 | ELLIPSE | 0° | 1.25 | $G^2$ |
| Nose | 4 | ELLIPSE | 0° | 1.00 | $G^0$ |
| Nose | 5 | ELLIPSE | −90° | 1.00 | $G^0$ |
| Tail | 0 | ELLIPSE | 90° | 0.75 | $G^0$ |
| Tail | 1 | ELLIPSE | 90° | 1.50 | $G^0$ |
| Tail | 2 | ELLIPSE | 0° (top), **−30° (bottom)** | 0.75 / 1.25 | $G^0$ |
| Tail | 3 | POINT | −90° | 0.75 | $G^0$ |

Two things are legible from that table. The nose's **90° tangent at the apex** is what makes
it close with a rounded rather than a conical tip, and the $G^2$ run through stations 1–3 is
what keeps the forebody fair. On the tail, **station 2 breaks top/bottom symmetry** — 0° on
top against −30° on the bottom — which is the upsweep, and it is the reason the tail
parameter file is named `tail_high_open`.

### 1.3 The mathematics of the loft

Angle and strength are Hermite boundary conditions expressed in Bézier form. For a
longitudinal segment between stations $i$ and $i+1$, with endpoints $\mathbf{P}_0$,
$\mathbf{P}_3$ on the two section curves and unit tangents $\hat{\mathbf{T}}_0$,
$\hat{\mathbf{T}}_1$ set by the **angles**, the interior control points are placed at a
distance set by the **strengths** $s_0, s_1$:

$$\mathbf{P}_1 = \mathbf{P}_0 + \tfrac{s_0}{3}\,\ell\,\hat{\mathbf{T}}_0,
\qquad
\mathbf{P}_2 = \mathbf{P}_3 - \tfrac{s_1}{3}\,\ell\,\hat{\mathbf{T}}_1$$

giving the cubic Bézier segment

$$\mathbf{B}(u) = \sum_{k=0}^{3}\binom{3}{k}(1-u)^{3-k}u^{k}\,\mathbf{P}_k ,
\qquad u\in[0,1]$$

The surface is the tensor product of that longitudinal family with the section curves:

$$\mathbf{S}(u,v) = \sum_{j}\sum_{k} N_j(v)\,B_k(u)\,\mathbf{P}_{jk}$$

so the OML is a **piecewise cubic Bézier surface** — a patchwork, $C^2$ where the
continuity flags demand it and $C^0$ where they do not. That is the entire shape
representation: a few dozen control points.

**One caveat worth stating rather than assuming.** Polynomial Bézier cannot represent a
true ellipse exactly — that needs a *rational* form (NURBS with non-unit weights). If
OpenVSP's `ELLIPSE` section is a non-rational cubic approximation, the sections are
accurate to roughly $10^{-4}$ of radius rather than exact. This does not matter for
printing and does matter if the STEP file is ever used as a datum for inspection. Verify
before relying on it either way.

### 1.4 Why this matters for every downstream use case

- **STEP export is lossless with respect to this model.** Bézier is a special case of
  NURBS, so writing STEP transfers the control net rather than approximating it. The
  36 MB of STL in `oml/` is a lossy sampling of a definition that would serialize in
  kilobytes.
- **The shape is editable.** A different nose is four to six numbers, not a re-mesh. UC-9's
  "generate new nose and tail shapes" is exactly this: drive the station parameters through
  the OpenVSP Python API rather than by hand in the GUI.
- **The sections are the natural place to enforce the airframe's own constraints.** The
  fuselage is square in cross-section; the OML is elliptical. Whether the OML should adopt
  `ROUNDED_RECTANGLE` sections to match is a design question nobody has recorded — see
  [OQ-DES-CW5](#open-questions).

---

## 2. The OML transform — exact algebra

`body_blank_full()` is the whole of the cowl's outer surface. It is four operations, and
OpenSCAD applies them innermost-first:

```scad
rotate([0, pitch_angle, 0])
  scale([s, s, s])
    translate([x₀, 0, 0])
      import(oml_filename);
```

So a mesh vertex **p** in file coordinates lands at

$$\mathbf{p}' = R_y(\theta)\,\big(s\,(\mathbf{p} + \mathbf{t})\big),
\qquad \mathbf{t} = [x_0,\;0,\;0]^{\mathsf T}$$

with

$$s = \frac{U}{\texttt{oml\_scale}}, \qquad
\theta = 90^\circ - 180^\circ\cdot[\![\texttt{oml\_reversed}]\!]
\;\in\;\{+90^\circ,\,-90^\circ\}$$

$$R_y(\theta) = \begin{bmatrix}\cos\theta & 0 & \sin\theta\\ 0 & 1 & 0\\ -\sin\theta & 0 & \cos\theta\end{bmatrix}
\;\Longrightarrow\;
R_y(90^\circ):\;(x,y,z)\mapsto(z,\,y,\,-x)
\quad
R_y(-90^\circ):\;(x,y,z)\mapsto(-z,\,y,\,x)$$

### 2.1 Three consequences, each of which is a trap

**(a) `oml_scale` is a divisor, and it encodes a convention rather than a fact.** With
`oml_scale = 1e-3`, $s = 1000\,U$. This is the only metre→millimetre conversion anywhere in
the OpenSCAD path, and it is written as a division by a small number rather than a
multiplication by 1000 — so it does not look like a unit conversion at the call site.

> **OpenVSP is dimensionless, so "the OML is in metres" is a project decision, not a
> property of the file.** Confirmed 2026-08-08 while implementing IP-FC-4. An OpenVSP model
> holds bare numbers: no unit travels with the geometry, which is why the API offers
> `LEN_UNITLESS` beside the real units and why several unrelated settings containers each
> carry an independent `*LenUnit` parm — every consumer declares its own interpretation.
>
> The convention this project uses is **1 model unit = 1 metre**, and the airframe is what
> fixes it: the OML's rounded-rectangle sections are 0.1 × 0.1 model units and must equal
> `unit_width` = 100 mm at U = 1 (§1.1). `oml_scale = 1e-3` *is* that convention, written
> as a reciprocal.
>
> **Consequence for the STEP path.** The exporter must write some unit into the file
> header, and it writes `CONVERSION_BASED_UNIT('FOOT')` — verified by reading the exported
> file. That label is an artifact, and it is not adjustable through `CADLenUnit`: setting
> it to `LEN_M` produces a **byte-identical** file. So a consumer reading the STEP
> naïvely gets 0.1 ft = 30.48 mm where the convention means 100 mm, and must apply
>
> $$\texttt{STEP\_IMPORT\_SCALE} = \frac{1000}{304.8} = 3.28084$$
>
> which is stated and applied in
> [`oml_export.py`](../../src/Fuselage/tools/oml_export.py). The number is exact:
> $30.48 \times 3.28084 = 100.0$.
>
> This is the same hazard as everything else in this section, one layer out — geometry
> that loads cleanly, carries valid surfaces, passes every structural check, and is
> silently wrong by a constant factor.

**(b) `oml_offset_x` is applied _before_ scaling, so it is in _mesh_ units — metres.** The
tail's `offset_x = -0.25` is **−0.25 m**, i.e. −250 mm at U = 1. It selects which OML
station lands on the model origin. Reading it as millimetres understates it by a factor of
1000, and the result still renders.

**(c) `oml_reversed` is a 180° flip about the transverse axis, not a mirror.** It changes
which end of the imported body points along −z. Because it is a rotation, chirality is
preserved — an asymmetric OML stays correctly handed. A mirror would not.

### 2.2 The model frame

After the transform, **+z is the cowl axis and z = 0 is the tip**, with the body extending
toward −z and meeting the cowling bulkhead at the far end. Every cutting mask in the file
sits at negative z, which is the corroborating evidence.

The axial extent of interest is

$$\texttt{body\_len} = \frac{U\cdot\texttt{oml\_length}}{\texttt{oml\_scale}} = s\cdot\texttt{oml\_length}\ \ \text{[mm]}$$

— the same scale factor applied to a length expressed in mesh units. `oml_length` is
therefore **metres** as well: 0.050 m for the nose (→ 50·U mm), 0.1 m for the tail
(→ 100·U mm).

*Inference:* naming these `oml_length` and `oml_offset_x` without a unit suffix, in a
codebase whose convention is millimetres, is the single most likely place for a 1000×
error in the FreeCAD port. See [OQ-DES-CW1](#open-questions).

---

## 3. Axial decomposition

Two half-space intersections split the blank. Both use a square prism of half-width
`unit_width` in x and y — deliberately oversized, so the prism only ever cuts in z:

| Module | Retains | Used by |
| --- | --- | --- |
| `body_blank_full_upper` | $-\texttt{cut\_len} \le z \le 0$ | `nose()` — the tip |
| `body_blank_full_lower` | $-\texttt{body\_len} \le z \le -\texttt{cut\_len}$ | `nose_cowl()`, `tail_cowl()` |

So `cut_len` is the axial length of the tip section, and "upper"/"lower" refer to **z, not
to the aircraft's vertical**. That naming has misled at least one reader — this one — and is
worth renaming at the port.

Lateral masks then reduce the blank by symmetry:

$$\texttt{right\_half\_mask}:\; y \ge 0
\qquad
\texttt{octant\_mask}:\; 0 \le y,\; y \ge x \ \text{(the wedge about the diagonal)}$$

The nose cowl is built from **one octant** and tiled by `octant_to_full()` (8 copies); the
tail cowl from **one half** and tiled by `mirror_y()` (2 copies). The difference is not
stylistic: the tail's buttress pattern is not 8-fold symmetric, so it cannot be built from
an octant.

---

## 4. The buttresses are cutting tools, not ribs

This is the most misread part of the file, and the name is the reason.

```scad
difference() {
    body_blank_half_lower(…);          // the solid blank
    difference() {
        union() { …all buttresses… }   // the cutting set
        union() { pyramid; cube; }     // regions protected from cutting
    }
}
```

A "buttress" is **subtracted**, and it is subtracted from the **outer** surface — it cuts a
groove into the outside of the cowl.

**The rib is produced by the slicer, not by the CAD.** This is the mechanism, and it is the
single most important thing to understand about the cowl:

1. The buttress cuts a channel into the outer surface, so the cowl's cross-section at that
   station is no longer a smooth closed curve — it has a re-entrant notch.
2. The part is printed with **perimeters and zero infill**. The slicer walks a fixed number
   of perimeters around whatever contour it is given.
3. Following the notch inward and back out, those perimeters lay down a **double wall
   projecting into the interior** — a structural rib — where a smooth contour would have
   produced a single wall.

So a groove on the outside becomes a stiffener on the inside, for no added CAD complexity
and no support material. **More buttress ⇒ more rib, not less material.** The naming is
right after all; it was my reading of it that was wrong.

Two consequences follow, and both matter for the port:

- **The rib does not exist in the CAD model.** It is an emergent property of slicing a
  notched contour with a perimeter count. Any solid-model interior surface (§6.2) must
  reproduce it deliberately, because a naive inward offset of the *outer* surface will
  reproduce the notch but not the double wall that fills it.
- **UC-8 structural analysis cannot use the outer surface alone.** The ribs are the
  stiffening structure, and they are invisible to any analysis that meshes the CAD solid as
  drawn.

The inner `difference()` removes a **pyramid ∪ cube** region from the *cutting set*, which
protects a core near the aft end from being grooved — that is the cowling-bulkhead
interface, and it must stay a clean surface.

### 4.1 `buttress_shape` — the cutting profile

Every buttress is a prism: a 2D profile extruded to `2·buttress_thickness`, centred. The
profile, in a plane whose axes are radius $r$ and axial station $\zeta$:

$$P = \Big\{
(-W,\; z_0),\;
(r_s,\; z_0),\;
(r_s + \rho,\; z_0 + \rho\tan\phi),\;
(r_e + \rho,\; L - z_e - \rho\tan\phi),\;
(r_e,\; L - z_e),\;
(-W,\; L - z_e)
\Big\}$$

where $W = \texttt{unit\_width}$, $L = \texttt{body\_len}$, $z_0 = \texttt{z\_offset}$,
$z_e = \texttt{z\_end}$, $r_s = \texttt{r\_start}$, $r_e = \texttt{r\_end}$,
$\rho = \texttt{r\_inset}$, $\phi = \texttt{cone\_angle}$.

Read structurally, this is a trapezoid spanning $\zeta \in [z_0,\; L - z_e]$ whose outer
boundary runs from $r_s$ to $r_e$, with the two corners **chamfered by $\rho$ radially and
$\rho\tan\phi$ axially**. The inner boundary at $r = -W$ is far outside the part, so the
profile behaves as a half-plane there — the cut always reaches the axis.

The chamfer edges therefore have slope

$$\frac{\mathrm{d}\zeta}{\mathrm{d}r} = \tan\phi
\quad\Longrightarrow\quad
\text{the chamfer makes angle } \phi \text{ with the radial direction.}$$

At $\phi = 35°$ that is an unsupported face 55° from the build axis if the part is printed
along $+z$ — steeper than the usual 45° self-supporting limit. Either the print orientation
is not along $z$, or these chamfers are not intended as printability relief.
[OQ-DES-CW2](#open-questions).

### 4.2 `cone_angle` appears twice, with reciprocal meanings

The same parameter also sets the plate-relief cone in `nose()`:

```scad
cylinder(h = L_c, r1 = R + L_c/tan(cone_angle), r2 = R, center = false);
```

with $R = \texttt{plate\_diam}/2 + \texttt{plate\_tol}$ and
$L_c = \texttt{cut\_len} - \texttt{plate\_thickness} + \texttt{nose\_flange\_height} + \varepsilon$.
The cone's half-angle measured from the axis is

$$\alpha = \arctan\!\left(\frac{r_1 - r_2}{L_c}\right) = \arctan(\cot\phi) = 90^\circ - \phi$$

So in the buttress profile $\phi$ is measured **from the radial direction**, and in the
plate cone it appears as $\cot\phi$, i.e. measured **from the axis**. Same number, same
name, complementary angles. One of the two call sites is using it against its natural
sense, and nothing records which.

### 4.3 Buttress placement

Placement is hard-coded in `tail_cowl_half()`, *not* parametric — the JSON carries a
`top_diag1`/`top_diag2` group whose `angle` and `y_offset` fields are read into the
parameter tree and then never used, because the SCAD uses literals:

| Family | Angles (deg) | Offsets |
| --- | --- | --- |
| side | 5, 12.5, 20 | $x = -0.30\,W,\; 0,\; +0.30\,W$ |
| top | 15, 0 | $y = 0.07\,W$ on the first |
| bottom | 15, 0 | $y = 0.07\,W$ on the first |
| top diagonal | ±30, at two stations | $\Delta\zeta = W\sin 30° $ apart |

The nose cowl uses exactly one side buttress at 0°, cut into the octant before tiling.

---

## 5. Parameter schema and the scaling rule

A cowl is defined by a JSON file — [`nose_round_plate.json`](../../src/Fuselage/tools/nose_round_plate.json),
[`tail_high_open.json`](../../src/Fuselage/tools/tail_high_open.json) — named by the
variation table's `parameter_filename` column. `derived_cowl_parameters()` expands it.

**The scaling rule is the thing to know:** every numeric field is a **fraction of
`unit_width`** and is multiplied by it, *except* the names in `NOSE_UNSCALED`:

```python
NOSE_UNSCALED = ("cone_angle", "tolerance", "flange_inset", "thickness",
                 "active", "angle", "filename", "scale", "length",
                 "offset_x", "reversed")
```

So three different unit conventions coexist in one JSON file:

| Class | Fields | Units |
| --- | --- | --- |
| Scaled | `cut_len`, `z_offset`, `r_inset`, `r_start`, `r_end`, `z_end`, `z_start`, `depth`, `diameter` | fraction of `unit_width` (dimensionless) |
| Unscaled, angular | `cone_angle`, `angle` | degrees |
| Unscaled, absolute | `thickness`, `tolerance`, `flange_inset` | **millimetres** |
| Unscaled, OML | `length`, `offset_x`, `scale` | **metres** (§1) |

`buttress.thickness = 0.05` is therefore 0.05 **mm** — an absolute value that does not
scale with the airframe — while `buttress.r_inset = 0.05` in the same object is 0.05 ×
`unit_width`. Two identical numbers, two different meanings, one file.

*Inference:* the unscaled-absolute group are printer-process quantities and correctly do not
scale, consistent with the greeble tolerance and `longeron_tolerance` elsewhere. But
`thickness = 0.05 mm` is one eighth of an extrusion width, which is implausible as a wall
and suggests it is a cut *clearance* rather than a wall thickness. [OQ-DES-CW3](#open-questions).

---

## 6. Shape representation: what is wrong today, and what has to change

### 6.1 The cowl is not a solid model

Every other part in this system is constructed from primitives and is a genuine solid. The
cowl is **an imported triangle mesh, cut by primitives**. Consequences:

- `oml/vsp_nose.stl` is **12 MB**; `oml/vsp_tail.stl` is **24 MB**. 36 MB of committed
  tessellation is the *authoritative definition* of the outer surface.
- Every curved surface on a cowl is faceted at whatever density OpenVSP happened to export.
  The tessellation is frozen in the repository, not a render setting.
- **UC-2, UC-3, UC-4 and UC-7 cannot be satisfied for cowls** while this holds: a mesh has
  no cylindrical face to STEP-export, no surface for an assembly constraint, and no arc for
  a drawing to dimension.

**OpenVSP exports STEP and IGES.** The fix is to import a *surface*, which makes the cowl a
B-rep like everything else — and removes 36 MB from the repository. That is IP-FC-4, it
depends on nothing, and it is on the critical path for four use cases.

### 6.2 The cowl has no interior surface

The cowl today is a **solid blank with channels cut into it**. It has no wall — the printed
part gets its interior from the slicer, as a zero-infill operation with a perimeter count.
That is sufficient for printing and insufficient for everything else: an open or solid blob
has no meaningful mass, no wall to analyse, and cannot be assembled.

**The interior must be generated as a per-layer 2D inset, not a 3D shell offset.** Those are
different surfaces, and the difference is not small.

Let the exterior be $S$, and let $C(\zeta) = S \cap \{z = \zeta\}$ be its cross-section at
station $\zeta$. The slicer-equivalent interior is

$$C_{\text{in}}(\zeta) \;=\; \text{erode}\big(C(\zeta),\; n_p \cdot w\big)$$

— a **2-D erosion of each layer's cross-section** by the perimeter count times the extrusion
width — and the interior surface is the union of those eroded contours stacked over
$\zeta$. A 3-D offset instead computes $\{ \mathbf{x} : \mathrm{dist}(\mathbf{x}, S) = t \}$,
measuring **normal** to the surface.

For a surface whose normal makes angle $\alpha$ with the horizontal plane, a horizontal
erosion of $t$ leaves a perpendicular wall of

$$t_\perp = t\cos\alpha$$

so the per-layer inset **thins toward horizontal surfaces**, reaching zero at a horizontal
face. On a cowl that means the nose tip and the tail cap have vanishing wall by this rule.

**That is correct**, because it is what the printer actually produces — and it is also why a
slicer adds top and bottom solid layers rather than relying on perimeters alone. The CAD
model needs the equivalent rule, or the generated interior will differ from the printed part
exactly where the printed part is thickest. The method belongs in an algorithm document;
this section states the requirement and the trap.

### 6.3 What the port should preserve

- The **transform algebra of §1** is the interface to the OML and must survive verbatim,
  including the fact that `offset_x` precedes the scale.
- The **hollowing-by-subtraction** structure of §3 maps cleanly onto `Part::` booleans. It
  does not map onto `PartDesign::` bodies, which is another data point for
  [OQ-ARCH-1](../architecture/freecad_migration.md#open-questions).
- The **protected core** (pyramid ∪ cube) is the bulkhead interface and is load-bearing.

---

## 7. Print orientation

**Confirmed 2026-08-07 (IP-FC-3).** The modeled frame is the print frame — the STLs the
sweep writes are already oriented for the bed, with no rotation applied between model and
slicer. System-wide, model `+z` is the build direction and corresponds to the **aircraft
body `x` axis**.

For the cowl family the **`z` sign is the whole story**, because none of these parts is
symmetric:

| Part | What goes on the bed (`z = 0`) |
| --- | --- |
| **Nose cowl** | The **large end** — the cowling-bulkhead end |
| **Tail cowl** | The **large end**, likewise — which is *forward* on the aircraft, so the tail cowl is built along the opposite body direction from the nose cowl |
| **`nose`** (the tip section) | Its **large end** down |
| **Nose plate** | **Flipped** — its flat side, which faces *forward* in body orientation, goes down |

**Every cowl prints large-end-down, tapering upward.** That is the orientation in which the
outer surface leans inward as it rises, so the OML is self-supporting over its whole length
— no support material inside a cosmetic aerodynamic surface, which is the point.

**The nose and tail cowls therefore print in opposite body directions.** Both put their
cowling-bulkhead face on the bed; on the nose that face is aft, on the tail it is forward.
This is the physical counterpart of `oml_reversed` in §2: the same 180° flip, appearing
once in the CAD transform and once on the print bed.

**The nose plate is the exception that proves the rule** — it is flipped relative to its
assembled orientation, so its forward-facing flat side is down. It is the one part in the
family whose print orientation is not its body orientation.

### 7.1 What this settles, and what it does not

**Settles:** the layer normal is the cowl axis, for every part in the family. An orthotropic
model (UC-8 tier 3) treats a cowl as weakest across planes normal to its axis — which is the
direction the cowl is loaded when the airframe is in tension, and the direction the buttress
ribs of §4 do nothing to help, since they stiffen the section rather than the joint.

**Does not settle [OQ-DES-CW2](#open-questions), but narrows it sharply.** With the build
direction now known to be axial, the buttress chamfer's overhang is computable rather than
speculative. The chamfer runs `dζ/dr = tan φ`, so its face sits at `90° − φ = 55°` from the
build axis at `φ = 35°` — steeper than the usual 45° self-supporting limit, in whichever of
the two chamfers forms a ceiling rather than a floor. Either `cone_angle` is measured from
the axis rather than the radius at that call site, or the upper chamfer is accepting a
short unsupported span. Measuring one rendered part settles it.

---

## Open questions

| ID | Summary | Blocking |
| --- | --- | --- |
| OQ-DES-CW1 | Should the metre-valued OML fields carry unit suffixes? | Not blocking — advisory before IP-FC-12 |
| OQ-DES-CW2 | What does `cone_angle` measure, and about which axis? | Not blocking — but IP-FC-12 will faithfully reproduce whichever call site is wrong |
| OQ-DES-CW3 | Is `buttress.thickness` a wall or a cut clearance? | Not blocking |
| OQ-DES-CW4 | Should buttress placement become parametric? | Not blocking |
| OQ-DES-CW5 | Are the OML sections rounded rectangles? | ~~Resolved 2026-08-07~~ — yes, 10 of 16 stations |
| OQ-DES-CW6 | How is the slicer-generated interior rib represented in a solid model? | **Blocking** IP-FC-17, IP-FC-23 |
| OQ-DES-CW7 | Is the committed `.vsp3` current, and what keeps it and the OML in step? | **Blocking** IP-FC-4 |

### OQ-DES-CW1 — Unit suffixes on the OML fields

**Problem.** The cowl geometry imports an outer-mould-line mesh produced by OpenVSP. Three
parameters control that import: `oml_scale`, `oml_length` and `oml_offset_x`. All three are
expressed in **metres**, while every other length in the OpenSCAD generator is in
**millimetres**, and none of the three carries a unit suffix.

Two of them are actively misleading. `oml_scale = 1e-3` is used as a *divisor* —
`scale = U/oml_scale` — so it multiplies by 1000 while looking like it divides. And
`oml_offset_x` is applied *before* the scale, so the tail's `-0.25` means −0.25 m (−250 mm
at U = 1), not −0.25 mm; reading it as millimetres understates it a thousandfold, and the
part still renders.

The project guideline is to encode units in a name when they are not obvious from context.
Here the context points the wrong way. This affects anyone editing a cowl parameter file
and, more seriously, the FreeCAD port (IP-FC-12), which will read these values and
reproduce whatever convention it infers.

**Alternatives**

1. **Rename with unit suffixes** — `oml_scale_m_per_unit`, `oml_length_m`,
   `oml_offset_x_m`.
   *Benefits:* the trap disappears at the point of reading; matches the guideline; costs
   nothing at runtime.
   *Drawbacks:* touches the SCAD modules, both cowl JSON files, and
   `derived_cowl_parameters()`; the standing rule is not to rename identifiers in a path
   scheduled for replacement.
   *Prerequisites:* none.

2. **Rename only on the Python side, leave the SCAD and JSON alone.**
   *Benefits:* the surviving layer is correct; small diff; provable byte-identical by
   `scad_snapshot.py`.
   *Drawbacks:* the JSON files — which a human edits — keep the misleading names, and they
   are the most likely place for the error.
   *Prerequisites:* none.

3. **Leave the names, document the convention here, and fix it at the port.**
   *Benefits:* no churn in retiring code; this document already records the algebra.
   *Drawbacks:* the port is exactly when the misreading is most costly, and documentation
   is a weaker guard than a name.
   *Prerequisites:* none.

**Recommendation: alternative 1.** This is the same argument that justified renaming
`nozzle_diameter` to `extrusion_width` in IP-GEO-24 and it applies more strongly here,
because the failure mode is a factor of 1000 rather than 20 %. The "do not rename retiring
code" rule exists to avoid churn for cosmetic gain; a name that states the wrong unit is not
cosmetic. Verify with a geometric comparison, since the generated `.scad` text changes.

### OQ-DES-CW2 — What `cone_angle` measures

**Problem.** `cone_angle` is a single parameter, set to 35° in both committed cowl files,
used at two places that measure it against **different axes**.

In `buttress_shape()` it sets the slope of the two chamfers on the cutting profile:
`dζ/dr = tan φ`, where `ζ` is the cowl axis and `r` the radius. The chamfer therefore makes
angle φ with the *radial* direction.

In `nose()` it sets a conical relief for the nose plate:
`r₁ = r₂ + L/tan(φ)`, whose half-angle from the *axis* is `90° − φ`.

So the same number means 35° from the radius in one place and 55° from the axis in the
other — complementary angles under one name. The print direction is known (axial, large end
down, §7), so the buttress chamfer is a 55°-from-vertical face wherever it forms a ceiling,
which is steeper than the usual 45° self-supporting limit. Either one call site is using the
parameter against its natural sense, or the upper chamfer accepts a short unsupported span.

Nothing records which. IP-FC-12 will reproduce both call sites faithfully, preserving
whichever is wrong.

**Alternatives**

1. **Measure a rendered part and infer the intent.**
   *Benefits:* cheap; the geometry already exists; settles the printability question
   directly rather than by argument.
   *Drawbacks:* tells you what the code does, not what was intended — if the two differ,
   you still have a decision.
   *Prerequisites:* none.

2. **Split into two parameters** — a `buttress_chamfer_angle` and a `plate_cone_angle` —
   each documented against a stated axis.
   *Benefits:* removes the ambiguity permanently; the two are not obviously the same
   quantity and nothing requires them to be equal.
   *Drawbacks:* two numbers to keep in step if they *are* meant to be equal; changes the
   JSON schema.
   *Prerequisites:* alternative 1, to know whether they should differ.

3. **Keep one parameter, define its axis once, and correct whichever call site disagrees.**
   *Benefits:* one number; forces the inconsistency to be resolved rather than documented
   around.
   *Drawbacks:* changes geometry at one of the two sites, so it is not behaviour-preserving
   and needs a print to confirm the change is an improvement.
   *Prerequisites:* alternative 1.

**Recommendation: alternative 1 first — this question cannot be answered from the code
alone.** Measure the as-built chamfer against the bed and establish whether the upper
buttress chamfer is self-supporting in practice. If it is, the parameter is being used
correctly at both sites and only the documentation is missing; if it is not, prefer
alternative 3. Do not resolve this by changing geometry before a part has been measured.

### OQ-DES-CW3 — Is `buttress.thickness` a wall or a cut clearance?

**Problem.** `buttress.thickness` is `0.05` in both cowl parameter files. It is in
`NOSE_UNSCALED`, so it is **not** multiplied by `unit_width` — it is an absolute 0.05 mm at
every airframe size.

0.05 mm is one eighth of a 0.4 mm extrusion width. It cannot be a printed wall: nothing
that thin can be produced by the process. It is used as `2·buttress_thickness` for the
extrusion depth of a *cutting* prism, which suggests it is setting a kerf or clearance
rather than a structure.

If it is a clearance, the name is wrong in the same way `nozzle_diameter` was wrong before
IP-GEO-24 — and the consequence is worse than cosmetic, because a reader sizing a rib would
reach for this parameter and get a cut width.

**Alternatives**

1. **Rename to reflect that it is a cut dimension** — `buttress_cut_width` or similar.
   *Benefits:* the name states what the value does; no geometry change.
   *Drawbacks:* touches the JSON schema and the SCAD signatures.
   *Prerequisites:* confirming it is in fact a cut dimension.

2. **Leave it, and document the meaning here.**
   *Benefits:* zero churn.
   *Drawbacks:* the misleading name survives into the port.
   *Prerequisites:* none.

3. **Reconsider whether it should scale.** If it is a kerf it is process-driven and
   correctly unscaled; if it is a structural dimension it should scale with `unit_width`.
   *Benefits:* settles the scaling question at the same time.
   *Drawbacks:* changes geometry at every size but U = 1 if the answer is "should scale".
   *Prerequisites:* the answer to the wall-or-clearance question.

**Recommendation: establish which it is, then alternative 1.** The evidence strongly favours
"cut clearance" — 0.05 mm is unprintable as a wall, and it is applied to a subtracted prism —
but that inference has not been confirmed by whoever chose the value. If it is a clearance,
the unscaled treatment is already correct and only the name needs fixing.

### OQ-DES-CW4 — Should buttress placement become parametric?

**Problem.** `tail_cowl_half()` hard-codes every buttress angle and offset as a literal:
side buttresses at 5°, 12.5° and 20°, top and bottom at 15° and 0°, diagonals at ±30°, with
offsets written as fractions of `unit_width` inline.

Meanwhile the cowl JSON carries `angle`, `y_offset`, `z_start` and `depth` fields for each
buttress group, `derived_cowl_parameters()` faithfully scales them into the parameter tree,
and the geometry **ignores all of them for placement**. This is the same defect class as
OQ-DES-B6 and OQ-DES-C3: a parameter threaded through the whole pipeline and discarded at
the point of use.

The practical consequence is that a new cowl shape cannot be given a different buttress
pattern without editing SCAD, which defeats the purpose of the JSON parameter files.

**Alternatives**

1. **Make placement parametric** — drive the angles and offsets from the fields that
   already exist.
   *Benefits:* the JSON becomes a complete description of a cowl; new cowl types stop
   requiring code changes; the dead fields become live.
   *Drawbacks:* the buttress *count* is also hard-coded (three side, two top, two bottom,
   two diagonal pairs), so a full solution needs a list rather than a fixed group set;
   larger change than it first appears.
   *Prerequisites:* deciding whether count is parametric too, or only placement.

2. **Delete the unused fields.**
   *Benefits:* removes the misleading appearance of configurability; smallest change.
   *Drawbacks:* gives up the capability; the next cowl shape re-raises the question.
   *Prerequisites:* none.

3. **Defer to the port**, and design the buttress set as a list of placements in the
   FreeCAD generator.
   *Benefits:* the port is rewriting this layer anyway; a list is natural in Python and
   awkward in OpenSCAD.
   *Drawbacks:* the dead fields persist until then, and any cowl designed meanwhile is
   hard-coded.
   *Prerequisites:* none.

**Recommendation: alternative 3, with alternative 2's honesty in the interim** — mark the
unused fields as unused in the JSON schema documentation so nobody sets them expecting an
effect. The full fix wants a list of buttress placements rather than a fixed set of named
groups, and that is a natural thing to build in the port and an unnatural one to retrofit
into the current SCAD.

### ~~OQ-DES-CW5 — Elliptical or rounded-rectangle sections?~~ — RESOLVED 2026-08-07

**Rounded rectangles**, on 10 of the 16 stations — including every station where a cowl
meets structure. The question was posed on a misreading of the `.vsp3` (see §1.1), and the
answer is better than the question: the OML is not an ellipse being reconciled to a square
fuselage, it is **square by construction**, 0.1 × 0.1 m, exactly `unit_width` at U = 1.

That carries into the port. The cowl's section and the cowling bulkhead's outer profile are
the same shape derived from the same number, so they cannot drift — the same class of
guarantee the greeble gets from being cut with `corner_end()`. A port that re-derives the
cowl section independently of `unit_width` would silently break it.

### OQ-DES-CW6 — Representing the slicer-generated rib in a solid model

**Problem.** The cowl's stiffening ribs do not exist in the CAD model. §4 establishes the
mechanism: a buttress cuts a groove into the **outer** surface, and the slicer — walking a
fixed perimeter count with zero infill — follows that notch inward and back out, laying
down a **double wall projecting into the interior**. The rib is an emergent property of
slicing a notched contour, not modelled geometry.

Every solid-model use case therefore has a problem. An interior surface generated by
offsetting the outer surface inward (§6.2) reproduces the notch but *not* the double wall
that fills it. The resulting solid understates both the part's stiffness and its mass, and
a structural analysis meshed from it would miss the entire stiffening structure — which is
the reason the buttresses exist.

Affects UC-4 (assemblies), UC-8 (analysis) and any mass estimate. Does **not** affect UC-1,
because the printed part is produced from the outer surface and is correct as it stands.

**Alternatives**

1. **Model the rib explicitly** — generate the double wall as geometry where the notch is.
   *Benefits:* the solid matches the printed part; analysis and mass properties are
   correct; assemblies show real interior clearance.
   *Drawbacks:* the rib's exact form depends on slicer settings — perimeter count,
   extrusion width, the slicer's own corner handling — so the CAD would encode a
   process-specific result; changing slicer profile invalidates the model.
   *Prerequisites:* the interior-surface algorithm (IP-FC-16) must exist first.

2. **Model a nominal rib** of stated thickness, not tied to a specific slicer.
   *Benefits:* captures the structure for analysis without pretending to slicer fidelity;
   robust to profile changes.
   *Drawbacks:* the model is then neither the CAD intent nor the printed reality; the
   discrepancy has to be stated wherever the model is used.
   *Prerequisites:* a decision on what nominal thickness represents.

3. **Model the interior without ribs and record the omission.**
   *Benefits:* simplest; the outer surface stays authoritative.
   *Drawbacks:* analysis is conservative in stiffness by an unknown margin, which is not
   the same as safe — a conservative stiffness can be unconservative for buckling and for
   resonance.
   *Prerequisites:* none.

4. **Stop generating ribs by notching, and model them directly** — change the design so the
   rib is real geometry and the slicer is not doing structural work.
   *Benefits:* removes the CAD/print divergence at its source; the model becomes the truth.
   *Drawbacks:* discards a mechanism that gets ribs for free with no support material;
   likely heavier; a substantial redesign of a working part.
   *Prerequisites:* evidence that the divergence actually costs something.

**Recommendation: alternative 2, and treat alternative 4 as out of scope unless analysis
shows the current design is marginal.** The notching mechanism is elegant and works; the
problem is representational, not structural. A nominal rib gives UC-8 something to analyse
and UC-4 something to assemble, and the honest thing is to state in the model where it
diverges from the print. Alternative 1's slicer-specific fidelity is more precision than
the rest of the analysis chain can use.

### OQ-DES-CW7 — Keeping the `.vsp3` and the exported OML in step

**Problem.** The cowl's outer surface is defined in
[`cad/modular_sUAS_nose_tail.vsp3`](../../src/Fuselage/cad/modular_sUAS_nose_tail.vsp3) and
consumed as `oml/vsp_nose.stl` (12 MB) and `oml/vsp_tail.stl` (24 MB). **Nothing connects
them.** No check asserts that the committed meshes were exported from the committed model,
no process re-exports when either changes, and the export is performed by hand in the GUI.

The committed `.vsp3` is dated 2025-07-13 and the meshes 2025-07-12 and -13. Whether the
model has been edited since is not determinable from the repository.

The failure mode is silent and was nearly demonstrated during this document's own writing:
a design document derived from the committed model can disagree with the designer's actual
design, and there is no signal distinguishing "the document is wrong" from "the committed
model is stale". Affects IP-FC-4 directly — exporting a STEP surface from a stale model
would propagate the staleness into every downstream use case.

**Alternatives**

1. **Automate the export** — drive OpenVSP headlessly to regenerate the OML from the
   committed `.vsp3` as part of the build.
   *Benefits:* the two cannot drift; the OML stops being a committed artifact and becomes a
   derived one; this is UC-9's first half, needed anyway.
   *Drawbacks:* adds OpenVSP as a build-time dependency; export settings become code that
   must itself be right.
   *Prerequisites:* OpenVSP Python API access, resolved as licence-clean in OQ-ARCH-9.

2. **Check rather than automate** — store a hash of the `.vsp3` alongside the exported OML
   and fail a verification run when they disagree.
   *Benefits:* much smaller; catches drift without owning the export; works with the
   existing manual workflow.
   *Drawbacks:* detects the problem rather than preventing it; requires discipline to
   regenerate the hash for the right reason.
   *Prerequisites:* none.

3. **Stop committing the meshes**, and treat the `.vsp3` as the only source.
   *Benefits:* removes 36 MB and the possibility of disagreement by construction.
   *Drawbacks:* nobody can build a cowl without OpenVSP installed; breaks the current
   workflow for anyone who only has the CAD toolchain.
   *Prerequisites:* alternative 1.

**Recommendation: alternative 2 now, alternative 1 with IP-FC-4.** The hash check is small
enough to do immediately and converts a silent failure into a loud one, which is the
property that matters. Automating the export is the real fix and is already scheduled as
part of the OML-as-surface work — at which point the mesh files disappear and the question
closes itself.

## See also

- [freecad_migration.md](../architecture/freecad_migration.md) — UC-9 (OML as a surface),
  OQ-ARCH-5 (the interior-surface method)
- [bulkhead.md](bulkhead.md) — the cowling bulkhead the cowl mates to
- [corner.md](corner.md) — the other half of the fuselage joint
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-4, IP-FC-7,
  IP-FC-16, IP-FC-17
