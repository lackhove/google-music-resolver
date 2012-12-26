#!/usr/bin/python2
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

import sys,  re,  os
import time,  datetime
import pickle
import json
import difflib
import logging
from struct import unpack, pack
import gmusicapi
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import SocketServer
from threading import Thread

logger = logging.getLogger('gmusic-resolver')
hdlr = logging.FileHandler('gmusic-resolver.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.DEBUG)

MIN_AVG_SCORE = 0.9
PORT = 8082
api = gmusicapi.Api()

class getHandler(BaseHTTPRequestHandler):
  def do_GET(self):
    id = self.path[1:]
    logger.info("forwarding stream for id: %s"%id)
    global api
    try:
        url = api.get_stream_url(id)
    except:
        logger.error("URL retrieval for id %s failed"%id)
        url = ""
    self.send_response(301)
    self.send_header('Location', url)
    self.end_headers()


class ThreadingHTTPServer(SocketServer.ThreadingMixIn, HTTPServer):
    pass


def serveOnPort(port):
    server = ThreadingHTTPServer(("localhost",port), getHandler)
    logger.info("server running on port %d"%port)
    server.serve_forever()


def printJson(o):
    s = json.dumps(o)
    logger.debug("responding %s", s)
    sys.stdout.write(pack('!L', len(s)))
    sys.stdout.write(s)
    sys.stdout.flush()


def init():
    global api

    loggedIn = False
    attempts = 0

    while not loggedIn and attempts < 3:

        try:
            emailFile = open("email.txt")
            email = emailFile.readline()
        except IOError:
            logger.error("reading email.txt file failed")
            exit(0)

        try:
            pwFile = open("pass.txt")
            password = pwFile.readline()
        except IOError:
            logger.error("reading pass.txt file failed")
            exit(0)

        loggedIn = api.login(email, password)

        if not loggedIn:
            logger.error("Login failed")
            attempts += 1

    return api


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


def fieldSearch(api,  gmLibrary,  request):
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
    logger.info('Found %d tracks in %d ms'%(len(results), d.microseconds/1000 ))


def main():

    try:
        logger.info("Advertising settings")
        settings = {
                    "_msgtype": "settings",
                    "name": "google music resolver",
                    "targettime": 100, # ms
                    "weight": 80,
                    "logoUrl": "gmusic-logo.png"
                    }
        printJson(settings)

        # Log in to Google Music
        global api
        api = init()
        if not api.is_authenticated():
            logger.error( "login failed. Exiting")
            exit(0)
        logger.info("login succeeded")

        # Get all songs in the library
        gmLibrary = []
        filename = "gmLibrary.p"
        if os.path.exists(filename):
            t = os.path.getmtime(filename)
            age = time.time() - t
            logger.info("cached library age: %d seconds"%age)
            if age <= 3600:
                gmLibrary = pickle.load(open(filename) )
                logger.info("loaded library tracks from file")

        if len(gmLibrary) == 0:
            logger.info("retrieving library tracks from google")
            gmLibrary = api.get_all_songs()
            pickle.dump(gmLibrary, open(filename, "wb" ) )
        logger.info('%d tracks in library'%len(gmLibrary))

        Thread(target=serveOnPort, args=[PORT]).start()
        logger.info("server running")

        while True:
            #logger.debug("waiting for message length")
            bigEndianLength = sys.stdin.read(4)

            if len(bigEndianLength) < 4:
                logger.debug("No length given (%r==EOF?). Exiting.",
                        bigEndianLength)
                api.logout()
                exit(0)
            length = unpack("!L", bigEndianLength)[0]
            if not length or not 4096 > length > 0:
                logger.warn("invalid length: %s", length)
                break
            #logger.debug("waiting for %s more chars", length)
            msg = sys.stdin.read(length)
            request = json.loads(msg)

            if '_msgtype' not in request:
                logger.warn("malformed request (no _msgtype): %s",
                    request)
            elif request['_msgtype'] == 'rq': # Search
                if 'fulltext' in request:
                    logger.debug("not handling searches for now")
                    continue
                else:
                    fieldSearch(api,  gmLibrary,  request)
            elif request['_msgtype'] == 'config':
                logger.debug("ignoring config message: %s", request)
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
