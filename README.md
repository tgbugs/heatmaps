Python for acquiring data to make heatmaps and actually making them.

## Basic setup
0. Heatmaps has been test on python3.4, it may work on earlier versions but has not been tested.
1. Currently the only external library dependency is the postgresql development libraries (see psycopg2 docs).
2. If you want to use your package manager to handle dependencies instead of pip see the install_requires section of setup.py.

## Database setup
0. You will need a working postgres database.
1. In util/ run dbsetup.py (may require some additional setup to target the correct host) or use heatmap_db_setup.sql direcitly.
2. Set hmadmin and hmuser passwords and add them to .pgpass.
3. If you are not running postgres on localhost heatmap_service will need to be adjusted. (In the future this may go in a config)

## Building the whl file
0. From this folder run `python3 setup.py bdist_wheel`
1. From this folder run `pip --install --user dist/heatmaps*.whl` or use the exact name of the whl file.

## Running the service
0. Once you have installed the whl file run hmweb to run the service.
1. You can also use various components of the service by importing from the heatmaps module.

## matplotlibrc
In the event that there are errors when you try to view png files from the webservice:
You must set
backend : Agg
in ~/.config/matplotlib/matplotlibrc

