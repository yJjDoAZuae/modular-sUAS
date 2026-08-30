"""IP-FC-91: the requirement register, as data.

`doc/design/system_requirements.md` states the requirements a person reads and signs. This
module carries the same set as tables, so the two can be checked against each other and so the
structural properties -- does every citation resolve, does every requirement below the design
level have a parent, does anything skip a level -- are answered by running something rather
than by reading carefully.

**Six registers, in four tiers.**

    ARCHITECTURE   AR-    constrains ANY compliant implementation
    DESIGN         DES-   constrains THIS one; cites AR, optionally
    INTERFACE      INT-   one joint, between two named parts
    DRAWING        DRW-   the drawing set
    MODEL          MDL-   the delivered FreeCAD model
    EQUIVALENCE    EQV-   the two geometry paths, and the sweep

The last four are peers: each states a rule about one part of the delivered system, and each
cites one or more design requirements. `AR-` citations from that tier are **level skips** --
allowed, because forbidding them would only mean inventing a middle statement to launder the
citation through, and reported, because a level skip means either the design tier has a hole or
the architectural requirement is really a design one. See OQ-DES-SR1.

**Nothing here is invented.** Every requirement below the architecture carries a `source`: the
document, decision or work item that already said it. A requirement with no source is a
requirement somebody made up while writing a register, which is the failure this file would
otherwise make easy.

    python requirements.py              # the register, and its structural checks
    python requirements.py --document   # the register against doc/design/system_requirements.md

Millimeters and degrees, as the OpenSCAD path uses them.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: The repository root, from `src/Fuselage/tools`.
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))

#: `doc/design/system_requirements.md`. The register is stated there and carried here.
DOCUMENT = os.path.join(ROOT, 'doc', 'design', 'system_requirements.md')


class Requirement(object):
    """One requirement: what it says, what it cites, why, what verifies it, and where it came
    from.

    `cites` may be empty at the design level -- citing architecture is optional by decision,
    OQ-DES-DB5 -- and then `rationale` is mandatory, because with nothing above it that sentence
    is the whole of its justification. Below the design level `cites` may not be empty: a rule
    about the drawing set or the delivered model that answers to nothing above it is a
    requirement nobody asked for.

    `verifier` names the tool that applies the requirement, as a repository-relative path, or
    one of `review` (no tool applies and none could) and `None` (nothing applies one, which is a
    finding rather than a state of affairs). A path is checked to exist.

    `source` names where the requirement was already decided. Mandatory below the architecture.
    """

    def __init__(self, statement, cites=(), rationale=None, verifier=None, source=None):
        self.statement = statement
        self.cites = tuple(cites)
        self.rationale = rationale
        self.verifier = verifier
        self.source = source

    @property
    def derived(self):
        """True when nothing above this requirement is cited.

        In the INCOSE, ARP4754A and DO-178C sense: traceable to no higher-level requirement,
        arising from the design solution itself. A review obligation, not a defect.
        """
        return not self.cites


# ------------------------------------------------------------------------------------------
# Architecture -- doc/architecture/requirements.md is the authority
# ------------------------------------------------------------------------------------------

ARCHITECTURE = {
    'AR-OBJ-1': 'facilitate iteration of aircraft sizing and configuration',
    'AR-OBJ-2': 'facilitate system integration',
    'AR-OBJ-3': 'maximize modularity',
    'AR-OBJ-4': 'decouple component designs',

    'AR-MOD-1': 'minimally constraining physical interface',
    'AR-MOD-2': 'allow interchange of fuselage sections',
    'AR-MOD-3': 'allow re-ordering of fuselage sections',
    'AR-MOD-4': 'interchange or re-ordering does not affect fuselage structure',
    'AR-MOD-5': 'the OML provides flat exterior panels for system integration',
    'AR-MOD-6': 'the OML provides a simple exterior shape for the wing interface',
    'AR-MOD-7': 'the OML uses a constant cross section, for longitudinal relocation of '
                'external components',
    'AR-MOD-8': 'the OML uses standardized dimensions, for commonality between '
                'implementations',
    'AR-MOD-9': 'the volume the airframe encloses is usable -- payload, wiring, and a hand',
    'AR-MOD-10': 'the OML cross section is a rounded square, and the corner radius fixes the '
                 'design position on the trade between flat panel area and aerodynamic '
                 'efficiency',

    'AR-PRT-1': 'printable using FDM technology',
    'AR-PRT-2': 'layer orientation aligned to structural performance needs',
    'AR-PRT-3': 'printable without support material',

    'AR-CON-1': 'structural parts are printed; longerons, booms, panels, fasteners and '
                'inserts are bought',

    'AR-ASM-1': 'components are self-aligning during assembly',
}


# ------------------------------------------------------------------------------------------
# Design -- doc/design/system_requirements.md section 4, argued in doc/design/design_basis.md
# ------------------------------------------------------------------------------------------

BASIS = 'doc/design/design_basis.md'
SCHEME = 'doc/design/dimension_scheme.md'
CHECK_DERIVATION = 'src/Fuselage/tools/check_derivation.py'
CHECK_GEOMETRY = 'src/Fuselage/freecad/check_derived_geometry.py'

DESIGN = {
    'DES-1': Requirement(
        'airframe dimensions are proportional to U, and scale freely with it -- including '
        'below their 1U value on a sub-unit airframe',
        cites=('AR-MOD-8', 'AR-MOD-10'),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-2': Requirement(
        'a feature whose size the print process governs is sized in whole extrusions or whole '
        'layers',
        cites=('AR-PRT-1',),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-3': Requirement(
        'every part reaching the outer surface lands on the mold line, and a joint\'s '
        'clearance is taken inboard of it',
        cites=('AR-MOD-4', 'AR-MOD-5'),
        verifier=CHECK_GEOMETRY, source=BASIS + ' section 4'),
    'DES-4': Requirement(
        'a JOINT\'s clearance appears once, on one named side; the other side is nominal -- '
        'which is not the same as a clearance PARAMETER appearing on one part',
        rationale='cites nothing, and could not: a joint has to accommodate print variation '
                  'and bond thickness, and MAUS-FOS excludes dimensional tolerances as '
                  'application dependent, so nothing above says the accommodation is '
                  'single-sided -- splitting it across both halves would comply equally. '
                  'Putting it on one side is a design decision, and its reason IS recorded '
                  '(the joint would otherwise take the clearance twice). **The unit is the '
                  'joint, not the parameter**; `panel_tolerance` is carried by both the corner '
                  'and the bulkhead, which is two joints against the same bought panel and not '
                  'a violation.',
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-5': Requirement(
        'the bought part is nominal and the printed part carries the fit',
        cites=('AR-CON-1',),
        rationale='AR-CON-1 names which parts are bought, adopted 2026-08-29; that a bought '
                  'part cannot be altered follows from it, since the supplier sets its size. '
                  'What AR-CON-1 does not say is that the clearance therefore goes on the '
                  'printed side rather than being split, and no reason for that is on record.',
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-6': Requirement(
        'at the corner/bulkhead interface the corner carries the clearance, so that the '
        'bulkhead\'s dimensions stay consistent across variants',
        cites=('AR-MOD-9',),
        rationale='the corner is less likely to have integrated components interfacing it '
                  'than the bulkhead, so the bulkhead is the part whose dimensions should stay '
                  'consistent. AR-MOD-9 is the parent because the rationale is about '
                  'components integrating to the bulkhead, on the INSIDE; AR-MOD-5 covers the '
                  'exterior only.',
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-7': Requirement(
        'where a joint does not exist its clearance is zero, and that zero is the absence of '
        'the joint rather than a fit set to nothing',
        rationale='cites nothing, and could not: it is a statement about clearances, which '
                  'MAUS-FOS excludes on purpose. A dimensioned zero asserts a coincident fit '
                  'that was designed and is inspectable, and here there is nothing to inspect '
                  '-- so a drawing omits the dimension rather than printing 0.0, and the '
                  'geometry merges or closes the feature rather than building it at zero '
                  'size.',
        verifier=CHECK_GEOMETRY, source=BASIS + ' section 4'),
    'DES-8': Requirement(
        'no part may intrude on the volume swept by another part\'s assembly motion',
        cites=('AR-ASM-1',),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-9': Requirement(
        'a drawing states which of several competing requirements produced a dimension',
        rationale='cites nothing because **the drawing set has no architectural parent at '
                  'all** -- doc/architecture/requirements.md says nothing about documentation, '
                  'and an earlier version of this table invented one. The reason stands on its '
                  'own: the value table carries the number, and a note has to carry which term '
                  'produced it, or an integrator takes the wrong design intent from a correct '
                  'number.',
        verifier=None, source=BASIS + ' section 4'),
    'DES-10': Requirement(
        'the panel envelope is fixed by the frame and stated without reference to any panel '
        'design',
        cites=('AR-MOD-1', 'AR-MOD-5'),
        verifier=CHECK_GEOMETRY, source=BASIS + ' section 6.1'),
    'DES-11': Requirement(
        'where a feature\'s function is set by something that does not scale with the '
        'airframe, its size is floored at what that function requires',
        cites=('AR-PRT-1',),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 4'),
    'DES-12': Requirement(
        'a cowl remains printable in spiral vase mode: the solid exported for printing carries '
        'one closed contour per layer and no interior geometry whatsoever',
        cites=('AR-PRT-1',),
        rationale='decided in OQ-DES-CW6 and stated as a constraint over the whole interior-'
                  'surface section: vase mode spirals a single continuous contour up the part, '
                  'so a cowl given a modelled wall is no longer vase-mode printable. The '
                  'interior surface serves the analysis use cases and must not become what the '
                  'print export produces.',
        verifier=None, source='doc/design/cowl.md section 6.4, OQ-DES-CW6'),
    'DES-13': Requirement(
        'a printed part is modelled in the orientation it prints in -- the print bed is the '
        'x/y plane and +z is the build direction -- and that orientation is chosen so the '
        'layer orientation carries the load the part is designed for',
        cites=('AR-PRT-2',),
        rationale='Two concerns, deliberately two requirements, decided in OQ-DES-SR1 on '
                  '2026-08-30. This one is about which way the part stands; DES-14 is about '
                  'whether it builds without support. They interact -- the orientation that '
                  'prints most easily is often not the strongest -- and merging them would '
                  'hide that trade behind one id. **Orientation is recorded by construction**: '
                  'every existing part is modelled in its print orientation, so the model IS '
                  'the record and there is no separate field that can go stale.',
        verifier='review',
        source='OQ-DES-SR1, 2026-08-30; doc/design/corner.md, where the corner is shown to '
               'print standing on end and the load path is read against the layer planes'),
    'DES-14': Requirement(
        'a printed part builds without support material: no downward-facing surface leans '
        'shallower than overhang_angle_from_bed measured from the bed',
        cites=('AR-PRT-3',),
        rationale='The half of printability that can be settled by measurement rather than by '
                  'judgement. `overhang_angle_from_bed` is 35 degrees FROM THE BED, one value '
                  'for the project since OQ-DES-CW11, and the constants file carries its '
                  'reason. It already governs the nose plate pocket and every cowl buttress. '
                  '**Nothing evaluates it across the parts yet** -- see IP-FC-95 -- but unlike '
                  'DES-13 it is computationally verifiable, which is why the two are separate.',
        verifier=None,
        source='OQ-DES-SR1, 2026-08-30; design_constants.json slicing.overhang_angle_from_bed'),
    'DES-15': Requirement(
        'at a bay end, the features that mate with the adjoining bay -- the OML perimeter, the '
        'longeron positions and sizes, and the fastener positions and sizes -- are identical '
        'across every bay of the same size, so any bay end mates any other. **The interior '
        'aperture is not one of those features** and is free to vary',
        cites=('AR-MOD-2', 'AR-MOD-3', 'AR-MOD-1'),
        rationale='Decided in OQ-DES-SR3 on 2026-08-30. Interchange and re-ordering are what '
                  'the bolted end joint delivers, and until now nothing at this tier said so: '
                  'a change making one bay end differ from another would have violated the '
                  'architecture and passed every check. **The scope is the correction that '
                  'matters.** An earlier draft said "the same end interface", which is false. '
                  'Sameness holds for the OML perimeter, the longerons and the fasteners, and '
                  'NOT for the bulkhead interior aperture, which varies with offsets and which '
                  'on a boom bulkhead -- and on other planar bulkheads that may be defined -- '
                  'is neither a standard dimension nor a standard shape. Excluding it is not a '
                  'concession; it is AR-MOD-1, a minimally constraining physical interface, '
                  'which means constraining what must be shared and deliberately nothing else.',
        verifier=None,
        source='OQ-DES-SR3, 2026-08-30'),
}


# ------------------------------------------------------------------------------------------
# Interface -- the ten joints of dimension_scheme.md section 2
# ------------------------------------------------------------------------------------------

INTERFACE = {
    'INT-1': Requirement(
        'the corner locates the bought longeron tube over the full length of the part without '
        'retaining it, and its inboard boundary leaves the bore\'s mouth open',
        cites=('DES-5', 'DES-8'),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-1'),
    'INT-2': Requirement(
        'the corner accepts the bulkhead\'s greeble post in a socket cut from the greeble\'s '
        'own profile grown by greeble_tolerance; the post is built at nominal',
        cites=('DES-4', 'DES-6'),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-2'),
    'INT-3': Requirement(
        'the corner plugs into a socket cut from its own description; its footprint is bounded '
        'by a flat face on each arm and a 45 degree diagonal that leaves one extrusion width '
        'of material outside the bore and does not rise above the panel seat',
        cites=('DES-4', 'DES-6', 'DES-9'),
        verifier=CHECK_GEOMETRY, source=BASIS + ' section 5, INT-3'),
    'INT-4': Requirement(
        'the corner captures the bought panel along each edge in a rebate, not a slot: the '
        'panel\'s outer face is exposed and is airframe surface',
        cites=('DES-3', 'DES-5', 'DES-10'),
        verifier=CHECK_GEOMETRY, source=BASIS + ' section 5, INT-4'),
    'INT-5': Requirement(
        'the panel runs the full length of a bay uninterrupted at a station, and the '
        'bulkhead\'s outer face is set back by the panel pocket and runs the panel\'s exposed '
        'span',
        cites=('DES-3', 'DES-10'),
        verifier=CHECK_GEOMETRY, source=BASIS + ' section 5, INT-5'),
    'INT-6': Requirement(
        'a printed collet grips the bought boom tube, taking the clearance in its bore, and '
        'its wall scales with the airframe with no floor',
        cites=('DES-1', 'DES-5'),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-6'),
    'INT-7': Requirement(
        'the cowl slides over a flange on the bulkhead with the cowl\'s outer surface on the '
        'mold line, so the flange is inboard by the cowl\'s own printed wall plus the fit; on '
        'a cowling type with no cowl the flange is absent rather than zero-height',
        cites=('DES-3', 'DES-7'),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-7'),
    'INT-8': Requirement(
        'the nose seats on the cowl\'s perimeter shell as a lap joint, taking alignment from '
        'the fit and its bond from the seating face; the fit is a nominal interference',
        cites=('DES-3',),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-8'),
    'INT-9': Requirement(
        'a printed plate closes the nose tip, and its pocket is relieved at '
        'overhang_angle_from_bed so the closure prints without support',
        cites=('DES-7', 'DES-14'),
        rationale='It cited AR-PRT-3 directly until 2026-08-30, because no design requirement '
                  'stood between that architectural requirement and this joint -- a level skip, '
                  'reported as one on every run. OQ-DES-SR1 closed it by adding DES-14, which '
                  'is now the parent, and the register reports no level skips.',
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-9'),
    'INT-10': Requirement(
        'bays bolt together end to end, one end taking a bolt through a clearance hole and the '
        'other a threaded insert, with the fastener on the diagonal and its boss floored',
        cites=('DES-1', 'DES-5', 'DES-11', 'DES-15'),
        verifier=CHECK_DERIVATION, source=BASIS + ' section 5, INT-10'),
}


# ------------------------------------------------------------------------------------------
# Drawing -- dimension_scheme.md sections 3 and 5
# ------------------------------------------------------------------------------------------

PLACEMENT = 'src/Fuselage/freecad/check_dimension_placement.py'
DRAWING_CHECK = 'src/Fuselage/freecad/check_drawing.py'
SHEET = 'src/Fuselage/freecad/check_sheet_standard.py'

DRAWING = {
    'DRW-1': Requirement(
        'H1 containment: the full extent of every dimension -- text box, dimension line, '
        'arrowheads, witness lines, any leader -- lies inside the view frame and inside the '
        'sheet\'s printable area',
        cites=('DES-9',),
        rationale='a dimension partly off-sheet is not a dimension',
        verifier=PLACEMENT, source=SCHEME + ' section 5.2'),
    'DRW-2': Requirement(
        'H2 text does not touch text: no two dimension text boxes intersect, and the clear gap '
        'between them is at least one text height',
        cites=('DES-9',),
        rationale='a smaller gap reads as a single block of digits',
        verifier=PLACEMENT, source=SCHEME + ' section 5.2'),
    'DRW-3': Requirement(
        'H3 text does not touch geometry: no text box intersects a visible edge, a hidden '
        'edge, a center line, or a hatch region',
        cites=('DES-9',),
        rationale='text over a line is the most common way a digit is misread',
        verifier=PLACEMENT, source=SCHEME + ' section 5.2'),
    'DRW-4': Requirement(
        'H4 a witness line does not cross a dimension line; crossing another witness line is '
        'conventional and permitted',
        cites=('DES-9',),
        rationale='at the crossing the reader cannot tell which extension belongs to which '
                  'measurement',
        verifier=PLACEMENT, source=SCHEME + ' section 5.2'),
    'DRW-5': Requirement(
        'H5 no structurally-zero dimension is placed at all',
        cites=('DES-7', 'DES-9'),
        verifier=PLACEMENT, source=SCHEME + ' section 5.2'),
    'DRW-6': Requirement(
        'where the hard constraints cannot all be satisfied the build fails and names the '
        'dimensions it could not place; it does not relax a constraint, shrink the text, or '
        'emit the overlap',
        cites=('DES-9',),
        rationale='the escape hatch when a view genuinely cannot hold its dimensions is to '
                  'split the view or add a detail view -- a drafting decision, made '
                  'deliberately -- not to accept a worse drawing',
        verifier=PLACEMENT, source=SCHEME + ' section 5.6'),
    'DRW-7': Requirement(
        'the same family produces byte-identical placement on every run: no unseeded '
        'randomness, no dependence on dictionary or set iteration order, every tie broken by a '
        'stated total order',
        cites=('DES-9',),
        rationale='a generator whose output moves between runs makes "did this drawing change" '
                  'unanswerable, and a drawing set that cannot be diffed cannot be reviewed. '
                  'The project already has one instance of this in OpenSCAD\'s facet ordering; '
                  'do not introduce a second where a human is the consumer.',
        verifier=None, source=SCHEME + ' section 5.5'),
    'DRW-8': Requirement(
        'the checker that re-derives the hard constraints is independent of the placer that '
        'satisfies them',
        cites=('DES-9',),
        rationale='a placer that certifies its own output has only proved it is '
                  'self-consistent, which is not the claim anyone needs. It earned this on its '
                  'first input: the original lane rule drew two collinear dimension lines and '
                  'put a witness line through one, and the independent checker named it H4.',
        verifier=PLACEMENT, source=SCHEME + ' section 5.6'),
    'DRW-9': Requirement(
        'the drawn view occupies at least three quarters of the sheet frame',
        cites=('DES-9',),
        rationale='decided in OQ-DES-D5. It is what makes the drawing the sheet\'s subject '
                  'rather than the table; it is why the stock ASME title block could not be '
                  'used, since its depth caps the view at 74.3 percent with no table on the '
                  'sheet at all.',
        verifier='src/Fuselage/freecad/check_dimension_placement.py',
        source=SCHEME + ' section 5.1a, OQ-DES-D5'),
    'DRW-10': Requirement(
        'the sheet states its units, as fixed text rather than an editable field',
        cites=('DES-9',),
        rationale='a drawing whose numbers are millimeters and does not say so is wrong in a '
                  'way no automated check reaches. An editable field can be filled in blank, '
                  'and the whole point is that the statement cannot go missing.',
        verifier=SHEET, source='doc/implementation/freecad_migration.md IP-FC-86'),
    'DRW-11': Requirement(
        'the sheet template and the font are project data, pinned by id, and a build against a '
        'substituted one fails loudly',
        cites=('DES-9',),
        rationale='a sheet built against the wrong template does not crash: it renders, it '
                  'exports, it diffs cleanly, and it prints with the value table over the '
                  'title block. The template used to resolve into the FreeCAD installation, so '
                  'two machines with different FreeCAD versions emitted different sheets from '
                  'the same source.',
        verifier=SHEET, source='doc/implementation/freecad_migration.md IP-FC-86'),
    'DRW-12': Requirement(
        'for every clearance in the register, the drawing carries every dimension that '
        'entry\'s governing expression consumes',
        cites=('DES-9', 'DES-10'),
        rationale='the completeness test. The seven tolerance entries already enumerate the '
                  'joints, because each exists precisely because two parts meet somewhere, so '
                  'the test rides on a file the sweep already validates rather than on a list '
                  'maintained beside the code.',
        verifier=DRAWING_CHECK, source=SCHEME + ' section 3'),
}


# ------------------------------------------------------------------------------------------
# Model -- the delivered FreeCAD document, not the airframe
# ------------------------------------------------------------------------------------------

TANGENCY = 'src/Fuselage/freecad/check_tangency.py'
TREE = 'src/Fuselage/freecad/check_tree.py'
UNREAD = 'src/Fuselage/freecad/check_unread_rows.py'
MIGRATION = 'doc/implementation/freecad_migration.md'

MODEL = {
    'MDL-1': Requirement(
        'the delivered .FCStd stays editable: a parameter change re-solves every sketch and '
        'rebuilds the part, headless, without the GUI',
        cites=('DES-1',),
        rationale='a generated model is not only a mesh source -- someone opens it and changes '
                  'a parameter. A sketch that solved once at generation time and then went '
                  'stale, or that only re-solves in the GUI, is a regression no volume check '
                  'would notice.',
        verifier=TANGENCY, source=MIGRATION + ' IP-FC-73'),
    'MDL-2': Requirement(
        'a parameter change is made by editing the parameter sheet and recomputing, not by '
        're-running the generator',
        cites=('DES-1',),
        rationale='that is what makes it a live tree rather than a build artifact, and it is a '
                  'stronger claim than the static port had to meet',
        verifier=TREE, source=MIGRATION + ' IP-FC-38'),
    'MDL-3': Requirement(
        'the document is still a live parametric tree after a save and reload',
        cites=('DES-1',),
        rationale='that is the file the user opens',
        verifier=TREE, source=MIGRATION + ' IP-FC-38'),
    'MDL-4': Requirement(
        'an unsatisfiable configuration is refused by name, naming the sub-system that could '
        'not be solved',
        cites=('DES-1',),
        rationale='this is the whole point of solving rather than computing: the max(...; 0) '
                  'these replaced used to clamp and return a plausible wrong center. All four '
                  'corners share one sketch since OQ-ARCH-14, so a refusal saying only "the '
                  'sketch failed" would be weaker than the four separate sketches it replaced.',
        verifier=TANGENCY, source=MIGRATION + ' IP-FC-73'),
    'MDL-5': Requirement(
        'a feature the variant does not have is left out, not relocated, and no sketch carries '
        'a construction element for it',
        cites=('DES-7',),
        verifier=TANGENCY, source=MIGRATION + ' IP-FC-73, OQ-ARCH-14'),
    'MDL-6': Requirement(
        'no geometry is constrained to a modeling convenience: moving a construction element '
        'whose extent means nothing moves no solved position',
        cites=('DES-1',),
        rationale='three of the sketch\'s four features are line segments whose endpoints mean '
                  'nothing; a constraint to one of them would be geometry depending on an '
                  'arbitrary choice',
        verifier=TANGENCY, source=MIGRATION + ' IP-FC-73'),
    'MDL-7': Requirement(
        'every row on a part\'s parameter sheet reaches that part\'s geometry',
        cites=('DES-1',),
        rationale='a row that reaches nothing is invisible from the outside -- the sheet is '
                  'longer than it should be and every number on it is right -- and it stops '
                  'being harmless as soon as someone reasons from it, exports a value for it, '
                  'or asserts that a variant must supply it',
        verifier=UNREAD, source=MIGRATION + ' IP-FC-56'),
}


# ------------------------------------------------------------------------------------------
# Equivalence -- the two geometry paths, and the sweep as a whole
# ------------------------------------------------------------------------------------------

REGENERATE = 'src/Fuselage/freecad/check_regenerate.py'
SWEEP = 'src/Fuselage/tools/sweep_check.py'
SCAD_CHANGE = 'src/Fuselage/tools/verify_scad_change.py'
DRIVERS = 'src/Fuselage/tools/verify_drivers.py'

EQUIVALENCE = {
    'EQV-1': Requirement(
        'the FreeCAD part and the OpenSCAD render of the same variant agree by measured '
        'geometry -- volume, bounding box, face count -- and not by bytes',
        cites=('DES-1',),
        rationale='generated output is not stable byte for byte. OpenSCAD emits the same mesh '
                  'with a different facet order on every run, so a file diff reports '
                  'differences that are not differences.',
        verifier=REGENERATE, source=MIGRATION + ' IP-FC-5'),
    'EQV-2': Requirement(
        'an agreement tolerance is relative to the quantity it bounds, and where it is a '
        'length it scales with U',
        cites=('DES-1',),
        rationale='a part\'s coordinates are proportional to U, and a residual a solver stops '
                  'on is proportional to the magnitude of the numbers it works in, so a fixed '
                  'millimeter figure means something four times stricter at U=4 than at U=1. '
                  'These are agreement tolerances between two engines and are NOT printed '
                  'clearances, which are about 0.1 mm and are design quantities.',
        verifier=TANGENCY, source=MIGRATION + ' IP-FC-73, compare_backends.bbox_tol'),
    'EQV-3': Requirement(
        'every scaling family in a sweep carries the same set of parts, where a family is one '
        'U scale plus one panel stock',
        cites=('DES-1',),
        rationale='that is what makes a set of parts mutually buildable. Sweep totals look '
                  'correct while one family is quietly short, because a total cannot see the '
                  'shape of what is missing.',
        verifier=SWEEP, source=SWEEP),
    'EQV-4': Requirement(
        'every exported mesh parses as a whole mesh',
        cites=('DES-1',),
        rationale='a killed render leaves a partial file that existence checks treat as '
                  'finished, so counting files proves nothing',
        verifier=SWEEP, source=SWEEP),
    'EQV-5': Requirement(
        'a change to a shared library is shown to alter no geometry before it is accepted, by '
        're-rendering real parts rather than by inspecting the diff',
        cites=('DES-1',),
        rationale='a generated .scad names its library by path and contains none of its text, '
                  'so editing a module under scad/ leaves every generated file byte-identical '
                  'and a text comparison is blind to it',
        verifier=SCAD_CHANGE, source=SCAD_CHANGE),
    'EQV-6': Requirement(
        'every GUI driver renders: the interactive path a person opens a part through is not '
        'allowed to break silently while the sweep passes',
        cites=('DES-1',),
        rationale='the drivers are the interactive path, and they set concrete values rather '
                  'than being swept. They are NOT a source of truth about design choices for '
                  'parameters -- what they establish is that the path still works.',
        verifier=DRIVERS, source=DRIVERS),
}


#: Every register below the architecture, in the order the document states them.
REGISTERS = (
    ('DES', DESIGN),
    ('INT', INTERFACE),
    ('DRW', DRAWING),
    ('MDL', MODEL),
    ('EQV', EQUIVALENCE),
)

#: What a requirement in each register may cite. The design tier may cite architecture and may
#: cite nothing; the tiers below it must cite something, normally a design requirement.
PARENTS = {
    'DES': ('AR',),
    'INT': ('DES', 'AR'),
    'DRW': ('DES', 'AR'),
    'MDL': ('DES', 'AR'),
    'EQV': ('DES', 'AR'),
}


def resolve(name):
    """The requirement `name` refers to, or None."""
    if name in ARCHITECTURE:
        return ARCHITECTURE[name]
    for _, table in REGISTERS:
        if name in table:
            return table[name]
    return None


def order(name):
    """Sort key: the trailing number, so DES-10 follows DES-9 rather than DES-1."""
    return int(name.rsplit('-', 1)[1])


def check_register():
    """The structural properties of the register itself.

    Returns (complaints, notes). Failures are the things a reader cannot see:

      * a citation that resolves to nothing -- a decision anchored to something that is not
        there;
      * a citation to the wrong tier -- a drawing rule citing another drawing rule says nothing
        about why the drawing set exists;
      * a requirement below the design tier citing nothing at all;
      * a design requirement citing nothing AND carrying no rationale;
      * a requirement below the architecture with no `source`, which means somebody wrote it
        while writing the register;
      * a `verifier` naming a file that is not in the repository.

    Notes are not failures. Two are reported: a **level skip**, where a requirement below the
    design tier cites architecture directly, and a requirement with **no verifier at all**.
    Both are real findings and both are open questions rather than defects.
    """
    complaints = []
    notes = []

    for prefix, table in REGISTERS:
        allowed = PARENTS[prefix]
        for name in sorted(table, key=order):
            req = table[name]

            for cited in req.cites:
                target = resolve(cited)
                if target is None:
                    complaints.append('%s cites %s, which is not a requirement' % (name, cited))
                    continue
                tier = cited.split('-')[0]
                if tier not in allowed:
                    complaints.append('%s cites %s, which is not a tier %s may cite (%s)'
                                      % (name, cited, prefix, ', '.join(allowed)))
                elif tier == 'AR' and prefix != 'DES':
                    notes.append('%s cites %s directly, skipping the design tier' %
                                 (name, cited))

            if not req.cites and prefix != 'DES':
                complaints.append('%s cites nothing; a rule about the delivered system that '
                                  'answers to nothing above it is a requirement nobody asked '
                                  'for' % name)
            if not req.cites and not req.rationale:
                complaints.append('%s cites nothing and carries no rationale; with nothing '
                                  'above it, that sentence would be its whole justification'
                                  % name)
            if not req.source:
                complaints.append('%s names no source; a requirement with no record of where '
                                  'it was decided is one somebody wrote while writing a '
                                  'register' % name)
            if req.verifier is None:
                notes.append('%s is verified by nothing' % name)
            elif req.verifier != 'review':
                if not os.path.exists(os.path.join(ROOT, req.verifier)):
                    complaints.append('%s names %s as its verifier, which is not in the '
                                      'repository' % (name, req.verifier))
    return complaints, notes


def check_document(path=DOCUMENT):
    """`doc/design/system_requirements.md` states the same set of ids this module carries.

    Deliberately shallow: it compares the *set* of ids, not the wording. A checker that
    compared prose would either be defeated by a rephrasing or would forbid one. What it
    catches is the failure that actually happens to a specification kept beside code -- a
    requirement added in one place and not the other.
    """
    if not os.path.exists(path):
        return ['%s does not exist; the requirement set is stated nowhere a reader can find it'
                % os.path.normpath(path)]

    with io.open(path, encoding='utf-8') as handle:
        text = handle.read()

    complaints = []
    for prefix, table in REGISTERS:
        found = set(re.findall(r'\b%s-\d+\b' % prefix, text))
        for name in sorted(found - set(table), key=order):
            complaints.append('%s names %s, which the register does not carry'
                              % (os.path.basename(path), name))
        for name in sorted(set(table) - found, key=order):
            complaints.append('%s is in the register and is not stated in %s'
                              % (name, os.path.basename(path)))
    return complaints


def coverage():
    """Which architectural requirements are reached, and by what.

    Returns {AR id: [citing ids]}, including the ones nothing reaches, since those are the
    point of running it.
    """
    reached = dict((name, []) for name in ARCHITECTURE)
    for _, table in REGISTERS:
        for name in sorted(table, key=order):
            for cited in table[name].cites:
                if cited in reached:
                    reached[cited].append(name)
    return reached


def report():
    total = sum(len(table) for _, table in REGISTERS)
    print('REGISTER -- %d architectural, %d below' % (len(ARCHITECTURE), total))
    for prefix, table in REGISTERS:
        print('  %-4s %2d' % (prefix, len(table)))
    print('')
    print('COVERAGE -- architectural requirements, and what reaches them')
    for name in sorted(ARCHITECTURE, key=lambda k: (k.split('-')[1], order(k))):
        who = coverage()[name]
        print('  %-10s %s' % (name, ', '.join(who) if who else '-- nothing'))


def main(argv):
    if '--report' in argv:
        report()
        return 0

    failed = 0
    broken, notes = check_register()
    if broken:
        failed += 1
        print('register -- %d defects' % len(broken))
        for line in broken:
            print('    ' + line)
    else:
        total = sum(len(table) for _, table in REGISTERS)
        derived = sorted((n for n in DESIGN if DESIGN[n].derived), key=order)
        print('register -- %d requirements below %d architectural; every citation resolves to '
              'a tier above' % (total, len(ARCHITECTURE)))
        print('    %d of the %d design requirements cite architecture, %d carry their own '
              'rationale (%s)'
              % (len(DESIGN) - len(derived), len(DESIGN), len(derived), ', '.join(derived)))
    for line in notes:
        print('    note: ' + line)

    drift = check_document()
    if drift:
        failed += 1
        print('document -- %d disagreements with doc/design/system_requirements.md'
              % len(drift))
        for line in drift:
            print('    ' + line)
    else:
        print('document -- doc/design/system_requirements.md states every id in the register, '
              'and no others')

    unreached = [name for name, who in sorted(coverage().items()) if not who]
    print('coverage -- %d of %d architectural requirements are cited; %d are not (%s)'
          % (len(ARCHITECTURE) - len(unreached), len(ARCHITECTURE), len(unreached),
             ', '.join(sorted(unreached))))

    if failed:
        print('')
        print('FAIL -- the register does not hold together')
        return 1
    print('')
    print('ok -- the register is structurally sound and the document states it')
    return 0


if __name__ == '__main__':
    _code = main(sys.argv[1:])
    sys.stdout.flush()
    sys.exit(_code)
