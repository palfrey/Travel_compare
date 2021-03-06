# -*- coding: utf-8 -*-
from urlgrab import GetURL
from urlgrab.URLTimeout import URLTimeoutError
from sys import argv
from urllib import quote_plus
from ConfigParser import ConfigParser, NoOptionError
from xml.dom.minidom import parseString, parse
from re import findall, finditer, DOTALL
import math
from datetime import date, timedelta
import pprint
from sets import Set
from xml.parsers.expat import ExpatError

import wsgiref.handlers
from google.appengine.ext import webapp

cache = None

cp = ConfigParser()
cp.read("tc.ini")

class ParseException(Exception):
	pass

class CityException(ParseException):
	pass

def loc_info(loc):
	yahoo_id = cp.get("secrets","yahoo_id")
	geocode_url = "http://local.yahooapis.com/MapsService/V1/geocode?appid=%s&location=%s"
	start_loc = cache.get(geocode_url%(yahoo_id,quote_plus(loc)), max_age=-1).read()

	dom = parseString(start_loc)

	country = dom.documentElement.getElementsByTagName("Country")[0].firstChild.data
	if country == "US":
		# FIXME: Cheating by adding ",uk" to requests. Also works for European locations!
		# Stops us getting US places
		try:
			ret = loc_info(loc + ", uk")
			ret["Original"] = loc
			return ret
		except CityException:
			# rewrite for loc change
			raise CityException, "No city found for '%s'. Please provide more precise information"%loc

	if len(dom.documentElement.getElementsByTagName("Result"))!=1:
		# FIXME: handle multiples. Current hack is use the first one only
		pass
		#print start_loc
		#raise Exception, "Don't handle multiple returns yet for '%s'"%loc

	city = dom.documentElement.getElementsByTagName("City")[0]
	if city.firstChild == None:
		raise CityException, "No city found for '%s'. Please provide more precise information"%loc
	city = city.firstChild.data
	if city.find(",")!=-1:
		city = ", ".join(city.split(",")[:-1])
	latitude = dom.documentElement.getElementsByTagName("Latitude")[0].firstChild.data
	longitude = dom.documentElement.getElementsByTagName("Longitude")[0].firstChild.data
	country = dom.documentElement.getElementsByTagName("Country")[0].firstChild.data

	fullname = dom.documentElement.getElementsByTagName("City")[0].firstChild.data
	if dom.documentElement.getElementsByTagName("Address")[0].firstChild != None:
		fullname = "%s, %s"%(dom.documentElement.getElementsByTagName("Address")[0].firstChild.data, fullname)

	return {"City":city, "Lat":float(latitude), "Long":float(longitude), "Address":fullname, "Country":country, "Original":loc}

def directions(start_loc, end_loc):
	try:
		mapquest_key = cp.get("secrets","mapquest_key")
	except NoOptionError:
		mapquest_key = ""
	if mapquest_key == "": # no key, let's try scraping google...
		gmaps_url = "http://maps.google.com/maps?f=d&source=s_d&saddr=%s&daddr=%s&hl=en&geocode=&mra=ls&vps=1&output=js"
		url = gmaps_url%("%f,%f"%(start_loc["Lat"], start_loc["Long"]),"%f,%f"%(end_loc["Lat"], end_loc["Long"]))
		data = cache.get(url, max_age=-1).read()
		dists = findall("distance:\"([\d,\.]+) ([^\"]+)\"", data)
		if dists == []:
			raise ParseException,"Can't seem to get directions between '%s' and '%s' from Google maps"%(start_loc["Original"],end_loc["Original"])
		shortest = None
		for (amount, unit) in dists:
			amount = float(amount.replace(",",""))
			if unit == "mi":
				amount *= 1.6 # miles -> km
			elif unit == "km":
				pass
			else:
				raise Exception, unit
			if shortest == None or shortest > amount:
				shortest = amount
		
		# distance always in km
		return {"distance": shortest}
	else:
		mapquest_url = "http://www.mapquestapi.com/directions/v1/route?key=%s&from=%f,%f&to=%f,%f&units=k&narrativetype=none&maxLinkId=0&outFormat=xml"
		url = mapquest_url%(mapquest_key,start_loc["Lat"], start_loc["Long"],end_loc["Lat"], end_loc["Long"])
		data = cache.get(url, max_age=-1).read()
		dom = parseString(data)
		status = dom.getElementsByTagName("statusCode")
		if status!=[] and int(status[0].firstChild.data) != 0:
			raise ParseException,"Can't seem to get directions between '%s' and '%s' from Mapquest (detailed error is '%s')"%(start_loc["Original"],end_loc["Original"],dom.getElementsByTagName("message")[0].firstChild.data)
		return {"distance": float(dom.getElementsByTagName("distance")[0].firstChild.data)}

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

# Distance code from http://www.zachary.com/s/blog/2005/01/12/python_zipcode_geo-programming

#
# The following formulas are adapted from the Aviation Formulary
# http://williams.best.vwh.net/avform.htm
#

def calcDistance(lat1, lon1, lat2, lon2):					  
	nauticalMilePerLat = 60.00721
	nauticalMilePerLongitude = 60.10793
	rad = math.pi / 180.0
	milesPerNauticalMile = 1.15078

	"""
	Calculate distance between two lat lons in NM
	"""
	yDistance = (lat2 - lat1) * nauticalMilePerLat
	xDistance = (math.cos(lat1 * rad) + math.cos(lat2 * rad)) * (lon2 - lon1) * (nauticalMilePerLongitude / 2)

	distance = math.sqrt( yDistance**2 + xDistance**2 )

	return distance * milesPerNauticalMile

# end copy+paste distance code

def co2InItems(amount, item):
	data = cache.get("http://carbon.to/%s"%item).read()
	try:
		dom = parseString(data)
		return amount/float(dom.getElementsByTagName("carbon")[0].firstChild.data)
	except ExpatError:
		return -1

class MainHandler(webapp.RequestHandler):

	def get(self):
		start = self.request.get("start")
		end = self.request.get("end")
		self.response.out.write("""<html>
			<title>Travel Comparison</title>
			<body>
			  <h1>Travel Comparison</h1>
			  Compare the costs (price/CO<sub>2</sub>/time) of different travel methods<br/>
			  <small>(Built by <a href="http://tevp.net">Tom Parker</a>. <a href="http://github.com/palfrey/Travel_compare/tree/master">Source Code</a>. Don't enter non-European locations, or it'll break)</small>
			  <form action="/" method="get">
				<div><br/>Start location: <input type="text" name="start" value="%s"</div>
				<div>Destination: <input type="text" name="end" value="%s"</div>
				<div><input type="submit" value="Discover cost"></div>
			  </form>
		"""%(start,end))
		if start == "" or end == "":
			self.response.out.write("</body></html>")
			return
		global cache
		cache = GetURL.GetURL()

		try:
			start = loc_info(start)
		except URLTimeoutError,e:
			if e.code == 400: # lookup failure
				self.response.out.write("Can't find '%s'"%start)
				self.response.out.write("</body></html>")
				return
			else:
				raise
		try:
			end = loc_info(end)
		except ParseException,e:
			self.response.out.write(e.message)
			self.response.out.write("</body></html>")
			return
		except URLTimeoutError,e:
			if e.code == 400: # lookup failure
				self.response.out.write("Can't find '%s'"%end)
				self.response.out.write("</body></html>")
				return
			else:
				raise

		#print start
		#print end
		try:
			path = directions(start, end)
		except ParseException,e:
			self.response.out.write(e.message)
			self.response.out.write("</body></html>")
			return

		#print path

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

		directDistance = calcDistance(start["Lat"],start["Long"],end["Lat"],end["Long"])*1.09 # add 9% for going in the air! See Plane_generic amee wiki page

		flightcost = (planeTotal(flights[k]["fname"])/flights[k]["limit"])*directDistance
		#print flightcost,"kg",directDistance,"km"

		ebookers_url = "http://www.ebookers.com/shop/airsearch?type=air&ar.type=oneWay&ar.ow.leaveSlice.orig.key=%s&ar.ow.leaveSlice.dest.key=%s&ar.ow.leaveSlice.date=%d%%2F%d%%2F%2d&ar.ow.leaveSlice.time=Anytime&ar.ow.numAdult=1&ar.ow.numSenior=0&ar.ow.numChild=0&ar.ow.child%%5B0%%5D=&ar.ow.child%%5B1%%5D=&ar.ow.child%%5B2%%5D=&ar.ow.child%%5B3%%5D=&ar.ow.child%%5B4%%5D=&ar.ow.child%%5B5%%5D=&ar.ow.child%%5B6%%5D=&ar.ow.child%%5B7%%5D=&_ar.ow.nonStop=0&_ar.ow.narrowSel=0&ar.ow.narrow=airlines&ar.ow.carriers%%5B0%%5D=&ar.ow.carriers%%5B1%%5D=&ar.ow.carriers%%5B2%%5D=&ar.ow.cabin=C&search=Search+Flights"

		when = date.today() + timedelta(30) # 30 days time
		try:
			if start["City"] == end["City"]: # can't get a plane flight!
				raise URLTimeoutError(None,None) # FIXME hack, handle places we can't get distances for
			ebookers = cache.get(ebookers_url%(start["City"], end["City"], when.day, when.month, when.year)).read()
			#open("dump","w").write(ebookers)
			prices = findall("class=\"price\">£([\d,]+\.\d+)\*</span>", ebookers)
			#schedules = findall("<table class=\"airItinerarySummary summary block hideFromNonJS\">(.+?)</table>", ebookers, DOTALL)
			schedules = findall("<td class=\"col5\">(.+?)</td>", ebookers, DOTALL)
			assert len(schedules) == len(prices),(len(schedules),len(prices))

			if len (prices) == 0:
				raise URLTimeoutError(None, None) # FIXME: hack, handle places we can't get distances for
			planeprice = float(prices[0])
			planetime = schedules[0].strip()
			if planetime.find(" ")!=-1: # assume hr bit on front
				hrs = planetime.split(" ")[0].strip()
				assert hrs[-2:] == "hr",hrs
				planemins = int(hrs[:-2])*60
				planetime = planetime.split(" ")[1]
			else:
				lanemins = 0
			assert planetime[-3:] == "min",planetime
			planemins += int(planetime[:-3])
		except URLTimeoutError:
			self.response.out.write("(Ebookers is being silly again, so no plane price data)<br/><br/>\n")
			planeprice = None
		
		results = {}
		results["Train"] = {
				"Distance":path["distance"],
				"CO2":traincost,
			}
		results["Plane"] = {
				"Distance":directDistance,
				"CO2":flightcost
		}

		if planeprice!=None:
			results["Plane"]["Price"] = planeprice
			results["Plane"]["Time"] = planemins

		totalkeys = Set()

		for k in results:
			keys = results[k].keys()
			for item in keys:
				if item == "CO2":
					results[k]["CO<sub>2</sub"] = "%.2f kg"%results[k][item]
				elif item == "Distance":
					results[k][item] = "%.1f km"%results[k][item]
				elif item == "Price":
					results[k][item] = "&pound;%.2f"%results[k][item]
				elif item == "Time":
					results[k][item] = "%d minutes"%results[k][item]
			co2 = co2InItems(results[k]["CO2"], "beers")
			if co2 != -1:
				bottles = "%.2f bottles"%co2
			else:
				bottles = "(don't know)"
			results[k]["<a href='http://carbon.to/'>Bottles of beer equivalent</a>"] = bottles
			del results[k]["CO2"]
			
			totalkeys.update(results[k].keys())
			
		self.response.out.write("Going from %s -> %s<br/>\n"%(start["Address"], end["Address"]))
		self.response.out.write("<table border=1><th>")
		for k in totalkeys:
			self.response.out.write("<td>%s</td>"%k)
		self.response.out.write("</th>\n")
		for k in results:
			self.response.out.write("<tr><td>%s</td>"%k)
			for t in totalkeys:
				if results[k].has_key(t):
					self.response.out.write("<td>%s</td>"%results[k][t])
				else:
					self.response.out.write("<td>&nbsp;</td>")
			self.response.out.write("</tr>\n")
		self.response.out.write("</table>\n")
		self.response.out.write("Plane is %.1f%% worse than train in terms of CO<sub>2</sub costs<br/>\n"%(((flightcost-traincost)/traincost)*100.0))
		self.response.out.write("</body></html>")


def main():
  application = webapp.WSGIApplication([('/', MainHandler)],
									   debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
	main()
