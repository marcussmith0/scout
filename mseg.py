#!/usr/bin/env python3

# import sys
import re
import numpy
import json
import copy

# Set AEO time horizon in years (used in list_generator function
# to check for correct length of microsegment value lists)
aeo_years = 32

# Identify files to import for conversion
EIA_res_file = 'RESDBOUT.txt'
json_in = 'microsegments.json'
json_out = 'microsegments_out.json'
res_tloads = 'Res_TLoads_Final.txt'
res_climate_convert = 'Res_Cdiv_Czone_ConvertTable_Final.txt'
com_tloads = 'Com_TLoads_Final.txt'
com_climate_convert = 'Com_Cdiv_Czone_ConvertTable_Final.txt'

# Define a series of dicts that will translate imported JSON
# microsegment names to AEO microsegment(s)

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
            'other fuel': ('LG', 'KS', 'CL', 'GE', 'WD')
            }
# Note that currently in RESDBOUT.txt, electric resistance heaters are
# categorized under GE (geothermal) fuel. Fuel types "SL" and "NG" have
# been removed from the "other fuel" category. "SL" (solar) fuel
# corresponds to solar insolation for solar water heating, and is only
# associated with the "SOLAR" technology type. "NG" is only used by the
# "FP" end use, and in an attempt to avoid problems later if EIA
# changes their natural gas fuel type code to "NG" from "GS", it is
# also left out of the "other fuel" definition.

# End use dict
endusedict = {'square footage': 'SQ',  # AEO handles sq.ft. info. as end use
              'heating': 'HT',
              'secondary heating': 'SH',
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
                         'electric WH': 'ELEC_WH',
                         'boiler (electric)': 'ELEC_RAD',
                         'ASHP': 'ELEC_HP',
                         'GSHP': 'GEO_HP',
                         'central AC': 'CENT_AIR',
                         'room AC': 'ROOM_AIR',
                         'linear fluorescent (T-12)': ('LFL', 'T12'),
                         'linear fluorescent (T-8)': ('LFL', 'T-8'),
                         'linear fluorescent (LED)': ('LFL', 'LED'),
                         'general service (incandescent)': ('GSL', 'Inc'),
                         'general service (CFL)': ('GSL', 'CFL'),
                         'general service (LED)': ('GSL', 'LED'),
                         'reflector (incandescent)': ('REF', 'Inc'),
                         'reflector (CFL)': ('REF', 'CFL'),
                         'reflector (halogen)': ('REF', 'HAL'),
                         'reflector (LED)': ('REF', 'LED'),
                         'external (incandescent)': ('EXT', 'Inc'),
                         'external (CFL)': ('EXT', 'CFL'),
                         'external (high pressure sodium)': ('EXT', 'HPS'),
                         'external (LED)': ('EXT', 'LED'),
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

# Import the residential census division to climate zone conversion array
res_convert_array = numpy.genfromtxt(res_climate_convert,
                                     names=True, delimiter='\t',
                                     dtype=None)

# Define a series of regex comparison inputs that determines what we don't need
# in the imported RESDBOUT.txt file for the "supply" and "demand" portions of
# the microsegment updating routine

# Unused rows in the supply portion of the analysis
# Exclude: (Housing Stock | Switch From | Switch To | Fuel Pumps)
unused_supply_re = '^\(b\'(HS|SF|ST |FP).*'
# Unused rows in the demand portion of the analysis
# Exclude everything except: (Heating | Cooling | Secondary Heating)
unused_demand_re = '^\(b\'(?!(HT|CL|SH)).*'


def json_translator(dictlist, filterformat):
    """ Determine filtering list for finding information in text file parse """

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
    # remove "technology_supplydict" and "technology_demanddict" from dictlist;
    # if a microsegment square footage update, include only "endusedict",
    # "cdivdict", and "bldgtypedict".
    if 'demand' in filterformat:
        dictlist_loop = dictlist[:(len(dictlist) - 2)]
        dictlist_add = dictlist[-1]
        dictlist_loop.append(dictlist_add)
    elif 'square footage' in filterformat and len(filterformat) == 3:
        dictlist_loop = dictlist[:(len(dictlist) - 3)]
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
    string that can be entered into a regex comparison in the
    list_generator function """

    # Set base "supply" filter string
    supply_filter = '.*'

    # Determine whether we are updating a "demand" microsegment by
    # whether or not the current function input is a tuple. If so,
    # use the first tuple element as a filter for the EIA data, and
    # the second tuple element as filter for the residential thermal
    # load components.
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
            if endusedict['lighting'] in txt_filter_loop:
                newelement = element[0] + '.+' + element[1]
                supply_filter = supply_filter + newelement + '.+'
            else:
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

    return (supply_filter, demand_filter)


def thermal_load_select(tl_array, comparefrom, demand_column):
    """ Select the desired thermal load component for the relevant
    operating condition (heating or cooling) from the input data
    based on the demand_column variable """

    # Loop through the thermal load component array rows to identify
    # the row matching the 'comparefrom' selection regex
    for row in tl_array:

        # Set up 'compareto' regex string using only the first three
        # columns of the thermal load components array
        compareto = str([row[0], row[1], row[2]])

        # Check whether there is a match for the current row
        match = re.search(comparefrom, compareto)

        # If there's a match, extract the demand modifier value
        # (the fraction of heating or cooling load gained/lost
        # through the relevant exterior surface) in the appropriate
        # column using 'demand_column'
        if match:
            tloads_component = (row[demand_column])

    return tloads_component


def stock_consume_select(data, comparefrom, file_type):
    """ Select the stock and consumption data for each year for a
    microsegment and combine them into lists for all reported years """

    # Determine whether we are parsing the "supply" version of the EIA data
    supply_parse = re.search('EIA_Supply', file_type, re.IGNORECASE)

    # Define initial list of rows to remove from data input
    rows_to_remove = []

    # Define initial stock and energy dicts
    group_stock = {}
    group_energy = {}

    # Loop through the numpy input array rows, match to 'comparefrom' input
    for idx, row in enumerate(data):
        # Set up 'compareto' list
        compareto = str(row)

        # Establish the match
        match = re.search(comparefrom, compareto)

        # If there's a match, append values for the current microsegment
        if match:

            # If data for the year is already present for the current
            # microsegment (as with microsegments that combine several
            # EIA categories together, add the new stock and consumption
            # values to the existing values (assume that if the year is
            # present in the group_stock dict it is also in group_energy)
            if str(row['YEAR']) in group_stock:
                # Record energy consumption and stock information
                # (change the year to a string to yield a valid
                # JSON dict, where all keys must be strings)
                group_stock[str(row['YEAR'])] += row['EQSTOCK']
                group_energy[str(row['YEAR'])] += row['CONSUMPTION']

            else:
                group_stock[str(row['YEAR'])] = row['EQSTOCK']
                group_energy[str(row['YEAR'])] = row['CONSUMPTION']

            # If handling the supply data, to reduce computation time,
            # record row index to delete later
            if supply_parse:
                rows_to_remove.append(idx)

    # Remove rows specified by rows_to_remove (an empty list when
    # demand data are being handled by this function, thus deleting no
    # rows, since the demand microsegments apply to multiple categories,
    # e.g. heating through window conduction and envelope conduction).
    data_reduced = numpy.delete(data, rows_to_remove, 0)

    return (group_energy, group_stock, data_reduced)


def sqft_select(data, comparefrom):
    """ Select the square footage data for each year for a
    given census division/building type and combine them into lists for all
    reported years """

    # Define initial list of rows to remove from data input
    rows_to_remove = []

    # Define initial sq. footage list
    group_sqft = {}

    # Loop through the numpy input array rows, match to 'comparefrom' input
    for idx, row in enumerate(data):
        # Set up 'compareto' list
        compareto = str(row)

        # Establish the match
        match = re.search(comparefrom, compareto)

        # If there's a match, append values for the current cdiv/bldg. type
        if match:
            # Record square foot info. (in "HOUSEHOLDS" column in .txt)
            group_sqft[str(row['YEAR'])] = row['HOUSEHOLDS']
            # To reduce computation time,
            # record row index to delete later
            rows_to_remove.append(idx)

    # Remove rows specified by rows_to_remove
    data_reduced = numpy.delete(data, rows_to_remove, 0)
    return (group_sqft, data_reduced)


def list_generator(ms_supply, ms_demand, ms_loads, filterdata, aeo_years):
    """ Given filtering list for a microsegment, find rows in text
    files to reference in determining associated energy data, append
    energy data to a new list """

    # Find the corresponding text filtering information
    txt_filter = json_translator(res_dictlist, filterdata)

    # Set up 'compare from' list (based on data file contents)
    [comparefrom_base, column_indicator] = filter_formatter(txt_filter)

    # Run through text file and add all appropriate lines to the empty list
    # Check whether current microsegment is a heating/cooling "demand"
    # technology (handled differently)
    if 'demand' in filterdata:
        # Find baseline heating or cooling energy microsegment (before
        # application of load component); establish reduced numpy array
        [group_energy_base, group_stock, ms_demand] = stock_consume_select(
            ms_demand, comparefrom_base, 'EIA_Demand')

        # Given the discovered lists of energy/stock values, ensure
        # length is equal to the number of years currently projected
        # by AEO. If not, and the list isn't empty, trigger an error.
        if len(group_energy_base) is not aeo_years:
            if len(group_energy_base) != 0:
                raise(ValueError('Error in length of discovered list!'))

        # Find/apply appropriate thermal load component

        # 1. Construct appropriate row filter for tloads array
        fuel_remove = re.search('(\.\*)(\(*\w+\|*\w+\)*)(\.\+\w+\.\+\w+)',
                                comparefrom_base)
        # If special case of secondary heating, change end use part of regex to
        # 'HT', which is what both primary and secondary heating are coded as
        # in thermal loads text file data
        if (fuel_remove.group(2) == 'SH'):
            comparefrom_tloads = fuel_remove.group(1) + 'HT' + \
                fuel_remove.group(3)
        else:
            comparefrom_tloads = fuel_remove.group()

        # 2. Find/return appropriate thermal loads component and reduced
        #    thermal loads array
        tloads_component = thermal_load_select(
            ms_loads, comparefrom_tloads, column_indicator)

        # 3. Apply component value to baseline energy values for final list
        group_energy = {key: val * tloads_component
                        for key, val in group_energy_base.items()}

        # Return combined energy use values and updated version of EIA demand
        # data and thermal loads data with already matched data removed
        return [{'stock': 'NA', 'energy': group_energy}, ms_supply]
    # Check whether current microsegment is updating "square footage" info.
    # (handled differently)
    elif 'square footage' in filterdata:
        # Given input numpy array and 'compare from' list, return sq. footage
        # projection lists and reduced numpy array (with matched rows removed)
        [group_sqft, ms_supply] = sqft_select(
            ms_supply, comparefrom_base)

        # Given the discovered lists of sq. footage values, ensure
        # length is equal to the number of years currently projected
        # by AEO. If not, and the list isn't empty, trigger an error.
        if len(group_sqft) is not aeo_years:
            if len(group_sqft) != 0:
                raise(ValueError('Error in length of discovered list!'))

        # Return sq. footage values and updated version of EIA
        # supply data with already matched data removed
        return [group_sqft, ms_supply]
    else:
        # Given input numpy array and 'compare from' list, return energy/stock
        # projection lists and reduced numpy array (with matched rows removed)
        [group_energy, group_stock, ms_supply] = stock_consume_select(
            ms_supply, comparefrom_base, 'EIA_Supply')

        # Given the discovered lists of energy/stock values, ensure
        # length is equal to the number of years currently projected
        # by AEO. If not, and the list isn't empty, trigger an error.
        if len(group_energy) is not aeo_years:
            if len(group_energy) != 0:
                raise(ValueError('Error in length of discovered list!'))

        # Return combined stock/energy use values and updated version of EIA
        # supply data with already matched data removed
        return [{'stock': group_stock, 'energy': group_energy}, ms_supply]


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
            [data_dict, supply] = list_generator(supply, demand, loads,
                                                 leaf_node_keys, aeo_years)
            # Set dict key to extracted data
            json_dict[key] = data_dict

    # Return final file
    return json_dict


def merge_sum(base_dict, add_dict, cd, clim, convert_array, cdivdict,
              cdiv_list):
    """ Given two dicts of the same structure, add values at the end
    of each branch of the second dict to those of the first dict
    (used to convert microsegment data from a census division to a
    climate zone breakdown) """

    for (k, i), (k2, i2) in zip(sorted(base_dict.items()),
                                sorted(add_dict.items())):
        # Check to ensure dicts do have same structure
        if k == k2:
            # Recursively loop through both dicts
            if isinstance(i, dict):
                merge_sum(i, i2, cd, clim, convert_array, cdivdict, cdiv_list)
            elif type(base_dict[k]) is not str:
                # Once end of branch is reached, add values weighted by an
                # appropriate census division to climate zone factor
                cd_convert = convert_array[cd][clim]

                # Special handling of first dict (no addition of the
                # second dict, only conversion of the first dict with
                # the appropriate factor)
                if (cd == (cdivdict[cdiv_list[0]] - 1)):
                    base_dict[k] = (base_dict[k] * cd_convert)
                else:
                    base_dict[k] = (base_dict[k] + add_dict[k2] * cd_convert)
        else:
            raise(KeyError('Merge keys do not match!'))

    # Return a single dict representing sum of values of original two dicts
    return base_dict


def clim_converter(input_dict, convert_array):
    """ Convert an updated microsegments dict from a census division
    to a climate zone breakdown """

    # Set climate zone and census division names
    clim_list = convert_array.dtype.names[1:]
    cdiv_list = list(input_dict.keys())

    # Set up empty dict to be updated
    converted_dict = {}

    # Climate zone for loop
    for climnum, clim in enumerate(clim_list):
        base_dict = copy.deepcopy(input_dict[cdiv_list[0]])

        # Census division for loop
        for cdiv in cdiv_list:
            # If cdivnum in cdivdict, find cdivnum using cdivdict; subtract 1
            # to ensure proper list indexing (1st element = 0th in python)
            if cdiv in cdivdict.keys():
                cdivnum = cdivdict[cdiv] - 1
                add_dict = copy.deepcopy(input_dict[cdiv])
                base_dict = merge_sum(base_dict, add_dict, cdivnum,
                                      (climnum + 1), convert_array, cdivdict,
                                      cdiv_list)
            else:
                raise(KeyError("Cdiv name not found in dict keys!"))
        newadd = base_dict
        converted_dict.update({clim: newadd})

    return converted_dict


def array_row_remover(data, comparefrom):
    """ Remove rows from large arrays (e.g. EIA data) based on a
    regular expression that defines which rows are not going to
    be needed later in the analysis """

    # Define an initial list of rows to remove from the input array
    rows_to_remove = []

    # Loop through the numpy input array rows and match to 'comparefrom' regex
    for idx, row in enumerate(data):

            # Set up 'compareto' string
            compareto = str(row)

            # Check whether there is a match for the current row
            match = re.search(comparefrom, compareto)

            # If there is a match, record the row index for later deletion
            if match:
                rows_to_remove.append(idx)

    # Delete matched rows from numpy input array
    data_reduced = numpy.delete(data, rows_to_remove, 0)

    return data_reduced


def main():
    """ Import text and JSON files; run through JSON objects; find
    analogous text information; replace JSON values; update JSON """

    # Import EIA RESDBOUT.txt file
    supply = numpy.genfromtxt(EIA_res_file, names=True,
                              delimiter='\t', dtype=None)
    # Reduce supply array to only needed rows
    supply = array_row_remover(supply, unused_supply_re)

    # Set RESDBOUT.txt data for separate use in "demand" microsegments
    demand = supply
    # Reduce demand array to only needed rows
    demand = array_row_remover(demand, unused_demand_re)

    # Set thermal loads .txt file (*currently residential)
    loads = numpy.genfromtxt(res_tloads, names=True,
                             delimiter='\t', dtype=None)

    # Import JSON file and run through updating scheme
    with open(json_in, 'r') as jsi:
        msjson = json.load(jsi)

        # Run through JSON objects, determine replacement information
        # to mine from the imported data, and make the replacements
        updated_data = walk(supply, demand, loads, msjson)

        # Convert the updated data from census division to climate breakdown
        final_data = clim_converter(updated_data, res_convert_array)

    # Write the updated dict of data to a new JSON file
    with open(json_out, 'w') as jso:
        json.dump(final_data, jso, indent=4)


if __name__ == '__main__':
    main()