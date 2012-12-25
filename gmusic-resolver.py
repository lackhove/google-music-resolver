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

import sys
import re
#import os
import json
import difflib
import logging
from struct import unpack, pack
import gmusicapi

logger = logging.getLogger('gmusic-resolver')
hdlr = logging.FileHandler('gmusic-resolver.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.DEBUG)


def printJson(o):
    s = json.dumps(o)
    logger.debug("responding %s", s)
    sys.stdout.write(pack('!L', len(s)))
    sys.stdout.write(s)
    sys.stdout.flush()


def init():
    api = gmusicapi.Api()

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

        if not loggedIn:
            logger.error("Login failed")
            attempts += 1

        loggedIn = api.login(email, password)

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
    results = []
    seqMatchArtist = difflib.SequenceMatcher(None, "foobar", simplify( request["artist"] ))
    seqMatchTitle = difflib.SequenceMatcher(None, "foobar", simplify( request["track"] ))
    for candidate in gmLibrary:
        seqMatchArtist.set_seq1( simplify( candidate["artist"] ) )
        seqMatchTitle.set_seq1( simplify( candidate["title"] ) )
        scoreArtist = seqMatchArtist.quick_ratio()
        scoreTitle = seqMatchTitle.quick_ratio()
        score = (scoreArtist + scoreTitle) /2
        if score >= 0.8:
            logger.debug("Found: %s - %s : %s - %s : %f,%f,%s"%(request["artist"],  request["track"], candidate["artist"], candidate["title"], scoreArtist, scoreTitle, score))
            url = api.get_stream_url(candidate["id"])
            result = {
                "artist": candidate["artist"],
                "track": candidate["title"],
                "album":  candidate["album"],
                "score":1,
                "url": url
                }
            results.append( result )

    logger.info('Found %d tracks in %d candidates'%(len(results),  len(gmLibrary)))
    response = {
            'qid': request['qid'],
            'results': results,
            '_msgtype': 'results'
        }
    printJson(response)


def main():

    try:
        logger.info("Advertising settings")
        settings = {
                    "_msgtype": "settings",
                    "name": "google music resolver",
                    "targettime": 100, # ms
                    "weight": 80
                    }
        printJson(settings)

        # Log in to Google Music
        api = init()
        if not api.is_authenticated():
            logger.error( "login failed. Exiting")
            exit(0)
        logger.info("login succeeded")

        # Get all songs in the library
        logger.info("retrieving library tracks")
        #gmLibrary = api.get_all_songs()
        import pickle
        #pickle.dump(gmLibrary, open( "gmLibrary.p", "wb" ) )
        gmLibrary = pickle.load( open( "gmLibrary.p", "rb" ) )
        logger.info('%d tracks in library'%len(gmLibrary))

        while True:
            logger.debug("waiting for message length")
            bigEndianLength = sys.stdin.read(4)

            if len(bigEndianLength) < 4:
                logger.debug("No length given (%r==EOF?). Exiting.",
                        bigEndianLength)
                exit(0)
            length = unpack("!L", bigEndianLength)[0]
            if not length or not 4096 > length > 0:
                logger.warn("invalid length: %s", length)
                break
            logger.debug("waiting for %s more chars", length)
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
                exit(0)
            else:
                logger.warn("unknown request: %s", request)

    except Exception:
        logger.exception("something went wrong")
        raise


if __name__ == "__main__":
    main()
