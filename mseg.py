#!/usr/bin/env python3

# import sys
import re
import numpy
import json
import copy

# Set AEO time horizon in years (used in "value_listfinder" function
# below to check correctness of microsegment value lists)
aeo_years = 32

# Identify files to import for conversion
EIA_res_file = 'RESDBOUT.txt'
json_in = 'microsegments_test.json'
json_out = 'microsegments_out.json'
res_tloads = 'Res_TLoads_Final.txt'
res_climate_convert = 'Res_Cdiv_Czone_ConvertTable_Final.txt'
com_tloads = 'Com_TLoads_Final.txt'
com_climate_convert = 'Com_Cdiv_Czone_ConvertTable_Final.txt'

# Define a series of dicts that will translate imported JSON
# microsegment name to AEO microsegment(s)

# Census division dict
cdivdict = {'new england': 1,
            'mid atlantic': 2,
            'east north central': 3,
            'west north central': 4,
            'south atlantic': 5,
            'east south central': 6,
            'west south central': 7,
            'mountain': 8,
            'pacific': 9
            }

# Building type dict (residential)
bldgtypedict = {'single family home': 1,
                'multi family home': 2,
                'mobile home': 3
                }

# Fuel type dict
fueldict = {'electricity (on site)': 'SL',
            'electricity (grid)': 'EL',
            'natural gas': 'GS',
            'distillate': 'DS',
            'other fuel': ('LG', 'KS', 'CL', 'SL', 'GE', 'NG', 'WD')
            }
# Note that currently in RESDBOUT.txt, electric resistance heaters are
# categorized under GE (geothermal) fuel. SL (solar) fuel is attached
# to water heating, but the end technology is only listed as "Solar",
# which will not currently be included in our analysis.

# End use dict
endusedict = {'heating': 'HT',
              'secondary heating': ('SH', 'OA'),
              'cooling': 'CL',
              'fans & pumps': 'FF',
              'ceiling fan': 'CFN',
              'lighting': 'LT',
              'water heating': 'HW',
              'refrigeration': 'RF',
              'cooking': 'CK',
              'drying': 'DR',
              'TVs': {'TV': 'TV',
                      'set top box': 'STB',
                      'DVD': 'DVD',
                      'home theater & audio': 'HTS',
                      'video game consoles': 'VGC'},
              'computers': {'desktop PC': 'DPC',
                            'laptop PC': 'LPC',
                            'monitors': 'MON',
                            'network equipment': 'NET'},
              'other (grid electric)': {'clothes washing': 'CW',
                                        'dishwasher': 'DW',
                                        'freezers': 'FZ',
                                        'other MELs': ('BAT', 'COF', 'DEH',
                                                       'EO', 'MCO', 'OA',
                                                       'PHP', 'SEC', 'SPA')}
              }

# Technology types (supply) dict
technology_supplydict = {'solar WH': 'SOLAR_WH',
                         'boiler (electric)': 'ELEC_RAD',
                         'ASHP': 'ELEC_HP',
                         'GSHP': 'GEO_HP',
                         'central AC': 'CENT_AIR',
                         'room AC': 'ROOM_AIR',
                         'linear fluorescent': 'LFL',
                         'general service': 'GSL',
                         'reflector': 'REF',
                         'external': 'EXT',
                         'furnace (NG)': 'NG_FA',
                         'boiler (NG)': 'NG_RAD',
                         'NGHP': 'NG_HP',
                         'furnace (distillate)': 'DIST_FA',
                         'boiler (distillate)': 'DIST_RAD',
                         'furnace (kerosene)': 'KERO_FA',
                         'furnace (LPG)': 'LPG_FA',
                         'stove (wood)': 'WOOD_HT',
                         'resistance': 'GE2',
                         'secondary heating (kerosene)': 'KS',
                         'secondary heating (LPG)': 'LG',
                         'secondary heating (wood)': 'WD',
                         'secondary heating (coal)': 'CL',
                         'non-specific': ''
                         }

# Technology types (demand) dict
technology_demanddict = {'windows conduction': 'WIND_COND',
                         'windows solar': 'WIND_SOL',
                         'wall': 'WALL',
                         'roof': 'ROOF',
                         'ground': 'GRND',
                         'infiltration': 'INFIL',
                         'people gain': 'PEOPLE',
                         'equipment gain': 'EQUIP'}

# Form residential dictlist for use in JSON translator
res_dictlist = [endusedict, cdivdict, bldgtypedict, fueldict,
                technology_supplydict, technology_demanddict]

# Import the residential cdiv->climate conversion array
res_convert_array = numpy.genfromtxt(res_climate_convert,
                                     names=True, delimiter='\t',
                                     dtype=None)

# Define a series of regex comparison inputs that determines what we don't need
# in the imported RESDBOUT.txt file for the "supply" and "demand" portions of
# the microsegment updating routine

# Unused rows in the supply portion of the analysis
# Exclude: (Housing Stock | Switch From | Switch To | Sq. Footage | Fuel Pumps)
unused_supply_re = '^\(b\'(HS|SF|ST|SQ|FP).*'
# Unused rows in the demand portion of the analysis
# Exclude everything except: (Heating | Cooling | Secondary Heating)
unused_demand_re = '^\(b\'(?!(HT|CL|SH|OA)).*'


def json_translator(dictlist, filterformat):
    """ Determine filtering list for finding information in .txt file parse """
    # Set base filtering list of lists (1st element supply filter, 2nd demand)
    json_translate = [[], '']
    # Set an indicator for whether a "demand" filtering element has been found
    # (special treatment)
    demand_indicator = 0
    # Set an indicator for whether the technology level is handled on the end
    # use level - i.e., set top boxes (special treatment)
    enduse_techlevel = 0
    # Set an indicator for what level in the microsegment hierarchy we are in:
    # 1) end use, 2) census division, 3) bldg type, 4) fuel type,
    # 5) "supply" tech type, 6) "demand" tech type)
    ms_level = 0
    # Reduce dictlist as appropriate to filtering information (if not a
    # "demand", microsegment, remove "technology_demanddict" from dictlist;
    # if not a "supply" microsegment", remove "technology_supplydict" from
    # dictlist; if a microsegment with no technology level (i.e. water heating)
    # remove "technology_supplydict" and "technology_demanddict" from dictlist.
    if 'demand' in filterformat:
        dictlist_loop = dictlist[:(len(dictlist) - 2)]
        dictlist_add = dictlist[-1]
        dictlist_loop.append(dictlist_add)
    elif len(filterformat) <= 4:
        dictlist_loop = dictlist[:(len(dictlist) - 2)]
    else:
        dictlist_loop = dictlist[:(len(dictlist) - 1)]
    # Loop through "dictlist" and determine whether any elements of
    # "filterformat" input are in dict keys; if so, add key value to output
    for j in dictlist_loop:
        # Count key matches for given dict
        match_count = 0
        ms_level += 1
        for num, key in enumerate(filterformat):
            # Check whether element is in dict keys
            if key in j.keys():
                match_count += 1
                # "Demand" technologies added to 2nd element of filtering list
                if demand_indicator != 1:
                    # If there are more levels in a keyed item, go down branch
                    if isinstance(j[key], dict):
                        nextkey = filterformat[num + 1]
                        if nextkey in j[key].keys():
                            json_translate[0].append(j[key][nextkey])
                            # Update enduse_techlevel indicator
                            enduse_techlevel = 1
                    else:
                        json_translate[0].append(j[key])
                    break
                else:
                    if isinstance(j[key], dict):
                        nextkey = filterformat[num + 1]
                        if nextkey in j[key].keys():
                            json_translate[1] = str(j[key][nextkey])
                    else:
                        json_translate[1] = str(j[key])
                    break
            # Flag a "demand" microsegment
            elif key == 'demand':
                demand_indicator = 1
        # If there was no key match for given dict and we don't have special
        # case of a technology being handled on the end use level, raise error
        if (match_count == 0 and ms_level != (len(dictlist) - 1)) or \
           (match_count == 0 and ms_level == (len(dictlist) - 1) and
           enduse_techlevel == 0):
            raise(KeyError("Filter list element not found in dict keys!"))

    # Return updated filtering list of lists: [[supply filter],[demand filter]]
    return json_translate


def filter_formatter(txt_filter):
    """ Given a filtering list for a microsegment, format into a
    string that can be entered into a regex comparsion in
    value_listfinder function """

    # Set base "supply" filter string
    supply_filter = '.*'

    # Determine whether we are updating a "demand" microsegment by whether or
    # not current function input is a tuple.  If so, use first tuple element
    # as filter for EIA .txt file, and second tuple element as filter for
    # residential thermal load components .txt file.
    if txt_filter[1]:
        txt_filter_loop = txt_filter[0]
        demand_filter = txt_filter[1]
    else:
        txt_filter_loop = txt_filter[0]
        demand_filter = 'NA'

    for element in txt_filter_loop:  # Run through elements of the filter list
        # If element is a tuple and not on the "demand" technology level, join
        # the tuple into a single string, put brackets around it for regex
        # comparison
        if isinstance(element, tuple):
            newelement = '|'.join(element)
            supply_filter = supply_filter + '(' + newelement + ').+'
        # If element is a number and not on the "demand" technology level, turn
        # into a string for regex comparison
        elif isinstance(element, int):
            newelement = str(element)
            supply_filter = supply_filter + newelement + '.+'
        # If element is a string and not on the "demand" technology level, add
        # it to the filter list without modification
        elif isinstance(element, str):
            supply_filter = supply_filter + element + '.+'
        else:
            print('Error in list finder form!')

    comparefrom = (supply_filter, demand_filter)
    return comparefrom


def txt_parser(mstxt, comparefrom, command_string, file_type, demand_column):
    """ Given a numpy array of "EIA_Supply", "EIA_Demand", or "TLoads"
    information (specified in file_type input), and information about what rows
    we want from it (specified in compare_from input), match the rows.  If
    command_string input = 'Reduce', remove matched rows; if command_string
    input = 'Record', record matched rows.  Note: demand_column input needed
    only in "TLoads" parse """
    # Determine whether we are removing numpy array rows or also recording them
    record_reduce = re.search('Record', command_string, re.IGNORECASE)
    # Determine whether we are parsing the "supply" copy of the EIA file
    supply_parse = re.search('EIA_Supply', file_type, re.IGNORECASE)
    # Determine whether we are parsing the "demand" copy of the EIA file
    demand_parse = re.search('EIA_Demand', file_type, re.IGNORECASE)
    # Define intial list of rows to remove from mstxt input
    rows_to_remove = []
    # If recording and removing rows, define initial stock/energy lists
    if record_reduce:
        if supply_parse or demand_parse:  # Parsing EIA array
            group_stock = []
            group_energy = []

    # Loop through the numpy input array rows, match to 'comparefrom' input
    for idx, txtlines in enumerate(mstxt):
            # Set up 'compareto' list
            if supply_parse or demand_parse:  # Parsing EIA array
                compareto = str(txtlines)
            else:  # Parsing TLoads array
                # Only compare to first three columns of tloads array
                compareto = str([txtlines[0], txtlines[1], txtlines[2]])
            # Establish the match
            match = re.search(comparefrom, compareto)
            # If there's a match, append line to stock/energy lists for
            # the current microsegment
            if match:
                # Record additional row index to delete
                rows_to_remove.append(idx)
                # If recording/removing rows, record energy/stock info.
                if record_reduce:
                    if supply_parse or demand_parse:  # Parsing EIA array
                        group_stock.append(txtlines['EQSTOCK'])
                        group_energy.append(txtlines['CONSUMPTION'])
                    else:  # Parsing TLoads array
                        # Use demand_column indicator to find value
                        tloads_component = (txtlines[demand_column])

    # Set up proper function return based on command_string input
    if record_reduce:
        # "Record" operation
        # For EIA_supply parse, report values & delete matched rows from array
        if supply_parse:
            mstxt_reduced = numpy.delete(mstxt, rows_to_remove, 0)
            parse_return = (group_energy, group_stock, mstxt_reduced)
        # For EIA_demand parse, only report values
        elif demand_parse:
            parse_return = (group_energy, group_stock)
        # For TLoads parase, only report matched value
        else:
            parse_return = (tloads_component)
    else:
        # "Reduce" operation
        mstxt_reduced = numpy.delete(mstxt, rows_to_remove, 0)
        parse_return = mstxt_reduced
    return parse_return


def list_generator(mstxt_supply, mstxt_demand, mstxt_loads, filterdata,
                   aeo_years):
    """ Given filtering list for a microsegment, find rows in *.txt
    files to reference in determining associated energy data, append
    energy data to a new list """

    # Find the corresponding txt filtering information
    txt_filter = json_translator(res_dictlist, filterdata)
    # Set up 'compare from' list (based on .txt file)
    [comparefrom_base, column_indicator] = filter_formatter(txt_filter)
    # Run through text file and add all appropriate lines to the empty list
    # Check whether current microsegment is a heating/cooling "demand"
    # technology (handled differently)
    if 'demand' in filterdata:
        # Find baseline heating or cooling energy microsegment (before
        # application of load component); establish reduced numpy array
        [group_energy_base, group_stock] = txt_parser(mstxt_demand,
                                                      comparefrom_base,
                                                      'Record',
                                                      'EIA_Demand',
                                                      '')
        # Given discovered list of energy values, ensure length = # years
        # currently projected by AEO. If not, reshape the list
        if len(group_energy_base) is not aeo_years:
            if len(group_energy_base) % aeo_years == 0:
                group_energy_base = \
                    numpy.reshape(group_energy_base,
                                  (aeo_years, -1),
                                  order='F').sum(axis=1).tolist()
            else:
                raise(ValueError('Error in length of discovered list!'))

        # Find/apply appropriate thermal load component
        # 1. Construct appropriate row filter for tloads array
        fuel_remove = re.search('(\.\*)(\(*\w+\|*\w+\)*)(\.\+\w+\.\+\w+)',
                                comparefrom_base)
        # If special case of secondary heating, change end use part of regex to
        # 'HT', which is what both primary and secondary heating are coded as
        # in thermal loads .txt
        if (fuel_remove.group(2) == '(SH|OA)'):
            comparefrom_tloads = fuel_remove.group(1) + 'HT' + \
                fuel_remove.group(3)
        else:
            comparefrom_tloads = fuel_remove.group()
        # 2. Find/return appropriate tloads component and reduced tloads array
        tloads_component = txt_parser(mstxt_loads, comparefrom_tloads,
                                      'Record', 'TLoads', column_indicator)
        # 3. Apply component value to baseline energy values for final list
        group_energy = [x * tloads_component for x in group_energy_base]

        # Return combined energy use values and updated version of EIA demand
        # data and thermal loads data with already matched data removed
        return [{'stock': 'NA', 'energy': group_energy}, mstxt_supply]
    else:
        # Given input numpy array and 'compare from' list, return energy/stock
        # projection lists and reduced numpy array (with matched rows removed)
        [group_energy, group_stock, mstxt_supply] = \
            txt_parser(mstxt_supply, comparefrom_base, 'Record', 'EIA_Supply',
                       '')

        # Given the discovered lists of energy/stock values, ensure length = #
        # years currently projected by AEO. If not, reshape the list
        if len(group_energy) is not aeo_years:
            if len(group_energy) % aeo_years == 0:
                group_energy = numpy.reshape(group_energy, (aeo_years, -1),
                                             order='F').sum(axis=1).tolist()
                group_stock = numpy.reshape(group_stock, (aeo_years, -1),
                                            order='F').sum(axis=1).tolist()
            else:
                raise(ValueError('Error in length of discovered list!'))

        # Return combined stock/energy use values and updated version of EIA
        # supply data with already matched data removed
        return [{'stock': group_stock, 'energy': group_energy}, mstxt_supply]


def walk(supply, demand, loads, json_dict, key_list=[]):
    """ Proceed recursively through data stored in dict-type structure
    and perform calculations at each leaf/terminal node in the data """
    for key, item in json_dict.items():

        # If there are additional levels in the dict, call the function
        # again to advance another level deeper into the data structure
        if isinstance(item, dict):
            walk(supply, demand, loads, item, key_list + [key])

        # If a leaf node has been reached, finish constructing the key
        # list for the current location and update the data in the dict
        else:
            leaf_node_keys = key_list + [key]
            # Extract data from original data sources
            [data_dict, supply] = \
                list_generator(supply, demand, loads, leaf_node_keys,
                               aeo_years)
            # Set dict key to extracted data
            json_dict[key] = data_dict

    # Return final file
    return json_dict


def merge_sum(base_dict, add_dict, cd, clim, convert_array):
    """ Given two dicts of the same structure, add values
    at the end of each branch of 2nd dict to those of the 1st dict
    (used to convert cdiv microsegment breakdown to czone) """
    for (k, i), (k2, i2) in zip(base_dict.items(), add_dict.items()):
        # Check to ensure dicts do have same structure
        if k == k2:
            # Recursively loop through both dicts
            if isinstance(i, dict):
                merge_sum(i, i2, cd, clim, convert_array)
            elif type(base_dict[k]) is not str:
                # Once end of branch is reached, add values weighted by
                # appropriate cdiv->czone translation factor
                cd_convert = convert_array[cd][clim]
                # Special handling of 1st dict (no addition of the 2nd dict,
                # only conversion of 1st with approrpriate translator factor)
                if (cd == 0):
                    base_dict[k] = [round((x * cd_convert), 4) for x in
                                    base_dict[k]]
                else:
                    base_dict[k] = [round((x + y * cd_convert), 4) for (x, y)
                                    in zip(base_dict[k], add_dict[k2])]
        else:
            raise(KeyError('Merge keys do not match!'))
    # Return a single dict representing sum of values of original two dicts
    return base_dict


def clim_converter(input_dict, convert_array):
    """ Convert an updated microsegments dict from a census division
    to a climate zone breakdown """
    # Set climate & census division names
    clim_list = convert_array.dtype.names[1:]
    cdiv_list = list(input_dict.keys())
    # Set up empty dict to be updated
    converted_dict = {}
    # Climate for loop
    for climnum, clim in enumerate(clim_list):
        base_dict = copy.deepcopy(input_dict[cdiv_list[0]])
        # Cdiv for loop
        for cdivnum, cdiv in enumerate(cdiv_list):
            add_dict = copy.deepcopy(input_dict[cdiv])
            base_dict = merge_sum(base_dict, add_dict, cdivnum, (climnum + 1),
                                  convert_array)
        newadd = base_dict
        converted_dict.update({clim: newadd})
    return converted_dict


def main():
    """ Import .txt and JSON files; run through JSON objects; find
    analogous .txt information; replace JSON values; update JSON """
    # Import EIA RESDBOUT.txt file
    supply = numpy.genfromtxt(EIA_res_file, names=True,
                              delimiter='\t', dtype=None)
    # Reduce supply array to only needed rows
    supply = txt_parser(supply, unused_supply_re, 'Reduce', 'EIA_Supply', '')

    # Set RESDBOUT.txt list for separate use in "demand" microsegments
    demand = supply
    # Reduce demand array to only needed rows
    demand = txt_parser(demand, unused_demand_re, 'Reduce', 'EIA_Demand', '')

    # Set thermal loads .txt file (*currently residential)
    loads = numpy.genfromtxt(res_tloads, names=True,
                             delimiter='\t', dtype=None)

    # Import JSON file and run through updating scheme
    with open(json_in, 'r') as jsi:
        msjson = json.load(jsi)
        # Run through JSON objects, determine replacement information
        # to mine from .txt file, and make the replacement
        updated_json = walk(supply, demand, loads, msjson)

        # Convert the updated json from cdiv->climate breakdown
        updated_json_final = clim_converter(updated_json,
                                            res_convert_array)

    # Write the updated json to new json file
    with open(json_out, 'w') as jso:
        json.dump(updated_json_final, jso, indent=4)


if __name__ == '__main__':
    main()
