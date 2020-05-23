import requests
import json
import sys
import logging

from datetime import datetime

import pkgutil
default_html_template = pkgutil.get_data(__name__, "templates/default_html_template.html").decode()

import jinja2


class DirectionsAPIGenericError(RuntimeError):
    """An error thrown when the Directions API returns an error.
    """
    pass

class DirectionsAPINoTransitDirectionsError(RuntimeError):
    """An error thrown when the Directions API could not find transit
    directions (but it would have found driving directions).
    """
    pass

class GeocodingAPIError(RuntimeError):
    """An error thrown when the Geocoding API returns an error.
    """
    pass

class TimeZoneAPIError(RuntimeError):
    """An error thrown when the Time Zone API returns an error.
    """
    pass

class NoEligibleRoutesError(RuntimeError):
    """An error thrown when there are no eligible routes left after filtering
    them by the number of transfers.
    """
    pass

def get_location_time_offset(location, unix_timestamp, api_key):
    """Get the time offset from UTC of location at unix_timestamp from Google
    APIs using the api_key

    Arguments:
        location {str} -- A place on Earth, whose name will be interpreted by
         Google
        unix_timestamp {int} -- Point in time for which the offset should be
         calculated (important because of DST)
        api_key {string} -- Google API key with Geocoding and Time Zone API
         enabled

    Raises:
        GeocodingAPIError: if the Geocoding API returns an error
        ValueError: if we could not identify latitude and longitude of the
         location
        TimeZoneAPIError: if the Time Zone API returns an error

    Returns:
        dict -- a dict with two values: 'offset', the calculated offset as an
         int and 'api_calls', which should be always 2.
    """
    count_api_calls = 0

    location_api_result = \
        requests.get(
            'https://maps.googleapis.com/maps/api/geocode/json', 
            params={'address': location, 'key': api_key}
        ).json()
    count_api_calls += 1
    
    if location_api_result['status'] != 'OK':
        raise GeocodingAPIError(
            location_api_result['status'], 
            location_api_result.get('error_message')
        ) 

    lat = location_api_result['results'][0]['geometry'].get('location').get('lat')
    lon = location_api_result['results'][0]['geometry'].get('location').get('lng')
    if lat is None or lon is None:
        raise ValueError('Coordinates could not be parsed from API results. The received data was: {0}'.format(location_api_result['results'][0]))
    
    time_zone_api_result = \
        requests.get(
            'https://maps.googleapis.com/maps/api/timezone/json',
            params={
                'location':f'{lat},{lon}',
                'timestamp': unix_timestamp,
                'key': api_key
                }
        ).json()
    count_api_calls += 1

    if time_zone_api_result['status'] != 'OK':
        raise TimeZoneAPIError(
            time_zone_api_result['status'], 
            time_zone_api_result.get('error_message')
        ) 
    
    time_offset = \
        time_zone_api_result.get('dstOffset', 0) +\
        time_zone_api_result.get('rawOffset', 0)

    return {
        'offset': time_offset,
        'api_calls': count_api_calls
    }

def get_transit_plan_for_timestamp(origin, destination, api_key, unix_timestamp, 
                                   language='en', vehicle_type_names={}, station_name_replacements=[], verbose=False):
    """Get first transit connection after unix_timestamp from origin to destination using api_key

    Arguments:
        origin {string} -- A string that the Google Transit API understands as
         a location, will be used as the origin of the route.
        destination {string} -- A string that the Google Transit API
         understands as a location, it will be used as the destination of 
         the route.
        api_key {string} -- Google API key with Directions, Geocoding, and Time 
         Zone API enabled.
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
        DirectionsAPIGenericError: the Directions API encountered an error.
        DirectionsAPINoTransitDirectionsError: the Directions API could not
         find transit directions at the given route at the given time.

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
        sys.stderr.flush()
    timetable_data = json.loads(r.text)

    if timetable_data['status'] != 'OK':
        # If 'available_travel_modes' is part of the API response, it means 
        # that we could not get transit directions at the given point in time
        # at the given route. This list will NOT have TRANSIT in it. If this is
        # part of the response, transit mode was available and there was some 
        # other error.
        if 'TRANSIT' not in timetable_data.get('available_travel_modes', 'TRANSIT'):
            raise DirectionsAPINoTransitDirectionsError(timetable_data['status'])
        else:
            raise DirectionsAPIGenericError(timetable_data['status'], timetable_data.get('error_message',''))
    
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
         get_transit_plan_for_timestamp(), also used to determine the time zone
         of the request
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

    # set the departure time unix timestamp to the beginning of the day
    utc_time = datetime.strptime(f'{date}T00:00:00.000Z', '%Y-%m-%dT%H:%M:%S.%fZ')
    start_of_day = int((utc_time - datetime(1970, 1, 1)).total_seconds())

    origin_time_offset_data = get_location_time_offset(origin, start_of_day, api_key)
    origin_time_offset = origin_time_offset_data['offset']
    total_api_calls += origin_time_offset_data['api_calls']

    start_of_day -= origin_time_offset # epoch of day start at location
    end_of_day = start_of_day + 24 * 60 * 60 # epoch of day end at location

    # initialize variable used in loop below
    this_departure_time = start_of_day

    # a placeholder for results to be filled in:
    full_transit_results = []

    # a counter of failed attempts in a row (sometimes the API says there are 
    # no transit directions for a route for a given time, we use this to handle
    # that)
    failed_attempts = 0
    # number of times we had such an error separately from each other (i.e.
    # not while retrying with another time stamp)
    total_times_error_encountered = 0

    # we don't know how many results will there be, so we loop until we 
    # get to the end of the day
    if verbose:
        sys.stderr.write(f'Getting routes for the day {date}:')
    while True:
        # the departure time we pass to the API should be one second
        # after the previous departure time to get the next option
        this_departure_time += 1
        try:
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
            failed_attempts = 0
        except DirectionsAPINoTransitDirectionsError:
            # The Directions API sometimes does not return routes for a given
            # time even though transit routing is available in the location.
            # Let's try a point in time five minutes later. If a problem is
            # encountered for the nth time, we try n*5 minutes later, until
            # a success, at which time n is reset to 0
            time_delta = 5 * 60 * (failed_attempts + 1)
            this_departure_time += time_delta

            if failed_attempts == 0:
                if verbose:
                    sys.stderr.write(f' !')
                    sys.stderr.flush()
                total_times_error_encountered += 1

            failed_attempts += 1

            if this_departure_time + 1 > end_of_day:
                # if we arrived at the end of the day, output the results as
                # done below
                pass
            else:
                # if there is still some time left, carry on with getting more
                # data
                continue
        else:
            # We will need current the departure time to look for
            # the next one after it. It is not the same as the unix_timestamp
            # argument of the function as the departure time will come after
            # that point in time. However, we only set this from the data if
            # there was no exception above (otherwise we increment it manually
            # in the "except" block).
            this_departure_time = transit_results[0]['departure_time_epoch']

        if this_departure_time + 1 > end_of_day:
            # break the loop if we are on the next day
            if len(full_transit_results) == 0:
                raise ValueError('No directions were found.')
            
            if verbose:
                sys.stderr.write('\n')
                sys.stderr.write('Found {0} route suggestions.\n'.format(len(full_transit_results)))

            if total_times_error_encountered:
                logging.warn(f'The API failed to return a route {total_times_error_encountered} time(s). This is not fatal but it might cause missing results in the final output. You might be able to fix this by providing more specific values (e.g. the name of a station instead of a city) for "from" and "to". However, since this is a quirk of the API, this may not fix the problem.')

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
                sys.stderr.flush()
            r = requests.get(reverse_geocode_api_url, params={'latlng': loc, 'key': api_key})
            total_api_calls += 1
            loc_data = json.loads(r.text)

            if loc_data['status'] != 'OK':
                raise GeocodingAPIError(loc_data['status'], loc_data.get('error_message'))

            # Municipality names are stored either in the 'locality' or 'postal_town'
            # type entries in the address components part of the API response.
            # We need the long_name for this; we take the first one as a rule of thumb.
            location_name = [x['long_name'] for x in loc_data['results'][0]['address_components'] 
                                if 'locality' in x['types'] or 'postal_town' in x['types']][0]
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