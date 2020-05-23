# gptt

gptt (Get Public Transport Timetables) is a command line tool to download and format public transport timetables from the Google Directions API for a given day between an origin and a destination using the Transit travel mode. 

## Installation

The best way to install gptt is via pip: `pip install gptt`. You can alternatively install it from the source: `python setup.py install`.

## Usage

### Command line

gptt is primarily intended to be used as a command line tool, although its functions can be used in a Python program (see below). Using the default template, it generates detailed timetables like this one:

![Example timetable](https://gitcdn.link/repo/andrashann/generate-nice-timetables/master/timetable.png)

`gptt -f "Budapest, Kelenföld vasútállomás" -t "Hejce" -d "2020-07-01" -k $GOOGLE_API_KEY -o timetable.html`, for example, downloads all public transport connections between *Budapest, Kelenföld vasútállomás* (a train station in Budapest, Hungary) and *Hejce* (a village in Hungary) for the date July 1, 2020 using the Google Maps API key defined in the environment variable `$GOOGLE_API_KEY`, then format this data using the default HTML template and output it to `timetable.html`.

*Note:* the default HTML template is designed to be used for routes between, not within municipalities (it emphasizes the locality more than the actual stop name), however, you can create custom templates to suit your specific needs.

Full description of command line options:

<table>
<thead>
  <tr>
    <th>flag</th>
    <th>option</th>
    <th>description</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>-h</td>
    <td>--help</td>
    <td>Show the help.</td>
  </tr>
  <tr>
    <td colspan="3"><span style="font-weight:normal">Basic arguments to get timetable data (must be passed here or in the config file):</span></td>
  </tr>
  <tr>
    <td>-f</td>
    <td>--from</td>
    <td>Where to plan the route from (in a form that Google Maps would understand).</td>
  </tr>
  <tr>
    <td>-t</td>
    <td>--to</td>
    <td>Where to plan the route to (in a form that Google Maps would understand).</td>
  </tr>
  <tr>
    <td>-d</td>
    <td>--date</td>
    <td>The date to be used for planning in a YYYY-MM-DD format.</td>
  </tr>
  <tr>
    <td>-k</td>
    <td>--api-key</td>
    <td>Google API key with the Directions, Geocoding, and Time Zone API enabled.</td>
  </tr>
  <tr>
    <td colspan="3"><span style="font-weight:normal">Further arguments to customize the timetable:</span></td>
  </tr>
  <tr>
    <td>-l</td>
    <td>--lang</td>
    <td>Language code used to display results, eg. 'en-GB' or 'hu' - see Google's <a href="https://developers.google.com/maps/faq#languagesupport" target="_blank" rel="noopener noreferrer">list of supported languages</a>. Defaults to 'en'.</td>
  </tr>
  <tr>
    <td> </td>
    <td>--max-transfers</td>
    <td>Maximum number of allowed transfers in the results. Default is 99.</td>
  </tr>
  <tr>
    <td> </td>
    <td>--vehicle-type-names</td>
    <td>Used to replace vehicle type names (e.g. HEAVY_RAIL or BUS with another string in the output – accepts one or more '=' separated pairs, e.g. "HEAVY_RAIL=Ⓣ" "BUS=Ⓑ".</td>
  </tr>
  <tr>
    <td colspan="3"> <span style="font-weight:normal">Arguments related to the output:</span></td>
  </tr>
  <tr>
    <td>-v</td>
    <td>--verbose</td>
    <td>Print diagnostic messages to stderr.</td>
  </tr>
  <tr>
    <td>-j</td>
    <td>--json</td>
    <td>Output the results in the raw JSON format it is processed from the API.</td>
  </tr>
  <tr>
    <td> </td>
    <td>--json-indent</td>
    <td>If the output is JSON, this many spaces will be used to indent it. If not passed, everything will be on one line.</td>
  </tr>
  <tr>
    <td> </td>
    <td>--template</td>
    <td>Jinja2 template file to use instead of the default template. The default template is HTML, but it could be any text format, such as Markdown or LaTeX. Irrelevant when `--json` is also passed.</td>
  </tr>
  <tr>
    <td>-o</td>
    <td>--output</td>
    <td>Output file to be written. If not given, results will be printed to stdout.</td>
  </tr>
  <tr>
    <td colspan="3">Using a config file:</td>
  </tr>
  <tr>
    <td>-c</td>
    <td>--config</td>
    <td>Accepts a JSON file with a single object whose keys are zero or more of the options described in this table. Values should be appropriate for the option. See an example below. If given, any value present in the config will overwrite the value given by the command line flag/option.</td>
  </tr>
</tbody>
</table>

Note: options **in bold** must be passed either as command line arguments or in the config file.

#### Using a config file

The following `config.json` adds values for the non-required options and the API key. (DO NOT commit your API key to a version control system!). 

```JSON
{
  "vehicle-type-names": ["HEAVY_RAIL=Ⓣ","BUS=Ⓑ"],
  "station-name-replacements": ["Hauptbahnhof=hbf.", "Bahnhof=bf."],
  "lang": "en-GB",
  "max-transfers": 3,
  "api-key": "ab4ab2fa-74c9-4af1-a250-9efe735c80fb"
}
```

Using this file, we can run `gptt -f "London" -t "Manchester" -d "2020-08-19" -c config.json`.

### Python package

The two main functions, `get_transit_plan_for_timestamp()` and `get_transit_plans_for_day()` can be accessed by

```python
from gptt import timetables
timetables.get_transit_plan_for_timestamp(...)
timetables.get_transit_plans_for_day(...)
```

Detailed documentation of these functions can be found in the code.

## Contributing

Issue submissions and pull requests are welcome. Simple fixes do not require an issue to be submitted, however, do submit one if your pull request includes a lot of changes or new features.

## More info

Read more about this project [on my blog](https://hann.io/articles/2020/get-public-transport-timetables).

## Changelog

- 0.1.1:
    - [bugfix] Fixed a bug when certain localities were not parsed correctly from API response ([#1][i1])
    - [bugfix] Made the program aware of the local time of the origin of the query to define the day ([#2][i2])
    - [bugfix] (partial): Better handling of the Routing API not returning transit results. This is not entirely resolved ([#3][i3])
- 0.1.0:
    - initial public release

[i1]: https://github.com/andrashann/gptt/issues/1
[i2]: https://github.com/andrashann/gptt/issues/2
[i3]: https://github.com/andrashann/gptt/issues/3