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

import gzip
from os import environ
from flask import Flask, url_for, redirect, request, render_template, render_template_string, make_response, abort

if environ.get('HEATMAP_PROD',None):
    embed = lambda args: print("THIS IS PRODUCTION AND PRODUCTION DOESNT LIKE IPYTHON ;_;")
else:
    from IPython import embed  #FIXME

from .services import heatmap_service, summary_service

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
                        #return 'Your submisison is processing, your number is # \n' + out
                        return out
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

class Select(Templated):
    TEMPLATE = """    <label>{{select_name}}</label>
    <select id="{{select_name}}" name="{{select_name}}" number=30>
    {% for opt, opt_val in options %}   <option value="{{opt}}">{{opt_val}}</option>
    {% endfor %}</select>"""

    def __init__(self, name, options, opt_val=None, onclick=''):
        self.name = name
        if opt_val:
            options = [(a, b) for a, b in zip(options, opt_val)]
        else:
            options = [(a, b) for a, b in zip(options, options)]

        if onclick:
            onclick = ' onclick="%s"' % onclick

        render_kwargs = dict(select_name=name, options=options)
        super().__init__(render_kwargs)


hmserv = heatmap_service(summary_service())  # mmm nasty singletons

hmapp = Flask("heatmap service")


#base_ext = "/servicesv1/v1/heatmaps/"
#hmext = base_ext + "heatmap/"

ext_path = "/servicesv1/v1/heatmaps"



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

def TERMFILE(name):  # TODO fuzz me!  #FIXME blank lines cause 500 errors!
    # identify sep
    # split
    # pass into make_heatmap_data
    # return csv and id
    try:
        file = request.files[name]
        print('TERMFILE type', file)
        terms = [l.rstrip().decode() for l in file.stream.readlines() if l]
        filename = file.filename
        return do_terms(terms, filename)
    except KeyError:
        raise

def do_terms(terms, filename=None):
    # FIXME FIXME this is NOT were we should be doing data sanitizaiton :/
    if not terms:
        print('no terms!')
        return None

    cleaned_terms, bad_terms = hmserv.term_server.terms_preprocessing(terms)  # FIXME :/
    if bad_terms:
        return 'Bad terms detected! Please fix and resubmit!<br>' + repr(bad_terms)

    if len(cleaned_terms) <= hmserv.TERM_MIN:  # FIXME I'm not happy w/ having this code here
        return hmserv.make_heatmap_data(cleaned_terms, None, filename)

    job_id = hmserv.submit_heatmap_job(cleaned_terms, filename)  # FIXME will increment even when the jobid resolves to an old jobid!

    javascript = (''
                  '')

    base_url = 'http://' + request.host + ext_path
    job_url = base_url + '/terms/jobs/' + str(job_id)
    output = ('Your list of terms has been submitted, your job is currently '
              'processing and you will be notified when it completes. '
              'Your job_id is {JOBID}. You when your job is done the url below will '
              'redirect to your heatmap.<br>'
              '<a href={JOBURL}>{JOBURL}</a>').format(JOBID=job_id, JOBURL=job_url)

    return output

    hm_data, hp_id, timestamp = hmserv.make_heatmap_data(cleaned_terms, filename)
    if hp_id == None:  # no id means we'll give the data but not store it (for now :/)
        return repr((timestamp, hm_data))  # FIXME this is a nasty hack to pass error msg out
    #return repr((hm_data, hp_id, timestamp))
    output = """
            <!doctype html>
            <title>Submit</title>
            When your job is finished your heatmap can be downloaded as
            a png, a csv, a tsv, an html table, or as a json file at:
            <br><br>
            <a href={url}.csv>{url}.csv</a>
            <br>
            <a href={url}.tsv>{url}.tsv</a>
            <br>
            <a href={url}.html>{url}.html</a>
            <br>
            <a href={url}.json>{url}.json</a>
            <br>
            <a href={url}.png>{url}.png</a>
            <br><br>
            You can also explore your heatmap data here: <br>
            <a href={exp_url}>{exp_url}</a>
            <br><br>
            If you ever need to download your heatmap again you can get it again
            as long as you know your heatmap id which is {id}.
            """.format(url=base_url + '/prov/' + str(hp_id), id=hp_id, exp_url=base_url + '/explore/' + str(hp_id))
    return output

def data_from_id(hm_id, filetype, collTerms=None, collSources=None,
                 sortTerms=None, sortSources=None,
                 idSortTerms=None, idSortSources=None,
                 ascTerms=True, ascSources=True):
    hm_id = int(hm_id)

    print('RUNNING:')
    print(hm_id, filetype, sortTerms, sortSources, collTerms, collSources, idSortTerms, idSortSources, ascTerms, ascSources)
    data, filename, mimetype = hmserv.output(hm_id, filetype, sortTerms, sortSources, collTerms, collSources, idSortTerms, idSortSources, ascTerms, ascSources)
    if data:
        if filetype == 'csv':
            attachment = 'attachment; '
        else:
            attachment = ''
        response = make_response(data)
        response.headers['Content-Disposition'] = '%sfilename = %s' % (attachment, filename)
        response.mimetype = mimetype
        #response.mimetype = 'text/plain'
        return response
    else:
        return abort(404)

def data_validation(field, value):
    """ The values entered via a <select> should always match their source.
        Since users could edit the html we have to make sure that they arent
        giving us garbage.
    """


###
#   Form creation
###

terms_form = Form("NIF heatmaps from terms",
                    ("Term list (comma separated)", "Term file (newline separated)"),  #TODO select!
                    ('text','file'),
                    (TERMLIST, TERMFILE))

###
#   Routes and implementations
###

@hmapp.route(ext_path + "/explore/submit/<hm_id>", methods = ['POST'])
def hm_viz(hm_id):
    sortTerms = request.form['sortTerms']
    if sortTerms in hmserv.sort_other:
        idSortTerms = request.form['idSortTerms']
    elif sortTerms in hmserv.sort_same:
        idSortTerms = request.form['idRefTerms']
    else:
        idSortTerms = None

    sortSources = request.form['sortSources']
    if sortSources in hmserv.sort_other:
        idSortSources = request.form['idSortSources']
    elif sortSources in hmserv.sort_same:
        idSortSources = request.form['idRefSources']
    else:
        idSortSources = None

    if False: # requests.form['sortType'] == 'double':
        sortTerms = request.form['sortTerms']
        if sortTerms in hmserv.sort_other:
            idSortTerms = request.form['idSortTerms']
        elif sortTerms in hmserv.sort_same:
            idSortTerms = request.form['idRefTerms']
        else:
            idSortTerms = None

        sortSources = request.form['sortSources']
        if sortSources in hmserv.sort_other:
            idSortSources = request.form['idSortSources']
        elif sortSources in hmserv.sort_same:
            idSortSources = request.form['idRefSources']
        else:
            idSortSources = None

    args = (hm_id,
            request.form['filetypes'],
            request.form['collTerms'],
            request.form['collSources'],
            sortTerms,
            sortSources,
            idSortTerms,
            idSortSources,
            request.form['ascTerms'],
            request.form['ascSources'])

    #input cleanup (ick)
    new_args = []
    for arg in args:
        if arg == 'None':
            new_args.append(None)
        elif arg == 'True':
            new_args.append(True)
        elif arg == 'False':
            new_args.append(False)
        else:
            new_args.append(arg)

    data = data_from_id(*new_args)
    return data

@hmapp.route(ext_path + "/explore/<hm_id>", methods = ['GET'])
def hm_explore(hm_id):
    try:
        hm_id = int(hm_id)
    except ValueError:
        return abort(404)

    explore_fields, select_mapping = hmserv.explore(hm_id)
    if explore_fields is None:
        return abort(404)

    for name, args in select_mapping.items():
        explore_fields[name] = Select(name, *args).render()

    js0 = """    <script>
    window.onload = function (){jso}
    document.getElementById("sortTerms").addEventListener("change", showTerms, false)
    document.getElementById("sortSources").addEventListener("change", showSources, false)
    document.getElementById("sortTerms2").addEventListener("change", showTerms2, false)
    document.getElementById("sortSources2").addEventListener("change", showSources2, false)
    {jsc}
    </script>"""
    js1 = """    <script>
    var idSort = {idSortOps};
    var idRef = {idRefOps};

    var style_any = document.getElementById("{anysort}").style
    var style_iss = document.getElementById("{iss}").style
    var style_irs = document.getElementById("{irs}").style
    var style_ist = document.getElementById("{ist}").style
    var style_irt = document.getElementById("{irt}").style

    function showTerms(){jso}
        if (idSort.indexOf(this.value) > -1){jso}
            style_any["display"] = ""
            style_ist["display"] = ""
            style_irt["display"] = "none"
        {jsc}
        else if (idRef.indexOf(this.value) > -1){jso}
            style_any["display"] = ""
            style_ist["display"] = "none"
            style_irt["display"] = ""
        {jsc}
        else {jso}
            style_ist["display"] = "none"
            style_irt["display"] = "none"
            if (style_iss["display"] == "none" && style_irs["display"] == "none"){jso}
                style_any["display"] = "none"
            {jsc}
        {jsc}
    {jsc}

    function showSources(){jso}
        if (idSort.indexOf(this.value) > -1){jso}
            style_any["display"] = ""
            style_iss["display"] = ""
            style_irs["display"] = "none"
        {jsc}
        else if (idRef.indexOf(this.value) > -1){jso}
            style_any["display"] = ""
            style_iss["display"] = "none"
            style_irs["display"] = ""
        {jsc}
        else {jso}
            style_iss["display"] = "none"
            style_irs["display"] = "none"
            if (style_ist["display"] == "none" && style_irt["display"] == "none"){jso}
                style_any["display"] = "none"
            {jsc}
        {jsc}
    {jsc}
    </script>"""

    rep = ['anysort', '_any', '_iss', '_irs', '_ist', '_irt', '{iss', '{irs', '{ist', '{irt', 'showTerms', 'showSources', 'var idSort', 'var idRef']
    js2 = js1
    for name in rep:
        js2 = js2.replace(name, name + '2')

    base = '\n'.join((
        '<!doctype html>',  # FIXME ICK
        '<title>NIF Heatmap {hm_id} exploration</title>',
        '<h1>Explore heatmap {hm_id}</h1>'
        '<h2>Created on: {date} at {time}</h2>',
        '<h2>Filename: {filename}</h2>',
        '<h3>Number of terms: {num_terms}</h3>',
        '<h3>Terms found in ontology: {num_matches}</h3>',
        '<br><br>',
        '<h2>Download configuration:</h2>',
        '<form action=submit/{hm_id} method=POST enctype=multipart/form-data target="_blank">',
            '<h3>Collapse options:</h3>',
            '{collTerms}',
            '{collSources} <br>',
            '<h3>Sorting Options:</h3>',
            '{sortTypeTerms}',
            '{sortTypeSrcs} <br>',

            '<h4>Primary sort:</h4>',
            '{sortTerms}',
            '{sortSources} <br>',

            '<div id={anysort} style="display:none;">',  # FIXME may want to default away from display:none and add it if we have js?
            '<h4>Reference value or identifier to sort against:</h4>',
                '<div id={ist} style="display:none;">',
                '{idSortTerms}',
                '</div>',
                '<div id={irt} style="display:none;">',
                '{idRefTerms}',
                '</div>',
                '<br>',
                '<div id={iss} style="display:none;">',
                '{idSortSources}',
                '</div>',
                '<div id={irs} style="display:none;">',
                '{idRefSources}',
                '</div>',
                '<br>',
            '</div>',

            '<div id={secondSort} style="display:none;">',  # FIXME may want to default away from display:none and add it if we have js?
            '<h4>Secondary sort:</h4>',
            '{sortTerms2}',
            '{sortSources2} <br>',
            '</div>',

            '<div id={anysort2} style="display:none;">',  # FIXME may want to default away from display:none and add it if we have js?
            '<h4>Second reference value or identifier to sort against:</h4>',
                '<div id={ist2} style="display:none;">',
                '{idSortTerms2}',
                '</div>',
                '<div id={irt2} style="display:none;">',
                '{idRefTerms2}',
                '</div>',
                '<br>',
                '<div id={iss2} style="display:none;">',
                '{idSortSources2}',
                '</div>',
                '<div id={irs2} style="display:none;">',
                '{idRefSources2}',
                '</div>',
                '<br>',
            '</div>',

            '<h3>Ascending:</h3>',
            '{ascTerms}',
            '{ascSources} <br>',
            '<h3>Filetype:</h3>',
            '{filetypes} <br><br>',
            '<input type=submit value=Generate>',
        '</form>',
        '<br><br>',
        '<h3>Expansion: putative term, curie, label, query</h3>',
        '<pre>\n{expansion}\n</pre>',
        js0, js1, js2))

    page = base.format(jso='{', jsc='}', **explore_fields)  # python format is stupid

    out = make_response(gzip.compress(page.encode()))
    out.headers['Content-Encoding'] = 'gzip'
    return out


#@hmapp.route(hmext + "terms", methods = ['GET','POST'])
@hmapp.route(ext_path + "/terms", methods = ['GET'])
def hm_terms():
    #if request.method == 'POST':
        #return terms_form.data_received()
    #else:
    page = terms_form.render()
    page += """<br>
    Submit a comma separated list of terms or a newline separated file of terms. <br>
    If both are provided the comma separated list will be preferred. <br>
    Building heatmaps can take a long time. Once you hit submit you may have to wait <br>
    as long as 30 minutes (if you have thousands of terms) for your heatmap to finish. <br>
    If you submit %s or less terms the heatmap will not be saved.
    """ % hmserv.TERM_MIN
    return page

@hmapp.route(ext_path + "/terms/submit", methods = ['GET', 'POST'])
def hm_submit():
    if request.method == 'POST':
        # TODO need WAY more here
        # specifically we need to return a "job submitted" page
        # that will have js and do a long poll that will update the
        # page to tell users that their job is done
        # this will require reworking when we put things into the database
        # and possibly the schema :/
        if request.json is not None:
            data = request.json
            if {'terms','filename'} != set(data):
                return abort(400)
            else:
                #print(data['terms'], data['filename'])
                #return 'COOKIES'
                return do_terms(data['terms'], data['filename'])  # THAT WAS EASY
        else:
            return terms_form.data_received()
    else:
        return "Nothing submited FIXME need to keep session alive??!"

@hmapp.route(ext_path + "/terms/jobs/<job_id>", methods = ['GET', 'POST'])
def hm_jobs(job_id):
    # GET should redirect to the finished heatmap OR start the polling process if the job has been submitted but not finished
    try:
        job_id = int(job_id)
    except ValueError:
        return abort(404)

    try:
        hm_id = hmserv.get_job(job_id)
    except KeyError:  # no job with that id...
        return abort(404)

    if request.method == 'POST':
        return str(hm_id) if hm_id else '0'  # to talk to the javascript... and redraw the page with the 'jobs done'
    elif request.method == 'GET':
        if hm_id is None:
            # TODO
            return abort(404)
        return redirect(ext_path + '/explore/%s' % hm_id)

@hmapp.route(ext_path + "/prov/<hm_id>", methods = ['GET'])
@hmapp.route(ext_path + "/prov/<hm_id>.<filetype>", methods = ['GET'])
def hm_getfile(hm_id, filetype=None):
    try:
        hm_id = int(hm_id)
        if filetype in hmserv.supported_filetypes:
            return data_from_id(hm_id, filetype)
        else:
            return abort(404)
    except ValueError:
        return abort(404)
    

#@hmapp.route(hmext + )

@hmapp.route(ext_path + '/', methods = ['GET'])
@hmapp.route(ext_path, methods = ['GET'])
def overview():
    base_url = 'http://' + request.host + ext_path
    page = """
    <!doctype html>
    <title>NIF Heatmaps</title>
    <h1>NIF heatmaps services </h1>
    Submit lists of terms and download overviews of the entireity of the NIF data federation.<br>
    Use the form found <a href={terms_url}>here</a> to submit lists of terms or
    you can use the<br>REST api described in the documentation. <br>
    Documentation can be found here: <br>
    <a href={docs_url}>{docs_url}</a>
    """.format(docs_url=base_url + '/docs', terms_url=base_url + '/terms')
    return page

@hmapp.route(ext_path + '/docs', methods = ['GET'])
@hmapp.route(ext_path + '/docs/', methods = ['GET'])
def docs():
    sort_docs = '<br><br>'.join(sorted([' '.join(('<b>' +k + '</b>', v)) for k, v in hmserv.sort_docs.items()]))
    base_url = 'http://' + request.host
    page = """
    <!doctype html>
    <title>NIF Heatmaps Documentation</title>
    <h1>NIF heatmaps documentation</h1>
    To view an existing heatmap append the heatmapid to the following url: <br>
    <a href={prov_url}>{prov_url}</a><br>
    Currently supported filetypes are csv, tsv, html, json, and png. <br>
    Example: <a href={prov_url}0.png>{prov_url}0.png</a> (note that this heatmap doesn't actually exist) <br>
    <br>
    To explore an existing heatmap append the heatmapid to the following url: <br>
    <a href={explore_url}>{explore_url}</a><br>
    Example: <a href={explore_url}0>{explore_url}0</a>
    <h2>Legend</h2>
    Bins for numbers are 0, 1-10, 11-100, >100
    <h2>Sorting options</h2>
    {sort_docs}
    """.format(prov_url=base_url + ext_path + '/prov/',
               explore_url=base_url + ext_path + '/explore/',
               sort_docs=sort_docs)
    return page


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
    hm_data, fails = hmserv.get_term_counts(terms)
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

def main(port=5000):
    try:
        if environ.get('HEATMAP_PROD',None):
            hmapp.debug = False
            hmapp.run(host='0.0.0.0', threaded=True)  # 0.0.0.0 tells flask to listen externally
        else:
            hmapp.debug = True
            hmapp.run(host='127.0.0.1', port=port, threaded=True)
    finally:
        print('closing database connection')
        hmserv.conn.close()


if __name__ == '__main__':
    main()
