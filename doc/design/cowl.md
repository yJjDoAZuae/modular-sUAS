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

**Updated 2026-08-09.** Five of the seven open questions were answered by the designer —
CW1, CW2, CW3, CW4 and CW6 — and the answers are marked as resolutions rather than folded
silently into the text, because four of them are *intent* that no reading of the code could
have recovered. Two of those four inverted a conclusion this document had drawn from the
code alone: `cone_angle` was not a violated printability limit but a deliberately aggressive
one, and the notched rib was not a modelling shortfall but the mechanism that makes spiral
vase printing possible. Where a resolution contradicts an earlier inference, the inference
is left in place with the correction beside it, so the failure mode stays visible.

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

**Only the cowl of each assembly is the vase-printed part, and the tip and plate exist so that
it can stay one.** A spiral-vase cowl is a single contour per layer, so it cannot cap itself:
closing the nose in the cowl would mean carrying that thin shell round the tip, where the
surface turns over and the wall would have to lean shallower than
`overhang_angle_from_bed`. The tip and the plate are separate printed pieces precisely so the
shell never has to violate the overhang limit to close the shape. **They are therefore not
shelled and not vase-printed**, and DES-12 does not reach them.

**The tail has no such pieces today and may later.** Its aft end is the OML's own closure
(OQ-DES-CW13), so one cowl suffices. A future tail design that needs an end piece to cap off
without an overhang violation would add one on the same footing as the nose's — a cap piece,
outside DES-12, for the same reason.

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

$$s = \frac{U}{\texttt{oml\_scale\_m\_per\_mm}}, \qquad
\theta = 90^\circ - 180^\circ\cdot[\![\texttt{oml\_reversed}]\!]
\;\in\;\{+90^\circ,\,-90^\circ\}$$

$$R_y(\theta) = \begin{bmatrix}\cos\theta & 0 & \sin\theta\\ 0 & 1 & 0\\ -\sin\theta & 0 & \cos\theta\end{bmatrix}
\;\Longrightarrow\;
R_y(90^\circ):\;(x,y,z)\mapsto(z,\,y,\,-x)
\quad
R_y(-90^\circ):\;(x,y,z)\mapsto(-z,\,y,\,x)$$

### 2.1 Three consequences, each of which is a trap

**(a) `oml_scale_m_per_mm` is a divisor, and it encodes a convention rather than a fact.** With
`oml_scale_m_per_mm = 1e-3`, $s = 1000\,U$. This is the only metre→millimetre conversion anywhere in
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
> `unit_width` = 100 mm at U = 1 (§1.1). `oml_scale_m_per_mm = 1e-3` *is* that convention, written
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

**(b) `oml_offset_x_m` is applied _before_ scaling, so it is in _mesh_ units — metres.** The
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

$$\texttt{body\_len} = \frac{U\cdot\texttt{oml\_length\_m}}{\texttt{oml\_scale\_m\_per\_mm}} = s\cdot\texttt{oml\_length\_m}\ \ \text{[mm]}$$

— the same scale factor applied to a length expressed in mesh units. `oml_length_m` is
therefore **metres** as well: 0.050 m for the nose (→ 50·U mm), 0.1 m for the tail
(→ 100·U mm).

*Inference:* naming these `oml_length_m` and `oml_offset_x_m` without a unit suffix, in a
codebase whose convention is millimetres, is the single most likely place for a 1000×
error in the FreeCAD port. See [OQ-DES-CW1](#open-questions).

**Fixed 2026-08-09.** The three are now `oml_length_m_m`, `oml_offset_x_m_m` and
`oml_scale_m_per_mm_m_per_mm`, in the SCAD signatures, the `OmlParameters` dataclass and both cowl
JSON files. Verified geometry-identical by `verify_sweep_change.py`.

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
2. The part is printed with **perimeters and zero infill** — and in **spiral vase mode**,
   which is a mode these cowls support and which is to be preserved, that number is one.
   The slicer walks a fixed number of perimeters around whatever contour it is given.
3. Following the notch inward and back out, those perimeters lay down a **double wall
   projecting into the interior** — a structural rib — where a smooth contour would have
   produced a single wall.

So a groove on the outside becomes a stiffener on the inside, for no added CAD complexity
and no support material. **More buttress ⇒ more rib, not less material.** The naming is
right after all; it was my reading of it that was wrong.

**And in vase mode it is the only mechanism available** (OQ-DES-CW6, 2026-08-09). Vase mode
spirals a single continuous contour up the part and admits no interior geometry whatsoever,
so a modelled rib is not merely unnecessary there — it is impossible, and a cowl given one
stops being vase-printable. Notching the exterior is how you get a rib inside a single-wall
print. That reframes everything below: the rib's absence from the CAD is not a shortfall to
be corrected, it is the consequence of a design choice worth keeping.

Two consequences follow, and both matter for the port:

- **The rib does not exist in the CAD model.** It is an emergent property of slicing a
  notched contour with a perimeter count. Any solid-model interior surface (§6.2) must
  reproduce it deliberately, because a naive inward offset of the *outer* surface will
  reproduce the notch but not the double wall that fills it. Its thickness is
  `2·w·n_perimeters + t_cut` (§4.1, OQ-DES-CW3) — **0.85 mm in vase mode** at a 0.4 mm
  extrusion width.
- **That interior surface must not become the printing export** (§6.4). Adding it destroys
  vase-mode printability, so the two representations stay separate.
- **UC-8 structural analysis cannot use the outer surface alone.** The ribs are the
  stiffening structure, and they are invisible to any analysis that meshes the CAD solid as
  drawn.

The inner `difference()` removes a **pyramid ∪ cube** region from the *cutting set*, which
protects a core near the aft end from being grooved — that is the cowling-bulkhead
interface, and it must stay a clean surface.

### 4.1 `buttress_shape` — the cutting profile

Every buttress is a prism: a 2D profile extruded to `buttress_cut_thickness`, centered —
0.1 mm. Until IP-FC-43 this read `2·buttress_thickness` with the parameter at 0.05, which cut
the same 0.1 mm by a route the parameter's name did not state; the factor was folded into the
value on 2026-08-18 and no geometry moved ([OQ-DES-CW8](#open-questions)). The
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
name, complementary angles.

**Both are right, and the complementarity is the point** (resolved 2026-08-09,
[OQ-DES-CW2](#open-questions)). The radius lies in the bed plane and
the axis is normal to it, so `35° from the radius` and `90° − 35° = 55° from the axis` are
one face: **35° above the print bed**. `cone_angle` is the overhang angle, and the two call
sites reach the same physical slope from perpendicular references.

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

**Every literal in that table is either an angle or a fraction of `W = unit_width`**, so the
buttress pattern already scales with the cowl, which is what was intended
([OQ-DES-CW4](#open-questions)). The one deliberate
exception is `buttress.cut_thickness`, which is a slicer tolerance rather than part geometry and
is scale-independent for that reason. What is wrong here is not the scaling — it is that the
numbers live in SCAD rather than in the JSON fields that already exist to hold them.

---

## 5. Parameter schema and the scaling rule

A cowl is defined by a JSON file — [`nose_round_plate.json`](../../src/Fuselage/tools/nose_round_plate.json),
[`tail_high_open.json`](../../src/Fuselage/tools/tail_high_open.json) — named by the
variation table's `parameter_filename` column. `derived_cowl_parameters()` expands it.

**The scaling rule is the thing to know:** every numeric field is a **fraction of
`unit_width`** and is multiplied by it, *except* the names in `NOSE_UNSCALED`:

```python
NOSE_UNSCALED = ("cone_angle", "tolerance", "flange_inset", "thickness",
                 "active", "angle", "filename", "scale_m_per_mm", "length_m",
                 "offset_x_m", "reversed")
```

So three different unit conventions coexist in one JSON file:

| Class | Fields | Units |
| --- | --- | --- |
| Scaled | `cut_len`, `z_offset`, `r_inset`, `r_start`, `r_end`, `z_end`, `z_start`, `depth`, `diameter` | fraction of `unit_width` (dimensionless) |
| Unscaled, angular | `cone_angle`, `angle` | degrees — and `cone_angle` is degrees **from the print bed** (§4.2) |
| Unscaled, absolute | `cut_thickness`, `tolerance`, `flange_inset` | **millimetres** |
| Unscaled, OML | `length_m`, `offset_x_m`, `scale_m_per_mm` | **metres** (§1) — now stated in the names |

`buttress.cut_thickness = 0.1` is therefore 0.1 **mm** — an absolute value that does not
scale with the airframe — while `buttress.r_inset = 0.05` in the same object is 0.05 ×
`unit_width`, which is 5 mm at U = 1. Two small decimals of the same order, two different
meanings, one file. Before IP-FC-43 the two were *literally* the same number, 0.05 against
0.05 in `tail_high_open.json`, which is how close this trap sits to the surface.

*Inference:* the unscaled-absolute group are printer-process quantities and correctly do not
scale, consistent with the greeble tolerance and `longeron_tolerance` elsewhere.

`buttress.cut_thickness` is **the thickness of the cut into the OML**, not a wall — the cut is
what produces the buttress, through slicing. The printed rib is far thicker than the cut,
because the slicer walls both faces of it:

$$t_{\text{rib}} = 2 \cdot w_{\text{extrusion}} \cdot n_{\text{perimeters}} + t_{\text{cut}}$$

In spiral vase mode, which is the mode these cowls are printed in, `n_perimeters = 1`, so a
0.05 mm parameter yields a **0.85 mm** rib at `extrusion_width = 0.4` and 1.25 mm at the
sweep's 0.6. Resolved 2026-08-09, [OQ-DES-CW3](#open-questions) and
[OQ-DES-CW6](#open-questions).

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

> **The surface and the mesh are not the same geometry, and the difference is not negligible
> where it matters.** Measured 2026-08-31. Over the whole nose they agree to 0.005% by
> enclosed volume — but over the *nose cowl's own extent*, the 44 mm slice the cowl is cut
> from, they differ by **0.253%**. The nose cowl built on the surface encloses 371569 mm³
> where the same cowl built on the mesh encloses 372511 mm³. The tail's equivalent figure is
> 0.039%.
>
> The reason the whole-part figure hides it is that the difference reverses along the length:
> a station-by-station comparison puts the two surfaces within 0.14 mm of each other
> everywhere, with the sign changing, so the errors cancel end to end and concentrate in any
> slice taken from one part of the body. The STEP is a NURBS *fit* of the same loft the STL
> tessellates, and 0.14 mm is the fit residual.
>
> **Neither is wrong** — both are exports of the model in §1, which is the definition. What
> matters is that a ported cowl cannot be checked against an OpenSCAD-rendered cowl by
> comparing volumes, because the two are cut from different source geometry and will disagree
> by two to twenty-five times the migration's 0.010% tolerance while both are correct.
> Verified by holding the OML constant: built on the *same* mesh the OpenSCAD path uses, the
> ported nose and tail cowls agree with their references to **−0.0000%** each. That is what
> establishes the port; the volume difference above is a change of input, not an error.

### 6.2 The cowl has no interior surface

The cowl today is a **solid blank with channels cut into it**. It has no wall — the printed
part gets its interior from the slicer, as a zero-infill operation with a perimeter count,
and **for cowls printed in spiral vase mode that count is one**. That is sufficient for
printing and insufficient for everything else: an open or solid blob has no meaningful mass,
no wall to analyse, and cannot be assembled.

> **Constraint on everything in this section.** Cowls are printable in **spiral vase mode**,
> and that capability is to be kept ([OQ-DES-CW6](#open-questions)). Vase mode requires one
> closed contour per layer and no interior geometry whatsoever, so a cowl that has been given
> a modelled wall **is no longer vase-mode printable**. The interior surface described below
> therefore serves UC-2, UC-3, UC-4 and UC-8; it must not become what UC-1 exports. See §6.4.
>
> **This is `DES-12` in
> [system_requirements.md](system_requirements.md#4-design-requirements)** as of 2026-08-29 —
> this paragraph is its source, and the requirement restates it rather than deciding anything
> new. It went into the register because **nothing verifies it**: a modelling change that gives
> the cowl a wall destroys the capability, and the part still builds, still exports, and still
> measures correctly. That is [OQ-DES-SR2](system_requirements.md#open-questions).

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
face.

**That is correct**, because it is what the printer actually produces, and **the cowl never
reaches the degenerate end of it** — the design avoids near-horizontal geometry rather than
accommodating it. The nose closure is split off as its own parts, `nose_nose` and
`nose_plate`, so the body never turns over; the tail is open at both ends; and every internal
relief is cut at `overhang_angle_from_bed`. The shallowest surface the design permits is 55°
from vertical, which still leaves `0.6 × cos 55° = 0.344 mm` of wall — about seven times the
0.05 mm floor. Nor is there a top or bottom skin here for a solid-layer rule to be the
equivalent of: only the perimeters are printed.
[OQ-ARCH-17](../architecture/freecad_migration.md#open-questions) settles this, and the
algorithm carries it as a **precondition it asserts** rather than as a material rule.

**The method is [cowl_interior_surface.md](cowl_interior_surface.md)** (IP-FC-16); this
section states the requirement and the trap.

### 6.3 What the port should preserve

- The **transform algebra of §1** is the interface to the OML and must survive verbatim,
  including the fact that `offset_x_m` precedes the scale -- it is metres in the mesh's
  own frame, which is what the suffix is there to say.
- The **hollowing-by-subtraction** structure of §3 maps cleanly onto `Part::` booleans. It
  does not map onto `PartDesign::` bodies, which is another data point for
  [OQ-ARCH-1](../architecture/freecad_migration.md#open-questions).
- The **protected core** (pyramid ∪ cube) is the bulkhead interface and is load-bearing.
- The **notched blank must remain exportable as it stands** — see §6.4.

### 6.4 Two representations of one cowl, and why they cannot be merged

*Added 2026-08-09, resolving [OQ-DES-CW6](#open-questions).*

A cowl has to be two things at once, and the port cannot collapse them:

| | **Print representation** | **Solid representation** |
| --- | --- | --- |
| What it is | The notched blank exactly as generated today — no wall, no modelled rib | The blank shelled by the §6.2 per-layer inset, with the rib modelled where each notch is |
| Serves | UC-1 | UC-2, UC-3, UC-4, UC-7, UC-8 |
| Wall comes from | The slicer, one contour per layer in vase mode | Geometry |
| The rib | Emerges, as the wall follows the notch in and back out | Present in the geometry, `2·w·n + t_cut / sin θ` thick measured in the layer plane — 1.3 mm at a vertical cut, 1.4 mm at the tail's 30° diagonals ([OQ-DES-CW19](#open-questions)) |

**They cannot be merged, and the direction of the incompatibility is the important part.**
Adding a wall to the print representation destroys vase-mode printability outright: vase mode
spirals a single contour and admits no interior geometry, so the moment the cowl has a
modelled inner surface the mode is unavailable. Meanwhile the print representation is useless
for analysis, because the structure that carries the load is not in it.

So the port produces **both from one parametric source**, and the invariant to hold is:
**the UC-1 export path continues to come from the un-shelled notched blank.** Shelling is a
downstream operation for the other use cases, never a replacement for the blank. A port that
"improves" the cowl by giving it a proper wall and exports that for printing has silently
removed a printing capability, and nothing in the geometry would flag it — the STL would look
better and slice worse.

**This also fixes the direction of the modelling work.** The rib is not something to be
reverse-engineered from a slicer's output as a curiosity; it is the structure, and the notch
is the *mechanism* that produces it under a mode that permits no other mechanism. The notch
is not a workaround for the model's shortcomings. It is a design choice that buys ribs inside
a single-wall print, and it is the reason the interior is worth modelling at all.

**Status: both representations exist as of 2026-09-04** (IP-FC-17). The solid representation is
built by [`cowl_interior.py`](../../src/Fuselage/freecad/cowl_interior.py) and delivered as two
**additional** part kinds, `nose_cowl_shell` and `tail_shell`, beside the unchanged `nose_cowl`
and `tail`. The invariant above is held by construction rather than by care: the shelled kinds
are separate parts, the print kinds' output is unchanged, and the shelled kinds are FreeCAD-only
— asking for one on the OpenSCAD backend raises rather than quietly rendering the blank. Two
things the table above have turned out to be more specific in the built version. The rib is **not
modelled** as a feature: eroding the notched section reproduces it, which the acceptance tests
measure rather than assume — so that row reads *"present in the geometry"* rather than
*"constructed separately"*. And its thickness carries the cut angle, `2·w·n + t_cut / sin θ`
([OQ-DES-CW19](#open-questions)): 1.3 mm at every vertical cut and 1.4 mm at the tail's 30°
diagonals, because the cut is a fixed thickness normal to its own plane while the perimeters are
measured parallel to the build plate. And the wall
is a **horizontal** inset, not a normal offset, which is what makes the rib come out at that
thickness at all. At `U` = 1 the nose wall measures 9714.2617 mm³ and the tail 23685.2264 mm³,
each one valid solid. What is not yet established — the construction alternative that was never
compared, the cost of the dilation, and verification at any `U` but 1 — is
[cowl_interior_surface.md §10](cowl_interior_surface.md), as IP-FC-115, IP-FC-116 and IP-FC-117.

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

**Settled [OQ-DES-CW2](#open-questions) — this section supplied the
missing half.** With the build direction known to be axial, the buttress chamfer's overhang is
computable rather than speculative. The chamfer runs `dζ/dr = tan φ`, so at `φ = 35°` its face
sits 55° from the build axis and **35° above the bed** — and that is the whole meaning of
`cone_angle`: the overhang angle, measured from the bed. The nose plate's cone reaches the
same 35° by the complementary spelling. What looked like an inconsistency was one face
described against two perpendicular references, and what looked like a violated 45° limit was
a deliberately aggressive value that modern printers hold comfortably in PLA.

---

## Open questions

| ID | Summary | Blocking |
| --- | --- | --- |
| OQ-DES-CW1 | Should the metre-valued OML fields carry unit suffixes? | ~~Resolved 2026-08-09~~ — yes; renamed and verified geometry-identical |
| OQ-DES-CW2 | What does `cone_angle` measure, and about which axis? | ~~Resolved 2026-08-09~~ — the overhang angle, from the bed; both call sites correct |
| OQ-DES-CW3 | Is `buttress.thickness` a wall or a cut clearance? | ~~Resolved 2026-08-09~~ — neither: it is the cut that *makes* the rib |
| OQ-DES-CW4 | Should buttress placement become parametric? | ~~Resolved 2026-08-09~~ — scaling is intended and already correct; placement becomes a list at the port, general siting deferred |
| OQ-DES-CW5 | Are the OML sections rounded rectangles? | ~~Resolved 2026-08-07~~ — yes, 10 of 16 stations |
| OQ-DES-CW6 | How is the slicer-generated interior rib represented in a solid model? | ~~Resolved 2026-08-09~~ — modelled nominally; the notched blank stays the print export, because vase mode depends on it. **Unblocks IP-FC-17, IP-FC-23** |
| OQ-DES-CW7 | Is the committed `.vsp3` current, and what keeps it and the OML in step? | ~~Resolved 2026-08-08~~ — both alternatives delivered |
| OQ-DES-CW8 | Is the factor of two in the buttress extrude a per-side convention or an error? | ~~Resolved 2026-08-18~~ — fold the doubling into the value: `buttress_cut_thickness = 0.1`, no `2*`, geometry unchanged. **Unblocks IP-FC-43** |
| OQ-DES-CW9 | Where does `n_perimeters` belong, and what is it for a part that is not vase-printed? | ~~Decided 2026-08-18~~ — a **per-part** `slicing` group, not one figure for the airframe. `cowl_n_perimeters` feeds the rib thickness, the cowling bulkhead's flange radius and the nose base offset — the *cowl's* count in all three. **Unblocks IP-FC-42 entirely**, the nose base offset included: 0.5 mm stays, written as `1 × 0.6 + (−0.1)`, and OQ-DES-CW10 confirms that is the correct built value |
| OQ-DES-CW10 | Is the nose cowl's base offset a function of the nozzle? | ~~Resolved 2026-08-21~~ — **yes**: the nose shape seats on the cowl's perimeter shell and is bonded there, and the inset gives that joint both its alignment and its bonding surface. `nose_flange_tolerance = -0.1`, so the offset is 0.5 mm at the sweep's 0.6 — **the built value, unchanged**. The `0.4 + 0.1` decomposition that twice argued for 0.7 is void: the hand drivers' 0.4 is a development test value and was never a tuning |
| OQ-DES-CW11 | Which group does the overhang angle belong in? | ~~Resolved 2026-08-21~~ — **`slicing`**: choosing an overhang angle is a slicing concern, and it fails `printer`'s own membership rule because it does not move with the nozzle. Renamed `cone_angle` → `overhang_angle_from_bed` and moved from four places to one. **Not a free parameter**: it has to agree with where the nose/cowl break line falls and changing it means adjusting the buttresses, neither of which is enforced in code. `slicing` gained a per-key validator, since a perimeter count and an angle cannot share one rule. **Unblocks IP-FC-28** |
| OQ-DES-CW12 | What measures whether a ported part is correct, now that `Shape.Volume` cannot? | Not blocking — the port proceeds on the tessellated volume, alternative 1 |
| OQ-DES-CW13 | Where does the tail's folded aft closure get fixed? | Not blocking — the closure is rebuilt at import, alternative 1 |
| OQ-DES-CW16 | How is a cowl document built and shipped, when FreeCAD's own document booleans produce wrong geometry for this part? | Blocking the claim that a cowl `.FCStd` can be re-solved by someone who has only FreeCAD |
| OQ-DES-CW17 | Two defects make the tail correct only near `U` = 1: the OML blank's faces are too coarsely subdivided for the cut, and the overlapping tools are fused before cutting. Fixing both, plus an exact C1 conversion that doubles the margin, holds the tail within 0.004% of OpenSCAD at every swept `U` and costs nothing on recompute. Adopt alternatives 3, 6 and 7 as one change? | Blocking the tail on the FreeCAD backend for every `U` except 1 |
| OQ-DES-CW18 | `plate_thickness`, the two plate flange dimensions and `nose_flange_height` are swept per `U` but were never tuned — 3.2 mm against the reference's 0.8 mm at `U` = 4, a factor of 4.8 in the plate's material. Should they scale, hold fixed, or be derived from the printer? | Not blocking the port — but the committed reference cannot check the nose plate or nose tip above `U` = 1 until it is settled |

### ~~OQ-DES-CW1 — Unit suffixes on the OML fields~~ — RESOLVED 2026-08-09

**Problem.** The cowl geometry imports an outer-mould-line mesh produced by OpenVSP. Three
parameters control that import: `oml_scale_m_per_mm`, `oml_length_m` and `oml_offset_x_m`. All three are
expressed in **metres**, while every other length in the OpenSCAD generator is in
**millimetres**, and none of the three carries a unit suffix.

Two of them are actively misleading. `oml_scale_m_per_mm = 1e-3` is used as a *divisor* —
`scale = U/oml_scale_m_per_mm` — so it multiplies by 1000 while looking like it divides. And
`oml_offset_x_m` is applied *before* the scale, so the tail's `-0.25` means −0.25 m (−250 mm
at U = 1), not −0.25 mm; reading it as millimetres understates it a thousandfold, and the
part still renders.

The project guideline is to encode units in a name when they are not obvious from context.
Here the context points the wrong way. This affects anyone editing a cowl parameter file
and, more seriously, the FreeCAD port (IP-FC-12), which will read these values and
reproduce whatever convention it infers.

**Alternatives**

1. **Rename with unit suffixes** — `oml_scale_m_per_mm_m_per_unit`, `oml_length_m_m`,
   `oml_offset_x_m_m`.
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

**RESOLVED 2026-08-09 — alternative 1, done.**

| Was | Now | Why the suffix reads that way |
| --- | --- | --- |
| `oml_length` | `oml_length_m` | Metres, in a codebase whose every other length is millimetres |
| `oml_offset_x` | `oml_offset_x_m` | Metres, and applied *before* the scale, so it is metres in the mesh's own frame — the tail's −0.25 is −250 mm at U = 1 |
| `oml_scale` | `oml_scale_m_per_mm` | A **divisor**: `scale = U/oml_scale_m_per_mm`. At 1e-3 it multiplies by 1000 while the bare name suggests it divides. The suffix names the ratio in the order the division takes it |

Renamed in all four places the value passes through: the SCAD module signatures
(`cowl_geometry.scad`, `nose_cowl.scad`, `tail_cowl.scad`), the `OmlParameters` dataclass,
and — because `derived_cowl_parameters()` copies OML fields by `fields()`, so the dataclass
field names *are* the schema — the JSON keys in both cowl parameter files.

**`_m_per_mm` rather than the `_m_per_unit` originally proposed.** "Unit" is the most
overloaded word in this project — `U`, `unit_width`, `unit_length` — and spending it here on
"model unit" would have planted a fresh ambiguity in the middle of a rename whose whole
purpose was removing one. `_m_per_mm` names both ends of the ratio and borrows nothing.

**Verified geometry-identical**, which was the stated requirement. This change alters SCAD
module signatures, so the generated `.scad` text necessarily differs and `scad_snapshot.py`
would report DIFF by construction — the case `verify_sweep_change.py` exists for. It re-ran
the real sweeps and compared the resulting solids: nose cowl, tail, and non-cowl parts as
controls, all identical.

### ~~OQ-DES-CW2 — What `cone_angle` measures~~ — RESOLVED 2026-08-09

**`cone_angle` is the overhang angle for printing, measured from the print bed. Both call
sites are correct, and the apparent inconsistency was an artefact of how this document posed
the question.**

The two expressions are complementary because they are written against **perpendicular
reference directions**, and the physical face they produce is the same. Working each through
to the bed plane:

| Call site | As written | Face relative to the axis | **Face relative to the bed** |
| --- | --- | --- | --- |
| `buttress_shape()` | `dζ/dr = tan φ` — angle φ from the *radius* | 55° | **35°** |
| `nose()` | `r₁ = r₂ + L/tan φ` — half-angle `90° − φ` from the *axis* | 55° | **35°** |

The radius lies in the bed plane and the axis is normal to it (the part prints axially, large
end down, §7), so "35° from the radius" and "55° from the axis" are two spellings of one
face. `tan 35° = 0.700`, and a cone whose radius grows by `L/0.700 = 1.428·L` over height `L`
stands at `atan(1.428) = 55°` from the axis — 35° above the bed. The parameter is used
against its natural sense at both sites; only the documentation was missing.

**Why 35° and not 45°.** The 45° figure this document measured against is a rule of thumb,
and a conservative one: modern printers do considerably better than 45° in PLA, and 35° from
the bed is readily achievable. It is an aggressive value chosen deliberately, not a value
that drifted past a limit. The earlier reading — "a 55°-from-vertical face, steeper than the
usual 45° self-supporting limit, so something must be wrong" — inverted the conclusion: 55°
from vertical *is* the achievable direction, and the design is spending the margin the rule
of thumb leaves on the table. **Other materials may not hold 35°**, which makes this a
material-dependent process limit rather than a shape parameter.

**Consequences for the port.**

- **Do not split it.** Alternative 2 of the original question is wrong: the two sites are one
  quantity, and forcing them apart would let them drift out of step for no reason. Nothing
  needs correcting under alternative 3 either — there is no disagreeing call site.
- **The name states a shape and hides a constraint.** `cone_angle` describes what the geometry
  looks like at one of the two sites and nothing at all at the other; what it *is* is a
  minimum printable angle. `overhang_angle_from_bed` names both the quantity and the reference
  the ambiguity turned on — and the reference is exactly what OQ-DES-CW1 argues belongs in the
  name. Note that it is a **floor, not a target**: shallower fails, steeper is free.
- **It is a printer setting, not a cowl setting.** It is already in `NOSE_UNSCALED` and does
  not scale, correctly — but it sits in the cowl JSON, where it reads as a property of the
  shape. Being material-dependent, it belongs in `PrinterSettings` with `extrusion_width`,
  `layer_height` and the `n_perimeters` that OQ-DES-CW6 needs (IP-FC-42): the four together
  are the process, and a cowl designed for one material should not have to be re-authored for
  another. Recorded as IP-FC-28.
- **It is the only printability constraint expressed anywhere in this project's geometry**,
  but that does not make it a single project-wide number. Every other self-supporting
  decision — the greeble chamfers, the bulkhead flange chamfer, the corner's snap groove
  cones — is a literal angle chosen to be printable, with nothing recording that printability
  is what set it. The tempting fix is to derive them all from one value; it is the wrong fix,
  because **the achievable angle depends on what is overhanging**:

  | What varies | Why it changes the achievable angle |
  | --- | --- |
  | Span | A 2 mm chamfer sags negligibly at an angle that would ruin a 40 mm one. Droop accumulates over the unsupported run, not per layer |
  | Surface type | A cone is self-supporting in a way a flat ceiling is not — each layer is a closed loop laid on the one below, with no free end |
  | Function | A cosmetic face tolerates droop; a mating surface — the plate relief, the snap groove — does not, and wants margin the cowl's exterior does not need |
  | Cooling and orientation | The same face on the same printer behaves differently depending on what is around it |

  So the process value is a **baseline**, and individual features are entitled to be more
  conservative where the span is long or the surface mates, or more aggressive where the span
  is short. What is worth capturing is not one angle but the *fact* that a given chamfer is
  set by printability and against which reference — so that changing material prompts a
  review of each rather than a silent global substitution. Whether the baseline should
  additionally carry per-feature overrides, and on what rule, is left open here; the cowl
  needs one value and this question is about the cowl.

### ~~OQ-DES-CW3 — Is `buttress.thickness` a wall or a cut clearance?~~ — RESOLVED 2026-08-09

**Neither, and the question was posed on a false dichotomy.** `buttress.thickness` is the
thickness of **the cut into the OML that produces the buttress through slicing**. It is not
a clearance around some other feature, and it is not the rib's thickness — it is the notch
whose walls, once the slicer has laid perimeters down both faces of it, *are* the rib.

The thickness of the buttress measured on the interior of the cowl is therefore

$$t_{\text{rib}} = 2 \cdot w_{\text{extrusion}} \cdot n_{\text{perimeters}} + t_{\text{cut}}$$

These cowls print in **spiral vase mode** ([OQ-DES-CW6](#open-questions)), so `n_perimeters`
is **1**: a 0.05 mm parameter yields a **0.85 mm** rib at `extrusion_width = 0.4`, 1.25 mm at
the sweep's 0.6. The value looked implausible because it was being read as the whole rib when
it is the smallest of the three terms that make it — and because a single-wall print was not
in view, which is the case where a 0.85 mm rib is a substantial fraction of the structure.

**This settles the scaling question too, and the current treatment is right.**
`buttress.thickness` **is a slicer tolerance, not a part geometry parameter**, and a slicer
tolerance has no business tracking the airframe — so it does not scale, and `thickness`
belongs in `NOSE_UNSCALED` exactly where it is. Alternative 3 of the original question is
answered: it should not scale. The consequence follows and is intended
([OQ-DES-CW4](#open-questions)): the buttress *pattern* — angles, offsets, extents — scales
with the cowl, while the rib's thickness does not, because the first is design and the second
is process.

**What the name should be.** `thickness` is defensible now that its referent is known, but it
reads as the rib's thickness at every call site, and a reader sizing a rib would take it and
be wrong by a factor of thirty. `buttress_cut_thickness` states which of the two thicknesses
it is. That is a rename across the JSON schema, `ButtressSet` and eight SCAD signatures, so
it is deferred to the port rather than done twice — recorded as IP-FC-29.

**One discrepancy to settle, flagged rather than fixed.** Every call site extrudes the cutting
prism as

```openscad
linear_extrude(height=2*buttress_thickness, center=true, ...)
```

so the cut actually taken out of the blank is **0.1 mm, twice the parameter**, and the rib
built on it is `2·w·n + 2·t`. Under the definition above the factor of two is either a
half-thickness-per-side convention that the parameter name does not state, or an error. It
is not resolvable by measurement — the two readings differ by 0.05 mm of rib thickness,
whatever the extrusion width — so it is a question of intent for whoever set the value.
*Split out as its own question and settled 2026-08-18 — see [OQ-DES-CW8](#open-questions).
The doubling is kept and folded into the value: the parameter becomes
`buttress_cut_thickness = 0.1` and the `2*` comes out of the four extrudes, so the cut stays
0.1 mm and no geometry moves. `t` in the rib formula is therefore the stored number, and the
printed parts remain reproducible from the files.*

**The perimeter count is not a parameter anywhere in this project.** `PrinterSettings` carries
`extrusion_width` and `layer_height` and nothing else; `n_perimeters` lives only in the slicer
profile, which is not in the repository. The formula above therefore cannot be evaluated by
the generator as it stands. That matters directly to OQ-DES-CW6 — a nominal rib cannot be
modelled without it — and it is the same class of gap as the OML/`.vsp3` link that OQ-DES-CW7
closed: a value the geometry depends on, held outside the system that depends on it.

### ~~OQ-DES-CW4 — Should buttress placement become parametric?~~ — RESOLVED 2026-08-09

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

**Resolved 2026-08-09 — with the question split in two, because it was conflating them.**

**Scaling: intended, and already correct.** The existing buttress design is meant to scale
with the cowl, and it does — every hard-coded placement in §4.3 is either an angle
(dimensionless) or a fraction of `unit_width`, and the `z` stations are taken from `tail_len`,
which scales. Nothing here needs changing and **the port must preserve it**: a placement
re-expressed in absolute millimetres would reproduce U = 1 exactly and be wrong everywhere
else, which is the failure mode this project has hit before and the reason the sweep is
checked at four values of U rather than one.

The single exception is `buttress.cut_thickness`, which is scale-independent **because it is a
slicer tolerance rather than a part geometry parameter** — the same reasoning that resolved
[OQ-DES-CW3](#open-questions). That also settles
the question CW3 left hanging: the rib's thickness being constant across airframe sizes while
its placement and extent scale is *deliberate*, not an oversight. A slicer tolerance has no
business tracking the airframe.

**Parametric placement: alternative 2 is rejected outright, alternative 3 stands, and its
scope shrinks.** The unused fields stay — they are wanted, not dead. But note what the port
is and is not being asked to do:

- **In scope: making today's chosen placements data.** The angles and offsets of the existing
  pattern move from SCAD literals into the buttress list, each entry scaled by `unit_width`
  exactly as the literals are now. This is a transcription, verifiable against the current
  geometry, and it makes the existing JSON fields live.
- **Out of scope: choosing placements for a new OML.** There is no generalized algorithm for
  siting buttresses on an arbitrary nose or tail, and none is claimed. That is a design
  problem worth exploring later, and it is not a prerequisite for the port — a list of
  placements is exactly the representation such an algorithm would eventually *write into*,
  so building the list now is a step towards it rather than a detour around it.

### ~~OQ-DES-CW5 — Elliptical or rounded-rectangle sections?~~ — RESOLVED 2026-08-07

**Rounded rectangles**, on 10 of the 16 stations — including every station where a cowl
meets structure. The question was posed on a misreading of the `.vsp3` (see §1.1), and the
answer is better than the question: the OML is not an ellipse being reconciled to a square
fuselage, it is **square by construction**, 0.1 × 0.1 m, exactly `unit_width` at U = 1.

That carries into the port. The cowl's section and the cowling bulkhead's outer profile are
the same shape derived from the same number, so they cannot drift — the same class of
guarantee the greeble gets from being cut with `corner_end()`. A port that re-derives the
cowl section independently of `unit_width` would silently break it.

### ~~OQ-DES-CW6 — Representing the slicer-generated rib in a solid model~~ — RESOLVED 2026-08-09

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

**OQ-DES-CW3's resolution supplies the number this question was missing.** The rib's
thickness is `2·w·n_perimeters + t_cut`, which is a closed form in two printer settings and
one existing parameter — so alternative 2's "nominal thickness" no longer has to be invented,
and alternative 1's slicer-specific geometry is a much smaller step than it looked. Its
*depth* into the interior is still open: that is set by how far the slicer's contour walks
into the notch before turning back, and it does not follow from the cut width alone.

The catch is that `n_perimeters` **is not a parameter in this project** — `PrinterSettings`
has only `extrusion_width` and `layer_height`, and the perimeter count lives in a slicer
profile that is not in the repository. Modelling any rib at all therefore requires adopting
it as a parameter first, which is the honest version of alternative 1's "the CAD would encode
a process-specific result": the process value has to enter the model *somewhere*, and the
choice is whether it does so explicitly or by a number written into the geometry code.

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
   *Prerequisites:* ~~a decision on what nominal thickness represents~~ — supplied by
   OQ-DES-CW3: `2·w·n_perimeters + t_cut`. Still needs `n_perimeters` adopted as a parameter,
   and a rule for the rib's depth.

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

*Amended 2026-08-09.* With OQ-DES-CW3 resolved, alternatives 1 and 2 have largely converged
on the thickness axis — the "nominal" thickness and the slicer-faithful one are the same
formula, and both need `n_perimeters` in the model. What still separates them is the rib's
**depth** and its end conditions, where alternative 1 would have to model what the slicer's
contour actually does at the ends of a notch and alternative 2 would state a depth and move
on. The recommendation stands, on the narrower grounds that depth is where slicer fidelity
gets expensive and stiffness is least sensitive to it.

---

**RESOLVED 2026-08-09 — alternative 2, and alternative 4 is ruled out on a ground the
question did not know about.**

**The notched rib implementation is to be kept, because it is what makes cowls printable in
spiral vase mode.** That is the fact this question was missing, and it inverts the framing.
Vase mode spirals a single continuous contour up the part: one wall per layer, no infill, no
top or bottom, and **no interior geometry permitted at all**. Under that constraint a
modelled rib is not merely unnecessary, it is *impossible* — any interior feature makes the
part un-vase-printable. Notching the exterior is therefore not a workaround for the model
lacking ribs. It is **the only mechanism that can put a rib inside a single-wall print**, and
the design gets its stiffening for free, with no support material, no second wall, and no
loss of the fastest and strongest-per-gram mode the printer has.

So:

- **Alternative 4 is rejected, not deferred.** "Stop generating ribs by notching and model
  them directly" would trade the vase-mode capability for representational tidiness. The
  drawback listed against it — "discards a mechanism that gets ribs for free" — turns out to
  understate the cost by a long way, because what is discarded is a whole printing mode.
- **Alternative 3 is rejected.** Recording the omission is not enough now that the rib's
  thickness has a closed form (OQ-DES-CW3) and the rib is known to be the primary stiffening
  structure of a single-wall part.
- **Alternative 2 is adopted**, with alternative 1 available where fidelity is later shown to
  matter. The rib is modelled at `2·w·n_perimeters + t_cut`, with `n_perimeters = 1` in vase
  mode — refined 2026-09-04 by [OQ-DES-CW19](#open-questions) to `2·w·n_perimeters + t_cut / sin θ`,
  measured in the layer plane, θ being the cut's angle to it and 90° for every vertical cut — which is the case that matters, and conveniently the case where the formula is least
  ambiguous.
- **The representational split is now a stated invariant, not a compromise.** §6.4 records it:
  the print export stays the un-shelled notched blank, and the shelled-and-ribbed solid is a
  downstream product for the other use cases. Two representations, one parametric source.

**This unblocks IP-FC-17 and IP-FC-23**, with a constraint attached that neither had: the
interior-surface work must be additive to the existing blank rather than a replacement for
it, and the sweep's printing output must be verifiable as unchanged by it.

**What is still open, and it is small.** `n_perimeters` is not a parameter anywhere in the
project (IP-FC-42), and the rib's *depth* into the interior — how far the contour walks into
a notch before turning back — does not follow from the cut width. Neither blocks the port;
both want one sliced cowl inspected in the slicer's preview to settle by observation.

### ~~OQ-DES-CW7 — Keeping the `.vsp3` and the exported OML in step~~ — RESOLVED 2026-08-08

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

**Recommendation was alternative 2 now, alternative 1 with IP-FC-4.** The hash check is
small enough to do immediately and converts a silent failure into a loud one; automating
the export is the real fix.

---

**RESOLVED 2026-08-08 — both delivered, in [`oml_export.py`](../../src/Fuselage/tools/oml_export.py).**

- **Alternative 1, automation:** the tool drives the committed `.vsp3` headlessly through
  the OpenVSP Python API. The OML is now *derived* from the model rather than hand-exported
  from a GUI session, so the two cannot silently diverge in the first place.
- **Alternative 2, detection:** `--check` compares a SHA-256 of the committed `.vsp3`
  against the hash recorded in `oml/oml_provenance.json` at export time, and exits
  non-zero when they disagree.

Two properties of the check worth keeping:

- **It does not import the OpenVSP API.** A provenance check has to be runnable in CI, or
  by anyone, without OpenVSP installed — otherwise only the people who could already
  regenerate the file are able to detect that it is stale.
- **It was tested in both directions and on its exit code.** Current → `OK`, exit 0;
  perturbed hash → `STALE` naming both hashes, exit 1. The first attempt reported the
  failure but exited 0, because a `grep` in the test pipeline masked the status — a check
  that prints a failure and exits clean is useless to CI.

**One thing this does not yet close.** The 36 MB of `.stl` remains, because OpenSCAD cannot
import STEP and the OpenSCAD path still consumes it. The meshes disappear at IP-FC-34, when
that path is retired — not before.

### ~~OQ-DES-CW8 — The factor of two in the buttress extrude~~ — RESOLVED 2026-08-18

*Raised and resolved 2026-08-18, split out of [OQ-DES-CW3](#open-questions), which flagged the
discrepancy rather than settling it.*

**The problem.** `buttress.thickness` is `0.05` in both parameter files and as the literal
default in both drivers, but all four modules that build a cutting prism extrude it as
`linear_extrude(height=2*buttress_thickness, center=true, ...)` — `top_buttress` at
`scad/cowl_geometry.scad:310`, `top_diag_buttress` at `:324`, `side_buttress` at `:338` and
`bottom_buttress` at `:354`. No call site omits the doubling. So the groove cut into every
cowl this repository has produced is **0.1 mm wide, twice what the parameter says**, and the
rib the slicer builds on it is $2wn + 2t$ rather than $2wn + t$ — a difference of exactly
0.05 mm of rib thickness, independent of extrusion width and perimeter count, because the cut
and the perimeters are additive terms rather than factors. All lengths here are millimeters:
the cowl generator is the OpenSCAD path, to which the project's SI convention does not apply.

**Resolved: fold the doubling into the value.** The parameter becomes `0.1` and the four
extrudes become `height=buttress_cut_thickness`. The extruded height is unchanged at 0.1 mm,
so **no geometry moves** — every cowl the repository has ever produced still comes out
identical, and the parts that were flown remain reproducible from the files.

**Why this rather than keeping `0.05` with a `2*` and a `_half_thickness` name.** That
alternative is equally geometry-preserving and equally honest about what the parameter denotes,
so the choice does not turn on either. It turns on two narrower points. First, the rib formula
is $t_{\text{rib}} = 2 w_{\text{extrusion}} n_{\text{perimeters}} + t_{\text{cut}}$, and
`buttress_cut_thickness` at `0.1` **is** $t_{\text{cut}}$ — the formula can be evaluated
straight from the parameter file, where a half-thickness cannot without knowing to double
first. Second, it removes the factor of two from the code entirely rather than leaving it
alive at four sites that must stay in step. The cost accepted in exchange is that the stored
number changes, so any external note or slicer profile recording "0.05" as the buttress
setting no longer matches the file.

**What this does not decide.** It does not recover what the person who wrote `0.05` intended,
and it does not claim the 0.1 mm cut is the *right* cut. It records what the tool has always
cut, which is the one part that was never in doubt. Whether 0.1 mm is the correct groove width
is a separate question, answerable only by printing a cowl each way and measuring rib
stiffness, and worth reopening only if the rib turns out to govern a structural margin — which
would also require `n_perimeters` to become a real parameter, since it currently lives only in
the slicer profile, outside the repository.

**Implementation.** Folded into **IP-FC-29**, which is already renaming `buttress.thickness` to
`buttress_cut_thickness` across the JSON schema, `ButtressSet` and the SCAD signatures; the
rename and this change are one edit to the same call sites. **Done 2026-08-18.**

*A textual check cannot verify this, and the reason is worth recording.* `scad_snapshot.py`
compares generated `.scad` text, which names the library by path and contains none of its
text — so the removal of the `2*` inside `cowl_geometry.scad` is invisible to it, while the
rename changes the module signature and makes it report DIFF by construction. It is wrong in
both directions at once. `verify_scad_change.py` is no better here: it re-renders the
`.stl.scad` files already in the output tree, and those pin the *old* signature. Only
`verify_sweep_change.py` reaches this class of change, because it runs the real sweep and
compares measured geometry, letting signatures and generated text move freely while the solid
must not. It reported both cowls identical against `variant_output_baseline`, and a control
run with the change stashed reproduced its output exactly. `verify_drivers.py` covers the
remaining gap — the hand drivers, which no other tool renders — and passed warning-free, a
warning being the only signal a missed rename gives, since a bare identifier with no matching
variable evaluates to `undef` rather than failing.

### ~~OQ-DES-CW9 — Where does `n_perimeters` belong, and what is it for a part that is not vase-printed?~~ — DECIDED 2026-08-18: a per-part `slicing` group

**The problem.** `n_perimeters` sets how many loops a slicer walks around a contour, and this
project's geometry depends on it in three places. It could not go into `PrinterSettings`, which
declares itself *"properties of the machine, not of the design"* — a perimeter count is neither.
Nor is it a property of a part: **spiral vase is a mode these cowls support, not the only way
they are printed**, so the same cowl is 1 perimeter on one build and 3 on another. And parts are
sliced independently, so a corner's count has nothing to do with a cowl's.

**It also already had a consumer, unnamed.** The cowling bulkhead's flange radius is written

```openscad
circle(r = corner_radius - extrusion_width - cowl_flange_tolerance)
```

in `fuselage_bulkhead_geometry.scad`. That lone `extrusion_width` is the radial room left for
the cowl's wall so the cowl's outer surface lands on the mold line — so the bulkhead hard-codes
**the cowl's** count at 1, with the `1` written nowhere. At 0.6 mm extrusion width a cowl
printed at three perimeters puts an 1.8 mm wall into a 0.6 mm gap: **1.2 mm of interference**,
six times the `cowl_flange_tolerance` that exists to absorb print variation.

**Decision: a `slicing` group, holding a perimeter count per part.** Not one figure for the
airframe — that would assert a constraint between independently sliced parts that does not
exist. The group names a count for each part kind, and the couplings are expressed where they
actually are and in the direction they actually run.

**`cowl_n_perimeters` has three consumers, and it is the *cowl's* count in all three** — the
bulkhead's own perimeter count is irrelevant to any of them, because each of these dimensions
is sized around the wall of the cowl:

1. **The cowl's rib thickness**, $2 w n + t_{\text{cut}}$ (OQ-DES-CW3), for whenever the rib is
   modelled (IP-FC-17, IP-FC-23). Until a count is fixed the rib has no single thickness: 1.3 mm
   at one perimeter against 3.7 mm at three, on the only stiffening structure the part has.
2. **The cowling bulkhead's flange radius**, which becomes
   `corner_radius - cowl_n_perimeters * extrusion_width - cowl_flange_tolerance`. Named for
   whose count it is, so nobody later reads it as the bulkhead's own.
3. **The nose cowl's base offset** — the `offset(r = -nose_flange_inset)` that insets the
   projected OML outline to form the base flange in `nose()`.

**One sub-choice was left open, and it was the only thing blocking consumer 3. Settled
2026-08-21, and the geometry did not move.** `nose_flange_inset` is **0.5 mm** and one
extrusion width in the sweep is **0.6 mm**, so unlike the flange radius — where substituting
`cowl_n_perimeters = 1` is byte-identical — the base offset had to be shown to be a function
of the perimeter count before it could be written as one. It is: the nose shape seats on top
of the cowl's perimeter shell and is bonded there, and the inset is what gives that joint its
alignment and its bonding surface. The offset is therefore
`cowl_n_perimeters * extrusion_width + nose_flange_tolerance` with
**`nose_flange_tolerance = -0.1`**, which at the sweep's 0.6 returns exactly the 0.5 mm every
nose cowl has been built with. The literal is gone, the parameterization now says what the
number depends on, and **no face moved** — verified across all 576 variants with no existing
parameter changing value. `design_constants.json`'s blanket refusal of negative tolerances was
removed to allow it, on the grounds that the assumption behind the rule had never been checked.
Recorded in full as [OQ-DES-CW10](#open-questions).

**A wrong turn is recorded here because it was convincing and it was wrong.** This note
originally argued that `0.5 = 0.4 + 0.1` — one perimeter at the hand drivers'
`extrusion_width = 0.4`, plus the 0.1 mm `panel_tolerance` uses — and concluded from that
apparent provenance that the sweep's offset "should" be `1 × 0.6 + 0.1 = 0.7 mm`, leaving the
flown parts 0.2 mm tight. **The 0.4 is a development test value.** It was never a tuned
parameterization, so an expression that lands exactly on it carries no information at all, and
the whole inference was arithmetic dressed as evidence. The sweep's parameterization is the
correct one and the only one any dimension here should be reasoned about through.

The related temptation, equally wrong, was to reach for `cowl_flange_tolerance = 0.2` on the
grounds that the cowl-to-bulkhead joint is the same kind of bonded lap. It is the same kind of
joint and **not the same fit** — which is exactly why the two are separate parameters, and why
neither one's value may be inferred from the other's.

**What does not change.** The perimeter count for any solid part remains unrecorded and must
not be invented — there is still no slicer profile in the repository. The `slicing` group gets
a cowl entry because the cowl's count has consumers; other kinds get entries when theirs do.

*Implementation: IP-FC-42.*

### ~~OQ-DES-CW10 — Is the nose cowl's base offset a function of the nozzle?~~ — RESOLVED 2026-08-21: yes, and the built value is correct

**Answer: yes.** The nose shape seats on top of the cowl's perimeter shell and is bonded
there — the same kind of lap joint the cowl makes when it slides onto the cowling bulkhead's
flange. The inset is what gives that joint both its **alignment** and its **bonding surface**,
so it is a function of the shell it lands on, and therefore of the perimeter count and the
extrusion width. `cowl_n_perimeters * extrusion_width + nose_flange_tolerance` is the right
form, which is what IP-FC-42 implemented.

**The value is `nose_flange_tolerance = -0.1`, and the geometry does not move.** At the
sweep's `extrusion_width = 0.6` and one perimeter that gives 0.5 mm, which is what every nose
cowl has been built with and what it should be built with. **The sweep's parameterization is
the correct one**; expressing the offset through it was the whole point, not a step toward
changing it.

**A negative fit and a bonded joint are not in conflict**, which is where this question went
wrong. The alignment fit and the bond are not the same surface: the inset locates the parts,
and the joint is glued on the face it seats against. Reading the sign of the fit as though it
decided whether the joint could be bonded is the error, and it is recorded here because it is
easy to make again.

**Two things must not be carried forward from the analysis that produced this question.**

1. **`0.5 = 0.4 + 0.1` is not provenance.** The hand drivers' `extrusion_width = 0.4` is a
   **development test value**. It was never an official tuning, so a decomposition that lands
   exactly on it is a coincidence of leftover test numbers. That arithmetic was treated here
   as the strongest evidence available and it was worth nothing — it is the reason this
   question twice concluded the sweep's offset should be 0.7 mm, which is wrong. No dimension
   in this project should be reasoned about through the 0.4 figure.
2. **`cowl_flange_tolerance` does not set this value.** The cowl-to-bulkhead joint and the
   nose base joint are both glued, and their **fits are different**. That is precisely why
   they are two parameters rather than one, and the 0.2 mm on the other joint says nothing
   about this one.

*Implementation: IP-FC-42, complete — no re-render, no baseline departure.*

### ~~OQ-DES-CW11 — Which group does the overhang angle belong in?~~ — RESOLVED 2026-08-21: `slicing`

**Decision: alternative 2, the `slicing` group.** Choosing an overhang angle is a slicing
concern. It is not a property of the machine, so `printer` was wrong for it — that group's
own rule is *"the same airframe printed on a different nozzle wants different numbers here and
no other change"*, and this number does not move with the nozzle. `slicing` already exists for
quantities that are neither machine nor design, which is what OQ-DES-CW9 created it for.

**And it is not a free parameter, which matters more than the group does.** Being categorically
a slicing setting does not make this one safe to re-tune whenever the material or the perimeter
count changes:

- **It has to agree with where the break line between the nose and the cowl falls.** The angle
  and the split location are two halves of one decision about how the part comes off the bed.
- **Changing it means adjusting the buttresses to match**, since `buttress_shape()` builds
  every leading and trailing ramp from `r_inset * tan(angle)`.
- **As the nose is currently designed, the angle is baked into the part.**

**Nothing in the code enforces either coupling.** Both are geometry a person would have to
move by hand, so editing this value alone yields a part that builds, renders, passes every
check this project has, and is wrong. That is why the constant carries the warning rather than
just the number — the group tells a reader what kind of thing it is, and only the entry can
tell them what else has to move with it.

**Two consequences for the schema, both landed.**

1. **`slicing` is no longer one kind of quantity, so the validator is per key.** A perimeter
   count is a whole number of loops; an overhang angle is continuous. One rule cannot serve
   both — "positive number" would admit half a perimeter, "whole number" would refuse 35.5° —
   so `_check_slicing` dispatches on the name, and a name with no rule is **refused** rather
   than passed through unchecked. The angle is required to lie strictly between 0 and 90:
   0 is a flat ceiling with no slope to print, the geometry divides by its tangent, and 90 is
   a vertical wall needing no relief.
2. **`slicing` is not uniformly per part.** A perimeter count is, because parts are sliced
   independently. An overhang angle is a limit of the process and applies to whatever is being
   printed. The group's `_about` says so rather than leaving the CW9 wording to be read as a
   rule it was never meant to be.

**Renamed, and moved from four places to one.** `cone_angle` said what it happened to build
rather than what it means; it is now `overhang_angle_from_bed`, which states the reference
frame OQ-DES-CW2 had to establish. It was written out four times — twice in the cowl parameter
files and twice in the hand drivers — and is now a single entry in `design_constants.json`.

**Verified geometry-neutral**, as a rename must be: all seven GUI drivers render the same
131,506 triangles before and after, compared as sorted facet sets rather than bytes, and the
sampled sweep agrees on every cowl. `audit_call_args.py` reports no positional mismatch across
the renamed signatures.

*Implementation: IP-FC-28, complete.*

### OQ-DES-CW12 — What measures whether a ported part is correct, now that volume cannot

**Problem.** The FreeCAD port checks each part it builds by comparing the volume of material
it encloses against the volume of the same part built by the existing OpenSCAD generator, and
accepts the part when the two agree to within 0.010%. IP-FC-12 records the boom bulkhead
passing at 0.00110%.

That check reads the volume from FreeCAD's `Shape.Volume`, which computes it from the
mathematical surfaces bounding the solid rather than from any approximation of them. Measured
2026-08-31, that figure is not accurate enough for parts whose surfaces are **freeform** —
the smoothly curving surfaces used for an aircraft's outer shape, stored as control points —
rather than the planes, cylinders and cones every part ported so far is made of:

| shape | reported volume error |
| --- | --- |
| a sphere built as a primitive | **0.000000%** at r = 5, 25, 50 and 100 mm |
| the *same sphere*, converted to a freeform surface | **−0.0437%**, identically at all four radii |
| the nose cowl's outer surface | **+0.077%** |
| the tail cowl's outer surface | **+6.79%** |

The tail's figure is not caused by the defect in [OQ-DES-CW13](#open-questions) — it is
unchanged after that defect is repaired. Three independent measurements of the tail (summing
the volume enclosed by its triangles, summing each surface patch's contribution separately,
and the triangle mesh OpenVSP exports directly) agree with one another to better than 0.02%
and all disagree with `Shape.Volume`.

So the acceptance tolerance is four times tighter than the instrument's own error on the
simplest possible freeform shape, and roughly 700 times tighter than its error on the tail.
Every cowl would fail the check while being geometrically correct. The more serious risk runs
the other way: because the error is not bounded in a known direction or magnitude, a cowl that
really is wrong could pass.

Parts already ported are unaffected. The corner, both bulkheads and the boom bulkhead are
built entirely from planes, cylinders and cones, where the figure is exact — the sphere
primitive row above is the evidence that the instrument is sound on those.

**Alternatives.**

1. **Measure the volume enclosed by the triangles instead.** Convert the finished solid to a
   triangle mesh at the tessellation setting the export already uses, and sum the volume those
   triangles enclose. *Benefits:* it is the same quantity the OpenSCAD side reports, since that
   side is triangles all the way down, so the comparison becomes like-for-like rather than
   surface-against-triangles; it needs about fifteen lines and no new dependency; and it agreed
   with OpenVSP's own mesh to 0.001% on the tail. *Drawbacks:* the answer depends on the
   tessellation setting, so the tolerance has to be stated against a fixed one; it is slower,
   by roughly a second on the tail. *Prerequisites:* none.
2. **Compare the surfaces directly, with `tools/surface_distance.py`.** Ask how far the ported
   surface lies from the reference surface at its worst point. *Benefits:* it answers the
   question the tolerance is really asking — has the shape moved — in millimetres, which is
   inspectable against a print tolerance; a volume check can pass while a surface is locally
   wrong by compensating errors. *Drawbacks:* it needs a reference mesh for every part, which
   only the cowls currently have; it is much slower. *Prerequisites:* deciding the acceptance
   distance, which is not the same question as the acceptance volume.
3. **Keep `Shape.Volume` but loosen the tolerance for freeform parts.** *Benefits:* no new
   code. *Drawbacks:* the loosened tolerance would have to be about 10%, which is wide enough
   to admit a badly wrong part; and it would have to be justified per part rather than
   derived, since the error is not predictable from the shape. *Prerequisites:* none.
4. **Compare cross-sectional areas at stations along the part.** *Benefits:* localizes a
   disagreement instead of reporting one number, which would have shortened this
   investigation considerably. *Drawbacks:* substantially more code; sectioning a freeform
   solid has its own failure modes, several of which were hit while diagnosing CW13.
   *Prerequisites:* none.

**Recommendation.** Alternative 1, because it makes the two sides of the comparison the same
kind of measurement, and it is the smallest change. Alternative 2 is worth adding afterwards
for the cowls specifically, since a cowl is a shape rather than an assembly of features and
"the surface has not moved by more than *x* mm" is the statement that actually matters for
one. Alternative 3 should be rejected: a tolerance wide enough to accommodate this instrument
is too wide to catch the errors the check exists to catch.

### OQ-DES-CW13 — Where the tail's folded aft closure gets fixed

**Problem.** The tail's outer surface is exported from OpenVSP as twelve freeform patches.
Four of them — the flat closure across the aft opening — are malformed. All four lie in a
single plane, as a flat closure should, but the mathematical description **doubles back on
itself**, covering part of that plane twice, facing opposite ways.

Measured 2026-08-31. On those four patches the surface's facing direction reverses across a
contiguous band covering a quarter to a third of the patch. The reversals are real rather than
numerical noise: they occur where the surface is well-conditioned (a well-behaved region
scores about 0.89 on the relevant measure; the reversed samples score 0.43, and only 9 of
roughly 120 lie on the patch edge, which is the one place a reversal would be meaningless).
Every other patch on the tail, and every patch on the nose — **including the nose's own aft
closure, the same kind of feature** — shows zero reversals.

The consequence is that cutting operations fail near the tail's aft end. Cutting the tail
blank with a cylinder passing through it returns *nothing* at 9 of 20 tested positions, all in
the upper half; the general-purpose splitting operation returns 3 pieces where a sound solid
gives 4; and relaxing the tolerance to 0.001 mm and 0.01 mm changes neither. The tail cowl is
built by cutting buttress tools out of this blank, so as it stands this blocks the tail cowl.

**No export setting avoids it.** Of the STEP options the model carries, only surface splitting
changes what `ExportFile` writes — merge-points, representation and tolerance produce a
byte-identical file, matching the behavior already recorded for `CADLenUnit` in
`tools/oml_export.py`. Splitting is what creates the closure patches at all: with it off, each
part exports as a single uncapped surface that cannot be closed into a solid. So there is no
setting that yields a closed tail without yielding these four patches.

**Alternatives.**

1. **Rebuild the closure when the surface is imported.** Discard the four patches and close
   the opening with one flat face built from the boundary the remaining eight leave behind.
   *Benefits:* measured 2026-08-31 to fix the cutting failures completely — 0 of 20 positions
   fail, against 9 before — and to be shape-preserving: the repaired solid encloses
   594449.974 mm³, identical to the original. About twenty lines, confined to the import.
   *Drawbacks:* the repository's surface no longer matches what OpenVSP wrote, so a reader
   comparing them finds a difference that only the importer explains; and the repair is
   specific to a *flat* closure, so a future model whose tail closes with a curved surface
   would need it revisited. *Prerequisites:* none — implemented.
2. **Fix the closure in the `.vsp3` model.** Change how the tail's aft end is built so the
   exporter produces a sound closure. *Benefits:* fixes it at the source, so every consumer
   benefits and no importer carries a special case. *Drawbacks:* it is not yet known what in
   the model provokes it, so the work is open-ended; it changes the airframe definition, which
   invalidates the recorded provenance hash and every exported artifact. *Prerequisites:*
   finding the provoking feature, which needs an experiment the aft closure's construction
   would have to be varied in.
3. **Trim the aft end away before use.** The tail cowl is open at both ends (§6.2), so the
   closure may be cut off by the part's own trimming before any buttress is cut. *Benefits:*
   no repair code at all, if it holds. *Drawbacks:* it has not been shown to hold — it depends
   on where `cut_len` falls, and it would silently stop holding if that changed; and it leaves
   an unusable blank in the repository for every other consumer. *Prerequisites:* confirming
   the trim always removes the affected region, at every unit size in the sweep.
4. **Export IGES instead of STEP.** `oml_export.py` already supports it. *Benefits:* a
   different exporter path might not produce the fold. *Drawbacks:* entirely unknown whether
   it helps; IGES carries less topology than STEP, so the sewing step could be worse rather
   than better. *Prerequisites:* one experiment.

**Recommendation.** Alternative 1, and it is what the port uses, because it is measured,
small, reversible, and provably does not change the shape. Alternative 2 is the durable fix
and should follow once the port is running, at which point there is a working comparison to
verify a model change against — which there is not today. Alternative 3 should not be relied
on even if it happens to be true, because it makes a part's correctness depend on a trim
length that nothing checks.

### ~~OQ-DES-CW14 — Should the buttress positions be editable values?~~ — WITHDRAWN 2026-08-31

**Withdrawn: already decided, and the framing was wrong.**
[OQ-DES-CW4](#open-questions) resolved this on 2026-08-09 — *"the full fix wants a list of
buttress placements rather than a fixed set of named groups"*. Placement becomes data at the
port. There was nothing left to ask.

Two things were wrong with asking it again. It re-opened a settled decision, which costs a
reader the work of re-deciding something the document already answers. And by offering "keep
them in the code" as an alternative and questioning whether the present angles are "deliberate
or incidental", it put the rib layout itself up for negotiation. **The ribs are designed
structure.** They are the cowl's only internal load path, and the mechanism that produces them
under a print mode that admits no other (§4, §6.4). Nothing about the port removes, moves or
reconsiders them.

*Implementation: the eleven tail placements and the nose's one become sheet rows under
IP-FC-12, per CW4.*

### ~~OQ-DES-CW15 — How much of a cowl document should survive changing the outer shape?~~ — WITHDRAWN 2026-08-31

**Withdrawn: speculative.** It asked what a cowl document should do if the aircraft's outer
shape were replaced. No such shape exists or is planned; the question invented a scenario and
asked for a decision about it, which is design effort spent on something that may never happen
and a decision made without the case that would inform it.

The nose tip's lip is derived from the outer surface the model actually has, which is what §1
establishes as the definition. If the airframe is ever reshaped, cowls are regenerated — the
OML provenance record ([OQ-DES-CW7](#open-questions)) already exists to make that change
visible, and it is the point at which a real question could be asked with a real case behind
it.

### OQ-DES-CW16 — How is a cowl document built, when FreeCAD's document booleans get it wrong?

**Problem.** A cowl is made by cutting slots into the aircraft's outer surface. The outer
surface arrives as a NURBS solid (the tail's is nine faces of degree 5×3 with 139 control
points along the body). The slots are 0.1 mm wide and do not scale with the aircraft — they
are fold lines for vase-mode printing, not gaps, and two of the tail's eleven slots cross each
other inside the solid at ±30°. Cutting a 0.1 mm slot across another 0.1 mm slot in a curved
NURBS body is the hardest case a solid modeller meets, because the two sides of a slot are
0.1 mm apart while the curves bounding them are computed by approximation.

A FreeCAD document is made of *document objects* — a `Part::Cut`, a `PartDesign::Pocket` — and
those are what make a saved file editable: change a number and the objects recompute. FreeCAD
also exposes the same operations directly on geometry, as `Part.Shape` methods, which are not
document objects and do not recompute on their own.

**Measured 2026-09-01 on FreeCAD 1.1.1, the two do not agree, and the document objects are the
ones that are wrong.** With byte-identical inputs — the same half-body, the same cutter:

| route | faces | valid | `Shape.Volume` | tessellated volume |
|---|---|---|---|---|
| `Part.Shape.cut` (not a document object) | 39 | yes | 308777.93 | 297004.19 |
| `Part::Cut` (document object) | 69 | no | 310563.18 | 232547.58 |
| `PartDesign::Boolean` | 69 | no | — | — |
| `PartDesign::Pocket`, slots cut in sequence | — | no | — | — |

The document result is not the right solid with a pedantic flag on it. It loses 68 mm³ of
material that the correct result has, it carries six invalid faces including one whose
boundary does not close, and it tessellates 22% smaller — so it would print wrong, not merely
report oddly. All three document routes give the same wrong answer because in FreeCAD 1.1 they
share one `TopoShape` layer, which emits `TopoShapeExpansion.cpp: hasher mismatch` throughout.
The same layer inflates tolerances generally: two plain 10 mm boxes fused by `Part::MultiFuse`
come out at 1.3e-05 where `Shape.fuse` gives 1.5e-07.

**What the document layer is doing is reproducible from the geometry API.** `Part.Shape.cut`
takes an optional fuzzy tolerance, and sweeping it reproduces the document's answer:

| fuzzy | faces | valid | volume |
|---|---|---|---|
| 0, 1e-09, 1e-07 | 39 | yes | 308777.93 |
| 1e-06 | 68 | yes | 310343.13 |
| 1e-05 | 68 | yes | 310367.26 |
| *the document* | 69 | no | 310563.18 |

So the document booleans behave as though a fuzzy value of about 1e-06 or larger were applied,
where the correct answer needs 1e-07 or tighter. **Nothing exposed changes it**, each of these
measured 2026-09-01 and each leaving the result at 69 faces and invalid: tightening both
operands with `fixTolerance` to 1e-07 and 1e-08 (the operands are already 3.8e-07 and 1.5e-07);
`Document.UseHasher = False`; clearing `_ElementMapVersion`, which the object rewrites;
`Refine`; a cutter cleaned to 1.5e-07. On 1.1.1 the boolean features' entire property list is
`Base`, `Tool`, `Refine`, `Placement`; on 1.1.3 `Part::Cut`'s list is unchanged and only
PartDesign gained a `FuzzyTolerance`. An earlier version of this paragraph also said there was
no fuzzy or tolerance preference anywhere in the parameter tree. **That was wrong** — there is
one, `Mod/Part/Boolean/BooleanFuzzy`, and setting it to 0 resolves this outright. See *What
1.1.3 changed* below, which carries the correction and the measurements.

**Rearranging the model does not avoid it either**, all measured: eleven separate cuts, the six
connected groups, a single `Part::Compound` tool, chained pairwise `Part::Fuse`, diagonals first
or last, the crossing pair pre-fused into one tool, `PartDesign::Pocket` per slot,
`PartDesign::Boolean` with the whole cutter, re-expressing the cut as an intersection with the
cutter's complement, and building the model 10× and 100× oversize so the 0.1 mm feature sits
further above OCC's absolute 1e-07 confusion. Cutting the full body before masking rather than
after — which is free set algebra, `(blank ∩ mask) − cutter` being `(blank − cutter) ∩ mask` —
returns an *empty* solid. The geometry API gets the right answer in every one of these
arrangements, including plain sequential cuts.

**What 1.1.3 changed, and what it did not.** Everything above was measured on FreeCAD 1.1.1.
FreeCAD 1.1.3 (rev 20260725) adds a `FuzzyTolerance` property to `PartDesign::Boolean`, and it
does exactly what it says — but it reaches one of the cowl's operations and not the other two.
All of the following measured 2026-09-01 on 1.1.3, against the same tail half and cutter.

*The cut is fixed.* With one clean tool and `FuzzyTolerance = 0`, `PartDesign::Boolean`
reproduces the reference solid with **zero** symmetric difference:

| route | faces | valid | `Shape.Volume` | symmetric difference |
|---|---|---|---|---|
| `Part.Shape.cut` (the reference) | 39 | yes | 308777.9299 | — |
| `Part::Cut` | 69 | no | 310563.1768 | 6.84e+01 |
| `PartDesign::Boolean`, `FuzzyTolerance = −1` (auto) | 69 | no | 310563.1768 | 6.84e+01 |
| `PartDesign::Boolean`, `FuzzyTolerance = 0` | 39 | yes | 308777.9299 | **0** |

`FuzzyTolerance` is an ordinary stored property, so it survives a save. Values of 1e-12, 1e-09
and 1e-07 give the same exact result; `Part::Cut` still has no such property.

*The fuse and the intersection are not.* A cowl is not one cut. The tail fuses its eleven
tools into a cutter, and both cowls intersect the blank with masks. Both come out wrong:

* **Fuse.** `PartDesign::Boolean` of type `Fuse` returns a *compound* rather than a union, at
  every fuzzy value tried (−1, 0, 1e-09, 1e-08, 1e-07, 1e-06). Fusing `Top1` with `Diag11`,
  which overlap by about 1.1 mm³, returned two solids totalling 2015.7495 — exactly the sum of
  the two inputs, with none of the overlap removed. Over the six overlapping tools it gives
  6065.3155 where the correct union is 6061.7611.
* **Common.** The nose's first mask intersection — a box against the NURBS blank — comes back
  with 5 faces where the reference has many, +4067.96 mm³, and a tolerance of 19.7 mm. Carried
  through, a fully stock nose ends as 4 solids with a symmetric difference of 1.84e+05. Retested
  with the *global* fuzz off as well (below), it is worse, not better: it returns an **empty
  shape** for the tail's lower mask, which covers the whole blank and should be a no-op.

Both of those were first measured with the global fuzz still at its default, relying on the
per-feature property alone; they were re-measured at `BooleanFuzzy = 0` and are unchanged for
`Fuse` (still a two-solid compound, +3.554461 mm³) and worse for `Common`. So these are real
defects in those operations, not fuzz.

**`PartDesign::Pocket` does work, and an earlier note here saying otherwise was wrong.** The
1.1.1 table above records it as going invalid at the second diagonal. Re-rigged properly on
1.1.3 — eleven pockets, each the buttress sketch carried on the slab's placement, `Midplane`
with `Length = buttress_cut_thickness`, `FuzzyTolerance = 0` — **all eleven succeed and every
one is a single valid solid.** It is still not the right part: the chain ends at 66 faces and
+561.60 mm³ against the reference's 39, because a pocket subtracts one profile at a time and
subtracting the crossing tools in sequence is not the same as subtracting their union. That is
the same 0.18% error the geometry API gives for sequential cuts, and it is 18× the project's
0.010% tolerance. The obstacle is the missing union, not PartDesign's ability to cut.

*Why no arrangement of stock `Part::` objects can supply the clean tool the cut needs.* The
tolerance a stock boolean records is proportional to the size of its operands — measured at
**7.0e-07 per mm of bounding-box diagonal**, from two independent cases: the six overlapping
tools (diagonal 170.3 mm) record 1.20e-04, and all eleven (diagonal 371.2 mm) record 2.63e-04.
The cut's requirement, by contrast, is *absolute*: 1.5e-07 gives the exact answer and 1.0e-06
already gives 68 faces and +1565 mm³, with nothing working in between. A stock-built tool is
therefore clean enough only if it fits inside a box about **0.2 mm** across, which no part does.

The geometry is not what is wrong. `Part::MultiFuse` followed by `Part::Cut` reproduces the
reference cutter to **±0.000000 mm³**. Forcing that stock cutter's tolerance down with
`fixTolerance` restores a 39-face valid result; forcing the clean cutter's tolerance *up* to
the stock value reproduces the 69-face invalid one. The recorded tolerance is the entire
defect — and nothing stock re-records it: `Part::Refine`, `Part::Mirroring` applied twice about
the same plane, and `Draft::Clone` at scale 1 each return the identical shape at the identical
2.63e-04.

**But the fuzz is a preference, and turning it off fixes everything.** This corrects an earlier
claim in this document, which said no such preference existed. It does. From PR #17119's own
diff, the value is read once at startup in `AppPart.cpp`

    hGrp = ...GetGroup("Mod/Part/Boolean");
    Part::FuzzyHelper::setBooleanFuzzy(hGrp->GetFloat("BooleanFuzzy", 10.0));

and applied in `FCBRepAlgoAPIHelper::setAutoFuzzy()` as

    op->SetFuzzyValue(getBooleanFuzzy() * sqrt(bounds.SquareExtent()) * Precision::Confusion());

`sqrt(SquareExtent)` is the bounding-box diagonal, so at the default of **10.0** the applied
fuzz is 1.0e-06 per mm of diagonal — which is the measured 7.0e-07 per mm of *recorded*
tolerance above, and explains it exactly. Two things had hidden it: the earlier search looked
only for 7-bit ASCII in the binaries, where a Windows build may hold the string otherwise; and
the value is read **once at module load**, so setting the parameter from a running session —
which is how it was first tested — cannot change anything.

Set `BooleanFuzzy = 0` before FreeCAD starts and the stock objects become correct. Measured
2026-09-01 on 1.1.3, against the same reference:

| | recorded tolerance | result |
|---|---|---|
| `Part::MultiFuse`, default fuzz | 2.63e-04 | — |
| `Part::MultiFuse`, `BooleanFuzzy = 0` | **2.12e-07** | geometry unchanged, ±0.000000 mm³ |
| `Part::Cut`, default fuzz | — | 69 faces, invalid |
| `Part::Cut`, `BooleanFuzzy = 0` | — | **39 faces, valid, symmetric difference 0** |

Carried through the whole part, with every boolean a stock `Part::MultiCommon`, `Part::MultiFuse`,
`Part::Cut` and `Part::Mirroring`, and nothing scripted in the chain:

    tail  stock solids=1 faces=74  valid=True  | scripted faces=74  | symmetric difference 0
    nose  stock solids=1 faces=64  valid=True  | scripted faces=64  | symmetric difference 0

So the three things that could not previously hold at once — correct geometry, a document that
re-solves in stock FreeCAD, and nothing of this project's installed — **all hold**, at the cost
of one preference set on each machine that opens the file. That is alternative 6.

*Further arrangements ruled out on 1.1.3*, adding to the list above: cutting by the eleven
tools separately rather than by their union (69 faces, +1496 mm³, tolerance 0.266); cutting by
a `BooleanFragments` decomposition of the overlapping group into 32 disjoint pieces, which is
itself exact and clean (±0.000000 mm³ at tolerance 2.12e-07, via FreeCAD's own `BOPTools`
scripted features, which take an explicit tolerance) but gives 52 faces and +1149 mm³ when cut
with; and cutting slot by slot in sequence (70 faces, invalid). One of these does not merely
return the wrong solid — `PartDesign::Boolean` handed all eleven tools at the stock tolerance
of 1.4e-04 ran for 24 minutes and then died of `Not enough memory available`, the same
pathology as the 4.4 GB build recorded in IP-FC-12. A tool at stock tolerance is not a
degraded input to these operations; it is one they cannot complete.

*One thing worth keeping from this.* Only **one** fuse in the tail is load-bearing. The eleven
tools form six disjoint solids, and only one group of six actually overlaps — `Top1`, `Top2`
and the four diagonals. Cutting by that group's union and then by the five remaining slabs
separately reproduces the reference exactly. So the scripted surface could in principle shrink
from seven nodes to one. It is not worth doing on its own: a single blocked module import
stops a document restoring just as completely as seven do, so it buys no deployment and costs
a construction the two cowls would no longer share.

The port therefore builds the cowls through a small scripted document object (`_ShapeBoolean`
in `cowl_tree.py`) that performs the operation with `Part.Shape` and stores the result. It is a
real document object — it links its operands, recomputes when the spreadsheet changes, and is
saved and reloaded — and with it both cowls come out geometrically identical to the reference
implementation, exactly zero difference in both directions.

**The cost is deployment.** FreeCAD 1.1 refuses to restore a scripted object whose defining
module is not FreeCAD's own or an installed addon:

    PropertyPythonObject::Restore: blocked import of module 'cowl_tree' during document
    restore. Only modules from FreeCAD or installed addons are permitted.

There is no preference anywhere in FreeCAD's parameter tree that grants trust; the decision is
made purely from where the module sits on disk. So opening `tail_U1.FCStd` on a machine that
has only FreeCAD gives a document that *displays the correct part* — the geometry is saved, and
the spreadsheet, sketches, extrusions, wedge and datum placements all restore — but the seven
boolean nodes come back inert, so changing a parameter rebuilds nothing. The document is
correct and readable; it is not re-solvable.

This affects nobody in the project's own toolchain: the sweep and `build_part.py` import
`cowl_tree` before opening anything, so they rebuild normally. It affects a person handed a
`.FCStd`.

**Alternatives.**

1. **Keep the scripted object; ship documents that display but do not re-solve.** The geometry
   is right, the parameter sheet and the whole feature tree are visible and inspectable, and
   anyone regenerating a variant does it through the sweep, which works. *Benefits:* nothing to
   install, no geometry compromise, no further work. *Drawbacks:* a recipient cannot change
   `U` in the GUI and get a new part; the boolean nodes show as errors on open, which looks
   like breakage even though the part is correct. *Prerequisites:* none.

2. **Ship the cowl modules as a FreeCAD addon.** Place them under a FreeCAD `Mod` path so the
   restore is permitted. *Benefits:* fully live documents — open, change `U`, recompute.
   *Drawbacks:* makes the project a FreeCAD extension, which is a deployment posture the
   project has not chosen; every recipient needs the install, and it must be kept in step with
   the repository. *Prerequisites:* deciding where the addon lives and how it is versioned
   against the source tree.

3. **Widen the slots until the document booleans cope.** The failure is specific to 0.1 mm
   features; a wider slot may be within what `Part::Cut` handles. *Benefits:* a fully stock
   document with no scripted objects at all. *Drawbacks:* changes the printed part. The slot
   width is not free — it is a vase-mode fold line, deliberately unscaled (§6.3), and widening
   it turns a fold into a gap. *Prerequisites:* measuring the width at which the document
   boolean becomes correct, then deciding whether the resulting part is still the design. This
   has not been measured.

4. **Build against a FreeCAD that does not apply automatic fuzz.** **This is a known upstream
   regression, identified 2026-09-01.** FreeCAD [PR #17119](https://github.com/FreeCAD/FreeCAD/pull/17119),
   merged October 2024 and shipped in 1.1, made every boolean in every core workbench apply an
   automatic fuzzy value computed as `BooleanFuzzy × Precision::Confusion() × size of the part
   in mm`. For this half — bounding box 100.08 × 50 × 100, diagonal 150.06 mm — that is about
   1.5e-05, and the table above shows the correct answer needs 1e-07 or tighter. It explains
   every observation: why `Part::Cut`, `PartDesign::Pocket` and `PartDesign::Boolean` agree with
   each other and not with `Part.Shape.cut`, and why no rearrangement helps. Upstream states the
   change "is also known to cause several regressions".

   [PR #31249](https://github.com/FreeCAD/FreeCAD/pull/31249), in **1.1.3**, adds a
   `FuzzyTolerance` property so a feature can ask for pre-1.1 non-fuzzy behaviour. Two limits:
   the changelog entry is *"PD: Add FuzzyTolerance property"* — PartDesign, not `Part::` — and
   1.1.x deliberately **keeps auto-fuzz as the default**. **1.1.3 was installed and tested on
   2026-09-01, and it does not resolve this.** It fixes the cut exactly — `PartDesign::Boolean`
   at `FuzzyTolerance = 0` reproduces the reference solid with zero symmetric difference — but
   PartDesign's `Fuse` returns compounds instead of unions and its `Common` collapses the NURBS
   intersection, so the cowl's other booleans are worse off than before, and no stock `Part::`
   object can supply the clean tool the fixed cut needs (all measured, *What 1.1.3 changed*
   above). An earlier version of this alternative said **26.3 reverts to pre-1.1 behaviour, no
   fuzziness by default**, citing `FeaturePartBoolean.cpp` on `main` as carrying no fuzzy
   property. **Both halves of that are withdrawn (2026-09-01).** The file check was of the wrong
   file — the fuzz has never lived there; it is applied in `FCBRepAlgoAPIHelper::setAutoFuzzy()`
   in `FCBRepAlgoAPI_BooleanOperation.cpp` and configured from `AppPart.cpp`. And the 26.3
   release notes say only that *"a Fuzzy Tolerance property was added to override the default
   fuzziness/tolerance for boolean operations determined from the size of the input shapes"* —
   a knob, not a revert — with the release date still a placeholder.

   **Checked directly against `main`, and this alternative is ruled out** (2026-09-01). On the
   branch 26.3 comes from: `FCBRepAlgoAPI_BooleanOperation`'s constructor still calls
   `setAutoFuzzy()` *unconditionally*; `AppPart.cpp` still reads `BooleanFuzzy` with the same
   default of **10.0**; and `Part::Boolean`'s property list is still just `Base`, `Tool`,
   `History`, `Refine`, with no per-feature `FuzzyTolerance`. So 26.3 neither disables the fuzz
   by default nor lets a `Part::` boolean override it per feature. The `FuzzyTolerance` the
   release notes describe is a PartDesign property, it is already present in 1.1.3, and
   PartDesign cannot build this part for reasons unrelated to fuzz. Waiting for 26.3 would
   change nothing; alternative 6 is the route, and the same preference exists on `main`, so it
   keeps working across the upgrade.

   *Benefits:* the only alternative that gives up nothing — correct geometry, a document that
   re-solves in stock FreeCAD, no addon, no design change, and nothing of this project's placed
   inside FreeCAD. On such a build the scripted objects come out and this question closes.
   *Drawbacks:* 26.3 is not released — it is planned for Q4 2026 under the new CalVer scheme and
   its release-notes page still carries a placeholder date — so this is a wait unless a weekly
   development build is used; and pinning a version is itself a constraint on whoever opens the
   files. 1.1.3 is now ruled out, so the wait is for 26.3 specifically rather than for the next
   1.1.x. *Prerequisites:* running the reproduction above against a build of `main`. Weekly
   development builds are published and would answer it now. Note this is not alternative 2:
   changing which FreeCAD is used adds nothing of this project's to FreeCAD.

5. **Flatten the boolean nodes when the document is saved**, replacing each with a plain
   `Part::Feature` holding its computed shape, and keep the sketches, spreadsheet and
   expressions. *Benefits:* opens anywhere with no errors and no install. *Drawbacks:* gives up
   re-solving deliberately rather than accidentally — the same capability as alternative 1,
   presented honestly instead of as a broken node. *Prerequisites:* none.

6. **Build the cowls from stock objects, and set `BooleanFuzzy = 0`.** Add the key
   `BooleanFuzzy` with value `0` under `BaseApp/Preferences/Mod/Part/Boolean` — in the GUI,
   Preferences → Part → Boolean — which restores pre-1.1 boolean behaviour for that FreeCAD
   install. Every boolean in both cowls then becomes an ordinary `Part::MultiCommon`,
   `Part::MultiFuse`, `Part::Cut` or `Part::Mirroring`, and the blank's scaler an ordinary
   `Draft::Clone`, so nothing scripted remains and the document restores and re-solves
   anywhere. **Measured 2026-09-01 on 1.1.3:** both cowls come out at exactly zero symmetric
   difference against the current build, with matching face counts (74 tail, 64 nose), and the
   `Draft::Clone` blank matches `_ScaledSurface` at zero difference and still tracks `U`
   (200.000 mm at `U` = 2). *Benefits:* correct geometry, a fully live document in stock
   FreeCAD, no addon, no design change, and it works on the FreeCAD already installed rather
   than on a version that does not exist yet. *Drawbacks:* it is a per-install setting, so a
   recipient must apply it too, and a document that silently depends on a preference is a trap
   if it travels without that instruction — the failure would be a wrong part rather than an
   error. It also changes boolean behaviour for everything else in that install, and upstream
   introduced the automatic fuzz to fix real failures for other users (PR #17119 lists eight
   issues), so turning it off may reintroduce those elsewhere. *Prerequisites:* deciding how the
   setting travels with the file, and — since the value is read once at startup — making the
   sweep and `build_part.py` set it before FreeCAD loads rather than after.

**Recommendation (revised 2026-09-01).** **Alternative 6.** It is the one that gives up
nothing, and unlike alternative 4 it is measured and available today rather than waiting on an
unreleased version. Everything below this paragraph was written before `BooleanFuzzy` was
found and is kept because the reasoning still holds for the other five: it is the argument for
why, *if the fuzz cannot be turned off*, the remaining alternatives all trade something away.
The premise it rests on — that correct geometry requires the `Part.Shape` API — is exactly what
alternative 6 removes.

The one thing alternative 6 needs decided is how the preference travels with a file, because a
document that depends on a setting nobody mentions fails by producing a *wrong part* rather
than an error. Alternative 5 pairs with it as a safety net: a flattened copy is correct on any
install regardless of the setting, so shipping both a live document and a flattened one covers
the recipient who never sets the preference.

Superseded reasoning follows. Pursue alternative 4 first, because it is the only one that gives up
nothing. Correct geometry requires the `Part.Shape` API; using that API inside a document
requires a scripted object; and FreeCAD 1.1 will not restore a scripted object whose module is
not an addon. Those three facts are what make the other alternatives trade something away —
under FreeCAD 1.1.1 and 1.1.3 alike, *correct geometry*, *a document that re-solves in stock
FreeCAD*, and *nothing installed* cannot all hold at once, and no arrangement of the model
changes that (see the ruled-out list above). Alternative 4 attacks the premise instead of
choosing among the consequences, and its cost is one afternoon with a second FreeCAD build.
That afternoon has now been spent. 1.1.3 did not pay, and 26.3 has been checked at source and
will not either — it keeps the automatic fuzz, keeps the default at 10.0, and adds no override
to the `Part::` booleans. Alternative 4 is closed.

If no version computes it correctly, then the trade has to be made and it should be made in
this order: alternative 1 or 5, which keep the part right and give up live re-solving; then
alternative 2, if handing out editable cowl files turns out to be a real requirement rather
than a preference, since it is the only one that delivers a live document. Alternative 3 is
last and should not be adopted on convenience grounds — it trades a correct part for a
convenient toolchain, which is the wrong way round, and the measurements above show the failure
is not simply a matter of the slot being too narrow.

### OQ-DES-CW17 — The tail cowl only builds correctly near `U` = 1

**Problem.** `U` is the airframe's size multiplier: every dimension of the aircraft is written
as a multiple of it, and the project sweeps `U` from 0.5 to 4.0. The tail cowl is made by
cutting eleven slots into the aircraft's outer surface, a NURBS solid. Those slots are 0.1 mm
wide and **do not scale with `U`** — they are fold lines for vase-mode printing, not gaps, and
that is deliberate (§6.3). So as `U` grows the body grows and the slots do not, and the slot
becomes ever finer relative to the part.

**Measured 2026-09-01 on FreeCAD 1.1.3, the tail is correct only at `U` = 1.** Everything
feeding the cut scales exactly: `Half` tracks `U`³ to four decimals, and the cutter's volume
tracks `U`² to four figures — 10464.28, 16353.48 and 23551.93 at `U` = 1, 1.25 and 1.5, which
is what fixed-thickness plates must do. It is the cut itself that degrades.

**This must be measured tessellated, not with `Shape.Volume`** (OQ-DES-CW12). The slots remove
231 mm³ from a 297 243 mm³ half — 0.078% — while `Shape.Volume` overstates that half by 5.5%,
so the raw-volume version of this test reports the removal as 5923.93 and is measuring its own
error. A first version of this question carried those raw figures and read the damage as
"+16.7% at `U` = 1.1"; **they are withdrawn**, and the tessellated measure shows the failure is
far larger than they suggested.

| `U` | faces | valid | half (tess) | cut (tess) | removed | should be | over |
|---|---|---|---|---|---|---|---|
| 1.0 | 39 | yes | 297242.57 | 297011.11 | 231.46 | 231.46 | — |
| 1.1 | 38 | yes | 395630.09 | 310740.07 | **84890.02** | 280.07 | **303×** |
| 1.25 | 68 | **no** | 580552.73 | 574666.06 | 5886.66 | 361.66 | 16× |
| 1.3 | 69 | **no** | 653042.97 | 648758.29 | 4284.68 | 391.17 | 11× |
| 1.5 | 68 | **no** | 1003196.03 | 993190.66 | 10005.37 | 520.79 | 19× |
| 1.6 | 7 | yes | — | — | cut volume **−11.05** | | |
| 1.75 | — | — | — | — | **empty** | | |
| 2.0 | — | — | — | — | **empty** | | |
| 3.0 | 7 | yes | — | — | cut volume **−339.51** | | |

`Half` tessellates to exactly `U`³ at every row (580552.73 is 297242.57 × 1.25³), so the input
is right and the cut is what fails. It removes between 11 and 303 times too much material at
every `U` above 1, is invalid from 1.25 to 1.5, and returns nothing or a negative volume above
that. The part is not slightly wrong above `U` = 1; it is destroyed at the first step above it.

**It is also not repeatable.** The same computation at `U` = 1.25 reported `valid = True` in one
run and `valid = False` in another, the only difference being which values of `U` the document
had been recomputed through first. Whatever the cause, the result depends on history.

**The failures are silent.** At `U` = 1.6 and 3.0 the result is a negative-volume solid that
`Shape.isValid()` accepts, which is the worst possible behaviour inside a sweep. A fresh build
fails identically to editing the sheet (`U` = 2.0 empty by either route, `U` = 1.25 agreeing to
three decimals), so this is not a recompute-order defect and the sweep is affected exactly as
the interactive path is. Fusing only the crossing group and cutting the rest singly gives
byte-identical results at every `U`, so it is not a construction-order defect either.

**The controlling quantity is the slot width relative to the body**, not `U` as such. Holding
`U` at 1 and thinning the slot instead reproduces the same collapse: at 0.1 mm the part is
correct; at 0.08 mm it returns a 40-face solid of 59.11 mm³ where 308 777 is right; at 0.05,
0.04 and 0.0125 mm it returns nothing. The ratios agree across both knobs — 0.08 mm at `U` = 1
and 0.1 mm at `U` = 1.25 are both slot/body = 0.0008 and both wrong; 0.05 mm at `U` = 1 and
0.1 mm at `U` = 1.75 are both about 0.0005 and both empty. The cliff sits near 0.0006–0.0008
and **the design sits at 0.001**, so the working configuration is only 25–40% clear of it, with
failure in both directions: a thinner slot or a larger body.

**The OpenSCAD path builds both cowls correctly at `U` = 4.0** (confirmed against the
pre-migration sweep output, 2026-09-01). The design is buildable at every scale in the swept
range; it is this port that is not. CGAL meshes have no curve-intersection tolerance, so none
of what follows arises there.

**One fault is confirmed to be in this port's construction, and it is not sufficient.** The
blank is built by *scaling* an imported NURBS solid, and `Shape.scale()` multiplies the recorded
tolerance along with the coordinates — so the body is stamped 3.3e-07 at `U` = 1 rising to
1.3e-06 at `U` = 4, while the cutter that has to meet it stays at 1.5e-07 at every scale. That
is bookkeeping, not geometry: scaling a NURBS surface moves its control points exactly.
Resetting it with `fixTolerance(1e-07)` measurably helps — `U` = 2.0 goes from **empty** to a
38-face valid solid, and `U` = 1.5 from 68 faces invalid to 40 faces valid — but the removal
stays an order of magnitude too high at every `U` above 1, and `U` = 4.0 is still empty. So it
is a real defect and not the root cause.

**It also shows the `U` = 1 configuration is not robust.** Resetting that tolerance, which
cannot change the geometry, changes the material removed at `U` = 1 from 231.46 to 457.66 mm³.
The one configuration that agrees with OpenSCAD is sitting on a knife edge rather than
comfortably correct, which is the more troubling result of the two.

**One construction explanation has been tested and ruled out.** The cutting tools extend well
past the body — at `U` = 2 a slab is 0.1 mm thick and 268 mm long, an aspect ratio of 2676:1 —
which costs nothing in CSG and is not free in a B-rep. Trimming every tool to the body's
bounding box, at 2% and at 20% padding, changes nothing: `U` = 1.25 and 1.5 still give 68 faces
and `U` = 2.0 is still empty. Whatever is wrong, it is not the tools' reach.

This is a property of the B-rep port, not of the design. The OpenSCAD path meshes with CGAL and
has no curve-intersection tolerance, so it builds the whole swept range. The nose cowl is
unaffected — 10 faces on its cut and 64 on the part at every `U` from 0.5 to 3.0, always valid,
with removal per `U`² holding to ±1.3%.

**A real finding that turned out *not* to be the cause: the blank is not a legal boolean
argument.** It is recorded here because it is true, because it cost a day to establish, and
because the experiment that disproved it as the cause is below and is worth keeping. OCC's own
argument analyser says so directly. `Shape.check(True)` runs `BOPAlgo_ArgumentAnalyzer`, which
asks whether a shape is fit to be handed to a boolean, and on every OML-derived shape it
raises:

```
BOP check found the following errors:
Error in Edge: BOPAlgo GeomAbs_C0
Error in Face: BOPAlgo GeomAbs_C0
```

`BOPAlgo_GeomAbs_C0` is the status OCC reports when an argument contains C0 geometry. Its
boolean algorithm requires arguments to be at least C1. Every shape on the OML side fails the
check and every cutting tool passes it:

| shape | `check(True)` at `U` = 1 | at `U` = 2 |
|---|---|---|
| `Blank`, `Lower`, `Half` | C0 errors | C0 errors |
| `Core`, `Cutter`, `Safe` | clean | clean |

**The blank has never been a legal argument, at any scale** — the condition is present at
`U` = 1 too, where the part comes out right.

**And legality is not what matters.** Two experiments settle it, and they point the same way.
First, the C0 condition can be removed *exactly*: reparameterising the V knot intervals so the
Bézier segments join at matching parametric speed makes the surface genuinely C1 (measured
below), after which the interior multiplicity drops from 3 to 2 at **all 45 joints** and
`check(True)` returns **CLEAN** on a 9-face blank. The cut still fails — `U` = 4 returns a
removal of **−3573.933 mm³**. Second, and conversely, splitting each face into three-knot-span
pieces gives a 129-face blank that OCC flags with **256 C0 errors**, and it produces the correct
part to +0.0036%. A legal blank that fails and an illegal blank that succeeds, in the same
harness: **subdivision is what the cut needs; continuity is neither sufficient nor necessary.**

**Continuity is not irrelevant, though — it buys margin**, and an earlier version of this
section overstated the case by saying it was not what the cut needs at all. Measured in one
harness with controls, the C1 conversion moves the subdivision cliff by a factor of two:

| blank | `k` | faces | removed | vs correct |
|---|---|---|---|---|
| C1 | 23 | 17 | −2438.945 | −0.500 |
| C1 | 12 | 33 | 4498.708 | 0.922 |
| **C1** | **6** | **65** | **4874.110** | **0.999** |
| plain | 6 | 65 | −46674.487 | −9.569 |
| C1 | 3 | 129 | 4873.375 | 0.999 |
| plain | 3 | 129 | 4877.857 | 1.000 |

Plain, the cliff sits between `k` = 3 and 6; converted, between 6 and 12. So both contribute to
conditioning, and the cheapest way to sit well clear of the edge is to do both.

The depth required is sharp and was measured at `U` = 4 by splitting at every `k`-th knot:

| `k` | faces | `check(True)` | removed | vs correct | whole part vs OpenSCAD |
|---|---|---|---|---|---|
| 46 | 9 | 16 C0 | 3979478.761 | 815× | −20.86% |
| 23 | 17 | 32 C0 | 2315319.183 | 474× | −12.14% |
| 12 | 33 | 64 C0 | −40644.893 | −8.3× | +0.2475% |
| 6 | 65 | 128 C0 | −46674.487 | −9.6× | +0.1506% |
| **3** | **129** | **256 C0** | **4877.857** | **1.000** | **+0.0036%** |
| 1 | 369 | — | 4879.645 | 1.000 | +0.0034% |

Three knot spans per face is enough and six is not, with nothing in between: the failure at
`k` = 6 is not a near miss but a negative-volume result. Going finer than `k` = 3 buys nothing.

**The exact C1 conversion, for the record**, since it is a usable technique even though it does
not solve this. The joints are G1 but not C1 — tangent directions agree to 0.000029° while the
parametric speeds do not — and the speed ratio at each V joint is **u-independent to 3.5e-07**,
with the ratios exact powers of two (0.125, 0.25, 0.5, 1, 2, 4; OpenVSP subdivides its domain
dyadically). So propagating `Δv[i+1] = Δv[i] · r[i]` along the chain makes it C1 with **no
control point moved**: measured deviation **2.9e-14 mm**, knot-interval dynamic range 512×.
Multiplicity then reduces 3 → 2 at all 45 joints at a further 3.1e-10 mm. Multiplicity 2 at
degree 3 is exactly C1, so the ten corner curvature breaks survive — unlike every refit. A
corroboration worth keeping: before reparameterisation `removeVKnot` succeeded at exactly 6 of
45 joints, which are exactly the 6 whose speed ratio was already 1.0.

**Where the C0 comes from.** The blank is imported from `vsp_tail.step`, and OpenVSP's internal
surface representation *is* a grid of Bézier patches. Its STEP writer joins them into one NURBS
by setting the interior knot multiplicity equal to the degree, which is C0 by definition. Each
of the blank's eight B-spline faces is degree 5 × 3 with **45 interior V knots at multiplicity
3** — 360 C0 seams on the blank. The V direction is circumferential; U is axial and is a single
quintic span.

**The surface is not creased, only written that way.** Measured across all 45 interior knots of
face 0, the worst normal break is **0.000029°**. The multiplicity permits a crease; the control
points line up and there is none. This matters because it is what makes the condition fixable
without touching the geometry — and it is also why the condition went unnoticed: nothing about
the surface looks wrong.

**Boolean fuzz is not the cause and does not help.** `Part.Shape.cut()` takes an explicit fuzz.
Scanned at the failing scales:

| fuzz | `U` = 1 | `U` = 1.5 | `U` = 2 |
|---|---|---|---|
| 0 | 39 faces, valid, 231.46 removed | 68 faces, invalid, 10004.97 | empty |
| 1e-07 | 39 faces, valid, 231.46 | 68 faces, invalid, 10004.97 | empty |
| 1e-06 | 68 faces, invalid, 1267.15 | 68 faces, invalid, 10004.97 | empty |
| 1e-04 | 69 faces, invalid, 64649.90 | 74 faces, invalid, 214667.23 | empty |

At `U` = 1.5 it is already wrong with **zero** fuzz, and there is nothing below zero. Setting
the `BooleanFuzzy` preference to 0 changes nothing either, and for a second reason: this port
builds through `Part.Shape` rather than document objects, and that path does not read the
preference. The `U` = 1 row does show how narrow the working margin is — the part is correct
only while the fuzz stays at or below 1e-07 mm, which is OCC's own `Precision::Confusion`.

**Refitting the surface is ruled out by the airframe, not by the kernel.** The obvious repair is
to re-approximate the faces at C1 or better. It cannot be used: the fuselage section is a
rounded rectangle, whose straight runs meet the corner arcs tangentially, so the section is C1
but emphatically **not C2** — curvature jumps from 0 to 1/r at every corner tangency, and the
bulkhead mates to that profile. Measured on face 0, **10 of the 45 interior knots carry real
curvature discontinuities**, up to a 99.3% jump (κ = 0.0687 → 9.4528 at knot 15, a corner radius
of 0.106 mm — the same order as the 0.1 mm cut itself). A C1 smoothing approximation was tried
and flattened all ten: curvature breaks over 5% went from 10 to 0, the maximum jump from 99.3%
to 0.1%, deviation reached 4.2e-03 mm against a 1e-04 mm budget, and the result would not sew
into a closed solid. Any free re-parameterisation smooths the corners, because the fit has no
reason to keep knots where the curvature breaks are.

**Splitting at the C0 seams changes no geometry and removes the scale dependence.** A B-rep is
entitled to tangent discontinuities *between* faces; the C0 seams are only illegal because they
sit inside a face. Splitting each face along its 45 C0 knot lines gives 46 strips per face, each
a single Bézier patch and so C∞ internally, at 369 faces for the blank. A first spike gives:

| `U` | solids | valid | removed | per `U`² from `U` = 1 |
|---|---|---|---|---|
| 1.0 | 1 | yes | 213.05 | 1.00 |
| 1.5 | 1 | yes | 685.35 | 1.43 |
| 2.0 | 1 | yes | 1218.36 | 1.43 |
| 4.0 | 1 | yes | 4873.08 | 1.43 |

Against 19× at `U` = 1.5 and nothing at all at 2.0 and 4.0, every scale now returns one valid
solid and the error is **constant** rather than growing — which is what scale-invariance looks
like.

**The split is geometrically exact and its costs are now measured** (2026-09-01). Tessellated,
the split blank is 16833.772147 mm³ against the original's 16833.911873 — a difference of
**−8.3e-04%**, eight parts per million. An earlier note here reported a 6.35% volume loss and
withdrew the split on it; that figure came from `Shape.Volume`, which reports 17975.091439 for
the same blank against the true 16833.911873, a 6.8% overstatement matching the +6.79% already
recorded for this shape. **It is withdrawn.** Sewing is not the cost either: `Part.Shell`,
`sewShape` and `makeSolid` together take 1.0 s for 369 faces. The 24-minute stall that first
made the split look unaffordable was `Shape.check(True)` — `BOPAlgo_ArgumentAnalyzer` scaling
badly with face count — and not the construction. What the split does cost is recompute: about
75 s per `U` against about 12 s for the whole document build with the 9-face blank, roughly 6×.

**The C0 condition is one of two defects, and the second is the fuse.** With the split blank the
error localises completely: cutting with each of the six disjoint `Safe` solids alone, five of
them scale as `U`² to **0.07%** (213.290 mm³ at `U` = 1 against 3410.144 at `U` = 4, where
213.290 × 16 = 3412.64). All of the remaining error sits in the sixth, which is the fused group
of six overlapping tools — `Top1`, `Top2` and the four diagonals — and it is not a tool defect:
cut individually, all six behave, and their removals sum to 91.320 mm³ at `U` = 1 and 1486.304
at `U` = 4.

| tool | `U` = 1 | `U` = 4 | per `U`² | factor |
|---|---|---|---|---|
| `Top1Slab` | 44.345 | 709.818 | 709.526 | 1.000 |
| `Top2Slab` | 22.875 | 365.962 | 365.998 | 1.000 |
| `Diag11Slab` | 7.686 | 138.407 | 122.978 | 1.125 |
| `Diag12Slab` | 6.999 | 111.864 | 111.992 | 0.999 |
| `Diag21Slab` | 3.459 | 54.814 | 55.346 | 0.990 |
| `Diag22Slab` | 5.956 | 105.439 | 95.296 | 1.106 |

**Fused, that group removes −0.252 mm³ at `U` = 1 and 1461.713 at `U` = 4.** At `U` = 4 that is
98.3% of the sum of the singles, which is what modest overlap should give; at `U` = 1 it is
zero. The fuse does not fail at large `U` — **it fails at `U` = 1**, which is the reverse of what
every earlier note here assumed, and it is why the `U` = 1 configuration looked like a knife
edge: the part that agreed with OpenSCAD was agreeing while silently omitting a cut.

**All three fixed, the tail is correct across the whole swept range.** Measured 2026-09-01, and
this is the shipping configuration: the blank converted to C1 (alternative 3), subdivided at
every third knot into 129 faces (alternative 6), and the eleven tools cut individually
(alternative 7), with the whole mirrored part measured against the pre-migration OpenSCAD sweep.

| `U` | recompute | removed | per `U`² | whole part | OpenSCAD reference | difference |
|---|---|---|---|---|---|---|
| 0.5 | 10.2 s | 76.106 | 1.0000 | 74158.400 | 74155.416 | **+0.0040%** |
| 1.0 | 10.4 s | 304.517 | 1.0003 | 593874.323 | 593851.961 | **+0.0038%** |
| 1.5 | 11.0 s | 685.318 | 1.0005 | 2005006.818 | 2004935.411 | **+0.0036%** |
| 2.0 | 12.3 s | 1218.285 | 1.0005 | 4753419.174 | 4753250.616 | **+0.0035%** |
| 3.0 | 12.1 s | 2741.312 | 1.0005 | 16045530.354 | 16044964.051 | **+0.0035%** |
| 4.0 | 11.5 s | 4873.375 | 1.0005 | 38037098.226 | 38035749.164 | **+0.0035%** |

One valid solid at every scale, **154 faces at every scale** — the topology is stable, not just
the volume — and the difference is **flat across an 8× range in `U` and 512× in volume**. It is
the mesh-OML against surface-OML difference (§6.1) and carries no scale term at all. Removal
tracks `U`² to **0.05%**.

**And it is not expensive.** Recompute runs 10.2 to 12.3 s against about 12 s for the original
9-face blank — no penalty at all, and slightly faster than the same subdivision without the C1
conversion (12.2–15.6 s), which is the reverse of what a heavier blank would suggest. The
conversion itself is a one-time 0.5 s at import. An earlier note here costed this fix at 6× on
recompute; that came from splitting to 369 faces, which the `k` table above shows is 2.9× more
subdivision than the cut needs. **It is withdrawn.**

**The nose runs the same conditioning, and it improves there too.** Both cowls import through
`oml_blank.surface()`, so whatever conditions one conditions the other; two cowls conditioned by
two different mechanisms would be the same trap `nose_cowl()` already avoids for its booleans.
The nose blank is not shaped like the tail's, and exercises a case the tail never does: its
faces 0–3 carry interior **U** multiplicities of 5 at degree 5, so it is C0 in *both* parametric
directions where the tail is C0 only in V. The conditioning handles both — 8 faces in, 96 out,
180 multiplicity reductions, deviation 9.5e-10 mm, 0.2 s — and the speed-ratio precondition
holds in both directions (spread 2.7e-11 in U, 5.7e-08 in V, against a 1e-04 tolerance).

The nose was never broken, but it was **drifting**, which had not been measured before:

| `U` | unconditioned | conditioned |
|---|---|---|
| 0.5 | +0.0110% | +0.0136% |
| 1.0 | +0.0111% | +0.0136% |
| 2.0 | **−0.0046%** | +0.0134% |
| 4.0 | **−0.0156%** | +0.0134% |

Unconditioned it moves 0.027% across the swept range and crosses zero, which is a scale term,
small but real. Conditioned it is flat, one valid solid and 88 faces at every scale, at 1.3 s
per recompute. This supersedes the note above that the nose "is unaffected": it does not fail,
and it was not clean either.

Neither fix alone suffices: without subdivision the cut fails at scale whatever the blank's
continuity, and without unfusing, `U` = 1 silently loses 91.491 mm³ — the fused tree removes
213.044 where 304.564 is right.

**Alternatives.**

1. **Declare the FreeCAD backend's tail valid only for `U` ≤ 1.2 and enforce it.** Add a domain
   check that refuses to build outside the range, the way `boom_key_validity_check()` does for
   the boom key. *Benefits:* honest, immediate, and converts a silent wrong answer into a loud
   refusal, which is the single most valuable change available. *Drawbacks:* leaves the tail
   unported over most of the swept range, so `compare_backends.py` cannot cover it there.
   *Prerequisites:* establishing the safe bound properly — the measurements above sample `U` at
   0.5, 0.75, 1.0, 1.1, 1.2, 1.25, 1.3, 1.5, 1.6, 1.75, 2.0 and 3.0, and `U` = 1.1 already
   removes 21% of the part, so the honest bound today is `U` = 1 exactly, not 1.2.

2. **Keep OpenSCAD as the production path for the tail cowl** and treat the FreeCAD tail as a
   single-point reference. *Benefits:* the swept range keeps working today, and nothing has to
   be solved. *Drawbacks:* abandons the port's purpose for this one part, and the migration's
   value comes from covering the whole space. *Prerequisites:* none.

3. **Convert the blank to C1 after import.** Reparameterise the V knot intervals so the Bézier
   segments join at matching parametric speed, then reduce interior multiplicity 3 → 2. Both
   steps are exact — no control point moves — and the whole conversion runs in **0.5 s** at a
   measured deviation of **5.8e-10 mm**. *Benefits:* it does not fix the cut on its own, but it
   **doubles the subdivision margin**: with it, `k` = 6 works where plain `k` = 6 fails at
   −9.57×, moving the cliff from between `k` = 3 and 6 to between 6 and 12. Paired with
   alternative 6 at `k` = 3 it also tightens `U`² tracking from 0.14% to 0.05% and is slightly
   *faster* to recompute, so it costs nothing to keep. Multiplicity 2 at degree 3 is exactly
   C1, which is the continuity the rounded-rectangle section actually has, so the ten corner
   curvature breaks survive untouched. *Drawbacks:* it depends on a property of this export —
   the speed ratio at each V joint is u-independent to 3.5e-07, with the ratios exact powers of
   two — which holds for OpenVSP's dyadic subdivision but is not guaranteed for a surface from
   another source, so the conversion needs to verify its own precondition rather than assume it.
   *Prerequisites:* none; measured and verified.

   **Alone it is not a fix.** A C1 9-face blank on which `check(True)` is CLEAN still returns
   −3573.933 mm³ at `U` = 4. The **refit** route once carried under this heading stays closed:
   the section is C1-but-not-C2 by design, and a C1 smoothing approximation flattened all ten of
   its curvature breaks.

4. **Cut the slots by splitting the surface rather than by a solid boolean**, building the cowl
   from the split surface. *Benefits:* avoids the solid-solid intersection that is failing.
   *Drawbacks:* a substantial rewrite of both cowls, and it must still produce a solid for
   vase-mode slicing, so the closure problem returns. *Prerequisites:* a spike showing a surface
   split survives at `U` = 2 where the boolean does not.

5. **Scale the slot width with `U` after all.** *Benefits:* removes the problem completely; the
   ratio stays at 0.001 everywhere. *Drawbacks:* changes the printed part at every `U` except 1,
   turning a fold line into a gap, which §6.3 and the source both reject. *Prerequisites:* none,
   but it is a design change and not a port fix.

6. **Subdivide the blank's faces on import**, at every third knot line — 129 faces for the
   blank. It belongs in `oml_blank.surface()`, which is the one place every consumer of the OML
   already passes through, and it pairs with alternative 3 in the same function. *Benefits:* it
   changes the geometry by **nothing** — a trimmed view on the original surface, no
   approximation, no tolerance budget, no argument about whether a deviation is small enough
   against the bulkhead fit — and it is what actually fixes the cut, across the whole swept
   range. *Drawbacks:* the blank goes from 9 faces to 129, and it affects every other consumer
   of the OML, not just the cowls. The recompute cost is **not** a drawback: 10.2–12.3 s with
   alternative 3, against about 12 s for the 9-face blank. **Necessary but not sufficient on its
   own** — it must be paired with alternative 7, or `U` = 1 still silently omits 91.5 mm³.
   *Prerequisites:* none; measured and verified at `U` = 0.5, 1.0, 1.5, 2.0, 3.0 and 4.0. On
   depth: with alternative 3, `k` = 6 already works and `k` = 3 is the belt-and-braces choice at
   no extra cost; without it, `k` = 3 is the minimum and `k` = 6 returns a negative volume.
   `k` = 1 (369 faces) buys nothing and costs 75 s per recompute.

7. **Cut with the eleven tools individually instead of fusing the overlapping group.** The six
   tools that overlap are fused into one solid before cutting, and that solid removes nothing at
   `U` = 1 (see *Cause* above). *Benefits:* with alternative 6 it makes the tail correct across
   the sweep — +0.0037% at `U` = 1 and +0.0034% at `U` = 4 against the OpenSCAD reference, the
   same offset at both, with removal tracking `U`² to 0.15%. It also removes a construction step
   rather than adding one. *Drawbacks:* eleven cuts instead of one, so more boolean calls per
   rebuild, and the scripted-boolean node count rises — which cuts against the direction
   OQ-DES-CW16 wants for restorability. *Prerequisites:* none; measured and verified. Note this
   **reverses** a finding recorded in IP-FC-12, that cutting by the group's union reproduces the
   reference exactly — the reference it was checked against was the baked FreeCAD document,
   which carries the same omission.

**Recommendation.** Note first that alternative 1 bounds the damage without curing it: the
`U` = 1 configuration is itself only marginally stable, since resetting a tolerance that cannot
change the geometry moves its removed volume by a factor of two. A domain check makes the
failure loud; it does not make the surviving point trustworthy.

Alternative 1 immediately and unconditionally, because the current state ships a *silent* wrong
answer — a negative-volume solid that passes `isValid()` — and that must stop regardless of what
else is decided. Set the bound at `U` = 1 on today's evidence and widen it only if measurement
supports it. A domain check is also the right shape of fix now that the cause is known: the
condition it should test is not a value of `U` at all but whether `check(True)` passes on the
blank, which is a direct question with a direct answer.

Then **alternatives 3, 6 and 7 together**, which are the cure, are measured rather than
proposed, and cost nothing. Together they hold the tail within **+0.0035% to +0.0040%** of the
OpenSCAD reference at every swept `U` from 0.5 to 4.0 — flat across 512× in volume, so no scale
term survives — with removal tracking `U`² to 0.05%, 154 faces at every scale, and recompute at
10–12 s against about 12 s today.

**6 and 7 are each load-bearing and neither works alone**: 6 without 7 silently omits 91.5 mm³
at `U` = 1, and 7 without 6 fails at scale. **3 is the one that is optional** — and it should
still be taken, because it is the difference between sitting two-fold clear of the subdivision
cliff and four-fold clear, and it makes the result more accurate and slightly faster for half a
second at import. Adopt all three as one change.

The only real cost is eleven booleans in place of one, which raises the scripted-node count and
so pulls against OQ-DES-CW16's restorability concern — that tension is worth stating, but it is
a small price against a part that is otherwise wrong by a factor of 20 above `U` = 1.

Do **not** repoint the alternative-1 domain check at `check(True)`, which an earlier version of
this recommendation proposed: a blank carrying 256 C0 errors builds the part correctly, so that
test would refuse a good configuration. If a guard is wanted, test the invariant that actually
holds — removal per `U`² against its value at `U` = 1, which is constant to 0.14% when the
construction is right and off by factors of 8 to 800 when it is not.

Check **alternative 3** first, since it is strictly cheaper if it works — a blank that arrives
C1 costs no faces and needs no code — but do not wait on it, because the piecewise-Bézier form
is OpenVSP's internal representation and an exporter option to change it may not exist.

Alternative 2 is the fallback if both fail, and should be stated openly rather than arrived at by
default. Alternative 5 should not be adopted: it trades the printed part for a convenient
toolchain, which is the wrong way round. The refit route once carried under alternative 3 is
closed — the section is C1-but-not-C2 by design and no free re-parameterisation preserves that.

### OQ-DES-CW18 — Should the plate and flange thicknesses scale with `U`?

**Problem.** `U` is the airframe's size multiplier: every dimension is written as a multiple of
it, and the project sweeps `U` from 0.5 to 4.0. Four values in `nose_size_variants.csv` are
given a separate column per `U` and increase linearly with it:

| `U` | `plate_thickness` | `plate_flange_width` | `plate_flange_height` | `nose_flange_height` |
|---|---|---|---|---|
| 0.5 | 0.4 | 1.2 | 0.6 | 0.6 |
| 1 | 0.8 | 2.0 | 1.0 | 1.0 |
| 2 | 1.6 | 4.0 | 2.0 | 2.0 |
| 4 | **3.2** | **8.0** | **4.0** | **4.0** |

All four are millimetres. `plate_thickness` is the nose plate's thickness — the plate is a flat
printed disc that closes the nose and carries the flange the tip plugs into. `plate_flange_width`
and `plate_flange_height` are that flange's section; `nose_flange_height` is the matching flange
on the tip.

**These are placeholders.** Recorded 2026-09-01: the per-`U` values were generated by plain
linear scaling when the sweep was set up, and were never tuned against a print or a load case.
The file has carried them unchanged since it was first committed on 2026-08-04. They are not a
decision that these dimensions scale, and the archive's fixed values are not a decision that
they do not — the question below is open on its merits.

**These read as manufacturing dimensions, not airframe dimensions.** At a 0.2 mm layer height,
0.8 mm is four layers and 3.2 mm is sixteen. §6.3 already establishes that
`buttress.cut_thickness` is deliberately absolute and does **not** scale, on the grounds that it
is a slicer tolerance and *a tolerance has no business tracking the airframe*; the same section
lists `tolerance` and `flange_inset` as unscaled for the same reason. It does not mention these
four, so the existing documentation neither confirms nor contradicts scaling them.

**The pre-migration sweep held all four fixed.** Read from the generated drivers it rendered
from, `variant_output_original/U_4.0/nose/U_4.0__nose_plate.stl.scad` calls
`nose_plate(plate_diam = 240.0, plate_flange_height = 1.0, plate_flange_width = 2,
plate_thickness = 0.8)` — `plate_diam` scaled from 60 to 240 while the other three stayed at
their `U` = 1 values. The tip driver does the same with `nose_flange_height = 1.0`. So the
archive and the current derivation disagree, and one of them is wrong.

**What the two readings give at `U` = 4:**

| | scaled (sweep) | fixed (archive) |
|---|---|---|
| plate volume | 184 542 mm³ | 38 669 mm³ |
| plate z-extent | 11.200 mm | 2.800 mm |
| tip z-extent | 28.000 mm | 25.000 mm |

A factor of 4.8 in the plate's material.

**No backend comparison can detect this.** `compare_backends.py` renders both engines from the
same `derived_cowl_parameters()` result, so a parameter that scales when it should not produces
two engines agreeing exactly on the wrong part. Measured 2026-09-01, FreeCAD and OpenSCAD agree
on the `U` = 4 plate to **2.0e-05** — inside `TOL_EXACT` — while building the 3.2 mm version.
The comparison validates the port; it never validates the parameters. That is why this question
survived a backend compare and needs answering separately.

**Alternatives.**

1. **Hold all four fixed at their `U` = 1 values**, as the archive does. *Benefits:* consistent
   with §6.3's rule for every other manufacturing dimension, and with the last physically
   printed configuration; a plate stays four layers whatever the airframe. *Drawbacks:* a
   240 mm plate 0.8 mm thick may be too floppy to handle or to print flat, so the rule that
   suits a tolerance may not suit a structural member. *Prerequisites:* a view on whether the
   plate is structure or skin.

2. **Scale all four with `U`**, as the current derivation does. *Benefits:* the part stays
   self-similar, so its stiffness keeps up with its span, and nothing has to change.
   *Drawbacks:* it silently contradicts the reasoning §6.3 gives for `cut_thickness`, and it
   makes a printed wall a function of the airframe rather than of the printer.
   *Prerequisites:* none; it is the status quo.

3. **Split them by what they are.** Scale `plate_thickness` because it is structural, and hold
   the three flange dimensions fixed because they are a joint fit — `flange_inset` is already
   unscaled by §6.3, so a flange whose inset is absolute and whose height scales is
   inconsistent. *Benefits:* answers each on its own merits rather than by category.
   *Drawbacks:* four values with three rules is harder to state and to check.
   *Prerequisites:* deciding each one.

4. **Derive the thicknesses from the printer instead of from `U`** — `plate_thickness =
   n_layers × layer_height`, the flanges from `extrusion_width`, the way
   `nose_flange_inset` is already `cowl_n_perimeters × extrusion_width + tolerance`.
   *Benefits:* puts a manufacturing dimension under the manufacturing parameters, where the
   existing precedent already sits, and it stops being a swept axis at all. *Drawbacks:* the
   largest change of the four, and it removes the ability to sweep them.
   *Prerequisites:* choosing `n_layers`, and confirming the plate's job is printing rather than
   stiffness.

**Recommendation.** **Alternative 4**, and the reason is that the values are untuned. A
derivation removes the need to tune them: `plate_thickness = n_layers × layer_height` and the
flange section from `extrusion_width` are numbers that follow from the printer rather than
numbers somebody has to pick eight times and keep consistent. It also puts these dimensions
where the precedent already is — `nose_flange_inset` is already
`cowl_n_perimeters × extrusion_width + tolerance`, and §6.3 puts `cut_thickness` and
`tolerance` in the same class — so it makes the rule uniform instead of adding a fourth
convention.

Alternative 2 is worth choosing on its merits if the plate is structural, but not on the grounds
that it is what the file already says.

The one thing that would change this recommendation is the plate being **structural**. If it
carries load rather than closing the nose, its thickness has to follow the span and not the
nozzle, which is alternative 1's drawback and alternative 2's whole case. That is the question
to answer first, and it is not answerable from the geometry.

Whichever is chosen, the sweep and the archive must be brought back into agreement, because at
present the committed reference geometry cannot be used to check the nose plate or the nose tip
at any `U` except 1.

### ~~OQ-DES-CW19 — The rib at an inclined buttress cut is thicker than the rib everywhere else~~ — RESOLVED 2026-09-04

**Alternative 1**, and for a better reason than the one recommended. The recommendation rested
on the cost of re-rendering the tail. The actual reason is that the two terms are measured in
different frames because they are two different kinds of dimension:

- **The thickness of the OML cut is fixed regardless of orientation.** `buttress_cut_thickness`
  is a property of the cut — 0.1 mm normal to the cut's own plane, whichever way that plane
  faces. It is not a function of the cut's angle, and there is nothing in the model to change.
- **The thickness of the perimeters is evaluated parallel to the build plate.** A perimeter is
  laid down by a nozzle travelling within a layer, so its width is an in-plane measurement by
  definition. That is the same fact that makes the interior a horizontal inset rather than a
  normal offset (§6.2, and [cowl_interior_surface.md](cowl_interior_surface.md) §9.2).

The rib is the two together, measured where the printer measures them — in the layer plane — so
its thickness is

    2 · n_p · w + t_cut / sin θ

with θ the angle between the cut plane and the layer plane. Every vertical cut has θ = 90°,
which returns the familiar 1.3 mm; the tail's 30° diagonals give 1.4 mm. **θ is bounded away
from 0, where the expression diverges, by the design and not by the arithmetic:** a rib forms
because the perimeter walks into the notch and back out within a layer, a notch lying in the
layer plane offers no such path, and a horizontal rib would therefore come out malformed under
thin-wall perimeter slicing — so horizontal ribs are not used. Stated 2026-09-04 and recorded as
P4 in [cowl_interior_surface.md](cowl_interior_surface.md) §2, where it sits beside P1 for the same
reason: a horizontal surface leaves no wall, and a horizontal notch leaves no rib. **Nothing in the
geometry changes, and nothing was ever wrong with it.** OQ-DES-CW3's `2·w·n + t_cut` is the
θ = 90° case of this expression, not a rule the diagonals break.

Alternatives 2, 3 and 4 are all rejected by the first clause: each of them scales the cut's
thickness by its orientation, which is precisely what a fixed cut thickness means not doing.

**Nothing to implement.** `check_cowl_interior.in_plane_width` already derives the width from
the cut face's own normal as `t_cut / hypot(n_x, n_y)`, which is this expression and holds for a
cut at any orientation rather than only for rotation about one axis. The measured 1.3000 mm at
every axial notch and 1.4000 mm at every diagonal is the design being met, not tolerated.

**One thing this does not settle, kept here rather than reopened.** The diagonal rib's thickness
is a function of `top_diag_angle` — 1.4 mm at 30°, 1.59 mm at 15° — and nothing couples the two.
Under this resolution that is correct behaviour rather than a defect, since the cut stays 0.1 mm
and a shallower layer plane simply cuts it wider. It does mean a shape parameter moves a
structural dimension with no note anywhere that it does, which is the same class of unenforced
coupling [OQ-DES-CW11](#open-questions) records for `overhang_angle_from_bed`.

## See also

- [cowl_interior_surface.md](cowl_interior_surface.md) — the interior-surface algorithm §6.2
  calls for, in full
- [freecad_migration.md](../architecture/freecad_migration.md) — UC-9 (OML as a surface),
  OQ-ARCH-5 (the interior-surface method), OQ-ARCH-17 (the precondition)
- [bulkhead.md](bulkhead.md) — the cowling bulkhead the cowl mates to
- [corner.md](corner.md) — the other half of the fuselage joint
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-4, IP-FC-7,
  IP-FC-16, IP-FC-17
