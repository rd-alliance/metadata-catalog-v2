import os
import re
import tempfile
import json
from html import unescape
import pytest
from werkzeug.datastructures import MultiDict

from rdamsc import create_app


class AuthActions(object):
    def __init__(self, client, page):
        self._client = client
        self._page = page

    def login(self):
        r = self._client.get('/callback/test', follow_redirects=True)
        html = r.get_data(as_text=True)
        if "<h1>Create Profile</h1>" in html:
            csrf = self._page.get_csrf(html)
            m = re.search(
                r'<input [^>]+ name="name" [^>]+ value="([^"]+)">', html)
            username = m.group(1)
            m = re.search(
                r'<input [^>]+ name="email" [^>]+ value="([^"]+)">', html)
            useremail = m.group(1)
            return self._client.post(
                '/create-profile',
                data={'csrf_token': csrf,
                      'name': username,
                      'email': useremail},
                follow_redirects=True)
        return r

    def logout(self):
        return self._client.get('/logout')


class DataDBActions(object):
    def __init__(self, app):
        self._app = app
        self.m1 = {
            "title": "Test scheme 1",
            "description": "Description without tags.",
            "keywords": [
                "http://rdamsc.bath.ac.uk/thesaurus/subdomain235",
                "http://vocabularies.unesco.org/thesaurus/concept4011"],
            "dataTypes": ["msc:datatype1"],
            "locations": [
                {
                    "url": "https://website.org/m1",
                    "type": "website"},
                {
                    "url": "http://document.org/m1",
                    "type": "document"}],
            "identifiers": [
                {
                    "id": "10.1234/m1",
                    "scheme": "DOI"}]}
        self.m2 = {
            "title": "Test scheme 2",
            "description": "<p>Paragraph 1.</p>"
                           "<p><a href=\"https://m.us/\">Paragraph</a> 2.</p>",
            "keywords": [
                "http://rdamsc.bath.ac.uk/thesaurus/subdomain235",
                "http://vocabularies.unesco.org/thesaurus/concept4011"],
            "dataTypes": ["msc:datatype1"],
            "versions": [
                {
                    "number": "1",
                    "title": "Scheme version title",
                    "note": "Version note without tags.",
                    "issued": "2020-01-01",
                    "available": "2018-08-31",
                    "valid": {
                        "start": "2020-01-01",
                        "end": "2022-01-01"},
                    "locations": [
                        {
                            "url": "http://website.org/m2v1",
                            "type": "website"},
                        {
                            "url": "https://document.org/m2v1",
                            "type": "document"}],
                    "identifiers": [
                        {
                            "id": "10.1234/m2v1",
                            "scheme": "DOI"}],
                    "samples": [
                        {
                            "title": "Sample of Test scheme 2, version 1",
                            "url": "https://sample.org/m2v1"}]},
                {
                    "number": "2",
                    "note": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
                    "valid": {
                        "start": "2020-03-01",
                        "end": "2022-01-01"},
                    "locations": [
                        {
                            "url": "http://website.org/m2v2",
                            "type": "website"},
                        {
                            "url": "https://document.org/m2v2",
                            "type": "document"}],
                    "identifiers": [
                        {
                            "id": "10.1234/m2v2",
                            "scheme": "DOI"}]}]}
        self.t1 = {
            "title": "Test tool 1",
            "description": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
            "types": ["web application"],
            "locations": [
                {
                    "url": "https://website.org/t1",
                    "type": "website"},
                {
                    "url": "http://documentation.org/t1",
                    "type": "document"}],
            "identifiers": [
                {
                    "id": "10.1234/t1",
                    "scheme": "DOI"}],
            "creators": [
                {
                    "givenName": "Forename",
                    "familyName": "Surname"}]}
        self.t2 = {
            "title": "Test tool 2",
            "description": "Test description no tags.",
            "types": ["web application"],
            "versions": [
                {
                    "number": "1",
                    "title": "Tool version title",
                    "note": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
                    "issued": "2020-01-01",
                    "locations": [
                        {
                            "url": "http://website.org/t2v1",
                            "type": "website"},
                        {
                            "url": "https://documentation.org/t2v1",
                            "type": "document"}],
                    "identifiers": [
                        {
                            "id": "10.1234/t2v1",
                            "scheme": "DOI"}]}]}
        self.c1 = {
            "name": "Test crosswalk 1",
            "description": "Description with no tags.",
            "locations": [
                {
                    "url": "https://library.org/c1",
                    "type": "library (Python)"},
                {
                    "url": "http://document.org/c1",
                    "type": "document"}],
            "identifiers": [
                {
                    "id": "10.1234/c1",
                    "scheme": "DOI"}],
            "creators": [
                {
                    "givenName": "Forename",
                    "familyName": "Surname",
                    "fullName": "Given Family"}]}
        self.c2 = {
            "name": "Test crosswalk 2",
            "description": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
            "versions": [
                {
                    "number": "1",
                    "note": "Note with no tags.",
                    "issued": "2020-01-01",
                    "locations": [
                        {
                            "url": "https://library.org/c2v1",
                            "type": "library (Python)"},
                        {
                            "url": "http://document.org/c2v1",
                            "type": "document"}],
                    "identifiers": [
                        {
                            "id": "10.1234/c2v1",
                            "scheme": "DOI"}]}]}
        self.g1 = {
            "name": "Organization 1",
            "description": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
            "types": "standards body",
            "locations": [
                {
                    "url": "http://website.org/g1",
                    "type": "website"},
                {
                    "url": "mailto:g1@website.org",
                    "type": "email"}],
            "identifiers": [
                {
                    "id": "10.1234/g1",
                    "scheme": "DOI"}]}
        self.e1 = {
            "title": "Test endorsement 1",
            "description": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
            "creators": [
                {
                    "fullName": "Corporation"}],
            "publication": "<i>IEEE MultiMedia</i>, 13(2), 84-88",
            "issued": "2017-12-31",
            "valid": {
                    "start": "2018-01-01",
                    "end": "2019-12-31"},
            "locations": [
                {
                    "url": "http://journal.org/e1",
                    "type": "document"}],
            "identifiers": [
                {
                    "id": "10.1234/e1",
                    "scheme": "DOI"}]}
        self.rel1 = {
            "@id": "msc:m1",
            "user": ["msc:g1"]}
        self.rel2 = {
            "@id": "msc:m2",
            "parent scheme": ["msc:m1"],
            "maintainer": ["msc:g1"]}
        self.rel3 = {
            "@id": "msc:t1",
            "supported scheme": ["msc:m3"]}
        self.rel4 = {
            "@id": "msc:c1",
            "input scheme": ["msc:m1"],
            "output scheme": ["msc:m2"],
            "funder": ["msc:g1"]}
        self.rel5 = {
            "@id": "msc:e1",
            "endorsed scheme": ["msc:m1", "msc:m2"],
            "originator": ["msc:g1"]}
        self.datatype1 = {
            "id": "https://www.w3.org/TR/vocab-dcat/#class-dataset",
            "label": "Dataset"}

        fw_tags = {
            "parent scheme": "parent_schemes",
            "supported scheme": "supported_schemes",
            "input scheme": "input_schemes",
            "output scheme": "output_schemes",
            "endorsed scheme": "endorsed_schemes",
            "maintainer": "maintainers",
            "funder": "funders",
            "user ": "users",
            "originator": "originators"}
        rv_tags = {
            "parent scheme": "child_schemes",
            "supported scheme": "tools",
            "input scheme": "input_to_mappings",
            "output scheme": "output_from_mappings",
            "endorsed scheme": "endorsements",
            "maintainer": "maintained_{}s",
            "funder": "funded_{}s",
            "user ": "used_schemes",
            "originator": "endorsements"}
        rc_cls = {'m': 'scheme', 't': 'tool', 'c': 'crosswalk'}
        rels = dict()
        i = 1
        while hasattr(self, f'rel{i}'):
            fw_rel = dict()
            id = getattr(self, f'rel{i}').get('@id').replace('msc:', '')
            for k, v in getattr(self, f'rel{i}').items():
                if k not in fw_tags:
                    continue
                fw_rel[fw_tags[k]] = v
                tag = rv_tags[k]
                for mscid in v:
                    if mscid not in rels:
                        rels[mscid] = dict()
                    if '{}' in tag:
                        tag = tag.format(rc_cls.get(mscid[4:5]))
                    if tag not in rels[mscid]:
                        rels[mscid][tag] = list()
                    rels[mscid][tag].append(id)
            if id not in rels:
                rels[id] = dict()
            rels[id].update(fw_rel)
            i += 1
        self.rels = rels

    def get_formdata(self, record: str, with_relations=False, version=None):
        dbdata = getattr(self, record)
        if version is not None:
            try:
                dbdata = dbdata.get('versions', list())[version]
            except IndexError:
                return MultiDict()
        kw_map = {
            'http://rdamsc.bath.ac.uk/thesaurus/subdomain235':
                "Earth sciences < Science",
            'http://vocabularies.unesco.org/thesaurus/concept4011':
                "Biological diversity < Ecological balance < Ecosystems <"
                " Environmental sciences and engineering < Science"}
        multi_dict_items = []
        for key in dbdata:
            if key == 'versions':
                continue
            value = dbdata[key]
            if isinstance(value, list):
                for index, subvalue in enumerate(value):
                    if isinstance(subvalue, dict):
                        for subsubkey in subvalue:
                            multi_dict_items.append(
                                ('{}-{}-{}'.format(key, index, subsubkey),
                                 subvalue[subsubkey]))
                    elif isinstance(subvalue, list):
                        for subsubvalue in subvalue:
                            multi_dict_items.append(
                                ('{}-{}'.format(key, index), subsubvalue))
                    elif key in ['keywords']:
                        multi_dict_items.append(
                            ('{}-{}'.format(key, index), kw_map[subvalue]))
                    else:
                        multi_dict_items.append(
                            ('{}'.format(key), subvalue))
            elif isinstance(value, dict):
                pass
            else:
                multi_dict_items.append((key, value))
        if with_relations:
            for rel, mscid in self.rels.get(record, dict()).items():
                multi_dict_items.append((rel, mscid))
        formdata = MultiDict(multi_dict_items)
        return formdata

    def write_db(self):
        db_file = self._app.config['MAIN_DATABASE_PATH']
        if os.path.isfile(db_file):
            with open(db_file, 'r') as f:
                db = json.load(f)
        else:
            db = {"_default": {}}

        db["m"] = {"1": self.m1}
        db["m"] = {"2": self.m2}
        db["t"] = {"1": self.t1}
        db["t"] = {"2": self.t2}
        db["c"] = {"1": self.c1}
        db["c"] = {"2": self.c2}
        db["g"] = {"1": self.g1}
        db["e"] = {"1": self.e1}
        db["rel"] = {"1": self.rel1}
        db["rel"] = {"2": self.rel2}
        db["rel"] = {"3": self.rel3}
        db["rel"] = {"4": self.rel4}
        db["rel"] = {"5": self.rel5}

        db_file = self._app.config['MAIN_DATABASE_PATH']
        with open(db_file, 'w') as f:
            json.dump(db, f, indent=1, ensure_ascii=False)

    def write_terms(self):
        terms_file = self._app.config['TERM_DATABASE_PATH']
        if os.path.isfile(terms_file):
            with open(terms_file, 'r') as f:
                terms = json.load(f)
        else:
            terms = {"_default": {}}

        terms['datatype'] = {"1": self.datatype1}
        with open(terms_file, 'w') as f:
            json.dump(terms, f, indent=1, ensure_ascii=False)


class PageActions(object):
    def __init__(self):
        self.html = ''
        self.trimmed_html = ''

    def read(self, html):
        '''Loads HTML ready to be tested or processed further. Could include
        additional prep, currently doesn't.'''
        self.html = html
        self.trimmed_html = re.sub(
            r'<datalist[^>]*>(\n\s+<option>[^<]*</option>)+\n\s+</datalist>\n',
            '', html)

    def get_csrf(self, html=None):
        '''Extracts CSRF token from page's form controls.'''
        if html is not None:
            self.read(html)
        m = re.search(
            r'<input id="csrf_token" name="csrf_token" type="hidden"'
            r' value="([^"]+)">', self.html)
        if not m:
            return None
        return m.group(1)

    def get_all_hidden(self, html=None):
        '''Extracts hidden inputs from page's form controls.'''
        if html is not None:
            self.read(html)
        results = MultiDict()
        for m in re.finditer(
                r'<input id="(?P<name>[^"]+)" name="(?P=name)" type="hidden"'
                r' value="(?P<value>[^"]+)">', self.html):
            results.add(m.group('name'), unescape(m.group('value')))
        return results

    def assert_contains(self, substring, html=None):
        '''Asserts page source includes substring.'''
        __tracebackhide__ = True
        if html is not None:
            self.read(html)
        if substring not in self.html:
            pytest.fail(
                f"‘{substring}’ not in page. Full page:\n{self.trimmed_html}")

    def assert_lacks(self, substring, html=None):
        '''Asserts page source does not include substring.'''
        __tracebackhide__ = True
        if html is not None:
            self.read(html)
        if substring in self.html:
            pytest.fail(
                f"‘{substring}’ is in page. Full page:\n{self.trimmed_html}")


@pytest.fixture
def app():
    inst_path = tempfile.mkdtemp()

    app = create_app({
        'TESTING': True,
        'MAIN_DATABASE_PATH': os.path.join(inst_path, 'data', 'db.json'),
        'VOCAB_DATABASE_PATH': os.path.join(inst_path, 'data', 'vocab.json'),
        'TERM_DATABASE_PATH': os.path.join(inst_path, 'data', 'terms.json'),
        'USER_DATABASE_PATH': os.path.join(inst_path, 'users', 'db.json'),
        'OAUTH_DATABASE_PATH': os.path.join(inst_path, 'oauth', 'db.json'),
        'OPENID_FS_STORE_PATH': os.path.join(inst_path, 'open-id'),
        'OAUTH_CREDENTIALS': {
            'test': {
                'id': 'test-oauth-app-id',
                'secret': 'test-oauth-app-secret'}}
    })

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def auth(client, page):
    return AuthActions(client, page)


@pytest.fixture
def data_db(app):
    return DataDBActions(app)


@pytest.fixture
def page():
    return PageActions()
