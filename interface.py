#!/usr/bin/env python3
"""
    The web implementation for the heatmaps service
    will probably also put the order service here
"""

# TODO do we need prov for generating lists of terms from the ontology?

# TODO: need to clear heatmap id and add a message on download!
# need to add a "collecting data" message for large queries
# need to add datetime and heatmap prov id to the csv download
# need to make the title of the csv nice
# neet to develop a series of tests designed to wreck the text input box

from os import environ
from flask import Flask, url_for, request, render_template, render_template_string, make_response, abort

if environ.get('HEATMAP_PROD',None):
    embed = lambda args: print("THIS IS PRODUCTION AND PRODUCTION DOESNT LIKE IPYTHON ;_;")
else:
    from IPython import embed  #FIXME

from services import heatmap_service, summary_service, term_service

###
#   Templates (FIXME extract)
###

class Templated:
    TEMPLATE = ""
    def __init__(self, render_kwargs, render_call=render_template_string):
        self.render_kwargs = render_kwargs
        self.render_call = render_call

    def render(self):
        return self.render_call(self.TEMPLATE, **self.render_kwargs)

class FormField:
    def __init__(self, title, type_, callback):
        self.title = title
        self.type = type_
        self.name = title.lower().replace(' ','_')  #FIXME
        self._callback = callback

    def callback(self):
        return self._callback(self.name)

    @staticmethod
    def factory(titles, types, callbacks):
        """ form field factory """
        return [FormField(title, type_, callback) for title, type_, callback in zip(titles, types, callbacks)]

    def __repr__(self):
        return "<FormField %s %s>" % (str(self.type), str(self.title)) 

class Form(Templated):  # FIXME separate callbacks? nah?

    TEMPLATE = """
    <!doctype html>
    <title>{{title}}</title>
    <form action=terms/submit method=POST enctype=multipart/form-data>
        {% for field in fields %}
            {{field.title}}: <br>
            <input type={{field.type}} name={{field.name}}> <br>
        {% endfor %}
        <input type=submit value=Submit>
    </form>
    """

    def __init__(self, title, titles, types, callbacks, exit_on_success=True):
        #action_url = base_url + route
        self.title = title
        self.fields = FormField.factory(titles, types, callbacks)
        render_kwargs = dict(title=self.title, fields=self.fields)#, action_url=action_url)
        super().__init__(render_kwargs)
        self.exit_on_success = exit_on_success  # single field forms mutex

    def data_received(self):
        if self.exit_on_success:
            print('dr', self.fields)
            for field in self.fields:
                out = field.callback()
                print(field, 'data_received', out)
                if out:
                    if type(out) == str:  #FIXME all callbacks need to return a response object or nothing
                        return 'Your submisison is processing, your number is # \n' + out
                        return self.render() + "<br>" + out  # rerender the original form but add the output of the callback
                    else:
                        return out
                    #return "Did this work?"
            return "You didnt submit anything... go back and try again!"
            return self.render()  # so that we don't accidentally return None
        else:
            for field in self.fields:
                field.callback()
                return "WUT"


hmserv = heatmap_service(summary_service(), term_service())  # mmm nasty singletons

hmapp = Flask("heatmap service")

#base_url = "localhost:5000"
#base_url = "http://nif-services.neuinfo.org:5000"

#base_ext = "/servicesv1/v1/heatmaps/"
#hmext = base_ext + "heatmap/"

if environ.get('HEATMAP_PROD',None):  # set in heatmaps.wsgi if not globally
    host = "http://nif-services.neuinfo.org"
else:
    host = "http://localhost:5000"

ext_path = "/servicesv1/v1/heatmaps"

base_url = ext_path


def HMID(name):
    #validate doi consider the alternative to not present the doi directly via our web interface?
    try:
        hm_id = int(request.form[name])
    except ValueError:  # FIXME error handling should NOT be written in here?
        return None
    except:
        raise
    return csv_from_id(hm_id)

def TERMLIST(name):  # TODO fuzz me!  FIXME "!" causes the summary service to crash!
    # identify separator  # this is hard, go with commas I think we must
    # split
    # pass into make_heatmap_data
    # return csv and id
    data = request.form[name]
    if not data:  # term list is empty
        return None
    terms = [t.strip().rstrip() for t in data.split(',')]  # FIXME chemical names :/
    return do_terms(terms)

def TERMFILE(name):  # TODO fuzz me!
    # identify sep
    # split
    # pass into make_heatmap_data
    # return csv and id
    try:
        file = request.files[name]
        print('TERMFILE type', file)
        terms = [ l.rstrip().decode() for l in file.stream.readlines() ]
        return do_terms(terms)
    except KeyError:
        raise

def do_terms(terms):
    # FIXME FIXME this is NOT were we should be doing data sanitizaiton :/
    if not terms:
        print('no terms!')
        return None
    hm_data, hp_id, timestamp = hmserv.make_heatmap_data(*terms)
    if hp_id == None:  # no id means we'll give the data but not store it (for now :/)
        return repr((timestamp, hm_data))  # FIXME this is a nasty hack to pass error msg out
    return repr((hm_data, hp_id, timestamp))

def csv_from_id(hm_id):
    hm_id = int(hm_id)
    hm_data = hmserv.get_heatmap_data_from_id(hm_id)
    timestamp = hmserv.get_timestamp_from_id(hm_id)
    if hm_data:
        out = hmserv.output_csv(hm_data, sorted(hm_data), sorted(hmserv.resources))
        response = make_response(out)  #FIXME get ur types straight
        response.headers['Content-Disposition'] = "attachment; filename = nif_heatmap_%s_%s.csv" % (hm_id, timestamp)
        response.mimetype = 'text/csv'
        return response
    else:
        return abort(404)
        #return "No heatmap with id %s." % hm_id  #FIXME TYPES!!!
    #return request.form[name]

terms_form = Form("NIF heatmaps from terms",
                    ("Heatmap ID (int)","Term list (comma separated)", "Term file (newline separated)"),  #TODO select!
                    ('text','text','file'),
                    (HMID, TERMLIST, TERMFILE))

#@hmapp.route(hmext + "terms", methods = ['GET','POST'])
@hmapp.route(base_url + "/terms", methods = ['GET','POST'])
def hm_terms():
    if request.method == 'POST':
        return terms_form.data_received()
    else:
        return terms_form.render()

@hmapp.route(base_url + "/terms/submit", methods = ['GET', 'POST'])
def hm_submit():
    if request.method == 'POST':
        return terms_form.data_received()
    else:
        return "Nothing submited FIXME need to keep session alive??!"
    
@hmapp.route(base_url + "/prov/<hm_id>", methods = ['GET'])
def hm_getfile(hm_id):
    try:
        hm_id = int(hm_id)
        return csv_from_id(hm_id)
    except ValueError:
        return abort(404)
        #return 'Invalid heatmap identifier "%s", please enter an integer.' % hm_id, 404
        #return None, 404
    

#@hmapp.route(hmext + )



###
#   various POST/GET handlers  XXX NOT BEING USED
##



def terms_POST():
    print(request)
    for field in term_fields:
        data = field.get()
        if data:
            if field.type == 'text':
                terms = file_to_terms(data)
            elif field.type == 'file':
                terms = file_to_terms(data)


    term_file = request.files['term_file']
    term_list = request.form['term_list']
    if heatmap_doi:
        return
    elif term_file:
        terms = file_to_terms(term_file)
        return repr(terms)
    elif term_list:
        print(term_list)
        return repr(term_list)
    else:
        return None
    hm_data, fails = hmserv.get_term_counts(*terms)
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
#   Utility funcs that will be moved elsewhere eventually  XXX NOT BEING USED
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
