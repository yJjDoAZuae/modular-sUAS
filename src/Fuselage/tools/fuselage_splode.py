import solid2
import fuselage_variants as fv


def get_params():

    csv_files = fv.axes('panel_variants.csv', 'bulkhead_type_variants.csv', 'bulkhead_size_variants.csv')
    param_axes = fv.read_all_param_axes(csv_files)
    all_combinations = fv.flatten_param_space(param_axes)

    # Already at the sweep's nozzle: PrinterSettings defaults come from
    # design_constants.json, so this no longer needs an override on the next line.
    printer_settings = fv.null_printer_settings()

    # print(len(param_axes))
    # print(len(param_axes[0]))
    # print(len(param_axes[1]))
    # print(len(param_axes[2]))
    
    # print(len(all_combinations))

    k_panel_variant = 7 # len 9
    k_bulkhead_type_variant = 0 # len 5, 0=end_bolt 1=end_anchor 2=cowling_bolt 3=cowling_anchor 4=interconnect
    k_bulkhead_size_variant = 2 # len 8
    
    k_combo = k_panel_variant*len(param_axes[1])*len(param_axes[2]) + k_bulkhead_type_variant*len(param_axes[2]) + k_bulkhead_size_variant
    print("k_combo = " + str(k_combo) + "\n")
    
    # print("params[0] = " + str(all_combinations[0]))
    # print("params[1] = " + str(all_combinations[1]))
    # print("params[40] = " + str(all_combinations[40]))
    # print("params[41] = " + str(all_combinations[41]))

    params = all_combinations[k_combo]  # U 4.0 end bolt bulkhead
    print("params = " + str(params) + "\n")

    FX = 1.0

    dp_bulk_bolt = fv.derived_parameters(params["U"], FX, params, printer_settings,True)
    dp_corn = fv.derived_parameters(params["U"], FX, params, printer_settings,False)

    # *****************************
    
    k_panel_variant = 7 # len 9
    k_bulkhead_type_variant = 1 # len 5, 0=end_bolt 1=end_anchor 2=cowling_bolt 3=cowling_anchor 4=interconnect
    k_bulkhead_size_variant = 2 # len 8
    
    k_combo = k_panel_variant*len(param_axes[1])*len(param_axes[2]) + k_bulkhead_type_variant*len(param_axes[2]) + k_bulkhead_size_variant
    print("k_combo = " + str(k_combo) + "\n")

    params = all_combinations[k_combo]  # U 4.0 end bolt bulkhead
    print("params = " + str(params) + "\n")
    
    dp_bulk_anchor = fv.derived_parameters(params["U"], FX, params, printer_settings,True)

    # *****************************
    
    k_panel_variant = 7 # len 9
    k_bulkhead_type_variant = 2 # len 5, 0=end_bolt 1=end_anchor 2=cowling_bolt 3=cowling_anchor 4=interconnect
    k_bulkhead_size_variant = 2 # len 8
    
    k_combo = k_panel_variant*len(param_axes[1])*len(param_axes[2]) + k_bulkhead_type_variant*len(param_axes[2]) + k_bulkhead_size_variant
    print("k_combo = " + str(k_combo) + "\n")

    params = all_combinations[k_combo]  # U 4.0 end bolt bulkhead
    print("params = " + str(params) + "\n")
    
    dp_bulk_cowl = fv.derived_parameters(params["U"], FX, params, printer_settings,True)

    # *****************************

    k_panel_variant = 7 # len 9
    k_bulkhead_type_variant = 4 # len 5, 0=end_bolt 1=end_anchor 2=cowling_bolt 3=cowling_anchor 4=interconnect
    k_bulkhead_size_variant = 2 # len 8
    
    k_combo = k_panel_variant*len(param_axes[1])*len(param_axes[2]) + k_bulkhead_type_variant*len(param_axes[2]) + k_bulkhead_size_variant
    print("k_combo = " + str(k_combo) + "\n")

    params = all_combinations[k_combo]  # U 4.0 end bolt bulkhead
    print("params = " + str(params) + "\n")
    
    dp_bulk_interconnect = fv.derived_parameters(params["U"], FX, params, printer_settings,True)

    # *****************************

    return (dp_bulk_bolt, dp_bulk_anchor, dp_bulk_cowl, dp_bulk_interconnect, dp_corn)
    