Google-Music-Resolver
=====================

A resolver for the [Tomahawk](http://www.tomahawk-player.org/) music player, based on Simon Weber's [Unofficial Google Music API](https://github.com/simon-weber/Unofficial-Google-Music-API).

The resolver is under heavy develpoment and might crash, corrupt your data or even eat your hamster. Use at your own risk!

Please report bugs, wishes and issues [here](https://github.com/crabmanX/google-music-resolver/issues/new).

##Usage

###Installation

Requirements:

* Unofficial Google Music API [Unofficial Google Music API](https://github.com/simon-weber/Unofficial-Google-Music-API)
* [keyring](http://pypi.python.org/pypi/keyring)
* Python 2.7 or 3.3 (other versions might work, but are untested
* [Tomahawk](http://www.tomahawk-player.org/)

You can use [pip](http://www.pip-installer.org/en/latest/) to automatically install all dependencies and google-music-resolver

```
pip install https://github.com/crabmanX/google-music-resolver/tarball/master
```

###Getting Started

Start Tomahawk, open setting, go to "Resolvers", click "add from file" and choose the
`gmusic-resolver.py` script (on linux systems `/usr/bin/gmusic-resolver.py`). Notice the
hypen, not an underscore!

If a little wrench appears on the right hand side at the bottom of the list, the resolver is running.
Click the wrench, enter your credentials and hit OK. Your password is stored in your operating systems
password storage, which might ask for permission now. On every start, the resolver fetches your library
information which may take a few seconds before its ready to resolve.

Tomahawk does not provide a way to tell if the login was succesful or not. Check the logfile under
`~/.local/share/Tomahawk/gmusic-resolver.log` for warnings and errors in case it doesnt work correctly.



- - -

Copyright 2013 Kilian Lackhove <Kilian.Lackhove@gmail.com>.


Licensed under the GPLv2. See LICENSE.txt

