import argparse
import sys
import json
import os

from . import timetables

def file_exists(x):
        """
        'Type' for argparse - checks that file exists but does not open it.
        https://stackoverflow.com/posts/11541495/revisions
        """
        if not os.path.exists(x):
            # Argparse uses the ArgumentTypeError to give a rejection message like:
            # error: argument input: x does not exist
            raise argparse.ArgumentTypeError("the file file {0} does not exist".format(x))
        return x

def main():
    parser = argparse.ArgumentParser(description='Download organized timetable information from the Google Directions API Transit mode for pretty output')

    # basic arguments
    required = parser.add_argument_group('Arguments to get timetable data (must be passed here or in the config file)')

    required.add_argument("-f", "--from",
                          dest="origin", type=str, required=False,
                          help="[required] Where to plan the route from", metavar="ORIGIN")
    required.add_argument("-t", "--to",
                          dest="destination", type=str, required=False,
                          help="[required] Where to plan the route to", metavar="DESTINATION")
    required.add_argument("-d", "--date",
                         dest="date", type=str, required=False,
                         help="[required] The date to be used for planning", metavar="YYYY-MM-DD")
    required.add_argument("-k", "--api-key",
                          dest="api_key", type=str, required=False,
                          help="[required] Your Google Directions API key", metavar="API_KEY")
    
    # further timetable-related
    optional = parser.add_argument_group('Further arguments to customize the timetable')

    optional.add_argument("-l", "--lang",
                          dest="lang", type=str, required=False,
                          help="Language code used to display results, eg. 'en-GB' or 'hu'", metavar="LANG")    
    optional.add_argument("--max-transfers",
                          dest="max_transfers", type=int, required=False, default=99,
                          help="Maximum number of allowed transfers (used to filter results)", metavar="TRANS")    
    optional.add_argument("--vehicle-type-names",
                          dest="vehicle_type_names", nargs='*', type=str,
                          help="How to display the name of vehicle types instead of the defaults returned by the API. Accepts multiple values. Key and value should be separated by =", 
                          metavar='"VEHICLE_TYPE=vehicle type"')
    optional.add_argument("--station-name-replacements",
                          dest="replacements", nargs='*', type=str,
                          help="Strings to be replaced in station names, typically for more concise output, e.g. 'Hauptbahnhof=Hbf'. Accepts multiple values. Key and value should be separated by =", 
                          metavar='"String=str"')

    # output arguments
    outputargs = parser.add_argument_group('Arguments related to the output')

    outputargs.add_argument("-v", "--verbose",
                            dest="verbose", required=False,  action="store_true",
                            help="Print diagnostic messages to stderr")
    outputargs.add_argument("-j", "--json",
                            dest="to_json", required=False,  action="store_true",
                            help="Output the results in the raw JSON format instead of the default rendered text")
    outputargs.add_argument("--json-indent",
                            dest="json_indent", required=False, type=int,
                            help="If the output is JSON, this many spaces will be used to indent it. If not passed, everything will be on one line.")
    outputargs.add_argument("--template",
                            dest="template_file", type=file_exists,
                            help="Jinja2 template file to use instead of the default template", metavar="FILE")
    outputargs.add_argument("-o", "--output",
                            dest="output_file", required=False,
                            help="Output file to be written. If not given, will print results to stdout.", 
                            metavar="FILE")

    configarg = parser.add_argument_group('Passing a config file')

    configarg.add_argument("-c", "--config",
                            dest="configfile", type=file_exists,
                            help="Config file to be used. Accepts a JSON file with a single object whose keys are zero or more of the options that can be passed to the script (e.g. \"from\" or \"output\"). Values should be appropriate for the option. If given, any value present in the config will overwrite the value given by the command line flag/option.", 
                            metavar="FILE")


    # get args
    args = vars(parser.parse_args())

    # if there is a config file, overwrite our args with its contents.
    # command line options are not called the same as the variables they are stored in,
    # therefore we need a mapping.
    if args['configfile']:
        config_variable_names = {
            "from": "origin",
            "to": "destination",
            "date": "date",
            "api-key": "api_key",
            "lang": "lang",
            "max-transfers": "max_transfers",
            "vehicle-type-names": "vehicle_type_names",
            "station-name-replacements": "replacements",
            "verbose":"verbose",
            "json": "to_json",
            "json-indent": "json_indent",
            "template": "template_file",
            "output": "output_file"
        }

        with open(args['configfile'], 'r') as f:
            config = json.load(f)
            for k in config.keys():
                try:
                    args[config_variable_names[k]] = config[k]
                except KeyError:
                    raise ValueError(f'"{k}", which was passed in the config file, is not a valid command line parameter.')

    # check if all required variables are passed in one way or another
    for arg in [['origin', 'from'], ['destination', 'to'], ['date', 'date'], ['api_key', 'api-key']]:
        if args[arg[0]] is None:
            raise ValueError(f'"{arg[1]}" must be passed either via the command line or the config file.')

    # parse the passed vehicle type names into a dict to work with later on
    vehicle_type_names = {}
    for vt in args['vehicle_type_names']:
        if len(vt.split('=')) != 2:
            raise ValueError(f'Error in vehicle type name definition "{vt}" – it must have exactly one = sign')
        # the key and value should be the passed string split at the '=' and
        # stripped of any spaces around it.
        k, v = [x.strip() for x in vt.split('=')]
        vehicle_type_names[k] = v
    
    # parse the passed station name replacements to work with later on
    # this is a list and the replacement is done in sequence
    # so the order does matter
    station_name_replacements = []
    for sn in args['replacements']:
        if len(sn.split('=')) != 2:
            raise ValueError(f'Error in station name text replacement definition "{sn}" – it must have exactly one = sign')
        # the replacement data should be the passed string split at the '=' and
        # stripped of any spaces around it.
        # it is turned into a list of two elements, which are then added to a
        # longer list of all substitutions, which will be carried out
        # sequentially.
        station_name_replacements.append([x.strip() for x in sn.split('=')])

    # get the data – it will be a dict
    timetable_data = \
        timetables.get_transit_plans_for_day(
            origin=args['origin'], destination=args['destination'], api_key=args['api_key'], date=args['date'], 
            language=args['lang'], vehicle_type_names=vehicle_type_names, station_name_replacements=station_name_replacements,
            max_transfers=args['max_transfers'], get_station_localities=True, verbose=args['verbose']
        )

    # keep the data as json if to_json, else render it into a template file
    if args['to_json']:
        output = json.dumps(timetable_data, indent=args['json_indent'], ensure_ascii=False)
    else:
        output = timetables.render_timetable_into_template(timetable_data, template_file=args['template_file'])
    
    # output to file or stdout
    if args['output_file']:
        if args['verbose']:
            sys.stderr.write(f'Saving data to {args["output_file"]}\n')
        with open(args['output_file'], 'w') as o:
            o.write(output)
    else:
        if args['verbose']:
            sys.stderr.write('Writing results to stdout:\n')
        sys.stdout.write(output)

if __name__ == '__main__':
    main()