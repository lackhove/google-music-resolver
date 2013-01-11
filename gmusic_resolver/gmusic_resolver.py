#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# gmusic-resolver
# Copyright (C) 2012 Kilian Lackhove
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import os,  logging

SHAREPATH = os.path.join( os.path.expanduser('~'), '.local', 'share', 'Tomahawk')
CONFPATH = os.path.join( os.path.expanduser('~'), '.config', 'Tomahawk')
os.chdir(SHAREPATH)

logger = logging.getLogger('gmusic-resolver')
hdlr = logging.FileHandler(os.path.join( SHAREPATH, 'gmusic-resolver.log'))
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.WARN)

try:
    import sys,  re
    import base64
    import keyring
    import time,  datetime
    import pickle
    import json
    import difflib
    from struct import unpack, pack
    import gmusicapi
    from threading import Thread

    if sys.version_info >= (3,): # python 3
        from http.server import HTTPServer, BaseHTTPRequestHandler
    else: # python 2
        from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except:
    logger.exception("module import failed. You are probalby missing a dependency")
    exit(1)

MIN_AVG_SCORE = 0.9
MIN_FULLTEXT_SCORE = 0.8
PORT = 8082
MAX_LIB_AGE = 120
api = gmusicapi.Api()

class getHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pattern = re.compile(r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
        reg = re.search(pattern, self.path)
        if not reg:
            logger.exception('invalid id requested: %s'%self.path)
            self.send_response(404)
            self.end_headers()

        id = reg.group(1)
        logger.debug("forwarding stream for id: %s"%id)
        global api
        try:
            url = api.get_stream_url(id)
            self.send_response(301)
            self.send_header('Location', url)
            self.end_headers()
        except:
            logger.exception("URL retrieval for id %s failed"%id)
            self.send_response(404)
            self.end_headers()


def serveOnPort(port):
    server = HTTPServer(("localhost",port), getHandler)
    logger.info("server running on port %d"%port)
    server.serve_forever()


def printJson(o):
    s = json.dumps(o)
    logger.debug("responding %s", s)
    sys.stdout.write(pack('!L', len(s)))
    sys.stdout.write(s)
    sys.stdout.flush()


def init(request):

    if not request:
        # read credentials from keyring
        try:
            userFile = open(os.path.join( CONFPATH, 'username.txt'))
            username= userFile.readline()
            userFile.close()
        except IOError:
            logger.warn("reading username.txt file failed")
            return None

        password = keyring.get_password('gmusic-resolver', username)
        if not password:
            logger.warn("no password for user %s found in keyring"%username)
            return None
    else:
        password = request["widgets"]["passwordLineEdit"]["text"]
        username = request["widgets"]["usernameLineEdit"]["text"]

        # store creds to config and keyring
        userFile = open(os.path.join( CONFPATH, 'username.txt'), 'w')
        userFile.write(username)
        userFile.close()
        keyring.set_password('gmusic-resolver', username,  password)

    # Log in to Google Music
    global api
    loggedIn = False
    attempts = 1
    if api.is_authenticated():
        api.logout()
        api = gmusicapi.Api()

    while not loggedIn and attempts <= 3:

        loggedIn = api.login(username, password)
        if not loggedIn:
            logger.warn("Login attempt # %dfailed"%attempts)
            attempts += 1

    if not api.is_authenticated():
        logger.error( "login failed. Waiting for user input")
        return None
    logger.info("login succeeded")

    # Get all songs in the library
    gmLibrary = []
    filename = os.path.join( SHAREPATH, 'gmusic-library.p')
    if os.path.exists(filename):
        t = os.path.getmtime(filename)
        age = time.time() - t
        logger.debug("cached library age: %d seconds"%age)
        if age <= MAX_LIB_AGE:
            gmLibrary = pickle.load(open(filename) )
            logger.info("loaded library tracks from file")

    if len(gmLibrary) == 0:
        logger.info("retrieving library tracks from google")
        gmLibrary = api.get_all_songs()
        pickle.dump(gmLibrary, open(filename, "wb" ) )
    logger.info('%d tracks in library'%len(gmLibrary))

    # tell tomahawk that we are ready
    try:
        logoFile = open(os.path.join(os.path.dirname(__file__),'gmusic-logo.png'))
        logo = logoFile.read()
    except IOError:
        logger.exception("reading icon file failed")
        api.logout()
        exit(1)
    logger.info("Advertising settings")
    settings = {
                "_msgtype": "settings",
                "name": "Google Music",
                "targettime": 200, # ms
                "weight": 95,
                "icon": base64.b64encode(logo),
                "compressed": "false"
                }
    printJson(settings)

    # start webserver
    Thread(target=serveOnPort, args=[PORT]).start()

    return gmLibrary


def simplify(s):
    # strip whitespaces and use lowercase
    s = s.strip()
    s = s.lower()

    # remove (feat. someartist)
    patterns = ['^(.*?)\(feat\..*?\).*?$',  '^(.*?)feat\..*?$']
    for pattern in patterns:
        reg = re.search(pattern,  s)
        if reg:
            s= reg.group(1)

    return s


def fulltextSearch(gmLibrary,  request):
    logger.debug("fulltext search for for \"%s\"", request['fulltext'])
    startTime =  datetime.datetime.now()
    seqMatchFulltext = difflib.SequenceMatcher(None, "foobar", simplify( request['fulltext'] ))

    # the search function in the gmusic-api is not satisfying (e.g. doesnt match artists, is not
    # error-tolerant enough...), so we use our own implementation for the meantime. Nice side-effect:
    # less load for google music servers and faster search for small collections (~5000 tracks)
    results = []
    for candidate in gmLibrary:
        seqMatchFulltext.set_seq1( simplify( candidate["title"] ) )
        score = seqMatchFulltext.quick_ratio()
        seqMatchFulltext.set_seq1( simplify( candidate["artist"] ) )
        score = max( score,  seqMatchFulltext.quick_ratio() )
        seqMatchFulltext.set_seq1( simplify( candidate["album"] ) )
        score = max( score,  seqMatchFulltext.quick_ratio() )

        if score >= MIN_FULLTEXT_SCORE:
            logger.debug("Found: %s : %s - %s - %s : %f"%(request["fulltext"],  candidate["artist"], candidate["album"],  candidate["title"], score))
            url = "http://localhost:" + str(PORT) + "/" + candidate["id"]
            result = {
                      "artist": candidate["artist"],
                      "track": candidate["title"],
                      "album":  candidate["album"],
                      "duration": candidate["durationMillis"] / 1000,
                      "score":1,
                      "url": url
                      }
            if candidate["year"] != 0:
                result["year"] = candidate["year"]
            if candidate["track"] != 0:
                result["albumPos"] = candidate["track"]
            if candidate["disc"] != 0:
                result["discnumber"] = candidate["disc"]
            results.append( result )


    response = {
            'qid': request['qid'],
            'results': results,
            '_msgtype': 'results'
        }
    printJson(response)

    endTime =  datetime.datetime.now()
    d =  endTime - startTime
    logger.debug('Found %d tracks in %d ms'%(len(results), d.microseconds/1000 ))


def fieldSearch(gmLibrary,  request):
    logger.debug("searching for for %s", request)
    startTime =  datetime.datetime.now()
    results = []
    seqMatchArtist = difflib.SequenceMatcher(None, "foobar", simplify( request["artist"] ))
    seqMatchTitle = difflib.SequenceMatcher(None, "foobar", simplify( request["track"] ))
    for candidate in gmLibrary:
        seqMatchTitle.set_seq1( simplify( candidate["title"] ) )
        scoreTitle = seqMatchTitle.quick_ratio()
        if scoreTitle <= (2*MIN_AVG_SCORE - 1):
            # dont waste time on computing artist score if the title score is already too low to achieve the
            # average score specified below.  This limit should be
            # (1 + x)/2 = y
            # where y is the MIN_AVG_SCORE below and x is this threshold
            continue
        seqMatchArtist.set_seq1( simplify( candidate["artist"] ) )
        scoreArtist = seqMatchArtist.quick_ratio()
        score = (scoreArtist + scoreTitle) /2
        if score >= MIN_AVG_SCORE:
            logger.debug("Found: %s - %s : %s - %s : %f,%f,%s"%(request["artist"],  request["track"], candidate["artist"], candidate["title"], scoreArtist, scoreTitle, score))
            url = "http://localhost:" + str(PORT) + "/" + candidate["id"]
            result = {
                "artist": candidate["artist"],
                "track": candidate["title"],
                "album":  candidate["album"],
                "duration": candidate["durationMillis"] / 1000,
                "score":1,
                "url": url
                }
            if candidate["year"] != 0:
                result["year"] = candidate["year"]
            if candidate["track"] != 0:
                result["albumPos"] = candidate["track"]
            if candidate["disc"] != 0:
                result["discnumber"] = candidate["disc"]
            results.append( result )

    response = {
            'qid': request['qid'],
            'results': results,
            '_msgtype': 'results'
        }
    printJson(response)

    endTime =  datetime.datetime.now()
    d =  endTime - startTime
    logger.debug('Found %d tracks in %d ms'%(len(results), d.microseconds/1000 ))


def main():

    try:

        logger.info('gmusic resolver started')

        # send config ui
        try:
            uiFile = open(os.path.join(os.path.dirname(__file__),'config.ui'))
            configUi = uiFile.read()
            logoFile = open(os.path.join(os.path.dirname(__file__),'gmusic-logo.png'))
            logo = logoFile.read()
        except IOError:
            logger.exception("reading ui files failed")
            exit(1)
        confwidget = {
                "_msgtype": "confwidget",
                "compressed": "false",
                "widget": base64.b64encode(configUi),
                "images": {"gmusic-logo.png": base64.b64encode(logo)}
                }
        printJson(confwidget)

        # the main loop
        gmLibrary = init(None)
        while True:
            #logger.debug("waiting for message length")
            bigEndianLength = sys.stdin.read(4)

            if len(bigEndianLength) < 4:
                logger.error("No length given (%r==EOF?). Exiting.",
                        bigEndianLength)
                api.logout()
                exit(1)
            length = unpack("!L", bigEndianLength)[0]
            if not length or not length > 0:
                logger.warn("invalid length: %s", length)
                logger.warn(sys.stdin.read(length))
                break
            #logger.debug("waiting for %s more chars", length)
            msg = sys.stdin.read(length)
            request = json.loads(msg)

            if '_msgtype' not in request:
                logger.warn("malformed request (no _msgtype): %s",
                    request)
            elif gmLibrary and request['_msgtype'] == 'rq': # Search
                if 'fulltext' in request:
                    fulltextSearch(gmLibrary,  request)
                else:
                    fieldSearch( gmLibrary,  request)
            elif request['_msgtype'] == 'config':
                logger.debug("ignoring config message: %s", request)
            elif request['_msgtype'] == 'setpref':
                gmLibrary = init(request)
            elif request['_msgtype'] == 'quit':
                logger.info("Asked to Quit. Exiting.")
                api.logout()
                exit(0)
            else:
                logger.warn("unknown request: %s", request)

    except Exception:
        logger.exception("something went wrong")
        raise

    api.logout()


if __name__ == "__main__":
    main()
