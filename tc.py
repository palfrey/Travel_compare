from urlgrab.GetURL import GetURL
from sys import argv
from urllib import quote_plus
from ConfigParser import ConfigParser
from xml.dom.minidom import parseString
from re import findall

geocode_url = "http://local.yahooapis.com/MapsService/V1/geocode?appid=%s&location=%s"
gmaps_url = "http://maps.google.com/maps?f=d&source=s_d&saddr=%s&daddr=%s&hl=en&geocode=&mra=ls&vps=1&output=js"

cache = GetURL()

cp = ConfigParser()
cp.read("tc.ini")

yahoo_id = cp.get("secrets","yahoo_id")
assert len(argv) == 3, len(argv)

def loc_info(loc):
	# FIXME: Cheating by adding ",uk" to all requests. Also works for European locations!
	# Stops us getting US places
	loc += ", uk"

	start_loc = cache.get(geocode_url%(yahoo_id,quote_plus(loc))).read()

	dom = parseString(start_loc)

	if len(dom.documentElement.getElementsByTagName("Result"))!=1:
		print start_loc
		raise Exception, "Don't handle multiple returns yet for '%s'"%loc

	city = dom.documentElement.getElementsByTagName("City")[0].firstChild.data.split(",")[0]
	latitude = dom.documentElement.getElementsByTagName("Latitude")[0].firstChild.data
	longitude = dom.documentElement.getElementsByTagName("Longitude")[0].firstChild.data

	fullname = dom.documentElement.getElementsByTagName("City")[0].firstChild.data
	if dom.documentElement.getElementsByTagName("Address")[0].firstChild != None:
		fullname = "%s, %s"%(dom.documentElement.getElementsByTagName("Address")[0].firstChild.data, fullname)
	return {"City":city, "Lat":float(latitude), "Long":float(longitude), "Address":fullname}

def directions(start_loc, end_loc):
	url = gmaps_url%("%f,%f"%(start_loc["Lat"], start_loc["Long"]),"%f,%f"%(end_loc["Lat"], end_loc["Long"]))
	data = cache.get(url).read()
	dists = findall("distance:\"([\d\.]+) ([^\"]+)\"", data)
	if dists == []:
		open("dump","w").write(data)
		raise Exception
	shortest = None
	for (amount, unit) in dists:
		amount = float(amount)
		if unit == "mi":
			amount *= 1.6 # miles -> km
		else:
			raise Exception, unit
		if shortest == None or shortest > amount:
			shortest = amount
	
	# distance always in km
	return {"distance": shortest}

start = loc_info(argv[1])
end = loc_info(argv[2])


print start
print end

path = directions(start, end)

print path
