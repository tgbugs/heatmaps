#!/usr/bin/env python3.4
"""
Usage:
    hmcli.py --createdb | --setupdb
    hmcli.py --test
    hmcli.py -h | --help
Options:
    -c --createdb   create and set up the db (implies --setupdb)
    -s --setupdb    set up the database if it has already been created
    -t --test       run some simple tests (wont work for production)
"""
from docopt import docopt
from IPython import embed

from dbsetup import setup_db
from dbtest import test
from services import term_service, ontology_service, heatmap_service

def main():
    args = docopt(__doc__, version='heatmaps .0001')
    if args['--createdb']:
        setup_db(True)
    elif args['--setupdb']:
        setup_db()

    if args['--test']:
        test(heatmap_service)


if __name__ == '__main__':
    main()




