"""
    The web implementation for the heatmaps service
    will probably also put the order service here
"""

# TODO do we need prov for generating lists of terms from the ontology?

from flask import Flask, url_for

from services import *

hmserv = heatmap_service(summary_service(), term_service())  # mmm nasty singletons

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
    terms = file_to_terms(term_file)
    hm_data, fails = hmserv.get_term_counts(*terms)
    return repr(hm_data) + "\n\n" + str(fails)

def terms_GET():
    form = """
    <form method=POST enctype=multipart/form-data action="{{ url_for('terms') }}">
        Term list:<br>
        <input type=text name=term_list>
        <br>
        Term file:<br>
        <input type=file name=term_file>
        <br>
        <input type=submit value=Submit>
    </form>
    """
    return "Paste in a list of terms or select a terms file"


###
#   Utility funcs that will be moved elsewhere eventually
##

def file_to_terms(file):  # TODO
    # detect the separator
    # split
    # sanitize
    return "brain"

#please login to get a doi? implementing this with an auth cookie? how do?

def main():
    hmapp.run()

if __name__ == '__main__':
    main()
