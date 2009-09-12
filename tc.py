from urlgrab.GetURL import GetURL
from sys import argv
from urllib import quote_plus

from ConfigParser import ConfigParser

cache = GetURL()

cp = ConfigParser()
cp.read("tc.ini")

yahoo_id = cp.get("secrets","yahoo_id")
geocode_url = "http://local.yahooapis.com/MapsService/V1/geocode?appid=%s&location=%s"

assert len(argv) == 3, len(argv)

start = quote_plus(argv[1])
end = quote_plus(argv[2])

start_loc = cache.get(geocode_url%(yahoo_id,start)).read()
print start_loc
