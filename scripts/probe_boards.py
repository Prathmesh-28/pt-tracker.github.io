"""Probe which Indian employers expose a public board feed, and on which ATS.

Slug discovery is guesswork, so this tests candidates rather than assuming.
A miss means "no public feed found under that slug", not "not hiring".
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Indian-founded or India-heavy employers that plausibly run a startup ATS.
CANDIDATES = """
razorpay zerodha groww cred phonepe paytm meesho swiggy zomato zepto blinkit
udaan lenskart nykaa purplle mamaearth boat licious countrydelight wakefit
physicswallah unacademy upgrad scaler emeritus practo pharmeasy healthifyme
curefit dehaat ninjacart postman freshworks zoho chargebee whatfix sprinto
atlan hasura browserstack zeta darwinbox keka leadsquared exotel gupshup
moengage clevertap netcore juspay cashfree payu bharatpe slice jupiter navi
kreditbee lendingkart setu decentro perfios innovaccer icertis druva plum
onsurity khatabook dukaan shiprocket delhivery porter rapido yulu zetwerk
moglix ofbusiness jumbotail elasticrun apna urbancompany nobroker cars24
spinny cardekho parkplus chalo redbus ixigo cleartrip oyo vedantu doubtnut
sarvam krutrim fractal tigeranalytics latentview quantiphi tredence gramener
cropin stellapps bijak vegrow dealshare citymall furlenco rentomojo bewakoof
myntra flipkart phable pristyncare mfine truemeds wysa emoha portea
turtlemint acko digit onsitego bounce blusmart everestfleet chargezone
battery smart exponent yubi vivriti indifi velocity klub gethyphen recur
zolve fi-money smallcase tickertape sensibull dhan angelone upstox
rupeek stashfin moneyview branchapp jar navadhan avail arth
scienaptic signzy idfy hyperverge bureau greypenguin
locus fareye shadowfax porter loadshare rivigo blackbuck
freightify wiz freightwalla cogoport odex
whatfix mindtickle darwinbox springworks peoplestrong
kissflow zluri spendflo cleartax quicko taxbuddy
skyroot agnikul pixxel dhruva bellatrix digantara
ather ola simple-energy river ultraviolette
licious freshtohome captainfresh waycool absolute
bluestone caratlane melorra giva
mokobara nappa thewholetruth slurrpfarm yogabar
sleepycat duroflex sheela wakefit
zolvit
vakilsearch
razorpayx
ezetap
pinelabs
mswipe
innoviti
worldline
fampay
akudo
jupitermoney
onecard
uni
indialends
paisabazaar
bankbazaar
creditmantri
wishfin
mymoneymantra
fisdom
scripbox
kuvera
piggy
wealthy
tarrakki
glide
invest
smallcase
sqrrl
goalwise
orowealth
turno
euler
altigreen
log9
batx
attero
recykal
saahas
zunroof
sunsource
freyr
amplus
cleanmax
fourth-partner
darwinbox
springrole
hrone
zimyo
greythr
sumhr
pockethrms
observe-ai
uniphore
haptik
yellowai
verloop
ameyo
ozonetel
knowlarity
sprinklr
chargebee
zenoti
mobikwik
easebuzz
instamojo
cashkaro
paisawapas
magicpin
nearbuy
zomaland
grofers
bigbasket
dailyninja
supr
milkbasket
freshvnf
otipy
superzop
shopkirana
peel-works
udaan-com
ninjakart
jumbotail
solv
bizongo
infra-market
livspace
pepperfry
urbanladder
homelane
arrivae
designcafe
nobrokerhood
mygate
adda
apartment-adda
practo-technologies
medibuddy
visit
docsapp
mfine
1mg
netmeds
zeno-health
apollo-247
wellness-forever
generico
lybrate
cure-fit
sarva
bodhi
byjus
whitehatjr
toppr
embibe
extramarks
meritnation
simplilearn
greatlearning
imarticus
jaro
talentedge
masaischool
almabetter
codingninjas
geeksforgeeks
interviewbit
airmeet
zluri
chargebee-inc
rocketlane
leadsquared-inc
freshdesk
kissflow
facilio
zenoti
clootrack
qure-ai
sigtuple
niramai
tricog
cardiotrack
skyroot-aerospace
agnikul-cosmos
pixxel-space
dhruva-space
tonbo
ideaforge
asteria
garuda
ather-energy
ola-electric
simple-energy
oben
raptee
zypp
yulu-bikes
bounce-share
vogo
drivezy
blusmart
everest-fleet
lithium-urban
shadowfax
delhivery-com
xpressbees
ecom-express
dtdc
gati
safexpress
rivigo-services
locus-sh
fareye-technologies
loginext
shipsy
zetwerk-manufacturing
moglix-com
ofb-tech
ripplr
elasticrun-in
whatfix-inc
mindtickle-inc
icertis-inc
netradyne
minds
capillary
manthan
crayon
exotel-in
ozonetel-in
kaleyra
route-mobile
gupshup-io
airtel-iq
browserstack-com
lambdatest
testsigma
qatouch
hasura-io
appsmith
tooljet
budibase
atlan-com
deepsource
sentry
juspay-in
cashfree-payments
payu-in
setu-in
decentro-tech
signzy-tech
perfios-software
finbox
lentra
yubi-com
vivriti-capital
credavenue
axio
kissht
zestmoney
simpl
lazypay
progcap
flexiloans
indifi-technologies
khatabook-app
okcredit-app
dukaan-app
zoho-corp
freshworks-inc
sarvam-ai
krutrim-ai
zomato-limited
swiggy-in
eternal
instamart
hyperpure
flipkart-internal
myntra-jabong
cleartrip-in
shopsy
nykaa-fashion
foxtale
minimalist
deconstruct
pilgrim
plumgoodness
earthrhythm
dot-key
wow-skin
sugarcosmetics
mcaffeine
beardo
ustraa
noise
boult
fireboltt
crossbeats
pebble
atomberg
agaro
glen
cello
mokobara
zouk
nasher-miles
safari
rare-rabbit
snitch
bewakoof-com
souled-store
libas
biba
w-for-woman
aurelia
lenskart-com
titan-eyeplus
cult-fit
curefit-in
fitternity
healthkart
nutrabay
wellbeing
mamaearth-in
honasa
the-derma-co
bblunt
bombayshavingcompany
bombay-shaving
country-delight
sid-farm
akshayakalpa
zepto-now
blinkit-in
swiggy-instamart
dunzo-daily
porter-in
shadowfax-in
ecomexpress
xpressbees-in
shiprocket-in
unicommerce
vinculum
browntape
easyecom
increff
wareiq
zoho-in
freshworks-india
chargebee-in
whatfix-com
mindtickle-com
icertis-com
darwinbox-in
keka-hr
zoho-people
hone
kredily
razorpayx-payroll
zolvit
vakil-search
indiafilings
cleartax-in
razorpay-software
razorpay-in
phonepe-in
paytm-money
paytm-insider
groww-in
zerodha-broking
upstox-in
angel-one
dhan-co
fyers
smallcase-in
tickertape-in
sensibull-in
indmoney
jar-app
fi-inc
epifi
navi-technologies
slice-it
uni-cards
onecard-in
kiwi-in
bharatpe-in
mswipe-in
pine-labs
ezetap-in
juspay-technologies
cashfree-in
signzy-in
hyperverge-in
idfy-in
perfios-in
finbox-in
lentra-ai
m2p-fintech
setu-co
decentro-in
zeta-in
yubi-in
vivriti-in
progcap-in
flexiloans-in
indifi-in
kreditbee-in
lendingkart-in
moneyview-in
axio-in
kissht-in
zestmoney-in
practo-in
tata-1mg
netmeds-in
pharmeasy-in
medibuddy-in
truemeds-in
apollo247
wellness-forever-in
qure-ai
sigtuple-in
niramai-in
tricog-in
innovaccer-in
hcah
portea-in
byjus-in
unacademy-in
vedantu-in
physics-wallah
pw-live
scaler-academy
newton-school
masai-school
almabetter-in
simplilearn-in
great-learning
upgrad-in
emeritus-in
eruditus
talentedge-in
cropin-in
ninjacart-in
dehaat-in
waycool-in
absolute-in
bijak-in
vegrow-in
arya-ag
samunnati-in
jai-kisan
stellapps-in
intello-labs
ideaforge-in
tonbo-imaging
asteria-aerospace
skyroot-in
agnikul-in
pixxel-in
dhruva-in
digantara-in
bellatrix-in
ather-in
ola-electric-in
ultraviolette-in
raptee-in
oben-electric
river-mobility
euler-motors
altigreen-in
turno-in
zypp-electric
battery-smart
chargezone-in
log9-materials
attero-in
recykal-in
zunroof-in
amplus-solar
cleanmax-in
fourth-partner-energy
sunsource-energy
locus-in
fareye-in
loginext-in
shipsy-in
blackbuck-in
rivigo-in
zetwerk-in
moglix-in
ofbusiness-in
bizongo-in
infra-market-in
jumbotail-in
elasticrun-com
solv-in
capillary-in
manthan-in
crayon-data
netcore-in
moengage-in
clevertap-in
kaleyra-in
route-mobile-in
gupshup-in
exotel-in
ozonetel-in
knowlarity-in
uniphore-in
haptik-in
yellow-ai
verloop-in
observe-ai-in
sprinklr-in
browserstack-in
lambdatest-in
testsigma-in
postman-in
hasura-in
appsmith-in
tooljet-in
atlan-in
deepsource-in
zluri-in
spendflo-in
rocketlane-in
facilio-in
kissflow-in
clootrack-in
airmeet-in
hopin
nobroker-in
housing-com
squareyards-in
magicbricks-in
99acres-in
cars24-in
spinny-in
cardekho-in
droom-in
park-plus
chalo-in
redbus-in
ixigo-in
oyo-rooms
treebo-in
fabhotels-in
urban-company
urbanclap-in
mygate-in
adda-io
nobrokerhood-in
livspace-in
pepperfry-in
homelane-in
furlenco-in
rentomojo-in
licious-in
freshtohome-in
captain-fresh
country-delight-in
milkbasket-in
otipy-in
superzop-in
shopkirana-in
dealshare-in
citymall-in
apna-in
hirect-in
jobhai-in
instahyre-in
cutshort-in
iimjobs-in
springworks-in
peoplestrong-in
turtlemint-in
acko-in
godigit-in
onsurity-in
plum-insurance
visit-health
khatabook-in
okcredit-in
dukaan-in
""".split()

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}


def count_jobs(ats: str, payload) -> int:
    if ats == "lever":
        return len(payload) if isinstance(payload, list) else 0
    if isinstance(payload, dict):
        return len(payload.get("jobs") or [])
    return 0


def probe(job) -> dict | None:
    ats, slug = job
    url = ENDPOINTS[ats].format(slug)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            if r.status != 200:
                return None
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError):
        return None
    n = count_jobs(ats, payload)
    if n == 0:
        return None
    return {"ats": ats, "slug": slug, "postings": n}


def main() -> None:
    slugs = sorted(set(CANDIDATES))
    jobs = [(ats, s) for s in slugs for ats in ENDPOINTS]
    print(f"probing {len(slugs)} slugs x {len(ENDPOINTS)} boards = {len(jobs)} requests",
          file=sys.stderr)

    hits = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        for result in pool.map(probe, jobs):
            if result:
                hits.append(result)
                print(f"  hit {result['ats']:11} {result['slug']:20} {result['postings']:>5} postings",
                      file=sys.stderr)

    hits.sort(key=lambda h: -h["postings"])
    with open("boards.json", "w") as f:
        json.dump(hits, f, indent=2)
    print(f"\n{len(hits)} live boards across {len({h['slug'] for h in hits})} employers "
          f"-> boards.json", file=sys.stderr)


if __name__ == "__main__":
    main()
