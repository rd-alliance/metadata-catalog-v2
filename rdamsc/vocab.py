# Dependencies
# ============
# Standard
# --------
import os
import shutil
from typing import (
    List,
    Mapping,
    Tuple,
    Union,
)

# Non-standard
# ------------
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import current_app, g, url_for
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query
from tinydb.database import Document
# See https://github.com/eugene-eeo/tinyrecord
from tinyrecord import transaction
# See http://rdflib.readthedocs.io/
import rdflib
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS, RDF

# Local
# -----
from .db_utils import JSONStorageWithGit

UNO = Namespace('http://vocabularies.unesco.org/ontology#')


class Thesaurus(object):
    def __init__(self):
        db = get_vocab_db()
        self.terms = db.table('thesaurus_terms')
        self.trees = db.table('thesaurus_trees')
        if len(self.terms) == 0:
            # Initialise from supplied data
            self.g = Graph()
            moddir = os.path.dirname(__file__)
            subjects_file = os.path.join(
                moddir, 'data', 'simplified-unesco-thesaurus.ttl')
            self.g.parse(subjects_file, format='turtle')

            # Populate handy lookup properties
            self.uriref = URIRef('http://rdamsc.bath.ac.uk/thesaurus')
            entries = self._to_list()
            n = 0
            with transaction(self.terms) as t:
                for entry in entries:
                    entry['position'] = n
                    t.insert(entry)
                    n += 1
            trees = self._to_tree()
            n = 0
            with transaction(self.trees) as t:
                for tree in trees:
                    tree['position'] = n
                    t.insert(tree)
                    n += 1

    @property
    def entries(self):
        return self.terms.all()

    @property
    def tree(self):
        return self.trees.all()

    def _to_list(self, parent_uris: List[URIRef]=None, parent_label: str=None)\
            -> List[Mapping[str, Union[URIRef, str]]]:
        full_list = list()
        sub_list = list()
        if parent_uris is None:
            domains = self.g.subjects(SKOS.topConceptOf, self.uriref)
            for domain in domains:
                label = str(self.g.preferredLabel(domain, lang='en')[0][1])
                sub_list.append({
                    'uri': domain,
                    'label': label,
                    'long_label': label,
                    'ancestry': []})
            sub_list.sort(key=lambda k: k['uri'])
            for entry in sub_list:
                full_list.append(entry)
                full_list.extend(self._to_list(
                    [entry['uri']], f" < {entry['long_label']}"))
        else:
            parent_uri = parent_uris[-1]
            children = self.g.objects(parent_uri, SKOS.narrower)
            for child in children:
                label = str(self.g.preferredLabel(child, lang='en')[0][1])
                long_label = label + parent_label
                sub_list.append({
                    'uri': child,
                    'label': label,
                    'long_label': long_label,
                    'ancestry': parent_uris})
            if sub_list:
                sub_list.sort(key=lambda k: k['label'])
                for entry in sub_list:
                    full_list.append(entry)
                    full_list.extend(self._to_list(
                        parent_uris + [entry['uri']],
                        f" < {entry['long_label']}"))
        return full_list

    def _to_tree(self, parent_uri: URIRef=None)\
            -> List[Mapping[str, Union[URIRef, str, List]]]:
        tree = list()
        if parent_uri:
            uris = self.g.objects(parent_uri, SKOS.narrower)
        else:
            uris = self.g.subjects(SKOS.topConceptOf, self.uriref)
        if not uris:
            return tree
        for uri in uris:
            label = str(self.g.preferredLabel(uri, lang='en')[0][1])
            entry = {'uri': uri, 'label': label}
            children = self._to_tree(uri)
            if children:
                entry['children'] = children
            tree.append(entry)
        if parent_uri:
            tree.sort(key=lambda k: k['label'])
        else:
            tree.sort(key=lambda k: k['uri'])
        return tree

    def _child_uris(self, tree: Mapping[str, Union[URIRef, str, List]]):
        uris = list()
        uris.append(tree['uri'])
        for child in tree.get('children', list()):
            uris.extend(self._child_uris(child))
        return uris

    def get_branch(self, term: str, broader: bool=True, narrower: bool=True):
        '''Given a term's label or URI, returns the term's URI along with the
        URI of each ancestor and descendent term. Returns an empty list if term
        not recognised.
        '''
        Q = Query()
        uris = list()

        # Get base entry
        if term.startswith('http'):
            base_entry = self.terms.get(Query().uri == term)
        else:
            base_entry = self.terms.get(Query().label == term)
        if not base_entry:
            return uris

        if broader:
            # Get list of ancestor entries
            uris = base_entry['ancestry']

        uris.append(base_entry['uri'])

        if narrower:
            # Get list of child entries
            # 1. URIs from current up to top level
            route = [base_entry['uri']]
            route.extend(base_entry['ancestry'][::-1])
            # 2. Get domain tree
            domain_uri = route.pop()
            tree = self.trees.get(Query().uri == domain_uri)
            if not tree:
                print("DEBUG get_branch: Domain not found.")
                return uris
            # 3. Traverse down to current term
            while route:
                children = tree.get('children', list())
                if not children:
                    print("DEBUG get_branch: Traversal ended early.")
                    return uris
                child_uri = route.pop()
                for child in children:
                    if child['uri'] == child_uri:
                        tree = child
                        break
            # 4. Tree now starts from current entry
            for child in tree.get('children', list()):
                uris.extend(self._child_uris(child))

        return uris

    def get_label(self, uri: str) -> str:
        entry = self.terms.get(Query().uri == uri)
        if entry:
            return entry.get('label')
        return None

    def get_labels(self):
        return [kw['label'] for kw in self.entries]

    def get_long_label(self, uri: str) -> str:
        entry = self.terms.get(Query().uri == uri)
        if entry:
            return entry.get('long_label')
        return None

    def get_long_labels(self):
        return [kw['long_label'] for kw in self.entries]

    def get_tree(self, filter: List[str], master: List=None)\
            -> List[Mapping[str, Union[str, List]]]:
        '''Takes a list of term URIs, and returns the corresponding terms in tree
        form, specifically as a list of dictionaries suitable for use with the
        contents template: 'url' holds the URL of the term's search result in
        the Catalog (not its ID URI), 'name' holds its preferred label in
        English, and (if applicable) 'children' holds a list of dictionaries
        corresponding to immediately narrower terms in the thesaurus
        ('children').
        '''
        tree = list()
        if master is None:
            # First call -- start at top of tree:
            master = self.tree
            # Add ancestor terms to whitelist:
            kw_branches_used = set()
            for kw in filter:
                if kw in kw_branches_used:
                    continue
                kw_branches_used.update(
                    self.get_branch(kw, narrower=False))
            filter = list(kw_branches_used)

        for entry in master:
            url = url_for('search.subject', subject=entry['label'])
            if str(entry['uri']) in filter:
                node = {'url': url, 'name': entry['label']}
                all_children = entry.get('children')
                if all_children:
                    children = self.get_tree(filter, all_children)
                    if children:
                        node['children'] = children
                tree.append(node)
        return tree

    def get_uri(self, label: str) -> str:
        '''Translates long or short label into term URI.'''
        if label is None:
            return None
        field = 'long_label' if '<' in label else 'label'
        entry = self.terms.get(Query()[field] == label)
        if entry:
            return entry.get('uri')
        return None

    def get_valid(self):
        values = list()
        for kw in self.entries:
            values.append(kw['label'])
            if kw['long_label'] != kw['label']:
                values.append(kw['long_label'])
        return values


def get_thesaurus():
    if 'thesaurus' not in g:
        g.thesaurus = Thesaurus()

    return g.thesaurus


def get_vocab_db():
    if 'vocab_db' not in g:
        g.vocab_db = TinyDB(
            current_app.config['VOCAB_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=1,
            ensure_ascii=False)

    return g.vocab_db
