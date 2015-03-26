#!/usr/bin/env python3
"""
    This file contains the code that:
    1) retrieves data from the summary service on a term by term basis
    2) maintains records for common terms (cache)
    3) manages the provenance for specific heatmaps that have been saved

"""

#SHOULD PROV also be handled here?
#SHOULD odering of rows and columns go here?

### THINGS THAT GO ELSEWHERE
# SCIGRAPH EXPANSION DOES NOT GO HERE
# REST API DOES NOT GO HERE


###
#   Retrieve summary per term
###

class summary_service:  #implement as a service/coro? with asyncio?


###
#   Stick the collected data in a datastore (postgres)
###
