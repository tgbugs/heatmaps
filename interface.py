"""
    The web implementation for the heatmaps service
    will probably also put the order service here
"""

# TODO do we need prov for generating lists of terms from the ontology?

from flask import Flask, url_for, request
from IPython import embed

###from services import *

###hmserv = heatmap_service(summary_service(), term_service())  # mmm nasty singletons

hmapp = Flask("heatmap service")

base_url = "http://nif-services.neuinfo.org/"
base_ext = "/servicesv1/"
hmext = base_ext + "heatmap/"

@hmapp.route(hmext + "terms", methods = ['GET','POST'])
def heatmap():
    if request.method == 'POST':
        return terms_POST()
    else:
        return terms_GET()

#@hmapp.route(hmext + )



###
#   various POST/GET handlers
##

def terms_POST():
    print(request)
    term_file = request.files['term_file']
    term_list = request.form['term_list']
    if term_file:
        terms = file_to_terms(term_file)
        return repr(terms)
    elif term_list:
        print(term_list)
        return repr(term_list)
    else:
        return None
    ###hm_data, fails = hmserv.get_term_counts(*terms)
    ###return repr(hm_data) + "\n\n" + str(fails)
    #return repr(terms)


#@hmapp.route('/')
def terms_GET():
    form = """
    <form method=POST enctype=multipart/form-data action="terms">
        Term list:<br>
        <input type=text name=term_list>
        <br>
        Term file:<br>
        <input type=file name=term_file>
        <br>
        <input type=submit value=Submit>
    </form>
    """
    #url = url_for(hmext + 'terms')  #FIXME
    #return "Paste in a list of terms or select a terms file"
    return form #% url


###
#   Utility funcs that will be moved elsewhere eventually
##

def file_to_terms(file):  # TODO
    # detect the separator
    # split
    # sanitize
    return "brain"

def do_sep(string):
    return string

#please login to get a doi? implementing this with an auth cookie? how do?

def main():
    hmapp.debug = True
    hmapp.run()

if __name__ == '__main__':
    main()
