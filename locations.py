# Helper routines to read "locations.ini" with reciever location like this:
#
#[default]
#name=Home
#lat= 123.45
#lon=  67.89
#alt= 123

import sys
import re
import os
from configparser import ConfigParser
from types import SimpleNamespace
import pyproj
import numpy as np
import argparse

ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')

to_lla = pyproj.Transformer.from_proj(ecef, lla)
to_ecef = pyproj.Transformer.from_proj(lla, ecef)


def parseangle(value):
    z = re.match(r"(?P<sign>[+-]?)(?P<deg>\d+(\.\d+)?)(° *((?P<min>\d+(\.\d+)?)['′] *)?((?P<sec>\d+(\.\d+)?)\")?(?P<dir>[NEOSW]?))?$", value)
    if z is None:
        raise ValueError("could not convert string to angle: '%s'"%value)
    parsed = z.groupdict()
    result = float(parsed['deg'])
    if parsed['min'] is not None:
        result += float(parsed['min'])/60
    if parsed['sec'] is not None:
        result += float(parsed['sec'])/60/60
    if parsed['dir'] == 'S' or parsed['dir'] == 'W' or parsed['sign'] == '-':
        result = -result
    return result


class GetObserver(argparse.Action):
     def __call__(self, parser, namespace, values, option_string=None):
         setattr(namespace, self.dest, get_observer(values))

def get_observer(location):
    observer = SimpleNamespace()

    config = ConfigParser(converters={'angle': parseangle})
    config.read(['locations.ini', os.path.join(os.path.dirname(__file__), 'locations.ini'), os.path.join(os.path.dirname(__file__), '..', 'locations.ini')])

    if location not in config:
        print("Location %s not defined" % location, file=sys.stderr)
        print("Available locations: ", ", ".join(config.sections()), file=sys.stderr)
        sys.exit(1)

    if 'name' in config[location]:
        observer.name = config[location]['name']
#        args.loc = observer.name
    else:
        observer.name = location

    if 'lat' in config[location]:
        lat = config.getangle(location, 'lat')
        lon = config.getangle(location, 'lon')
        alt = config.getfloat(location, 'alt')
        observer.__dict__.update(lat=lat, lon=lon, alt=alt)

        x, y, z = to_ecef.transform(lon, lat, alt, radians=False)
        observer.xyz = np.array([x, y, z])/1000

    elif 'x' in config[location]:
        x = config.getfloat(location, 'x')
        y = config.getfloat(location, 'y')
        z = config.getfloat(location, 'z')
        observer.xyz = np.array([x, y, z])/1000

        lon, lat, alt = to_lla.transform(x, y, z, radians=False)
        observer.__dict__.update(lat=lat, lon=lon, alt=alt)

    else:
        print("Location %s has no location information" % location, file=sys.stderr)
        sys.exit(1)

    return observer


def get_locations():
    config = ConfigParser()
    config.read(['locations.ini', os.path.join(os.path.dirname(__file__), 'locations.ini'), os.path.join(os.path.dirname(__file__), '..', 'locations.ini')])

    if config.sections():
        return config.sections()

    raise SystemExit("locations.ini missing or empty")


if __name__ == "__main__":
    assert parseangle("123") == 123
    assert parseangle("-13.30") == -13.30
    assert parseangle("13°") == 13
    assert parseangle("13°30'S") == -13.5
    assert parseangle("13°30'1\"") == 13 + 30/60 + 1/3600
    assert parseangle("174° 47′ O") == 174 + 47/60

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--loc",       choices=get_locations(), default="default", help="location")
    args = parser.parse_args()

    observer = get_observer(args.loc)
    print(observer)
