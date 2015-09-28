#!/usr/bin/env python3.4
"""
Usage:
    hmcli.py --createdb | --setupdb | --run
    hmcli.py --test
    hmcli.py -h | --help
Options:
    -c --createdb   create and set up the db (implies --setupdb)
    -r --run        run the web server (useful for flask autoreload)
    -s --setupdb    set up the database if it has already been created
    -t --test       run some simple tests (wont work for production)
"""
from docopt import docopt
from IPython import embed

from util.dbsetup import setup_db
from tests.dbtest import test
from heatmaps.services import term_service, heatmap_service

def main():
    args = docopt(__doc__, version='heatmaps .0001')
    if args ['--run']:
        from heatmaps import webapp
        webapp.main(port=4999)
    elif args['--createdb']:
        setup_db(True)
    elif args['--setupdb']:
        setup_db()

    if args['--test']:
        test(heatmap_service)


if __name__ == '__main__':
    main()




