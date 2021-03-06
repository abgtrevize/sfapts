import scraperwiki
import requests
import hashlib
import time
import os
import geojson
import datetime
from slackclient import SlackClient

# Environment Variables
base_url='https://sfbay.craigslist.org'
start_url='/jsonsearch/apa/sfc/?s=120&map=1'
ticker=0
os.environ['TZ']='US/Central'
time.tzset()
#Neighborhood definitions - https://data.sfgov.org/Geographic-Locations-and-Boundaries/SF-Find-Neighborhoods/pty2-tcw4

# Apartment Class
class apartment(object):
	"""Apartment class that parses Craigslist json.
		Create Instance with apartment(dict)"""
	def __init__(self, obj):
		self.bedrooms=obj['Bedrooms']
		self.price=obj['Ask']
		self.title=obj['PostingTitle']
		self.latitude=obj['Latitude']
		self.longitude=obj['Longitude']
		self.url=obj['PostingURL']
		self.postingID=obj['PostingID']
		self.postingDate=obj['PostedDate']
		self.timeStamp=time.strftime('%Y-%m-%d %H:%M:%S')
		self.neighborhood=get_neighborhood_for_point(self.latitude,self.longitude,poly)
		self.hashedTitle=hashlib.md5(str((self.title).encode('utf-8'))+str(self.price)+str(self.neighborhood)).hexdigest()	
		self.daysSince=(datetime.datetime.now()-datetime.datetime.fromtimestamp(self.postingDate)).days
	def inFilter(self):
		filterNeighborhoods=['Russian Hill','Pacific Heights','Lower Pacific Heights','Presidio Heights','Laurel Heights / Jordan Park','Presidio Terrace',
			'Dogpatch','Central Waterfront', 'Showplace Square', 'Mission Bay', 'Bernal Heights',' Potrero Hill', 'Peralta Heights', 'Midtown Terrace',
			'Forest Knolls','Sherwood Forest','St. Francis Wood','Miraloma Park', 'Noe Valley'
		]
		if self.neighborhood in filterNeighborhoods and self.price < 6800 and self.bedrooms >2 and self.bedrooms<6 and self.price>2900:
			return True
		else:
			return False
	def saveToDB(self):
		scraperwiki.sqlite.save(
			table_name='data',
			unique_keys=['hashedTitle'],
			data={
					'bedrooms':self.bedrooms,
					'price':self.price,
					'title':self.title,
					'latitude':self.latitude,
					'longitude':self.longitude,
					'url':self.url,
					'postingID':self.postingID,
					'postingDate':self.postingDate,
					'hashedTitle':self.hashedTitle,
					'timeStamp':self.timeStamp,
					'neighborhood':self.neighborhood,
					'daysSince':self.daysSince
				})

## Recursive function that combines getResults getListings
def getListings(url,ticker):
	sess=requests.Session()
	sess.headers['User-Agent']='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.98 Safari/537.36'
	adapter=requests.adapters.HTTPAdapter(max_retries=100)
	sess.mount('http://',adapter)	
	response=sess.get(url)
	if response.ok:
		pass
	elif ticker<10:
		print response.reason
		print response.content
		ticker=ticker+1
		pass
	else:
		sys.exit()
	listings=[]
	items=[x for x in response.json()[0] if 'GeoCluster' not in  x.keys()]
	listings.extend(items)
	try:
		clusters=[x for x in response.json()[0] if 'GeoCluster' in  x.keys()]
		for cluster in clusters:
			getListings(base_url+cluster['url'],0)
	except:
		pass
	return listings

def processListings(listings):
	dupKey = ["PostingID"]
	filtered = {tuple((k, d[k]) for k in sorted(d) if k in dupKey): d for d in listings}
	noDupListings = list(filtered.values())
	apartments = [apartment(apt) for apt in noDupListings]		
	hashList = [x['hashedTitle'] for x in scraperwiki.sqlite.select('distinct hashedTitle from data')]
	newListings = [x for x in apartments if x.hashedTitle not in hashList]
	status = "New Listings: {0}. Of Interest: {1}".format(str(len(newListings)),str(len([x for x in newListings if x.inFilter()])))
	print status
	sc.api_call(
		"chat.postMessage", channel=SLACK_CHANNEL, text=status,
		username='auntagatha', icon_emoji=':older_woman:'
	)
	for unit in newListings:
		unit.saveToDB()
		if unit.inFilter():
			desc = "{0} | {1} | {2} | <{3}>".format(str(unit.neighborhood), unit.price, unit.title.encode('utf-8'), unit.url)	
			sc.api_call(
			    "chat.postMessage", channel=SLACK_CHANNEL, text=desc,
			    username='auntagatha', icon_emoji=':older_woman:'
			)

def point_inside_polygon(x,y,poly):
    """Return True if the point described by x, y is inside of the polygon
    described by the list of points [(x0, y0), (x1, y1), ... (xn, yn)] in
    ``poly``

    Code from http://www.ariel.com.au/a/python-point-int-poly.html which
    in turn was adapted from C code found at
    http://local.wasp.uwa.edu.au/~pbourke/geometry/insidepoly/
    """
    n = len(poly)
    inside =False

    p1x,p1y = poly[0]
    for i in range(n+1):
        p2x,p2y = poly[i % n]
        if y > min(p1y,p2y):
            if y <= max(p1y,p2y):
                if x <= max(p1x,p2x):
                    if p1y != p2y:
                        xinters = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x,p1y = p2x,p2y
    return inside

def get_neighborhood_for_point(lat, lng, commareas):
    for neighborhood in commareas:
        if point_inside_polygon(lng, lat, neighborhood['geometry']['coordinates'][0][0]):
            return neighborhood['properties']['name']


if int(time.strftime('%d'))%1==0:
	SLACK_TOKEN = os.environ['MORPH_SLACK_TOKEN']
	SLACK_CHANNEL = "#auntagatha"
	sc = SlackClient(SLACK_TOKEN)
	poly=geojson.loads(open('SF Find Neighborhoods.geojson').read())['features']
	listings=getListings(base_url+start_url,ticker)
	processListings(listings)
