import binascii
import re
import string
import threading
import time
from flask import Flask, json, send_from_directory, render_template, redirect, request
import sqlite3
from base64 import urlsafe_b64decode, urlsafe_b64encode
from urllib import request as urlrequest
import urllib.error
from waitress import serve
import os
import humanfriendly
import logging


# Delay (in seconds) before the link became inactive 
EXPIRATION_DELAY = int(os.getenv("EXPIRATION_DELAY", "259200"))

# The maximum amount of link that can be stored at the same time in the database. 
# Prevent potential spam bots to fill up completly the hard drive.
MAX_LINK_AMOUNT = int(os.getenv("MAX_LINK_AMOUNT", "10000"))

# The base URL of the website
WEBSITE_URL = os.getenv("WEBSITE_URL", "localhost")

# A forbidden websites list provider because we don't want to link to bad websites.
FORBIDDEN_WEBSITES_LIST_PROVIDER = os.getenv("FORBIDDEN_WEBSITES_LIST_PROVIDER", "https://raw.githubusercontent.com/elbkr/bad-websites/refs/heads/main/websites.json")


# Init various objects
app = Flask(__name__, template_folder="frontend/templates")
db = sqlite3.connect("data/data.db", check_same_thread=False)
cur = db.cursor()
lock = threading.Lock()
logger = logging.getLogger("VeryShortLink") # Setup the logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs.log"), 
        logging.StreamHandler()
    ]
)

forbidden_websites = []

def check_table_exists(name):
    """Return true if the table with the given name already exists in the database."""
    execution = cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';").fetchone()
    return not (execution is None or len(execution) == 0)

def update_forbidden_websites_list():
    """Update the forbidden websit list from the given provider."""
    try:
        response_data = urlrequest.urlopen(FORBIDDEN_WEBSITES_LIST_PROVIDER).read()
    except urllib.error.URLError:
        raise Exception("Unable to recover bad websites list : File is unavailable")
    
    try:
        data = json.loads(response_data.decode("utf-8"))
    except (UnicodeDecodeError, json.decoder.JSONDecodeError):
        raise Exception("Unable to recover bad websites list : File is corrupted")
    
    global forbidden_websites
    forbidden_websites = data["links"]
    logger.info("Updated forbidden websites list.")

def check_website_is_allowed(url):
    """Check if the website is in the forbidden websites list."""
    for website in forbidden_websites:
        if website in url:
            return False
    return True

def encode_url(url):
    """Encode the given url with url safe base 64."""
    return urlsafe_b64encode(url.encode("utf-8")).decode("utf-8")

def create_link(base_url):
    """Create a new link, store it in the database and return the id."""
    try:
        lock.acquire(True)
        cur.execute(f"INSERT INTO Link (endpoint, expiration_date) VALUES(\"{encode_url(base_url)}\", {int(time.time())+EXPIRATION_DELAY})")
        new_id = cur.execute(f"SELECT MAX(id) FROM Link;").fetchone()[0]
        db.commit()
    finally:
        lock.release()

    logger.info(f"Created new link with id \"{new_id}\" pointing to \"{base_url}\".")
    return get_link_with_id(str(hex(new_id)[2:]))

def get_link_with_id(id):
    """Return a formated link with the given ID."""
    return f"{WEBSITE_URL}/{id}"

def check_url_already_exists(url):
    result = cur.execute(f"SELECT id FROM Link WHERE endpoint = \"{encode_url(url)}\";").fetchone()

    if result is None or len(result) == 0:
        return None
    
    try:
        lock.acquire(True)
        cur.execute(f"UPDATE Link SET expiration_date = \"{int(time.time())+EXPIRATION_DELAY}\" WHERE id = {result[0]};")
    
        db.commit()
    finally:
        lock.release()
    
    logger.info(f"Renewed expiration date for id {result[0]}.")

    return result[0]

def get_links_amount():
    """Return the number of links that are in the database."""
    return cur.execute("SELECT COUNT(id) FROM Link;").fetchone()[0]

def check_expired():
    """Delete all expired links."""
    try:
        lock.acquire(True)
        cur.execute(f"DELETE FROM Link WHERE expiration_date < {int(time.time())}")
        db.commit()
    finally:
        lock.release()

def get_setting(key):
    """Get the settings stored as key-value. Return the value if the key exists or None if it doesn't."""
    result = cur.execute(f"SELECT value FROM Setting WHERE key = \"{key}\"").fetchone()
    if result is None: return None
    if len(result) == 0: return None
    return result[0]

def set_setting(key, value):
    """Set a setting stored as key-value and save it to the database."""
    cur.execute(f"INSERT INTO Setting (key, value) VALUES(\"{key}\", \"{value}\") ON DUPLICATE KEY UPDATE value=\"{value}\";")
    db.commit()

@app.route("/")
def index():
    """The main page of the website."""
    return render_template("index.html", validity_time=humanfriendly.format_timespan(EXPIRATION_DELAY))

@app.route("/assets/<file>")
def asset(file):
    """Access an asset from the assets directory."""
    return send_from_directory("frontend/assets", file)

@app.route("/robots.txt")
def robots():
    """Access robots.txt page"""
    return send_from_directory("frontend", "robots.txt")

@app.route("/<id>")
def access_link(id):
    """Redirect the user to the endpoint url if the given id exists."""
    check_expired()

    id = id.lower()

    # Check if the link is valid
    if len(id)<0 or not all(c in string.hexdigits for c in id):
        return render_template("link_access_error.html", message="The given link is invalid. The link contains invalid characters.")
    
    # Get the endpoint link from the database and check if it successed
    result = cur.execute(f"SELECT endpoint FROM Link WHERE id = {int(id, 16)};").fetchone()
    if result is None or len(result) == 0:
        return render_template("link_access_error.html", message="The given link seems to be expired or never existed.")
    
    logger.info(f"{request.remote_addr} redirected. ID: {id}")

    url = urlsafe_b64decode(result[0]).decode("utf-8")

    if not url.startswith("http"):
        url = "http://" + url
    
    return redirect(url)


@app.route("/api/shortit/", methods=["POST"])
def shortit():
    """Private api endpoint to create a new short link."""
    check_expired()

    print(request.headers)

    body = request.get_json()

    if "url" in body:
        url = body["url"]
    else:
        return {"error": "Invalid request body."}
    
    if not isinstance(body["url"], str):
        return {"error": "Wrong data type for URL."}
    
    # Check the lenght of the URL. We don't want URLs to be to long as we don't want people 
    # using our service to store custom data. And it also prevents the database to became enormous.
    if len(url) >= 1024:
        return {"error": "URL is too long. Please use URL that is shorter than 1024 characteres."}
    
    # Check if the data is a valid URL
    if re.match(r"[(http(s)?):\/\/(www\.)?a-zA-Z0-9@:%._\+~#=\-]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)", url) is None:
        return {"error": "The given URL doesn't seem to be a valid URL."}
    
    # Check if the website is forbidden
    if not check_website_is_allowed(url):
        return {"error": "This website is not allowed."}
    
    # Check if we don't exced the maximum amount of links we can create
    if get_links_amount() > MAX_LINK_AMOUNT:
        return {"error" : "The website exceded the maximum of link that can be created. We may be experiencing bot spams issues. Please wait a few minutes before retrying."}
    
    already_exists = check_url_already_exists(url)
    if already_exists is not None:
        return {"new_url": get_link_with_id(already_exists)}
    else:
        return {"new_url": create_link(url)}
    

if __name__ == "__main__":
    # Init the tables if they doesn't exist yet in the database
    if not check_table_exists("Link"):
        cur.execute("CREATE TABLE Link(id INTEGER PRIMARY KEY, endpoint TEXT, expiration_date INT);")
    if not check_table_exists("Setting"):
        cur.execute("CREATE TABLE Setting(key VARCHAR(32) PRIMARY KEY NOT NULL, value VARCHAR(32));")

    update_forbidden_websites_list()
    
    logger.info("Starting")
    serve(app, port=8080)
