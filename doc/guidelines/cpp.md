# C++ Coding Guidelines

Refer to [general.md](general.md) for project-wide standards on TDD, naming, units, and
architecture. This document covers C++-specific conventions.

**Status: forward-looking.** No C++ exists in this repository yet. These guidelines apply
to anticipated numerical work in the aircraft design workflow — geometry optimization
solvers, fluid dynamics analysis, structural sizing — where Python is too slow and the
computation is a self-contained numerical kernel. Nothing here obliges the project to add
C++; it settles the conventions in advance so the first solver does not set them by
accident.

Do not write C++ for anything Python can do at acceptable speed. The generator toolchain,
parameter handling, and file I/O stay in Python.

---

## Integration Boundary — Decide This Before Writing Any C++

C++ has to reach a project whose driver layer is Python and whose geometry layer is
OpenSCAD. There are two viable shapes, and the choice is **not yet made**. Record it as an
architecture open question (`/oq` in `doc/architecture/overview.md`) before the first
solver is written, because it determines the build, the packaging, and the test strategy.

| | Python extension module | Standalone CLI tool |
| --- | --- | --- |
| Binding | `nanobind` or `pybind11` | None — process boundary |
| Data exchange | In-memory arrays, zero-copy | Files or stdin/stdout (JSON, STL, VTK) |
| Build | Must build a wheel per platform; `uv` has to install it | Built once, invoked via `subprocess` |
| Debugging | Mixed-language stack traces | Debuggable in isolation |
| Failure mode | A segfault kills the whole sweep | A crash is one non-zero exit code |
| Best for | Tight loops called many times per part (optimization inner loops) | Long-running batch analysis (CFD, FEM) |

**Recommendation:** start with a standalone CLI tool. The project already shells out to
OpenSCAD and will shell out to FreeCAD, so a subprocess boundary is an established pattern
here, and it keeps a solver crash from taking down a multi-thousand-part sweep. Move to a
binding only when a measured profile shows the process overhead dominates.

Whichever is chosen, the C++ side must be **runnable and testable without Python**.

---

## Language Standard

- **C++20** minimum (concepts, ranges, `std::span`). Numerical code benefits directly from
  ranges and `std::span`, and the toolchain is new enough that C++17 costs more than it saves.
- Compile with warnings enabled and treated as errors: `-Wall -Wextra -Wpedantic -Werror`.
- Enable sanitizers in debug/test builds: `-fsanitize=address,undefined`.
- Numerical code additionally builds clean under `-Wfloat-equal` and `-Wconversion`.

---

## Naming Conventions (C++)

| Category | Convention | Example |
| --- | --- | --- |
| Classes / Structs | `PascalCase` | `PanelSolver`, `MeshOptimizer` |
| Abstract base classes | `PascalCase`, no prefix | `Solver`, `ObjectiveFunction` |
| Methods | `camelCase` | `computeLiftDistribution()`, `solve()` |
| Private / protected members | `snake_case_` (trailing underscore) | `panel_count_`, `tolerance_mm_` |
| Public struct fields | `snake_case` (no trailing underscore) | `chord_mm`, `span_mm` |
| Method parameters | `snake_case` (no trailing underscore) | `max_iterations`, `tolerance_mm` |
| Local variables | `snake_case` | `residual`, `cell_volume_mm3` |
| Constants / `constexpr` | `SCREAMING_SNAKE_CASE` | `DEFAULT_TOLERANCE_MM` |
| Enums | `enum class`, `PascalCase` type and values | `SolverStatus::Converged` |
| Namespaces | `snake_case`, lowercase | `namespace geometry`, `namespace flow` |
| Template parameters | `PascalCase` | `template <typename Scalar>` |
| Macros | `SCREAMING_SNAKE_CASE` with project prefix | `MSUAS_ASSERT(...)` |

The trailing underscore on private/protected members is the primary visual signal that a
name is instance state, not a local or parameter. Apply it consistently: every `private`
and `protected` data member gets it; public struct fields and all function parameters do not.

Abbreviation rules follow [general.md](general.md#general-rules), with the standard
aerodynamics and numerics abbreviations additionally permitted where they are the canonical
name: `cfd`, `fem`, `cfl`, `rans`, `les`, `bem`, `vlm` (vortex lattice method), `lhs`/`rhs`,
`jacobian`. Single-letter identifiers remain forbidden except as loop indices and standard
mathematical notation inside a derivation the surrounding comment defines.

### Unit Encoding in Names

Encode units in the name whenever they are not obvious:

```cpp
double chord_mm_;                  // member: chord in millimetres
double freestream_speed_mps_;      // member: freestream speed in m/s
double pressure_pa_;               // member: static pressure in pascals
constexpr double DEFAULT_TOLERANCE_MM = 1.0e-3;
```

---

## Units

C++ code is **SI throughout** — metres, seconds, kilograms, radians, newtons, pascals. This
is the project standard; see
[general.md](general.md#units--si-is-the-project-standard). Solvers are new code, so they
follow it from the start with no legacy to reconcile.

That is also what the physics wants: Reynolds number, dynamic pressure, and every published
aerodynamic and structural correlation assume SI. A flow solver running in millimetres is
wrong by factors of 1000.

The conversions to watch, all of which live at the solver's **input and output boundary**
and nowhere inside it:

| Source | Arrives as | Convert |
| --- | --- | --- |
| Mesh from OpenSCAD / STL / 3MF | millimetres | mm → m on load |
| Geometry from FreeCAD | millimetres | mm → m on load |
| FreeCAD FEM results | N/mm² (MPa) | MPa → Pa on load |
| Mesh written for a slicer | must be millimetres | m → mm on export |

Rules:

- Convert **once** on the way in and once on the way out. Name the conversion site; do not
  scatter factors of `1e-3` through the numerics.
- Unit-suffix every dimensional parameter so the regime is unambiguous at a glance.
  `computeDrag(double chord_mm, double speed_mps)` is a bug waiting to happen — convert at
  the boundary so the interior is uniformly SI.
- State the unit system in a one-sentence comment at the top of every solver header.
- Be aware that the inherited Python generator toolchain is currently millimetres
  throughout and is scheduled for conversion as a single deliberate roadmap item. Until
  that lands, a C++ boundary consuming its output converts mm → m explicitly and says so.
  Do not convert the Python side as a side effect of adding a solver.

---

## File and Directory Structure

```text
src/
  solvers/
    include/
      <domain>/
        ClassName.hpp        // public interface
    src/
      <domain>/
        ClassName.cpp        // implementation
    test/
      <domain>/
        ClassName_test.cpp   // unit tests
    CMakeLists.txt
```

C++ lives under `src/solvers/`, parallel to `src/Fuselage/`, not mixed into it. The
Fuselage tree is Python and OpenSCAD; keeping the boundary visible in the directory layout
keeps the build simple.

- One class per header/source pair.
- Headers use `#pragma once`.
- Implementation files include their own header first, then standard library, then
  third-party, then project headers — each group separated by a blank line.

```cpp
#pragma once

// PanelSolver.hpp
#include <cstddef>
#include <span>
#include <vector>

#include <Eigen/Dense>

#include "geometry/Mesh.hpp"
```

---

## Solver Interface

Numerical solvers are **not** simulation components with a step lifecycle. They take an
input, run to convergence or failure, and return a result. Model them that way.

```cpp
namespace flow {

enum class SolverStatus {
    Converged,
    MaxIterationsReached,
    Diverged,
    InvalidInput,
};

struct SolverResult {
    SolverStatus status = SolverStatus::InvalidInput;
    int iterations = 0;
    double residual = 0.0;
    // domain-specific outputs follow
};

class PanelSolver {
public:
    /// All lengths SI (m); geometry is converted from mm at the call boundary.
    [[nodiscard]] SolverResult solve(const Mesh& mesh, const FreestreamConditions& conditions);
};

} // namespace flow
```

Rules:

- **Never signal non-convergence by returning a plausible-looking number.** Return a status,
  the iteration count, and the final residual. A silently non-converged result that flows
  into a design decision is the worst failure mode in this domain.
- Solvers are deterministic and reproducible: same input, same output, bit for bit. Seed any
  stochastic component explicitly and record the seed in the result.
- Solvers do no file I/O and no logging to stdout. The caller owns I/O.
- Long-running solvers accept a cancellation or progress callback rather than blocking
  opaquely.

---

## Memory Management

- Use **RAII** for all resource management. Never use raw `new`/`delete`.
- Prefer **value semantics** and stack allocation for small, fixed-size objects.
- Use `std::unique_ptr` for single ownership; `std::shared_ptr` only when shared ownership
  is genuinely required.
- Prefer `std::vector`, `std::array`, and standard containers over raw arrays.
- For large numerical arrays, pass `std::span` (non-owning) rather than copying a vector.
- Avoid `std::shared_ptr` cycles; use `std::weak_ptr` to break them.

---

## Type Safety and Modern C++

- Prefer `enum class` over plain `enum`.
- Use `constexpr` for compile-time constants instead of `#define`.
- Use `[[nodiscard]]` on every function returning a status or a computed result — a
  discarded `SolverResult` is a bug.
- Use `explicit` on single-argument constructors and conversion operators.
- Prefer `auto` where the type is obvious; avoid it when it obscures the type. In numerical
  code, beware `auto` with expression-template libraries such as Eigen — it captures the
  expression, not the evaluated result, and dangles if the operands go out of scope.
- Avoid raw pointers in interfaces; use references, `std::span`, or smart pointers.

```cpp
// Good — status cannot be silently dropped, units unambiguous
[[nodiscard]] SolverResult solve(const Mesh& mesh_m, const FreestreamConditions& conditions);

// Bad — returns a bare number with no convergence information and unclear units
double solve(const Mesh& mesh, double speed);
```

---

## Numerical Practice

Domain-specific rules that matter more here than general style:

- **Never compare floating-point values with `==`.** Compare against a tolerance that is
  meaningful in the quantity's units, and name the tolerance constant.
- Prefer `double` throughout. Use `float` only where a measured profile or a memory
  constraint justifies it, and say so in a comment.
- State the convergence criterion explicitly — absolute residual, relative residual, or
  both — and expose the tolerance as a parameter rather than hardcoding it.
- Every iterative solver has a maximum iteration count. There are no unbounded loops.
- Guard against division by near-zero and against `sqrt`/`log` of negative values arising
  from round-off. Clamp with an explicit epsilon and document why.
- Validate mesh and input geometry at solver entry — degenerate cells, non-manifold edges,
  zero-area panels — and fail with a specific message naming the offending element index.
  Geometry arriving from a parametric sweep will eventually be degenerate at some corner of
  the parameter space.

---

## Data Exchange

Use [nlohmann/json](https://github.com/nlohmann/json) for JSON exchange with the Python
layer. Use established binary formats for meshes and fields (STL and 3MF for geometry, VTK
for volumetric results) rather than inventing one.

There is no serialization lifecycle in this project — solvers do not checkpoint or restore
internal state. What crosses the boundary is inputs in and results out.

Rules:

- Serialized field names carry unit suffixes: `"chord_mm"`, `"freestream_speed_mps"`.
- The JSON exchanged with Python must state its unit system explicitly in a top-level field.
- Every exchange format has a round-trip test.
- Keep the exchange schema documented with the `/schema` skill, the same as a parameter file.

---

## Testing (C++)

Use **Google Test (gtest)** with **Google Mock (gmock)**.

```cpp
// src/solvers/test/flow/PanelSolver_test.cpp
#include <gtest/gtest.h>
#include "flow/PanelSolver.hpp"

namespace flow {
namespace {

TEST(PanelSolverTest, FlatPlateAtZeroIncidenceProducesZeroLift) {
    const auto mesh = makeFlatPlateMesh(/*chord_m=*/1.0, /*span_m=*/10.0);
    PanelSolver solver;
    const auto result = solver.solve(mesh, FreestreamConditions{/*speed_mps=*/50.0, /*alpha_rad=*/0.0});

    ASSERT_EQ(result.status, SolverStatus::Converged);
    EXPECT_NEAR(result.lift_coefficient, 0.0, 1e-6);
}

TEST(PanelSolverTest, DegenerateMeshIsRejectedNotSolved) {
    PanelSolver solver;
    const auto result = solver.solve(makeZeroAreaMesh(), FreestreamConditions{});
    EXPECT_EQ(result.status, SolverStatus::InvalidInput);
}

} // namespace
} // namespace flow
```

### Rules — Testing

- Test names follow `MethodName_ConditionUnderTest_ExpectedBehavior`.
- Use `EXPECT_NEAR` (never `EXPECT_EQ`) for floating-point comparisons; choose a tolerance
  meaningful in the quantity's units.
- **Verify against analytical solutions wherever one exists** — flat plate, thin airfoil
  theory, elliptical loading, a beam in pure bending. A solver with no closed-form check is
  a solver nobody can trust.
- **Test convergence behavior, not just converged values.** Assert that a refined mesh moves
  the answer in the expected direction and by roughly the expected order.
- Assert that invalid input is rejected rather than silently solved.
- Tests are independent; no shared mutable state.

---

## Build System

- Use **CMake** (3.20+), with the C++ tree self-contained under `src/solvers/`.
- Tests are built and run with `ctest`.
- Enable sanitizers in the `Debug` configuration.
- The C++ build must not be a prerequisite for running the Python generator toolchain.
  Someone doing geometry work should never need a compiler.

```cmake
target_compile_options(msuas_solvers PRIVATE
    $<$<CONFIG:Debug>:-fsanitize=address,undefined>
)
```

---

## External Dependency Management

License policy follows [general.md](general.md#license-policy). Two warnings specific to
this domain, where the most obvious libraries are the most encumbered:

- **CGAL** is the standard computational-geometry library, and most of its packages are
  **GPL v3**. Linking it makes the linked binary GPL. Its core is LGPL, and a commercial
  license exists. Check the specific package before depending on it.
- **OpenFOAM** is GPL and is normally used as a **separate executable**, which does not
  propagate to this project's code. Invoking it as a subprocess is fine; linking against
  its libraries is not.

Likely permissive alternatives for this domain: Eigen (MPL-2), NLopt (MIT/LGPL), Ceres
(BSD-3), OpenVDB (MPL-2), VTK (BSD-3), Open CASCADE (LGPL with an exception — the geometry
kernel FreeCAD itself uses).

### Adding a dependency

```text
Is the library in ConanCenter?
├── YES → Add to conanfile.txt; use find_package() in CMakeLists.txt  (preferred)
└── NO  → Is source available?
          ├── YES → FetchContent, pinned to a tag or commit SHA
          └── NO  → Reconsider. A binary-only numerical library is a last resort.
```

Rules:

- Always pin to a specific **tag or commit SHA** — never `main` or `master`.
- Record the library name, version/SHA, and license in a comment next to the declaration.
- Maintain a dependency registry table as a comment header in the root `CMakeLists.txt`,
  in this format:

```text
# Dependency | Version/Commit | License | Method
# -----------|----------------|---------|---------------------
# (none yet)
```

---

## Error Handling

- Use exceptions for programming errors and unrecoverable state violations
  (`std::logic_error`, `std::runtime_error`).
- Use `std::optional` / `std::expected` or an explicit status enum for expected failure
  modes — non-convergence, degenerate input, an empty result set. Non-convergence is an
  expected outcome, not an exception.
- Never use exceptions for normal control flow.
- Assert preconditions at function entry in debug builds using `MSUAS_ASSERT` or `assert`.
- Do not `catch (...)` silently; always log or re-throw.
- When crossing into Python, translate C++ exceptions into a Python exception with the
  original message preserved. A solver failure must never surface as a bare segfault.

---

## Code Style

- Indentation: **4 spaces** (no tabs).
- Brace style: **K&R**.
- Line length: **120 characters** maximum.
- Use `clang-format` with the project's `.clang-format` file.
- Use `clang-tidy` for static analysis.

```yaml
# .clang-format
BasedOnStyle: Google
IndentWidth: 4
ColumnLimit: 120
AccessModifierOffset: -4
```
