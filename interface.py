"""
    The web implementation for the heatmaps service
    will probably also put the order service here
"""

# TODO do we need prov for generating lists of terms from the ontology?

from flask import Flask, url_for, request, render_template, render_template_string
from IPython import embed  #FIXME

###from services import *

###
#   Templates (FIXME extract)
###
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

class Templated:
    TEMPLATE = ""
    def __init__(self, render_kwargs, render_call=render_template_string):
        self.render_kwargs = render_kwargs
        self.render_call = render_call

    def render(self):
        return self.render_call(self.TEMPLATE, **self.render_kwargs)

class Form(Templated):  # FIXME separate callbacks? nah?

    TEMPLATE = """
    <!doctype html>
    <title>{{title}}</title>
    <form method=POST enctype=multipart/form-data>
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
            for field in self.fields:
                out = field.callback()
                if out:
                    return self.render() + "<br>" + out
                    #return "Did this work?"
            return self.render()  # so that we don't accidentally return None
        else:
            for field in self.fields:
                field.callback()
                return "WUT"


###hmserv = heatmap_service(summary_service(), term_service())  # mmm nasty singletons

hmapp = Flask("heatmap service")

base_url = "http://nif-services.neuinfo.org"
base_url = "localhost:5000"
base_ext = "/servicesv1/"
hmext = base_ext + "heatmap/"

def HMID(name):
    #validate doi consider the alternative to not present the doi directly via our web interface?
    try:
        hm_id = int(request.for[name])
    #hm_data = hs.get_heatmap_data_from_id(hm_id)
    #return hs.output_csv(hm_data)
    return request.form[name]

def TERMLIST(name):
    return request.form[name]

def TERMFILE(name):
    return request.files[name]

terms_form = Form("NIF heatmaps from terms",
                    ("Heatmap ID (int)","Term list", "Term file"),
                    ('text','text','file'),
                    (HMID, TERMLIST, TERMFILE))

@hmapp.route(hmext + "terms", methods = ['GET','POST'])
def hm_terms():
    if request.method == 'POST':
        return terms_form.data_received()
    else:
        return terms_form.render()

#@hmapp.route(hmext + )



###
#   various POST/GET handlers
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
