import os
from typing import (
    List,
    Mapping,
    Union,
)

# See https://flask.palletsprojects.com/en/1.1.x/
from flask import (
    current_app, g, url_for
)
# See http://rdflib.readthedocs.io/
import rdflib
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS, RDF

UNO = Namespace('http://vocabularies.unesco.org/ontology#')


class Thesaurus(Graph):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        subjects_file = os.path.join(
            os.path.dirname(current_app.config['MAIN_DATABASE_PATH']),
            'subject_terms.ttl')
        if os.path.isfile(subjects_file):
            self.parse(subjects_file, format='turtle')
        else:
            tmp = Graph()
            tmp.parse(r'http://vocabularies.unesco.org/browser/rest/v1/'
                      'thesaurus/data?format=text/turtle', format='turtle')
            self.bind('uno', 'http://vocabularies.unesco.org/ontology#')

            self += tmp.triples((None, SKOS.prefLabel, None))
            self += tmp.triples((None, RDF.type, SKOS.Concept))
            self += tmp.triples((None, RDF.type, UNO.MicroThesaurus))
            self += tmp.triples((None, RDF.type, UNO.Domain))
            self += tmp.triples((None, SKOS.broader, None))
            self += tmp.triples((None, SKOS.narrower, None))
            for s, p, o in tmp.triples((None, SKOS.member, None)):
                if (o, RDF.type, SKOS.Concept) in tmp and (
                        o, SKOS.topConceptOf, URIRef(
                            'http://vocabularies.unesco.org/thesaurus')
                        ) not in tmp:
                    continue
                self.add((s, SKOS.narrower, o))
                self.add((o, SKOS.broader, s))

            domain0 = URIRef('http://rdamsc.bath.ac.uk/thesaurus/domain0')
            self.add((domain0, RDF.type, UNO.Domain))
            self.add((domain0, SKOS.prefLabel, Literal("Multidisciplinary", lang='en')))

            print('Writing simplified thesaurus.')
            self.serialize(subjects_file, format='turtle')

        # Populate handy lookup properties
        self.entries = self._to_list()
        self.tree = self._to_tree()

    def _to_list(self, parent_uri: URIRef=None, parent_label: str=None)\
            -> List[Mapping[str, Union[URIRef, str]]]:
        full_list = list()
        sub_list = list()
        if parent_uri is None:
            domains = self.subjects(RDF.type, UNO.Domain)
            for domain in domains:
                label = str(self.preferredLabel(domain, lang='en')[0][1])
                sub_list.append({
                    'uri': domain,
                    'label': label,
                    'long_label': label})
            sub_list.sort(key=lambda k: k['uri'])
            for entry in sub_list:
                full_list.append(entry)
                full_list.extend(self._to_list(
                    entry['uri'], f" < {entry['long_label']}"))
        else:
            children = self.objects(parent_uri, SKOS.narrower)
            for child in children:
                label = str(self.preferredLabel(child, lang='en')[0][1])
                long_label = label + parent_label
                sub_list.append({
                    'uri': child,
                    'label': label,
                    'long_label': long_label})
            if sub_list:
                sub_list.sort(key=lambda k: k['label'])
                for entry in sub_list:
                    full_list.append(entry)
                    full_list.extend(self._to_list(
                        entry['uri'], f" < {entry['long_label']}"))
        return full_list

    def _to_tree(self, parent_uri: URIRef=None)\
            -> List[Mapping[str, Union[URIRef, str, List]]]:
        tree = list()
        if parent_uri:
            uris = self.objects(parent_uri, SKOS.narrower)
        else:
            uris = self.subjects(RDF.type, UNO.Domain)
        for uri in uris:
            label = str(self.preferredLabel(uri, lang='en')[0][1])
            entry = {'uri': uri, 'label': label}
            children = self._to_tree(uri)
            if children:
                entry['children'] = children
            tree.append(entry)
        if parent_uri and tree:
            tree.sort(key=lambda k: k['label'])
        else:
            tree.sort(key=lambda k: k['uri'])
        return tree

    def get_choices(self):
        return [kw['long_label'] for kw in self.entries]

    def get_label(self, uri: str) -> str:
        for entry in self.entries:
            if str(entry['uri']) == uri:
                return entry['label']
        return None

    def get_long_label(self, uri: str) -> str:
        for entry in self.entries:
            if str(entry['uri']) == uri:
                return entry['long_label']
        return None

    def get_tree(self, master: List=None, filter: List[str]=None)\
            -> List[Mapping[str, Union[str, List]]]:
        '''Returns a list of dictionaries, each of which provides the URL
        ('uri') of a term in the Catalog, its preferred label in English
        ('label'), and (if applicable) a list of dictionaries corresponding to
        immediately narrower terms in the thesaurus ('children'). If filter (a
        list of URIs) is given, only those URIs will be present in the tree:
        other terms will be filtered out.
        '''
        tree = list()
        if master is None:
            master = self.tree
        for entry in master:
            uri = str(entry['uri'])
            if filter is None or uri in filter:
                node = {'uri': uri, 'label': entry['label']}
                all_children = entry.get('children')
                if all_children:
                    children = self.get_tree(all_children, filter)
                    if children:
                        node['children'] = children
                tree.append(node)
        return tree

    def get_uri(self, label: str) -> str:
        '''Translates long or short label into term URI. If a short label is used,
        the URI corresponding to the broadest matching term is returned.'''
        print(f"DEBUG get_uri: label = {label}.")
        if '<' in label:
            for entry in self.entries:
                if entry['long_label'] == label:
                    return str(entry['uri'])
            return None

        # Testing for short label
        level = 99999
        uri = None
        for entry in self.entries:
            if entry['label'] == label:
                this_level = entry['long_label'].count(' < ')
                if this_level < level:
                    level = this_level
                    uri = str(entry['uri'])
        return uri


def get_subject_terms():
    if 'subject_terms' not in g:
        g.subject_terms = Thesaurus()

    return g.subject_terms
