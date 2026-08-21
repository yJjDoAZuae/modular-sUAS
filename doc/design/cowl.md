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
| The rib | Emerges, as the wall follows the notch in and back out | Modelled, `2·w·n + t_cut` thick |

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
  mode — which is the case that matters, and conveniently the case where the formula is least
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

## See also

- [cowl_interior_surface.md](cowl_interior_surface.md) — the interior-surface algorithm §6.2
  calls for, in full
- [freecad_migration.md](../architecture/freecad_migration.md) — UC-9 (OML as a surface),
  OQ-ARCH-5 (the interior-surface method), OQ-ARCH-17 (the precondition)
- [bulkhead.md](bulkhead.md) — the cowling bulkhead the cowl mates to
- [corner.md](corner.md) — the other half of the fuselage joint
- [freecad_migration.md](../implementation/freecad_migration.md) — IP-FC-4, IP-FC-7,
  IP-FC-16, IP-FC-17
