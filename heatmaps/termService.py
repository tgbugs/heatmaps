
from scigraph_client import Graph, Vocabulary

#initiate scigraph services
graph = Graph()
vocab = Vocabulary()

class term_service():  # FURL PLS

    def __init__(self):
        self.known_curies = vocab.getCuriePrefixes()
        self.expansion_cache = {}  # TODO see if we actually need to gc this periodically
        self.curie_map = {}  # for the time being we will construct this a term at a time

    def terms_preprocessing(self, terms):

        assert type(terms[0]) == str, "terms[0] has wrong type: %s" % terms
        # TODO do we want to deal with id/term overlap? (NO)
        terms = tuple(set([TOTAL_TERM_ID]+list(terms)))  #removes dupes

        cleaned_terms = []
        bad_terms = []
        for term in terms:
            term = term.strip().rstrip().strip('"').strip().rstrip()  # insurance
            cleaned_terms.append(term)
            if ':' in term and ' ' not in term:
                if term.split(':')[0] not in self.known_curies:
                    reason = ('Colon detected in term without a space. '
                    'Please remove the colon, it will cause a parse error')
                    bad_terms.append((term, reason))
            elif '&' in term:
                reason = ('Ampresand detect in term. '
                'Please remove the ampresand, it will cause a parse error.')
                bad_terms.append((term, reason))

        return cleaned_terms, bad_terms

    def get_fragment(self, curie):
        prefix, id_ = curie.split(':')
        if prefix not in self.known_curies:
            # this should never happen: preprocessing should have caught it
            raise TypeError('curie has unknown prefix! %s' % prefix)

        iri = self.curie_map.get(prefix, None)

        if not iri:
            iri = vocab.findById(curie)['iri'].rstrip(id_)
            self.curie_map[prefix] = iri
            #iri = record['iri'].rstrip(id_)

        if iri.endswith('#'):
            return id_

        prefrag = iri.rsplit('/',1)[-1]
        return prefrag + id_

    def get_equiv_classes(self, curie):
        if curie is None:
            raise TypeError('curie is None!')
        json = graph.getNeighbors(curie, relationshipType='equivalentClass')
        if json is None:
            return (curie,), (curie,)

        syns = set()
        curies = set()

        for node in json['nodes']:
            curies.add(node['id'])
            if node['lbl'] is not None:  # sometimes it happens! :/
                syns.add(node['lbl'])
            if 'synonym' in node['meta']:
                syns.update(node['meta']['synonym'])  # FIXME lower()?

        output = tuple(sorted(curies)), tuple(syns)  # sort for crossrun const
        return output

    def pick_identifier(self, term, record_list):
        """
            give a score to each potential identifier
            return the identifiers of all equivalent classes
            of the curie with the highest score
            if there is more than one record at a given score level
            rank the subrecords and return the identifiers of all
            equivalent classes of the curie with the highest score
        """
        scores = [[], [], [], [], []]
        for record in record_list:
            label = record['labels'][0] if record['labels'] else None
            syns = record['synonyms']

            if label == None:
                continue  # DO NOT WANT
            elif term == label:
                scores[0].append(record)
            elif term.lower() == label.lower():
                scores[1].append(record)
            elif term in syns:
                scores[2].append(record)
            elif term.lower() in [s.lower() for s in syns]:
                scores[3].append(record)
            else:
                continue

        # equivalent class assertions check?

        record = None
        for score, records in enumerate(scores):
            if records:
                print('record found at score', score)
                if len(records) == 1:
                    record = records[0]
                    if record['curie'] is not None:
                        curie = record['curie']
                        new_cs, new_syns = self.get_equiv_classes(curie)
                        return new_cs, new_syns, (curie, record['labels'][0] if record['labels'] else None)
                else:  # CURIE preference ordering if there are multiples at the same lvl
                    # cscore will be by max number of matching equiv curies (min is 1)
                    # that is 1 then we fail over to total equiv curies
                    # then number of syns
                    # all else fails we go alpha on the curie
                    curies = [r['curie'] for r in records]
                    #"""
                    # careful with curies that are None, need to fix that in nifstd :/
                    curies_labels = [t for t in sorted([(r['curie'], r['labels'][0])
                                                        for r in records if r['curie'] is not None])]
                    bad_symbols = ('/','#')
                    i = 0
                    stop = len(curies_labels)
                    while i < stop:
                        for symbol in bad_symbols:
                            if symbol in curies_labels[i][0]:
                                curies_labels.append(curies_labels.pop(i))
                                stop -= 1
                                break  # inner break
                        i += 1

                    """  # if you need this code you are probably missing a curie somewhere
                    for r in records:
                        c = r['curie']
                        l = r['labels'][0]
                        if c is None or l is None:
                            embed()

                    curies_labels = [t for t in sorted([(r['curie'] if r['curie'] else '###### WTF M8',
                                                         r['labels'][0] if r['labels'][0] else '###### WTF M8') for r in records])]
                    #"""
                    output_curies = None
                    output_syns = None
                    oc = None
                    ol = None

                    s_total_match = 0
                    s_total_equiv = 0
                    s_total_syns = 0
                    for c, l in curies_labels:
                        new_cs, new_syns = self.get_equiv_classes(c)
                        if new_cs == curies:  # they're all equivalent classes
                            oc, ol = c, l
                            print('ALL SYNONYMS CASE')
                            return new_cs, new_syns, (oc, ol)

                        match = len(set(new_cs).intersection(set(curies)))

                        if match > s_total_match:
                            output_curies = new_cs
                            output_syns = new_syns
                            oc, ol = c, l
                            s_total_match = match
                            s_total_equiv = len(new_cs)
                            s_total_syns = len(new_syns)
                        elif match == s_total_match:
                            if len(new_cs) > s_total_equiv:
                                output_curies = new_cs
                                output_syns = new_syns
                                oc, ol = c, l
                                s_total_equiv = len(new_cs)
                                s_total_syns = len(new_syns)
                            elif len(new_cs) == s_total_equiv:
                                if len(new_syns) > s_total_syns:
                                    output_curies = new_cs
                                    output_syns = new_syns
                                    oc, ol = c, l
                                    s_total_syns = len(new_syns)
                                else:
                                    pass  # already sorted alphabetically

                    return output_curies, output_syns, (oc, ol)

        return (), (term,), (None, None)  # all fail terms are own syns

    def term_id_expansion(self, putative_term):  # FIXME NOT deterministic wrt changes in scigraph
        # TODO do we need to store raw term -> id mappings?! we want to collect terms that have no hits
        # but if we just store the raw query term in the database then 
        # this approach also means that stuff can get out of sync w/ the nif results
        # we REALLY do not want to store the full expanded query (with ands etc that we use for each term
        # maybe we can return all the expansions we are going to use on the first page and then
        # have that page with an OK button to actually build the heatmap... yes... this seems good
        """
            We do all expansions here internally to keep things in sync
            the summary service should never see a raw identifier if it exists
            in scigraph.

            TODO we do need to map lists of terms to identifiers so that we can
            do sorting and clustering, need to work out how we will do this and
            when we will do this. We probably need 3 things:
            1) the term the user entered
            2) the id if it exists, None if we don't find a match
            3) the label for that id
            4) synonyms (no acronyms or abbrevs for now)

            return the exact query string to run on services
        """
        if type(putative_term) is not str:
            raise TypeError('putative term is not a string! %s' % str(putative_term))

        if putative_term in self.expansion_cache:
            return self.expansion_cache[putative_term]

        # curie or fragment
        if putative_term.split(':')[0] in self.known_curies or putative_term.split('_')[0] in self.known_curies:
            # this sucks esp hard when we have birnlex_xxxxxxx prefixed identifiers used with
            # 20 different iri prefixes :/
            if ':' not in putative_term:
                curie = putative_term.replace('_', ':')
            else:
                curie = putative_term
            record_list = vocab.findById(curie)  # assume its a curie and try
            if type(record_list) is dict:  # heh, stupid hack
                record_list = [record_list]
        else:
            curie = None
            record_list = vocab.findByTerm(putative_term)

        if record_list:  # it is a curie
            if curie is not None:
                if len(record_list) == 1:
                    record = record_list[0]
                    curie = record['curie']
                    label = record['labels'][0] if record['labels'] else None
                    if ':' not in curie and curie != putative_term.replace('_',':'):  # matches both _ and : versions
                        raise TypeError('%s != %s' % (curie, putative_term))
                    curies, syns = self.get_equiv_classes(curie)
                else:
                    embed()
                    raise TypeError('WAT')
            else:  # we're going to treat it like a term
                curies, syns, (curie, label) = self.pick_identifier(putative_term, record_list)
        else:
            curie = None
            label = None
            syns = (putative_term,)

        # check if it is a term, a fragment, or a curie
        # try to expand terms to identifiers
        # if that fails try to expand identifiers to terms
        # guess agressively that terms with '_' in them are identifiers
        # same goes for things that look like curies

        #query = ' AND '.join(syns)
        output = putative_term, curie, label, syns
        self.expansion_cache[putative_term] = output
        return output

    def get_name(self, tid):
        # try to convert fragments into CURIE form
        tid = tid.replace('_',':')  # FIXME this will only work SOMETIMES
        if ' ' in tid or ':' not in tid:  # no space in ids & SG>1.5 requries cuires
            return None
        json_data = vocab.findById(tid)  # FIXME cache this stuff?
        return json_data['labels'][0] if json_data else None