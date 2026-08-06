
# Write a collection of python functions to perform parametric analysis for a design tool. The functions will read an array of properties from the rows of each of N csv files that represent N independent axes of parametric variation, then flattens the parametric iteration into a single axis table of parameter values that will be iterated over, with an example call to a library function using the iterated parameters from the csv files. The library call will produces an output data object that these functions will save to a uniquely named file generated from the parameter values used for that iteration.

# Got it — you want a Python toolkit that:
# 1. Reads N CSV files — each one representing a set of values for a single independent parameter axis.
# 2. Produces a full factorial combination (Cartesian product) of all parameter values.
# 3. Iterates through that flattened list, calling a library function for each combination.
# 4. Saves the resulting object to a uniquely named file derived from the parameter values.

import pandas as pd
import itertools
import os
import re
from pathlib import Path
import json  # example for saving results

import solid2
import subprocess
import argparse
import concurrent.futures
import contextlib
import filecmp
import sys
import time
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesh_stats
import stl_preview

# Every path below is anchored to this file, not to the working directory, so
# the sweeps produce the same result whether they are run from the Fuselage
# root, from tools/, or from anywhere else.
_HERE = os.path.dirname(os.path.abspath(__file__))      # .../Fuselage/tools
_ROOT = os.path.dirname(_HERE)                          # .../Fuselage

# The CSVs are axes of parametric variation and stay at the Fuselage root.
PARAM_DIR = os.path.join(_ROOT, "variant_param")

# The cowl JSONs are not variation parameters -- each one is a named shape
# definition that a row of a *_type_variants.csv refers to by filename -- so
# they travel with the scripts that interpret them.
COWL_DIR = _HERE

# Insert dimensions are a fixed reference table, likewise beside the scripts.
INSERT_TABLE = os.path.join(_HERE, "threaded_insert_dimensions.csv")

# Sweep output, at the Fuselage root alongside the parameter axes.
OUTPUT_DIR = os.path.join(_ROOT, "variant_output")

# The OpenSCAD geometry modules. import_scad() resolves a bare filename against
# the working directory, so once these moved into scad/ the sweeps could only
# run from inside that one directory -- and not from tools/, where this script
# lives. Anchoring the lookup here makes the working directory irrelevant.
SCAD_DIR = os.path.join(_ROOT, "scad")


def scad_module(name):
    """Load an OpenSCAD geometry module by name, wherever the caller stands."""
    return solid2.import_scad(os.path.join(SCAD_DIR, name), use_not_include=True)


def oml_ref(filename):
    """An OML mesh named the way cowl_geometry.scad will resolve it.

    The `import()` call lives in scad/cowl_geometry.scad, and OpenSCAD resolves
    import() against the file containing the call -- not the root document and
    not the working directory. So the reference hops up out of scad/ and into
    oml/, where the meshes now live. Verified against OpenSCAD 2021.01 with a
    fixture: a module in scad/ importing "../oml/x.stl", invoked from a root
    document in a third directory, resolves correctly.

    Kept relative rather than absolute on purpose: an absolute path is what put
    a long-dead `R:\\` drive mapping into every file the 2025-09-22 sweep wrote.
    """
    return '../oml/' + filename.replace('\\', '/').lstrip('/')


# ------------------------------------------------------------
# Example "library function" to simulate your design tool call
# ------------------------------------------------------------
def example_design_tool(**params):
    """
    Simulates a library function call for the design tool.
    Replace this with your actual library call.
    """
    # Pretend the output is a dict with results
    result = {
        "input_parameters": params,
        "output_metric": sum(v for v in params.values() if isinstance(v, (int, float)))
    }
    return result

def standard_values():
    
    c = dict()
    
    c["unit_width"] = 100
    c["unit_length"] = 100
    c["corner_radius"] = 10
    c["longeron_radius"] = 2
    c["bolt_offset"] = 8

    return c

def null_printer_settings():

    c = dict()
    
    c["nozzle_diameter"] = 0.4
    c["layer_height"] = 0.2

    return c

class BulkheadType(Enum):
    NULL         = 0
    END          = 1
    INTERCONNECT = 2
    COWLING      = 3
    TAIL_BOOM    = 4

def null_parameters():

    c = dict()
    
    c["corner"] = null_corner_parameters()
    c["bulkhead"] = null_bulkhead_parameters()
    c["boom_bulkhead"] = null_boom_bulkhead_parameters()
    c["panel"] = null_panel_parameters()
    c["longeron"] = null_longeron_parameters()
    c["bolt"] = null_bolt_parameters()
    c["greeble"] = null_greeble_parameters()
    c["plate"] = null_plate_parameters()
    c["web"] = null_web_parameters()
    c["bulkhead_flange"] = null_bulkhead_flange_parameters()
    c["cowl_flange"] = null_cowl_flange_parameters()
    c["printer"] = null_printer_settings()

    return c

def null_corner_parameters():

    c = dict()

    c["FX"] = 1
    c["radius"] = 0
    c["length"] = 0
    
    return c

def null_bulkhead_parameters():

    c = dict()

    c["U"] = 1
    c["width"] = 0
    c["thickness"] = 0
    c["type"] = BulkheadType.NULL
    c["type_name"] = ""
    
    return c

def null_boom_bulkhead_parameters():

    c = dict()

    c["diameter"] = 0
    c["thickness"] = 0
    c["y_position"] = 0
    c["z_position"] = 0
    c["collet_thickness"] = 0
    c["key_width"] = 0
    c["key_height"] = 0
    c["key_radius"] = 0
    c["key_web_width"] = 0
    c["key_angle"] = 0
    c["tolerance"] = 0
    c["type_name"] = ""
    c["make_vert_web"] = False;
    c["make_lower_web"] = False;
    
    return c

def null_panel_parameters():

    c = dict()

    c["thickness"] = 0
    c["offset"] = 0
    c["overlap"] = 0
    c["tolerance"] = 0
    c["type_name"] = ""
    c["is_metric"] = True

    return c

def null_longeron_parameters():

    c = dict()

    c["radius"] = 0
    c["tolerance"] = 0

    return c

def null_bolt_parameters():

    c = dict()

    c["radius"] = 0
    c["thickness"] = 0
    c["offset"] = 0
    c["is_anchor"] = False

    return c

def null_greeble_parameters():

    c = dict()

    c["opening_angle"] = 0
    c["tolerance"] = 0
    c["thickness"] = 0
    c["nub_thickness"] = 0

    return c

def null_plate_parameters():

    c = dict()

    c["thickness"] = 0
    
    return c

def null_web_parameters():

    c = dict()

    c["fillet_radius"] = 0
    c["width"] = 0
    
    return c

def null_bulkhead_flange_parameters():

    c = dict()

    c["fillet_radius"] = 0
    c["thickness"] = 0
    c["chamfer"] = 0
    
    return c

def null_cowl_flange_parameters():

    c = dict()

    c["height"] = 0
    c["tolerance"] = 0
    
    return c

def null_nose_parameters():

    c = dict()

    c["cowl_type"] = "nose"     # "nose" or "tail"; set from the parameter file
    c["type_name"] = ""
    c["U"] = 1
    c["unit_width"] = 0

    c["cut_len"] = 0
    c["cone_angle"] = 0

    c["oml"] = null_oml_parameters()
    # NOTE: the nose plate is not the bulkhead plate. null_plate_parameters()
    # describes the bulkhead's plate (thickness only); the nose plate carries a
    # diameter and flange. Calling the wrong one here silently produced a plate
    # with no diameter.
    c["plate"] = null_nose_plate_parameters()
    c["nose"] = null_nose_nose_parameters()
    c["buttress"] = null_buttress_full_parameters()
    c["printer"] = null_printer_settings()

    return c

def null_oml_parameters():

    c = dict()

    c["filename"] = ""
    c["scale"] = 0
    c["length"] = 0
    c["offset_x"] = 0
    c["reversed"] = False

    return c

def null_nose_plate_parameters():

    c = dict()

    c["active"] = False
    c["diameter"] = 0
    c["thickness"] = 0
    c["flange_width"] = 0
    c["flange_height"] = 0
    c["tolerance"] = 0

    return c

def null_nose_nose_parameters():

    c = dict()

    c["active"] = False
    c["flange_inset"] = 0
    c["flange_height"] = 0

    return c

def null_buttress_full_parameters():

    c = null_buttress_common_parameter()

    c["top"] = null_buttress_parameter()
    c["top_diag1"] = null_buttress_parameter()
    c["top_diag2"] = null_buttress_parameter()
    c["bottom"] = null_buttress_parameter()
    c["side"] = null_buttress_parameter()

    return c

def null_buttress_common_parameter():

    c = dict()

    c["z_offset"] = 0
    c["r_inset"] = 0
    c["thickness"] = 0

    return c

def null_buttress_parameter():

    c = dict()

    c["active"] = False
    c["angle"] = 0
    c["y_offset"] = 0
    c["z_start"] = 0
    c["depth"] = 0      # named "depth" to match the JSON parameter files
    c["z_end"] = 0
    c["r_start"] = 0
    c["r_end"] = 0

    return c
    
def scaled_standard_values(U,FX):

    sv = standard_values()
    
    c = dict()

    c["unit_width"] =sv["unit_width"]*U
    c["unit_length"] = sv["unit_length"]*U*FX
    c["corner_radius"] = sv["corner_radius"]*U
    c["longeron_radius"] = sv["longeron_radius"]*U
    c["bolt_offset"] = sv["bolt_offset"]*U

    return c

def derived_parameters(U,FX,user_parameters,printer_settings,is_bulkhead):

    import math

    c = null_parameters()

    # transcribe standard values
    ssv = scaled_standard_values(U,FX)
    c["bulkhead"]["U"] = U
    c["bulkhead"]["width"] = ssv["unit_width"]
    c["corner"]["FX"] = FX
    c["corner"]["radius"] = ssv["corner_radius"]
    c["corner"]["length"] = ssv["unit_length"]
    c["longeron"]["radius"] = ssv["longeron_radius"]
    c["bolt"]["offset"] = ssv["bolt_offset"]

    c["printer"] = printer_settings

    # fixed parameters

    c["longeron"]["tolerance"] = 0.05
    c["greeble"]["opening_angle"] = 35
    
    # derive values from user_paraemters

    if is_bulkhead:
        is_end = user_parameters["is_end"]
        is_interconnect = user_parameters["is_interconnect"]
        is_cowling = user_parameters["is_cowling"]
        is_boom = user_parameters["is_boom"]
        is_anchor = user_parameters["is_anchor"]
    
        c["bulkhead"]["type_name"] = user_parameters["bulkhead_type_name"]
        c["greeble"]["tolerance"] = 0.0
    else:
        is_end = False
        is_interconnect = False
        is_cowling = False
        is_boom = False
        is_anchor = False
        
        c["bulkhead"]["type_name"] = ""
        c["greeble"]["tolerance"] = 0.05
        
    c["bulkhead"]["type"] = encode_bulkhead_type(is_end, is_interconnect, is_cowling, is_boom)
    c["bulkhead"]["thickness"] = user_parameters["bulkhead_thickness"]
    c["panel"]["is_metric"] = user_parameters["panel_is_metric"]
    c["panel"]["thickness"] = user_parameters["panel_thickness_mm"]
    c["panel"]["type_name"] = user_parameters["panel_name"]

    # recreate derived dimensions from corner_end()
    c["greeble"]["thickness"] = max(2*math.sqrt(U)*c["printer"]["nozzle_diameter"], 2*c["printer"]["nozzle_diameter"])
    c["greeble"]["nub_thickness"] = max(2*math.sqrt(U)*c["printer"]["nozzle_diameter"], 2*c["printer"]["nozzle_diameter"])

    if is_cowling or c["panel"]["thickness"]==0:
        c["panel"]["tolerance"] = 0.0
    else:
        c["panel"]["tolerance"] = 0.1
    
    if not is_cowling:
        
        if c["panel"]["thickness"]==0:
            c["panel"]["overlap"] = 0
        else:
            c["panel"]["overlap"] = max(c["panel"]["thickness"], 4)

        # keep the inside corner of the panel from coming too close to the greeble perimeter
        panel_clearance_radius = c["longeron"]["radius"] + c["longeron"]["tolerance"] + c["greeble"]["thickness"]  + c["greeble"]["nub_thickness"] + 2*c["printer"]["nozzle_diameter"]

        # lower edge of the panel
        panel_corner_y = max(c["corner"]["radius"] - c["panel"]["thickness"] - c["panel"]["tolerance"], 0)

        if panel_clearance_radius > panel_corner_y:
            panel_offset = math.sqrt(panel_clearance_radius*panel_clearance_radius - panel_corner_y*panel_corner_y);
        else:
            panel_offset = 0

        # keep the offset + overlap outside of the greeble nub bevel

        # print("panel_offset = " + str(panel_offset))
        # print("panel_clearance_radius = " + str(panel_clearance_radius))
        
        greeble_clearance_width = 1*U # extra width around the greeble to allow the corner to snap in on the back side
        # print("greeble_clearance_width = " + str(greeble_clearance_width))
        
        panel_offset = max(panel_offset, (panel_clearance_radius - 2*c["printer"]["nozzle_diameter"])/math.sqrt(2) + 2*c["printer"]["nozzle_diameter"] + greeble_clearance_width - c["panel"]["overlap"])
        panel_offset = max(panel_offset, 0)
        panel_offset = min(panel_offset, math.sqrt(2)*c["corner"]["radius"])
        panel_offset = 0.25*math.ceil(4*panel_offset) # inflate to nearest 0.25 mm

        # print("panel_offset = " + str(panel_offset))
        
        c["panel"]["offset"] = panel_offset
    else:
        c["panel"]["overlap"] = 0
        c["panel"]["offset"] = 0

    c["bolt"]["diameter"] = user_parameters["bulkhead_bolt_diameter"]
    
    if is_anchor:
        # look up anchor size from bolt radius
        c["bolt"]["radius"] = lookup_anchor_diameter(c["bolt"]["diameter"])/2
    else:
        c["bolt"]["radius"] = c["bolt"]["diameter"]/2

    if is_cowling:
        c["cowl_flange"]["height"]=2*U;
        c["cowl_flange"]["tolerance"]=0.2;
        c["bulkhead_flange"]["thickness"]=max(math.ceil(3*U)*c["printer"]["nozzle_diameter"], 3*c["printer"]["nozzle_diameter"])
    else:
        c["cowl_flange"]["height"]=0;
        c["cowl_flange"]["tolerance"]=0.0;
        c["bulkhead_flange"]["thickness"]=max(math.ceil(2*U)*c["printer"]["nozzle_diameter"], 2*c["printer"]["nozzle_diameter"])
    
    c["bolt"]["thickness"]=max(3*U, 3)
    c["plate"]["thickness"]=math.ceil(4*U)*c["printer"]["layer_height"]
    c["web"]["fillet_radius"]=2*U
    
    if is_boom:
        c["web"]["width"]=6*U
    else:
        c["web"]["width"]=3*U
        
    c["bulkhead_flange"]["fillet_radius"]=2*U
    c["bulkhead_flange"]["chamfer"]=1*U

    if is_boom:
        c["boom_bulkhead"] = derived_boom_bulkhead_parameters(U,FX,user_parameters,printer_settings)
    
    return c

def read_param_json(file_path):
    """
    Reads one of the nose/tail JSON parameter files.
    """
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


# Values in the nose/tail JSON files are fractions of unit_width; a few are
# ratios or angles and are used as-is. Which is which was recovered from the
# hand-written drivers, e.g. nose_cowl.scad at U=1 (unit_width=100):
#
#     plate.diameter      0.6    -> plate_diam         = U*60
#     cut_len             0.06   -> cut_len            = U*6
#     buttress.z_offset   0.02   -> buttress_z_offset  = U*2
#     buttress.top.r_end  0.066  -> buttress_r_end     = U*6.6
#     nose.flange_height  0.01   -> nose_flange_height = 1.0
#
#     nose.flange_inset   0.5    -> nose_flange_inset  = 0.5    (unscaled)
#     plate.tolerance     0.1    -> plate_tol          = 0.1    (unscaled)
#     buttress.thickness  0.05   -> buttress_thickness = 0.05   (unscaled)
#     oml.length          0.05   -> oml_length         = 0.050  (unscaled)
#     cone_angle          35     -> cone_angle         = 35     (unscaled)
NOSE_UNSCALED = ("cone_angle", "tolerance", "flange_inset", "thickness",
                 "active", "angle", "filename", "scale", "length",
                 "offset_x", "reversed")


def derived_cowl_parameters(U, FX, user_parameters, printer_settings):
    """
    Expands a nose or tail JSON parameter file into the nested dict the cowl
    geometry modules expect, scaling fractional values by unit_width.

    Nose and tail share this because they share the cowl bulkhead and the OML
    blank; the JSON schema is a superset covering both. What differs is which
    geometry module consumes it, and that is decided by "cowl_type" in the file
    itself rather than by which sweep happens to be running -- feeding a tail
    parameter file to the nose module produces a shape nobody designed.
    """
    c = null_nose_parameters()

    unit_width = scaled_standard_values(U, FX)["unit_width"]

    param_path = os.path.join(COWL_DIR, user_parameters["parameter_filename"])
    src = read_param_json(param_path)

    c["cowl_type"] = src.get("cowl_type", "nose")
    c["type_name"] = (user_parameters.get("nose_type_name")
                      or user_parameters.get("tail_type_name")
                      or user_parameters.get("cowl_type_name", ""))
    c["U"] = U
    c["unit_width"] = unit_width
    c["printer"] = printer_settings

    c["cone_angle"] = src["cone_angle"]
    c["cut_len"] = src["cut_len"] * unit_width

    for k in c["oml"]:
        c["oml"][k] = src["oml"][k]

    # Absolute millimetres from the per-U variation table
    # (nose_size_variants.csv), NOT scaled by unit_width. These are set by the
    # printing process as much as by airframe size: a plate is a whole number
    # of layers thick and a flange a whole number of extrusion widths wide.
    # Seeded from linear U scaling rounded UP to the next 0.2 mm layer (Z) or
    # 0.4 mm extrusion (XY); the U=1 row reproduces the original constants.
    # The table is the place to tune these -- do not reintroduce a formula.
    # The nose tip and its plate exist only on a nose. A tail parameter file
    # carries no size row for them, so they are read only when they apply --
    # requiring them of a tail would be demanding dimensions for parts it does
    # not have.
    c["nose"]["active"] = src["nose"]["active"]
    c["nose"]["flange_inset"] = src["nose"]["flange_inset"]
    c["nose"]["flange_height"] = user_parameters.get("nose_flange_height", 0)

    c["plate"]["active"] = src["plate"]["active"]
    c["plate"]["tolerance"] = src["plate"]["tolerance"]
    c["plate"]["diameter"] = src["plate"]["diameter"] * unit_width
    c["plate"]["thickness"] = user_parameters.get("plate_thickness", 0)
    c["plate"]["flange_width"] = user_parameters.get("plate_flange_width", 0)
    c["plate"]["flange_height"] = user_parameters.get("plate_flange_height", 0)

    b_src = src["buttress"]
    c["buttress"]["thickness"] = b_src["thickness"]
    c["buttress"]["z_offset"] = b_src["z_offset"] * unit_width
    c["buttress"]["r_inset"] = b_src["r_inset"] * unit_width

    for name in ("top", "top_diag1", "top_diag2", "bottom", "side"):
        s = b_src[name]
        d = c["buttress"][name]
        for k in d:
            d[k] = s[k] if k in NOSE_UNSCALED else s[k] * unit_width

    return c


def derived_boom_bulkhead_parameters(U,FX,user_parameters,printer_settings):

    c = null_boom_bulkhead_parameters()
    ssv = scaled_standard_values(U,FX)

    c["diameter"] = ssv["unit_width"]*user_parameters["boom_diameter"]
    c["thickness"] = U*2
    c["y_position"] = ssv["unit_width"]*user_parameters["y_position"]
    c["z_position"] = ssv["unit_width"]*user_parameters["z_position"]
    c["collet_thickness"] = U*3
    c["key_width"] = max(U*2, 2)
    c["key_height"] = max(U*2, 2)
    c["key_radius"] = max(U*0.5, 0.5)
    c["key_web_width"] = U*6
    c["key_angle"] = 0
    c["tolerance"] = 0.2
    c["type_name"] = user_parameters["bulkhead_type_name"]
    c["make_vert_web"] = user_parameters["make_vert_web"]
    c["make_lower_web"] = user_parameters["make_lower_web"]

    return c

# ------------------------------------------------------------
# Functions for parametric analysis
# ------------------------------------------------------------
def read_param_csv(file_path):
    """
    Reads a CSV file and returns a list of parameter dictionaries.
    Assumes each CSV has one parameter per column.
    """
    df = pd.read_csv(file_path)
    return df.to_dict(orient="records")


def read_all_param_axes(file_paths):
    """
    Reads all CSV files (each representing one axis of variation).
    Returns a list of lists of parameter dicts.
    """
    return [read_param_csv(path) for path in file_paths]


def flatten_param_space(param_axes):
    """
    Creates the full factorial combination of parameter values from each axis.
    Each axis is a list of dicts; we combine them into merged dicts.
    """
    combinations = []
    for combo in itertools.product(*param_axes):
        merged = {}
        for param_dict in combo:
            merged.update(param_dict)
        combinations.append(merged)
    return combinations


def generate_filename_from_params(params, prefix="result", extension=".json"):
    """
    Creates a unique filename based on parameter values.
    """
    safe_parts = [
        f"{k}={str(v).replace(' ', '_')}" for k, v in sorted(params.items())
    ]
    return prefix + "__" + "__".join(safe_parts) + extension


def generate_fuselage_corner_variant_filename_from_params(dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    
    if dp["panel"]["is_metric"]:
        unit_str = "metric"
    else:
        unit_str = "imperial"
            
    # return "bulk" + "__U_" + str(dp["bulkhead"]["U"]) + "__metric_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__type_" + dp["bulkhead"]["type"] + extension
    
    dir_name = os.path.join("U_" + str(dp["bulkhead"]["U"]), unit_str, "panel_" + dp["panel"]["type_name"].replace('/', '_'), "corner")
    file_name = "U_" + str(dp["bulkhead"]["U"]) + "__" + unit_str + "_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__" + "corner_FX_" + str(dp["corner"]["FX"]) + extension
    
    # return "bulk" + "__U_" + str(dp["bulkhead"]["U"]) + "__metric_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__type_" + dp["bulkhead"]["type"] + extension

    return os.path.join(dir_name, file_name)

def corner_validity_check(dp):
    """
    Tests the parameters for valid agreement
    """

    sv = standard_values()
    
    U = (dp["bulkhead"]["width"]/sv["unit_width"])
    
    bulkhead_min_panel_thickness_parametric = U * 1
    bulkhead_max_panel_thickness_parametric = dp["corner"]["radius"] - (dp["longeron"]["radius"] + dp["longeron"]["tolerance"] + dp["greeble"]["thickness"] + dp["greeble"]["nub_thickness"])
    
    # check bulkead_thickness >= bulkhead_max_panel_thickness_parametric

    is_valid = dp["panel"]["thickness"] == 0 or dp["panel"]["thickness"] >= bulkhead_min_panel_thickness_parametric
    is_valid &= dp["panel"]["thickness"] <= bulkhead_max_panel_thickness_parametric
    
    return is_valid

def run_corner_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    printer_settings = null_printer_settings()
    printer_settings["nozzle_diameter"] = 0.6

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        # print(params)
        U = params["U"]
        FX = params["FX"]
        
        dp = derived_parameters(U,FX,params,printer_settings,False)
        
        is_valid = corner_validity_check(dp)

        if is_valid:

            print(dp)
            # result = example_design_tool(**params)  # replace with your actual call
            filename = generate_fuselage_corner_variant_filename_from_params(dp)

            corner_render(dp, output_dir, filename)

def generate_fuselage_bulkhead_variant_filename_from_params(dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    
    if dp["panel"]["is_metric"]:
        unit_str = "metric"
    else:
        unit_str = "imperial"
            
    # return "bulk" + "__U_" + str(dp["bulkhead"]["U"]) + "__metric_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__type_" + dp["bulkhead"]["type"] + extension
    
    dir_name = os.path.join("U_" + str(dp["bulkhead"]["U"]), unit_str, "panel_" + dp["panel"]["type_name"].replace('/', '_'), "bulkhead")
    file_name = "U_" + str(dp["bulkhead"]["U"]) + "__" + unit_str + "_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__" + "bulkhead_" + dp["bulkhead"]["type_name"] + extension
    
    # return "bulk" + "__U_" + str(dp["bulkhead"]["U"]) + "__metric_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__type_" + dp["bulkhead"]["type"] + extension

    return os.path.join(dir_name, file_name)

def generate_fuselage_boom_bulkhead_variant_filename_from_params(dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    
    if dp["panel"]["is_metric"]:
        unit_str = "metric"
    else:
        unit_str = "imperial"
            
    # return "bulk" + "__U_" + str(dp["bulkhead"]["U"]) + "__metric_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__type_" + dp["bulkhead"]["type"] + extension
    
    dir_name = os.path.join("U_" + str(dp["bulkhead"]["U"]), unit_str, "panel_" + dp["panel"]["type_name"].replace('/', '_'), "bulkhead")
    file_name = "U_" + str(dp["bulkhead"]["U"]) + "__" + unit_str + "_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__" + "boom_bulkhead_" + dp["bulkhead"]["type_name"] + extension
    
    # return "bulk" + "__U_" + str(dp["bulkhead"]["U"]) + "__metric_panel_" + dp["panel"]["type_name"].replace('/', '_') + "__type_" + dp["bulkhead"]["type"] + extension

    return os.path.join(dir_name, file_name)
    
def generate_fuselage_nose_variant_filename_from_params(U, dp, is_nose_cowl, is_nose_nose, is_nose_plate, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    if is_nose_cowl:
        type_name = "cowl"
    elif is_nose_nose:
        type_name = "nose"
    elif is_nose_plate:
        type_name = "plate"
    else:
        type_name = ""

    # The nose-type name has to be in the path: the sweep now runs one pass per
    # JSON parameter file, and without it every variant would write over the
    # previous one at the same U.
    variant = dp["type_name"]

    dir_name = os.path.join("U_" + str(U), "nose", variant)
    file_name = "U_" + str(U) + "__" + variant + "__nose_" + type_name + extension

    return os.path.join(dir_name, file_name)
    
def generate_fuselage_tail_variant_filename_from_params(U, dp, extension=".scad"):
    """
    Creates a unique filename based on parameter values.
    """
    # The variant name is in the path for the same reason it is on the nose
    # side: one pass per parameter file, and without it a second tail type
    # would overwrite the first at the same path rather than sit beside it.
    variant = dp["type_name"]

    dir_name = os.path.join("U_" + str(U), "tail", variant)
    file_name = "U_" + str(U) + "__" + variant + "__tail" + extension

    return os.path.join(dir_name, file_name)

def bulkhead_validity_check(dp):
    """
    Tests the parameters for valid agreement
    """

    sv = standard_values()
    
    U = (dp["bulkhead"]["width"]/sv["unit_width"])
    
    bulkhead_min_panel_thickness_parametric = U * 1
    bulkhead_max_panel_thickness_parametric = dp["corner"]["radius"] - (dp["longeron"]["radius"] + dp["longeron"]["tolerance"] + dp["greeble"]["thickness"] + dp["greeble"]["nub_thickness"])
    
    # check bulkead_thickness >= bulkhead_max_panel_thickness_parametric

    is_valid = dp["panel"]["thickness"] == 0 or dp["panel"]["thickness"] >= bulkhead_min_panel_thickness_parametric
    is_valid &= dp["panel"]["thickness"] <= bulkhead_max_panel_thickness_parametric
    is_valid &= (not dp["bulkhead"]["type"] == BulkheadType.COWLING) or dp["panel"]["thickness"] == 0
    
    return is_valid

def run_bulkhead_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    printer_settings = null_printer_settings()
    printer_settings["nozzle_diameter"] = 0.6
    
    FX = 1.0

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        # print(params)
        U = params["U"]
        
        dp = derived_parameters(U,FX,params,printer_settings,True)
        
        is_valid = bulkhead_validity_check(dp)

        if is_valid:

            print(dp)
            filename = generate_fuselage_bulkhead_variant_filename_from_params(dp)

            bulkhead_render(dp, output_dir, filename)

def run_boom_bulkhead_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    printer_settings = null_printer_settings()
    printer_settings["nozzle_diameter"] = 0.6
    
    FX = 1.0

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        # print(params)
        U = params["U"]
        
        dp = derived_parameters(U,FX,params,printer_settings,True)
        
        is_valid = bulkhead_validity_check(dp)

        if is_valid:

            print(dp)
            filename = generate_fuselage_boom_bulkhead_variant_filename_from_params(dp)

            boom_bulkhead_render(dp, output_dir, filename)


def run_nose_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    # FX does not vary for cowl geometry -- a cowl is defined against the OML,
    # not a bay length -- but derived_cowl_parameters shares the scaling helper
    # with the other sweeps, which takes it.
    FX = 1.0
    printer_settings = null_printer_settings()
    printer_settings["nozzle_diameter"] = 0.6

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        U = params["U"]

        dp = derived_cowl_parameters(U, FX, params, printer_settings)

        if dp["cowl_type"] != "nose":
            raise ValueError(
                "%s declares cowl_type=%r but is listed in the NOSE type axis. "
                "A tail parameter file rendered through the nose modules "
                "produces geometry nobody designed; put it in "
                "tail_type_variants.csv instead."
                % (params["parameter_filename"], dp["cowl_type"]))

        print(dp)

        # Which of the three parts exist is a property of the parameter file.
        wanted = [(True, False, False)]
        if dp["nose"]["active"]:
            wanted.append((False, True, False))
        if dp["plate"]["active"]:
            wanted.append((False, False, True))

        for (is_nose_cowl, is_nose_nose, is_nose_plate) in wanted:
            filename = generate_fuselage_nose_variant_filename_from_params(
                U, dp, is_nose_cowl, is_nose_nose, is_nose_plate)
            nose_render(U, dp, output_dir, filename,
                        is_nose_cowl, is_nose_nose, is_nose_plate)


def run_tail_parametric_sweep(csv_files, output_dir):
    """
    Main function:
    1. Reads CSVs
    2. Flattens parameter space
    3. Calls the library function
    4. Saves results to unique files
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: Read and flatten
    param_axes = read_all_param_axes(csv_files)
    all_combinations = flatten_param_space(param_axes)

    FX = 1.0
    printer_settings = null_printer_settings()
    printer_settings["nozzle_diameter"] = 0.6

    # Step 3 & 4: Iterate, run, save
    for params in all_combinations:

        U = params["U"]

        dp = derived_cowl_parameters(U, FX, params, printer_settings)

        if dp["cowl_type"] != "tail":
            raise ValueError(
                "%s declares cowl_type=%r but is listed in the TAIL type axis."
                % (params["parameter_filename"], dp["cowl_type"]))

        print(dp)

        filename = generate_fuselage_tail_variant_filename_from_params(U, dp)

        tail_render(U, dp, output_dir, filename)
            
_SCAD_REF_RE = re.compile(r'(?m)^(\s*)(use|include)\s*<([^>]+)>\s*;')


def relativize_scad_references(scad_path):
    """Rewrite absolute `use <...>` / `include <...>` lines to relative ones.

    solid2's resolve_scad_filename() calls .absolute() unconditionally, so every
    generated file records the exact directory it was produced in. The
    2025-09-22 sweep was run from a mapped drive, and all 1774 of its .scad
    files still say `use <R:\\Alex\\...>` -- a path that resolves nowhere now, so
    none of them can be re-rendered.

    OpenSCAD resolves `use` and `include` against the directory of the file
    containing them, so a path relative to the generated file is both correct
    and portable. Paths on another drive or share cannot be expressed relatively
    and are left absolute rather than mangled.
    """
    here = os.path.dirname(os.path.abspath(scad_path))

    def to_relative(match):
        indent, keyword, target = match.groups()
        if not os.path.isabs(target):
            return match.group(0)
        try:
            rel = os.path.relpath(target, here)
        except ValueError:
            return match.group(0)          # different drive; no relative form
        return '%s%s <%s>;' % (indent, keyword, rel.replace(os.sep, '/'))

    with open(scad_path, encoding='utf-8') as f:
        text = f.read()
    rewritten = _SCAD_REF_RE.sub(to_relative, text)
    if rewritten != text:
        with open(scad_path, 'w', encoding='utf-8', newline='') as f:
            f.write(rewritten)


class RenderFailed(RuntimeError):
    """One or more queued OpenSCAD runs failed."""


class RenderQueue:
    """Runs the sweep's OpenSCAD invocations, optionally across a thread pool.

    The sweep is a serial loop whose per-part cost is almost entirely a blocking
    `openscad` subprocess, so it uses one core out of however many the machine has.
    Splitting the loop is unnecessary: only the subprocess calls need to overlap,
    and the Python either side of them -- building the solid2 tree, writing the
    .scad, rewriting its references -- stays on the main thread where it belongs.

    Threads rather than processes, because each job blocks in a child process and
    releases the GIL while waiting. That also sidesteps solid2's module-level facet
    state (`set_global_fn`/`fa`/`fs`), which is set during generation and would be
    a race if generation itself were parallel.

    Work is drained in chunks rather than all at the end. A failing render would
    otherwise stay invisible until thousands more had been queued behind it, and
    the run would look like it was skipping everything.
    """

    def __init__(self, workers=1, chunk=None, progress_every=20):
        self.workers = max(1, int(workers))
        self.chunk = chunk or max(self.workers * 4, 8)
        self.progress_every = progress_every
        self._pending = []
        self._done = 0
        self._failed = 0
        self._recovered = 0
        self._start = None

    def submit(self, cmd, on_success=None):
        """Queue an OpenSCAD command, or run it now when not parallel.

        `on_success` runs only if the command exits zero. That is what makes the
        write atomic: OpenSCAD renders to a temporary path and the callback moves
        it into place, so a crashed or killed render leaves no file at the real
        path rather than a convincing partial one.
        """
        job = (cmd, on_success)
        if self.workers == 1:
            self._run(job)
            self._done += 1
            return
        self._pending.append(job)
        if len(self._pending) >= self.chunk:
            self.drain()

    @staticmethod
    def _run(job):
        cmd, on_success = job
        subprocess.check_call(cmd,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
        if on_success is not None:
            on_success()

    def drain(self):
        """Run everything queued. Raises RenderFailed if any job failed."""
        if not self._pending:
            return
        jobs, self._pending = self._pending, []
        if self._start is None:
            self._start = time.time()

        failures = []
        with concurrent.futures.ThreadPoolExecutor(self.workers) as pool:
            futures = {pool.submit(self._run, c): c for c in jobs}
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:                     # noqa: BLE001
                    failures.append((futures[future], exc))
                self._done += 1
                if self._done % self.progress_every == 0:
                    rate = (time.time() - self._start) / self._done
                    sys.stderr.write(
                        '      rendered %d  (%.1f s/part, %d worker(s))\n'
                        % (self._done, rate, self.workers))
                    sys.stderr.flush()

        if failures:
            failures = self._retry_serially(failures)

        if failures:
            detail = '\n'.join('  %s\n    %s' % (job[0], e)
                               for job, e in failures[:10])
            raise RenderFailed(
                '%d of %d render(s) failed after a serial retry '
                '(%d succeeded, %d recovered on retry):\n%s'
                % (len(failures), self._done, self._done - self._failed,
                   self._recovered, detail))

    def _retry_serially(self, failures):
        """Re-run failed commands one at a time; return those that failed again.

        The dominant failure mode here is memory, not geometry. A large tail holds
        well over a gigabyte during its CGAL solve, and several at once on a loaded
        machine abort with STATUS_FATAL_APP_EXIT -- which is transient and depends
        entirely on what else was resident at that moment. Retrying serially, with
        the rest of the batch finished and its memory returned, recovers them:
        measured on the U=0.75 and U=2.0 tails, both of which aborted at five
        workers and then completed cleanly on their own in about 255 s each.

        A genuine geometry error fails again here and is reported, so this cannot
        turn a real defect into a silent pass.
        """
        self._failed += len(failures)
        still_failing = []
        sys.stderr.write('      %d render(s) failed; retrying serially\n'
                         % len(failures))
        sys.stderr.flush()
        for job, original in failures:
            try:
                self._run(job)
                self._recovered += 1
            except Exception:                                # noqa: BLE001
                still_failing.append((job, original))
        sys.stderr.write('      recovered %d of %d on retry\n'
                         % (len(failures) - len(still_failing), len(failures)))
        sys.stderr.flush()
        return still_failing

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Only flush the tail on a clean exit; on an error the queue is abandoned
        # rather than run, so a failure does not drag thousands of renders with it.
        if exc_type is None:
            self.drain()
        return False


# Module-level so the five sweep functions and their render helpers need no
# plumbing. Serial by default, which is exactly the previous behaviour; main()
# installs a parallel queue for the duration of a run.
_RENDER_QUEUE = RenderQueue(workers=1)


def set_render_queue(queue):
    """Install the queue solid_render submits to. Returns the previous one."""
    global _RENDER_QUEUE
    previous, _RENDER_QUEUE = _RENDER_QUEUE, queue
    return previous


# Resume state. Off by default so a plain run reproduces every part, which is what
# you want when geometry or parameters have changed; a resume trusts what is on disk.
_RESUME = False
_RESUME_COUNTS = {'skipped': 0, 'changed': 0}


def set_resume(enabled):
    """Skip parts that are already rendered and unchanged. Returns the previous value.

    Safe to leave on: a part is skipped only when the .scad it would generate now
    is byte-identical to the one on disk *and* the STL beside it is a whole mesh.
    Edit a geometry module or a parameter CSV and the affected parts re-render on
    their own, because their generated .scad no longer matches.

    Use --force to re-render regardless, e.g. after changing something the .scad
    text cannot see -- an OpenSCAD version bump, or an OML mesh replaced in place.
    """
    global _RESUME
    previous, _RESUME = _RESUME, bool(enabled)
    _RESUME_COUNTS['skipped'] = 0
    _RESUME_COUNTS['changed'] = 0
    return previous


# Preview PNGs are produced by the sweep, alongside each STL. On by default: a run
# should yield the parts and the images to check them by, in one command.
#
# They are rendered from the finished STL by stl_preview, not by a second OpenSCAD
# invocation. The old `--render` pass re-solved the whole CSG tree just to take a
# picture, which was the dominant cost of a run; rasterizing the mesh that the
# first invocation already produced costs a couple of seconds.
_PREVIEWS = True

# Parts a resumed run found already rendered but without a preview. Rendered in
# one parallel batch at the end rather than inline, because the resume path runs on
# the main thread and rasterizing is numpy-bound.
_PREVIEW_BACKLOG = []


def set_previews(enabled):
    """Enable or disable preview generation. Returns the previous value."""
    global _PREVIEWS
    previous, _PREVIEWS = _PREVIEWS, bool(enabled)
    del _PREVIEW_BACKLOG[:]
    return previous


def find_rendered_stls(output_dir):
    """Every finished STL under output_dir, in a stable order.

    '*.partial.stl' is excluded: those are in-flight or abandoned renders, named
    that way because OpenSCAD picks its export format from the extension and so
    cannot write to a name that does not end in .stl.
    """
    return [str(p) for p in sorted(Path(output_dir).rglob('*.stl'))
            if not p.name.endswith('.partial.stl')]


def render_preview_batch(stl_paths, workers=None, size=None, supersample=None,
                         progress_every=25):
    """Render previews for many STLs across a process pool. Returns failures.

    Processes rather than threads: rasterizing is numpy-bound, so a thread pool
    would serialize on the GIL and gain nothing. That is the opposite of the
    OpenSCAD render queue, where threads are right precisely because each job
    blocks in a child process.
    """
    size = size or stl_preview.DEFAULT_SIZE
    supersample = (stl_preview.DEFAULT_SUPERSAMPLE if supersample is None
                   else supersample)
    jobs = [(str(p), size, True, True, supersample) for p in stl_paths]
    if not jobs:
        return []
    workers = workers or default_render_workers()

    failures = []
    start = time.time()
    try:
        with concurrent.futures.ProcessPoolExecutor(workers) as pool:
            futures = [pool.submit(stl_preview.render_one, j) for j in jobs]
            for done, future in enumerate(
                    concurrent.futures.as_completed(futures), start=1):
                path, error = future.result()
                if error:
                    failures.append((path, error))
                    print('  preview FAILED  %s: %s'
                          % (os.path.basename(path), error), flush=True)
                if progress_every and (done % progress_every == 0
                                       or done == len(jobs)):
                    rate = (time.time() - start) / done
                    print('  previews %d/%d  %.2f s each  ~%.1f min left'
                          % (done, len(jobs), rate,
                             (len(jobs) - done) * rate / 60), flush=True)
    except concurrent.futures.process.BrokenProcessPool:
        # Windows spawns workers by re-importing the caller's __main__, so a driver
        # script without an `if __name__ == "__main__":` guard makes every worker
        # re-run that script and the pool collapses. Serial is slow but produces
        # the images; losing them to a harness detail would be the worse outcome.
        print('  preview pool broke -- falling back to serial. If the caller is a '
              'script, it needs an `if __name__ == "__main__":` guard.', flush=True)
        failures = [(p, e) for p, e in
                    (stl_preview.render_one(j) for j in jobs) if e]
    return failures


def rebuild_previews(output_dir=None, workers=None, force=False):
    """Regenerate previews across an existing output tree, without touching geometry.

    For look changes -- a camera fix, different edge or occlusion settings -- where
    the meshes are already correct and only the images are stale. Re-rendering the
    geometry to get new pictures would cost hours for no benefit.
    """
    output_dir = OUTPUT_DIR if output_dir is None else output_dir
    stls = find_rendered_stls(output_dir)
    if force:
        todo = stls
    else:
        todo = [p for p in stls
                if not os.path.isfile(str(Path(p).with_suffix('.png')))]

    print('previews: %d STL(s) under %s, %d to render%s'
          % (len(stls), output_dir, len(todo),
             '' if force else ' (missing only; --force redoes all)'), flush=True)
    if not todo:
        return []
    workers = workers or default_render_workers()
    failures = render_preview_batch(todo, workers=workers)
    if failures:
        print('previews: %d failed' % len(failures), flush=True)
    return failures


def _write_preview(stl_path, png_path):
    """Render a preview beside a finished STL.

    Runs on the worker thread, immediately after the STL is moved into place, so
    previews keep pace with the sweep rather than needing a second pass.

    A preview failure is reported but does not fail the part: the STL is the
    deliverable and is already written and verified by this point, so discarding a
    good part because its picture did not render would be the wrong trade. This is
    the one place a broad except is warranted, and it is not silent.
    """
    try:
        stl_preview.render_stl_to_png(stl_path, png_path)
    except Exception as exc:                                 # noqa: BLE001
        sys.stderr.write('      preview failed for %s: %s: %s\n'
                         % (os.path.basename(stl_path), type(exc).__name__, exc))
        sys.stderr.flush()


# Peak resident set observed for the heaviest part in the sweep -- a U=4.0 tail,
# roughly 367k triangles -- was about 1.27 GB. The headroom above that covers the
# larger boom bulkheads and leaves room for the CGAL peak to overshoot the steady
# state without pushing the machine into swap.
RENDER_MEMORY_PER_WORKER_MB = 1600


def _available_memory_bytes():
    """Physical memory currently available, or None if it cannot be determined."""
    try:
        if sys.platform == 'win32':
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong),
                            ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong),
                            ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong),
                            ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.ullAvailPhys)
        return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (AttributeError, OSError, ValueError):
        return None


def render_worker_budget():
    """Return (workers, reason) for the default worker count.

    Bounded by cores *and* by free memory. The memory bound is not optional: a
    CGAL render of a large tail holds well over a gigabyte, and five of them at
    once on a loaded machine exhausts physical memory and aborts OpenSCAD with
    STATUS_FATAL_APP_EXIT -- which looks like a geometry failure but is not one.

    Measured live rather than from total RAM, because this machine routinely runs
    an IDE, MCP servers, and a FreeCAD GUI alongside the sweep; the memory that
    matters is what is free at the moment the sweep starts.
    """
    override = os.environ.get('FUSELAGE_RENDER_WORKERS')
    if override:
        return max(1, int(override)), 'FUSELAGE_RENDER_WORKERS'

    # An OpenSCAD render is compute-bound and gains little from hyperthreading, so
    # the physical count is the useful number; logical // 2 is the closest estimate
    # available without adding a dependency. One core is left for the machine.
    logical = os.cpu_count() or 2
    physical = max(1, logical // 2)
    by_cores = max(1, physical - 1)

    available = _available_memory_bytes()
    if available is None:
        return by_cores, '%d physical core(s) of %d logical, 1 reserved; memory unknown' % (
            physical, logical)

    per_worker = int(os.environ.get('FUSELAGE_RENDER_WORKER_MB',
                                    RENDER_MEMORY_PER_WORKER_MB))
    by_memory = max(1, int(available // (per_worker * 1024 * 1024)))
    workers = min(by_cores, by_memory)
    reason = ('%d physical core(s) of %d logical, 1 reserved -> %d; '
              '%.1f GB free / %d MB per worker -> %d; taking the lower'
              % (physical, logical, by_cores,
                 available / (1024 ** 3), per_worker, by_memory))
    return workers, reason


def default_render_workers():
    """Workers to use when the caller does not say."""
    return render_worker_budget()[0]


def solid_render(scad_obj, output_dir, filename):

    user_path = os.environ.get('OPENSCADPATH')

    solid2.set_global_fn(0)
#    solid2.set_global_fa(5)
#    solid2.set_global_fs(0.5)
    solid2.set_global_fa(1)
    solid2.set_global_fs(0.05)

    # print(filename)

    file_dir = os.path.dirname(filename)
    file_name = os.path.basename(filename)
    (head, tail) = os.path.split(filename)

    full_output_dir = os.path.join(output_dir, file_dir)
    
    # Ensure output directory exists
    Path(full_output_dir).mkdir(parents=True, exist_ok=True)
    
    scad_filepath = os.path.join(full_output_dir, Path(file_name).with_suffix(".stl.scad").name)
    stl_filepath = os.path.join(full_output_dir, Path(file_name).with_suffix(".stl").name)
    png_filepath = os.path.join(full_output_dir, Path(file_name).with_suffix(".png").name)

    # Generate the .scad to a temporary path first, so a resume can compare it
    # against what is already on disk. Generating is cheap next to rendering, and
    # it is what makes --resume trustworthy: a resumed run that skipped purely on
    # "the STL exists" would silently keep stale parts after a .scad module or a
    # parameter CSV changed. Same code path for both sides of the comparison, so
    # they are guaranteed comparable.
    partial_scad = os.path.join(
        full_output_dir, Path(file_name).with_suffix('.partial.scad').name)
    solid2.scad_render_to_file(scad_obj, partial_scad)
    relativize_scad_references(partial_scad)     # same directory, so same result

    definition_unchanged = (
        os.path.isfile(scad_filepath)
        and filecmp.cmp(partial_scad, scad_filepath, shallow=False)
    )

    # Resume: skip a part whose definition is unchanged and whose STL is already a
    # whole mesh. The mesh sentinel is mesh_stats.is_complete, not os.path.isfile --
    # a killed render used to leave a partial .stl that every existence check
    # treated as finished. Combined with the atomic write below, a present .stl now
    # genuinely means a finished render of the definition sitting beside it.
    if _RESUME and definition_unchanged and mesh_stats.is_complete(stl_filepath):
        os.remove(partial_scad)
        _RESUME_COUNTS['skipped'] += 1
        if _RESUME_COUNTS['skipped'] % 50 == 0:
            sys.stderr.write('    ...%d already rendered\n'
                             % _RESUME_COUNTS['skipped'])
            sys.stderr.flush()
        # The geometry is done, but its preview may not be -- a run interrupted
        # before the preview, or output from before previews existed. Collect the
        # gap rather than rendering it here: this runs on the main thread, so
        # backfilling inline would render hundreds of previews one at a time while
        # every core sat idle. sweep_session renders the backlog across a pool.
        if _PREVIEWS and not os.path.isfile(png_filepath):
            _PREVIEW_BACKLOG.append(stl_filepath)
        return (scad_filepath, stl_filepath, png_filepath)

    if _RESUME and not definition_unchanged and os.path.isfile(scad_filepath):
        _RESUME_COUNTS['changed'] += 1

    os.replace(partial_scad, scad_filepath)

    # Render to a temporary path and move it into place only on success. OpenSCAD
    # writes its output progressively, so without this an interrupted run leaves a
    # convincing partial .stl at the real path -- which a resume would then skip,
    # permanently baking in a truncated part. os.replace is atomic within a volume.
    #
    # The temporary name must still end in .stl: OpenSCAD picks its export format
    # from the extension, so `-o foo.stl.partial` fails outright with exit 1. Tools
    # that scan the tree for parts filter '*.partial.stl' back out.
    partial_filepath = os.path.join(
        full_output_dir, Path(file_name).with_suffix('.partial.stl').name)
    cmd = solid2.config.config.openscad_stl_command.format(scadfile=scad_filepath, stlfile=partial_filepath)

    def _finalize(src=partial_filepath, dst=stl_filepath, png=png_filepath):
        os.replace(src, dst)
        if _PREVIEWS:
            _write_preview(dst, png)

    # Submitted rather than run directly. With a serial queue -- the default --
    # this executes immediately and behaves exactly as the direct call did; with a
    # parallel queue installed by main() it is deferred and overlapped. The .scad
    # on disk is complete either way, so nothing downstream is affected by the
    # STL arriving later; none of the five call sites use the returned STL path.
    _RENDER_QUEUE.submit(os.path.join(user_path, cmd), on_success=_finalize)

    # The preview PNG is rendered by _finalize above, from the finished STL, as
    # soon as that STL is in place. OpenSCAD used to produce it with a second
    # invocation carrying --render, which re-solved the whole CSG tree purely to
    # take a picture -- the dominant cost of the sweep, for an image the STL
    # already contains all the information for.
    #
    # To regenerate previews across an existing tree without re-rendering any
    # geometry -- after a camera or shading change, say -- use --previews-only:
    #     uv run python src/Fuselage/tools/fuselage_variants.py --previews-only --force
    # The path is returned either way so callers know where the preview belongs.
    return (scad_filepath, stl_filepath, png_filepath)

def lookup_anchor_diameter(bolt_diameter):

    anchor = read_param_csv(INSERT_TABLE)

    anchor_diam = 0;
    for a in anchor:
        if a["bolt_diameter"] == bolt_diameter:
            return a["anchor_diameter"]
            
    return 0

def decode_bulkhead_type(bulkhead_type):

    if bulkhead_type == BulkheadType.END:

        is_end = True
        is_interconnect = False
        is_cowling = False
        is_boom = False

    elif bulkhead_type == BulkheadType.INTERCONNECT:

        is_end = False
        is_interconnect = True
        is_cowling = False
        is_boom = False

    elif bulkhead_type == BulkheadType.COWLING:

        is_end = False
        is_interconnect = False
        is_cowling = True
        is_boom = False

    elif bulkhead_type == BulkheadType.TAIL_BOOM:

        is_bolt = False
        is_interconnect = False
        is_cowling = False
        is_boom = True

    else:

        is_bolt = False
        is_interconnect = False
        is_cowling = False
        is_boom = False

    return (is_end, is_interconnect, is_cowling, is_boom)

def encode_bulkhead_type(is_end, is_interconnect, is_cowling, is_boom):

    if is_end:
        bulkhead_type = BulkheadType.END
    elif is_interconnect:
        bulkhead_type = BulkheadType.INTERCONNECT
    elif is_cowling:
        bulkhead_type = BulkheadType.COWLING
    elif is_boom:
        bulkhead_type = BulkheadType.TAIL_BOOM
    else:
        bulkhead_type = BulkheadType.NULL

    return bulkhead_type

def corner_render(dp, output_dir, filename):

    fgeom = scad_module('fuselage_corner_geometry.scad')

    scadobj = fgeom.fuselage_corner(
        dp["bulkhead"]["U"],
        dp["corner"]["length"],
        dp["bulkhead"]["thickness"],
        dp["corner"]["radius"],
        dp["panel"]["thickness"],
        dp["panel"]["offset"],
        dp["panel"]["overlap"],
        dp["panel"]["tolerance"],
        dp["longeron"]["radius"],
        dp["longeron"]["tolerance"],
        dp["greeble"]["thickness"],
        dp["greeble"]["nub_thickness"],
        dp["greeble"]["tolerance"],
        dp["printer"]["nozzle_diameter"])

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)
    
    
def bulkhead_render(dp, output_dir, filename):

    # import math
    
    fgeom = scad_module('fuselage_bulkhead_geometry.scad')

    (is_end, is_interconnect, is_cowling, is_boom) = decode_bulkhead_type(dp["bulkhead"]["type"])
    
    scadobj = fgeom.bulkhead_section_full(is_interconnect,
                                       is_cowling,
                                       dp["bulkhead"]["width"],
                                       dp["corner"]["length"],
                                       dp["bulkhead"]["thickness"],
                                       dp["corner"]["radius"],
                                       dp["panel"]["thickness"],
                                       dp["panel"]["offset"],
                                       dp["panel"]["overlap"],
                                       dp["panel"]["tolerance"],
                                       dp["longeron"]["radius"],
                                       dp["longeron"]["tolerance"],
                                       dp["bolt"]["radius"],
                                       dp["bolt"]["thickness"],
                                       dp["bolt"]["offset"],
                                       dp["greeble"]["opening_angle"],
                                       dp["greeble"]["thickness"],
                                       dp["greeble"]["nub_thickness"],
                                       dp["greeble"]["tolerance"],
                                       dp["plate"]["thickness"],
                                       dp["web"]["fillet_radius"],
                                       dp["web"]["width"],
                                       dp["bulkhead_flange"]["fillet_radius"],
                                       dp["bulkhead_flange"]["thickness"],
                                       dp["bulkhead_flange"]["chamfer"],
                                       dp["cowl_flange"]["height"],
                                       dp["cowl_flange"]["tolerance"],
                                       dp["printer"]["nozzle_diameter"])
    
    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def boom_bulkhead_render(dp, output_dir, filename):

    # import math
    
    fbbgeom = scad_module('fuselage_boom_bulkhead_geometry.scad')
    
    scadobj = fbbgeom.boom_bulkhead(   dp["bulkhead"]["width"],
                                       dp["corner"]["radius"],
                                       dp["panel"]["thickness"],
                                       dp["panel"]["offset"],
                                       dp["panel"]["overlap"],
                                       dp["panel"]["tolerance"],
                                       dp["longeron"]["radius"],
                                       dp["longeron"]["tolerance"],
                                       dp["bolt"]["radius"],
                                       dp["bolt"]["offset"],
                                       dp["web"]["fillet_radius"],
                                       dp["web"]["width"],
                                       dp["boom_bulkhead"]["diameter"],
                                       dp["boom_bulkhead"]["thickness"],
                                       dp["boom_bulkhead"]["y_position"],
                                       dp["boom_bulkhead"]["z_position"],
                                       dp["boom_bulkhead"]["collet_thickness"],
                                       dp["boom_bulkhead"]["key_width"],
                                       dp["boom_bulkhead"]["key_height"],
                                       dp["boom_bulkhead"]["key_radius"],
                                       dp["boom_bulkhead"]["key_angle"],
                                       dp["boom_bulkhead"]["key_web_width"],
                                       dp["boom_bulkhead"]["tolerance"],
                                       dp["boom_bulkhead"]["make_vert_web"],
                                       dp["boom_bulkhead"]["make_lower_web"])
    
    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def nose_render(U, dp, output_dir, filename, is_nose_cowl, is_nose_nose, is_nose_plate):

    cgeom = scad_module('cowl_geometry.scad')

    # Every value below now comes from the JSON parameter file via
    # derived_nose_parameters(), rather than being hard-coded to the U=1
    # nose_round_plate case as it was before.
    unit_width = dp["unit_width"]
    cone_angle = dp["cone_angle"]
    cut_len = dp["cut_len"]

    plate_diam = dp["plate"]["diameter"]
    plate_tol = dp["plate"]["tolerance"]
    plate_thickness = dp["plate"]["thickness"]
    plate_flange_width = dp["plate"]["flange_width"]
    plate_flange_height = dp["plate"]["flange_height"]

    nose_flange_inset = dp["nose"]["flange_inset"]
    nose_flange_height = dp["nose"]["flange_height"]

    buttress_z_offset = dp["buttress"]["z_offset"]
    buttress_r_inset = dp["buttress"]["r_inset"]
    buttress_thickness = dp["buttress"]["thickness"]
    buttress_r_start = dp["buttress"]["top"]["r_start"]
    buttress_r_end = dp["buttress"]["top"]["r_end"]

    oml_filename = oml_ref(dp["oml"]["filename"])
    oml_scale = dp["oml"]["scale"]
    oml_length = dp["oml"]["length"]
    oml_offset_x = dp["oml"]["offset_x"]
    oml_reversed = dp["oml"]["reversed"]

    if is_nose_cowl:
        scadobj = cgeom.nose_cowl(U,
                                  unit_width,
                                  oml_filename,
                                  oml_scale,
                                  oml_length,
                                  oml_offset_x,
                                  oml_reversed,
                                  cut_len,
                                  buttress_thickness, 
                                  buttress_z_offset, 
                                  buttress_r_start, 
                                  buttress_r_end, 
                                  buttress_r_inset, 
                                  cone_angle)
    elif is_nose_nose:
        scadobj = cgeom.nose(U, 
                             unit_width,
                             oml_filename,
                             oml_scale,
                             oml_offset_x,
                             oml_reversed,
                             cut_len,
                             nose_flange_height,
                             nose_flange_inset,
                             plate_diam,
                             plate_thickness,
                             plate_tol,
                             cone_angle)
    elif is_nose_plate:
        scadobj = solid2.mirror(v=(0,0,-1))( cgeom.nose_plate(plate_diam,
                                   plate_thickness,
                                   plate_flange_width,
                                   plate_flange_height,
                                   cone_angle) )

    else:
        return

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def tail_render(U, dp, output_dir, filename):

    cgeom = scad_module('cowl_geometry.scad')

    # Every value now comes from the JSON parameter file via
    # derived_cowl_parameters(), matching how the nose is driven. Verified to
    # reproduce the previous hard-coded values exactly at U = 0.5, 1.0, 2.5 and
    # 4.0 -- 22 of 22 each time -- before the hard-coded block was removed.
    #
    # The tail uses five independently specified buttress groups because it is
    # mirrored about one plane; the nose needs only one because it is built
    # from an octant and repeated radially.
    b = dp["buttress"]

    unit_width = dp["unit_width"]
    cut_len = dp["cut_len"]
    cone_angle = dp["cone_angle"]

    buttress_z_offset = b["z_offset"]
    buttress_r_inset = b["r_inset"]
    buttress_thickness = b["thickness"]

    side_buttress_z_end = b["side"]["z_end"]
    side_buttress_r_start = b["side"]["r_start"]
    side_buttress_r_end = b["side"]["r_end"]

    top_buttress_z_end = b["top"]["z_end"]
    top_buttress_r_start = b["top"]["r_start"]
    top_buttress_r_end = b["top"]["r_end"]

    top_diag_buttress_z_start = b["top_diag1"]["z_start"]
    top_diag_buttress_depth = b["top_diag1"]["depth"]

    bottom_buttress_z_end = b["bottom"]["z_end"]
    bottom_buttress_r_start = b["bottom"]["r_start"]
    bottom_buttress_r_end = b["bottom"]["r_end"]

    oml_filename = oml_ref(dp["oml"]["filename"])
    oml_scale = dp["oml"]["scale"]
    oml_length = dp["oml"]["length"]
    oml_offset_x = dp["oml"]["offset_x"]
    oml_reversed = dp["oml"]["reversed"]

    scadobj = cgeom.tail_cowl(U,
                              unit_width,
                              oml_filename,
                              oml_scale,
                              oml_length,
                              oml_offset_x,
                              oml_reversed,
                              cut_len,
                              buttress_thickness,
                              buttress_z_offset,
                              buttress_r_inset,
                              side_buttress_z_end,
                              side_buttress_r_start,
                              side_buttress_r_end,
                              top_buttress_z_end,
                              top_buttress_r_start,
                              top_buttress_r_end,
                              bottom_buttress_z_end,
                              bottom_buttress_r_start,
                              bottom_buttress_r_end,
                              top_diag_buttress_depth,
                              top_diag_buttress_z_start,
                              cone_angle)

    (scad_filename, stl_filename, png_filename) = solid_render(scadobj, output_dir, filename)


def axes(*names):
    """Parameter axis CSVs, resolved against PARAM_DIR rather than the cwd."""
    return [os.path.join(PARAM_DIR, n) for n in names]


@contextlib.contextmanager
def sweep_session(workers=None, resume=False, previews=True):
    """Configure and tear down a sweep run.

    Owns the render queue, the resume and preview settings, and -- importantly --
    the preview backfill. Any driver of the `run_*_parametric_sweep` functions
    should go through this rather than setting the pieces up itself: the backfill
    is easy to omit, and omitting it silently leaves finished parts with no image.

        with sweep_session(workers=5, resume=True):
            run_nose_parametric_sweep(axes(...), out_dir)
    """
    workers = default_render_workers() if workers is None else max(1, int(workers))
    queue = RenderQueue(workers)
    previous_queue = set_render_queue(queue)
    previous_resume = set_resume(resume)
    previous_previews = set_previews(previews)
    try:
        yield queue
        # Only on the clean path: an abandoned run should not drag its whole
        # queue of pending renders along behind the failure.
        queue.drain()
    finally:
        set_render_queue(previous_queue)
        # Captured before set_resume, which zeroes the counters.
        skipped = _RESUME_COUNTS['skipped']
        changed = _RESUME_COUNTS['changed']
        backlog = list(_PREVIEW_BACKLOG)
        set_resume(previous_resume)
        set_previews(previous_previews)

    if resume:
        print('resume: skipped %d unchanged part(s)%s'
              % (skipped,
                 ', re-rendered %d whose definition changed' % changed
                 if changed else ''),
              flush=True)

    # After the queue has closed, so the OpenSCAD renders have finished and
    # released their memory before the preview pool starts competing for it.
    if previews and backlog:
        print('previews: backfilling %d missing preview(s) across %d process(es)'
              % (len(backlog), workers), flush=True)
        failures = render_preview_batch(backlog, workers=workers)
        if failures:
            print('previews: %d failed (the parts themselves are fine)'
                  % len(failures), flush=True)


def main(workers=None, resume=False, previews=True):
    """Run all five sweeps, writing an STL and a preview PNG for every part.

    `workers` is the number of concurrent OpenSCAD renders; None picks a default
    bounded by cores and free memory, and 1 restores strictly serial behaviour.
    Override without editing code via FUSELAGE_RENDER_WORKERS.

    `resume` skips parts whose STL is already a complete mesh, so an interrupted
    run finishes instead of starting over. It trusts what is on disk, so use it
    only when the inputs have not changed since. A skipped part still gets its
    preview if that is missing.

    `previews` renders each part's PNG from its finished STL, on the worker thread,
    as soon as the STL lands. One command produces the parts and the images.
    """
    workers = default_render_workers() if workers is None else max(1, int(workers))
    budget, why = render_worker_budget()
    print('render workers: %d  (%s)' % (workers, why if workers == budget else 'explicit'),
          flush=True)
    print('previews: %s' % ('on, rendered from each STL' if previews else 'off'),
          flush=True)
    if resume:
        print('resume: skipping parts whose STL is already complete', flush=True)

    with sweep_session(workers=workers, resume=resume, previews=previews):
        _run_all_sweeps()


def _run_all_sweeps():

    run_corner_parametric_sweep(axes('panel_variants.csv', 'bulkhead_size_variants.csv', 'corner_size_variants.csv'), OUTPUT_DIR)

    run_bulkhead_parametric_sweep(axes('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv'), OUTPUT_DIR)

    run_boom_bulkhead_parametric_sweep(axes('panel_variants.csv', 'bulkhead_size_variants.csv', 'boom_bulkhead_type_variants.csv'), OUTPUT_DIR)

    # nose_size_variants.csv carries U *and* the print-driven nose dimensions,
    # so it replaces bulkhead_size_variants.csv as this sweep's size axis --
    # using both would multiply the two U columns into a nonsense product.
    run_nose_parametric_sweep(axes('nose_size_variants.csv',
                                   'nose_type_variants.csv'), OUTPUT_DIR)

    # The tail is now JSON-driven like the nose. It borrows the nose size axis
    # for U; the nose-only columns in it (plate/flange dimensions) are simply
    # unused by a tail, which has neither a tip nor a plate.
    run_tail_parametric_sweep(axes('nose_size_variants.csv',
                                   'tail_type_variants.csv'), OUTPUT_DIR)

if __name__ == "__main__":
    _parser = argparse.ArgumentParser(
        description='Render every fuselage variant to STL.')
    _parser.add_argument('workers', nargs='?', type=int, default=None,
                         help='concurrent OpenSCAD renders '
                              '(default: bounded by cores and free memory)')
    _mode = _parser.add_mutually_exclusive_group()
    _mode.add_argument('--resume', action='store_true',
                       help='skip parts that are already rendered and whose '
                            'generated .scad is unchanged; parts affected by a '
                            'geometry or parameter edit re-render on their own')
    _mode.add_argument('--force', action='store_true',
                       help='re-render every part regardless of what is on disk '
                            '(the default; state it explicitly to be unambiguous, '
                            'and to override a change this tool cannot see, such '
                            'as a new OpenSCAD version or an OML mesh replaced '
                            'in place)')
    _parser.add_argument('--no-previews', action='store_true',
                         help='skip the preview PNGs (they are generated by '
                              'default, from each finished STL)')
    _parser.add_argument('--previews-only', action='store_true',
                         help='render no geometry; regenerate previews for the '
                              'STLs already in variant_output. Use after a look '
                              'change -- with --force to redo every preview, '
                              'without it to fill in only the missing ones')
    _args = _parser.parse_args()
    if _args.previews_only:
        _failures = rebuild_previews(workers=_args.workers, force=_args.force)
        raise SystemExit(1 if _failures else 0)
    main(workers=_args.workers, resume=_args.resume and not _args.force,
         previews=not _args.no_previews)

