# -*- coding: utf-8 -*-
from urlgrab.GetURL import GetURL
from sys import argv
from urllib import quote_plus
from ConfigParser import ConfigParser
from xml.dom.minidom import parseString, parse
from re import findall, finditer, DOTALL
import math
from datetime import date, timedelta
import pprint

#from sys import path
#path.append("amee")
#from amee import AMEEConnection

geocode_url = "http://local.yahooapis.com/MapsService/V1/geocode?appid=%s&location=%s"
gmaps_url = "http://maps.google.com/maps?f=d&source=s_d&saddr=%s&daddr=%s&hl=en&geocode=&mra=ls&vps=1&output=js"

cache = GetURL()

cp = ConfigParser()
cp.read("tc.ini")

yahoo_id = cp.get("secrets","yahoo_id")
assert len(argv) == 3, len(argv)

def loc_info(loc):
	start_loc = cache.get(geocode_url%(yahoo_id,quote_plus(loc)), max_age=-1).read()

	dom = parseString(start_loc)

	country = dom.documentElement.getElementsByTagName("Country")[0].firstChild.data
	if country == "US":
		# FIXME: Cheating by adding ",uk" to requests. Also works for European locations!
		# Stops us getting US places
		return loc_info(loc + ", uk")

	if len(dom.documentElement.getElementsByTagName("Result"))!=1:
		print start_loc
		raise Exception, "Don't handle multiple returns yet for '%s'"%loc

	city = dom.documentElement.getElementsByTagName("City")[0].firstChild.data
	if city.find(",")!=-1:
		city = ", ".join(city.split(",")[:-1])
	latitude = dom.documentElement.getElementsByTagName("Latitude")[0].firstChild.data
	longitude = dom.documentElement.getElementsByTagName("Longitude")[0].firstChild.data
	country = dom.documentElement.getElementsByTagName("Country")[0].firstChild.data

	fullname = dom.documentElement.getElementsByTagName("City")[0].firstChild.data
	if dom.documentElement.getElementsByTagName("Address")[0].firstChild != None:
		fullname = "%s, %s"%(dom.documentElement.getElementsByTagName("Address")[0].firstChild.data, fullname)

	return {"City":city, "Lat":float(latitude), "Long":float(longitude), "Address":fullname, "Country":country}

def directions(start_loc, end_loc):
	url = gmaps_url%("%f,%f"%(start_loc["Lat"], start_loc["Long"]),"%f,%f"%(end_loc["Lat"], end_loc["Long"]))
	data = cache.get(url, max_age=-1).read()
	dists = findall("distance:\"([\d,\.]+) ([^\"]+)\"", data)
	if dists == []:
		open("dump","w").write(data)
		raise Exception
	shortest = None
	for (amount, unit) in dists:
		amount = float(amount.replace(",",""))
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

def trainPerKm(trainfile):
	dom = parse(trainfile)
	for p in dom.getElementsByTagName("Path"):
		if p.firstChild.data == "kgCO2PerKmPassenger" and p.parentNode.tagName == "ItemValue":
			return float(p.parentNode.getElementsByTagName("Value")[0].firstChild.data)
	raise Exception

def planeTotal(planefile):
	dom = parse(planefile)
	for p in dom.getElementsByTagName("Path"):
		if p.firstChild.data == "kgCO2PerPassengerJourney" and p.parentNode.tagName == "ItemValue":
			return float(p.parentNode.getElementsByTagName("Value")[0].firstChild.data)
	raise Exception

national = trainPerKm("train-National")
international = trainPerKm("train-International")

if start["Country"] == end["Country"]:
	trainrate = national
else:
	trainrate = (national + international) / 2.0

traincost = trainrate*path["distance"]

flights = {
		"domestic":{"fname":"plane-Domestic","limit":463},
		"short-haul":{"fname":"plane-ShortHaul","limit":1108},
		"long-haul":{"fname":"plane-LongHaul","limit":6482}
		}

kind = None
for k in sorted(flights.keys(),cmp=lambda x,y:cmp(flights[x]["limit"],flights[y]["limit"])):
	if path["distance"]<(flights[k]["limit"]*1.5): # 50% extra limit
		kind = k
		break

assert kind!=None,path["distance"]

# Distance code from http://www.zachary.com/s/blog/2005/01/12/python_zipcode_geo-programming

#
# The following formulas are adapted from the Aviation Formulary
# http://williams.best.vwh.net/avform.htm
#

nauticalMilePerLat = 60.00721
nauticalMilePerLongitude = 60.10793
rad = math.pi / 180.0
milesPerNauticalMile = 1.15078

def calcDistance(lat1, lon1, lat2, lon2):                      
    """
    Caclulate distance between two lat lons in NM
    """
    yDistance = (lat2 - lat1) * nauticalMilePerLat
    xDistance = (math.cos(lat1 * rad) + math.cos(lat2 * rad)) * (lon2 - lon1) * (nauticalMilePerLongitude / 2)

    distance = math.sqrt( yDistance**2 + xDistance**2 )

    return distance * milesPerNauticalMile

# end copy+paste distance code

directDistance = calcDistance(start["Lat"],start["Long"],end["Lat"],end["Long"])*1.09 # add 9% for going in the air! See Plane_generic amee wiki page

def co2InItems(amount, item):
	data = cache.get("http://carbon.to/%s?co2=%f"%(item,amount)).read()
	dom = parseString(data)
	return float(dom.getElementsByTagName("amount")[0].firstChild.data)

flightcost = (planeTotal(flights[k]["fname"])/flights[k]["limit"])*directDistance
print flightcost,"kg",directDistance,"km"

ebookers_url = "http://www.ebookers.com/shop/airsearch?type=air&ar.type=oneWay&ar.ow.leaveSlice.orig.key=%s&ar.ow.leaveSlice.dest.key=%s&ar.ow.leaveSlice.date=%d%%2F%d%%2F%2d&ar.ow.leaveSlice.time=Anytime&ar.ow.numAdult=1&ar.ow.numSenior=0&ar.ow.numChild=0&ar.ow.child%%5B0%%5D=&ar.ow.child%%5B1%%5D=&ar.ow.child%%5B2%%5D=&ar.ow.child%%5B3%%5D=&ar.ow.child%%5B4%%5D=&ar.ow.child%%5B5%%5D=&ar.ow.child%%5B6%%5D=&ar.ow.child%%5B7%%5D=&_ar.ow.nonStop=0&_ar.ow.narrowSel=0&ar.ow.narrow=airlines&ar.ow.carriers%%5B0%%5D=&ar.ow.carriers%%5B1%%5D=&ar.ow.carriers%%5B2%%5D=&ar.ow.cabin=C&search=Search+Flights"

when = date.today() + timedelta(30) # 30 days time
ebookers = cache.get(ebookers_url%(start["City"], end["City"], when.day, when.month, when.year)).read()
open("dump","w").write(ebookers)
prices = findall("class=\"price\">£([\d,]+\.\d+)\*</span>", ebookers)
#schedules = findall("<table class=\"airItinerarySummary summary block hideFromNonJS\">(.+?)</table>", ebookers, DOTALL)
schedules = findall("<td class=\"col5\">(.+?)</td>", ebookers, DOTALL)
assert len(schedules) == len(prices),(len(schedules),len(prices))

planeprice = float(prices[0])
planetime = schedules[0].strip()
if planetime.find(" ")!=-1: # assume hr bit on front
	hrs = planetime.split(" ")[0].strip()
	assert hrs[-2:] == "hr",hrs
	planemins = int(hrs[:-2])*60
	planetime = planetime.split(" ")[1]
else:
	planemins = 0
assert planetime[-3:] == "min",planetime
planemins += int(planetime[:-3])

print "planemins",planemins

print
print "Going from %s -> %s"%(start["Address"], end["Address"])
print "Train: distance %.1f km, Co2 %.1f kg"%(path["distance"], traincost),"or %d bottles of beer"%co2InItems(traincost, "beers")
print "Plane: distance %.1f km, Price £%.2f, Time %d minutes, Co2 %.1f kg"%(directDistance, planeprice, planemins, flightcost),"or %d bottles of beer"%co2InItems(flightcost, "beers")
print "Plane is %.1f%% worse than train"%(((flightcost-traincost)/traincost)*100.0)
