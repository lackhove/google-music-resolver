from setuptools import *

setup(
    name = 'gmusic-resolver',
    version = '0.1dev',
    description = 'Tomahawk resolver for Google Music',
    author = 'Kilian Lackhove',
    author_email = 'kilian.lackhove@gmail.com',
    license = 'GPLv2',
    url = 'https://github.com/crabmanX/google-music-resolver',
    packages = find_packages(),
    package_data = {'': ['*.ui', '*.png']},
    entry_points = {'console_scripts': ['gmusic-resolver = gmusic_resolver.gmusic_resolver:main']},
    install_requires=[
        "gmusicapi>= 1.0.0",
        "keyring >= 0.10"],
    zip_safe = False,
)
