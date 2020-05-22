import requests
import json
import sys

import dateutil.parser as dp
from datetime import datetime

import pkgutil
default_html_template = pkgutil.get_data(__name__, "templates/default_html_template.html").decode()

import jinja2


class DirectionsAPIError(RuntimeError):
    """An error thrown when the Directions API returns an error.
    """
    pass

class GeocodingAPIError(RuntimeError):
    """An error thrown when the Geocoding API returns an error.
    """
    pass

class NoEligibleRoutesError(RuntimeError):
    """An error thrown when there are no eligible routes left after filtering
    them by the number of transfers.
    """
    pass

def ts_to_date(ts):
    '''Turn an unix timestamp into an ISO date'''
    return datetime.fromtimestamp(int(ts)).isoformat()[:10]

def get_transit_plan_for_timestamp(origin, destination, api_key, unix_timestamp, 
                                   language='en', vehicle_type_names={}, station_name_replacements=[], verbose=False):
    """Get first transit connection after unix_timestamp from origin to destination using api_key

    Arguments:
        origin {string} -- A string that the Google Transit API understands as
         a location, will be used as the origin of the route.
        destination {string} -- A string that the Google Transit API
         understands as a location, it will be used as the destination of 
         the route.
        api_key {string} -- Google API key with Directions and Geocoding 
         enabled.
        unix_timestamp {int or str} -- Timestamp to search from. The first
         result after this point in time will be returned

    Keyword Arguments:
        language {str} -- Language of the results, see valid values here:
         https://developers.google.com/maps/faq#languagesupport
         (default: {'en'})
        vehicle_type_names {dict} -- values used to replace the VEHICLE_TYPE
         field in the API response, e.g. {'HEAVY_RAIL':'Ⓣ'} (default: {{}})
        station_name_replacements {list} -- list of replacements to be done
         in the station names, e.g. [["Hauptbahnhof", "hbf.], ["Bahnhof",
         "bf."]] (default: {[]})

    Raises:
        DirectionsAPIError: the Directions API encountered an error.

    Returns:
        list -- a list of dictionaries, each of which contains details of
        one step in the journey.
    """
    request_data = {
        'origin': origin,
        'destination': destination,
        'mode': 'transit',
        'language': language,
        'key': api_key,
        'departure_time': unix_timestamp
    }

    directions_api_url = 'https://maps.googleapis.com/maps/api/directions/json'

    r = requests.get(directions_api_url, params=request_data)
    if verbose:
        sys.stderr.write(' .')
    timetable_data = json.loads(r.text)

    if timetable_data['status'] != 'OK':
        raise DirectionsAPIError(timetable_data['status'], timetable_data.get('error_message'))        
    
    # only one route will be returned (for given dep time)
    # "Generally, only one entry in the routes array is returned
    # for directions lookups, though the Directions service may 
    # return several routes if you pass alternatives=true."
    # https://developers.google.com/maps/documentation/directions/intro#DirectionsResponses
    # But we don't pass alternatives=true.
    route = timetable_data['routes'][0] 
    
    # only one leg will be returned, as no intermediate stops are possible in transit
    leg = route['legs'][0] 
    
    # ignore walking directions between stops
    transit_steps = [x for x in leg['steps'] if x['travel_mode'] != 'WALKING'] 
    
    # initialize result container which will contain a dict for each step
    transit_results = []

    # there will be steps (i.e. different vehicles one takes)
    # process these to get the parts of the data we need
    for step in transit_steps:
        # get the fields from the API response that we will
        # actually use
        s = step['transit_details']

        step_data = {}

        step_data['departure_stop'] = s['departure_stop']['name']
        # replace whatever needs to be replaced in departure station names
        # (e.g. to shorten Hauptbahnhof to Hbf) and do this sequentially over
        # the passed list of replacements:
        for r in station_name_replacements:
            step_data['departure_stop'] = step_data['departure_stop'].replace(*r)
        step_data['departure_location'] = str(s['departure_stop']['location']['lat']) + \
                                          ',' + str(s['departure_stop']['location']['lng'])
        step_data['departure_time'] = s['departure_time']['text']
        step_data['departure_time_epoch'] = s['departure_time']['value']
        
        step_data['arrival_stop'] = s['arrival_stop']['name']
        # replace whatever needs to be replaced in arrival station names
        # (e.g. to shorten Hauptbahnhof to Hbf) and do this sequentially over
        # the passed list of replacements:
        for r in station_name_replacements:
            step_data['arrival_stop'] = step_data['arrival_stop'].replace(*r)
        step_data['arrival_location'] = str(s['arrival_stop']['location']['lat']) + \
                                        ',' + str(s['arrival_stop']['location']['lng'])
        step_data['arrival_time'] = s['arrival_time']['text']
        step_data['arrival_time_epoch'] = s['arrival_time']['value']

        step_data['vehicle'] = s['line']['vehicle']['name']
        # get the vehicle type name from the vehicle_type_names dict,
        # or, if it does not exist there, use what was returned by the API.
        step_data['vehicle_type'] = vehicle_type_names.get(s['line']['vehicle']['type'], s['line']['vehicle']['type'])
        step_data['headsign'] = s['headsign']
        step_data['line_short_name'] = s['line'].get('short_name')
        step_data['line_name'] = s['line'].get('name')
 
        # add current step to the results list
        transit_results.append(step_data)
    
    # return a list of dicts (one for each step in the journey)
    return transit_results

def get_transit_plans_for_day(origin, destination, api_key, date, 
                              language='en', max_transfers=99, vehicle_type_names={}, station_name_replacements=[],
                              get_station_localities=False, verbose=False):
    """Call the get_transit_plan_for_timestamp() function as many times as
    needed from the beginning of the day until the end of the day to fetch all
    transit routes suggested by Google on this date between the origin and
    destination. For the full description of each of the arguments, check the
    docstring of get_transit_plan_for_timestamp().

    Arguments:
        origin {string} -- Origin; will be passed to 
         get_transit_plan_for_timestamp()
        destination {string} -- Destination; will be passed to
         get_transit_plan_for_timestamp()
        api_key {string} -- API key to be used; will be passed to
         get_transit_plan_for_timestamp()
        date {string} -- Date in YYYY-MM-DD format, will be passed to
         get_transit_plan_for_timestamp()

    Keyword Arguments:
        language {str} -- Language, will be passed to
         get_transit_plan_for_timestamp() (default: {'en'})
        max_transfers {int} -- Maximum number of transfers allowed in
         the results (default: {99})
        vehicle_type_names {dict} -- Mapping for vehicle type names, will be 
         passed to get_transit_plan_for_timestamp() (default: {{}})
        station_name_replacements {list} -- Station name text replacements,
         will be passed to get_transit_plan_for_timestamp() (default: {[]})
        get_station_localities {bool} -- Should we get the locality (city,
         village, etc.) of the transit stops? This can be used in the output
         but it requires more API calls. (default: {False})
        verbose {bool} -- Print diagnostic messages to stderr

    Raises:
        NoEligibleRoutesError: raised when max_transfers is too high and we end
         up with zero routes in the list
        GeocodingAPIError: raised when the Google Geocoding API returns an
         error.

    Returns:
        A list of transit results, each of which is a list of dictionaries 
         describing its steps.
    """                              

    total_api_calls = 0 #not used for anything right now

    t = '{}T00:00:00.000Z'.format(date)
    parsed_t = dp.parse(t)
    
    # set the departure time to the beginning of the day
    this_departure_time = parsed_t.strftime('%s')

    full_transit_results = []

    # we don't know how many results will there be, so we loop until we 
    # get to the end of the day
    if verbose:
        sys.stderr.write(f'Getting routes for the day {date}:')
    while True:
        # the departure time we pass to the API should be one second
        # after the previous departure time to get the next option
        this_departure_time = str(int(this_departure_time) + 1)

        transit_results = \
            get_transit_plan_for_timestamp(
                origin=origin, 
                destination=destination, 
                api_key=api_key, 
                unix_timestamp=this_departure_time, 
                language=language,
                vehicle_type_names=vehicle_type_names,
                station_name_replacements=station_name_replacements,
                verbose=verbose
            )
        total_api_calls += 1

        # we will need current the departure time to look for
        # the next one after it. it is not the same as the unix_timestamp
        # argument of the function as the departure time will come after
        # that point in time
        this_departure_time = transit_results[0]['departure_time_epoch']

        if ts_to_date(this_departure_time) != date:
            # break the loop if we are on the next day
            if verbose:
                sys.stderr.write('\n')
                sys.stderr.write('Found {0} route suggestions.\n'.format(len(full_transit_results)))
            break
        full_transit_results.append(transit_results)

    filtered_results = [x for x in full_transit_results if len(x) <= max_transfers + 1]
    if verbose:
        sys.stderr.write(f'After filtering out those with more than {max_transfers} transfers, {len(filtered_results)} remain.\n')

    if len(filtered_results) == 0:
        raise NoEligibleRoutesError('No routes left after filtering by the number of transfers. Try increasing the number of maximum transfers.')

    if get_station_localities:
        # gather all unique locations that are mentioned so that we can
        # query the Google Location API to find out which locality
        # (city, village, etc.) they are in.
        locations = list(set([y['arrival_location'] for x in filtered_results for y in x] + 
                             [y['departure_location'] for x in filtered_results for y in x]))
        if verbose:
            sys.stderr.write(f'Getting locality information for {len(locations)} locations:')
        reverse_geocode_api_url = 'https://maps.googleapis.com/maps/api/geocode/json'

        # actually query the locations and store them in a dict
        location_lookup = {}
        for loc in locations:
            if verbose:
                sys.stderr.write(' .')
            r = requests.get(reverse_geocode_api_url, params={'latlng': loc, 'key': api_key})
            total_api_calls += 1
            loc_data = json.loads(r.text)

            if loc_data['status'] != 'OK':
                raise GeocodingAPIError(loc_data['status'], loc_data.get('error_message'))

            location_name = [x['long_name'] for x in loc_data['results'][0]['address_components'] 
                                if 'locality' in x['types']][0]
            location_lookup[loc] = location_name
        if verbose:
            sys.stderr.write('\n')

        # add the localities to each of the results in the filtered_results list
        for res in filtered_results:
            for step in res:
                step['departure_locality'] = location_lookup[step['departure_location']]
                step['arrival_locality'] = location_lookup[step['arrival_location']]

    return filtered_results

def render_timetable_into_template(timetable_data, template_file=None):
    """Render timetable data into a template

    Arguments:
        timetable_data {list} -- A list containing timetable data results
        obtained from the Google Directions API using the 
        get_transit_plan_for_timestamp() or get_transit_plans_for_day() 
        function.

    Keyword Arguments:
        template_file {str} -- The name of a file that uses Jinja2 templating
        to be used to put the timetable data into. If not given, will use the
        default template that is part of the package. Custom templates would
        typically be HTML files, but they could be anything: Markdown, LaTeX,
        etc. (default: {None})
    """
    if template_file:
        with open(template_file) as f:
            template = jinja2.Template(f.read())
    else:
        template = jinja2.Template(default_html_template)

    rendered_timetable = template.render(results=timetable_data)

    return rendered_timetable