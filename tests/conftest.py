from html import unescape
import json
import os
import re
import tempfile
import time

import email_validator
from passlib.apps import custom_app_context as pwd_context
import pytest
from requests.auth import _basic_auth_str
from werkzeug.datastructures import MultiDict

from rdamsc import create_app

email_validator.TEST_ENVIRONMENT = True


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
            "slug": "test-scheme-1",
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
            "namespaces": [
                {
                    "prefix": "foo",
                    "uri": "https://schemes.org/ns/foo#"}],
            "identifiers": [
                {
                    "id": "10.1234/m1",
                    "scheme": "DOI"}]}
        self.m2 = {
            "title": "Test scheme 2",
            "slug": "test-scheme-2",
            "description": "<p>Paragraph 1.</p>"
                           "<p><a href=\"https://m.us/\">Paragraph</a> 2.</p>",
            "keywords": [
                "http://rdamsc.bath.ac.uk/thesaurus/subdomain235",
                "http://vocabularies.unesco.org/thesaurus/concept4011"],
            "dataTypes": ["msc:datatype1"],
            "versions": [
                {
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
                    "samples": [
                        {
                            "title": "Sample of Test scheme 2, version 1",
                            "url": "https://sample.org/m2v1"}],
                    "namespaces": [
                        {
                            "prefix": "bar1",
                            "uri": "https://schemes.org/ns/bar/1.0/"}],
                    "identifiers": [
                        {
                            "id": "10.1234/m2v1",
                            "scheme": "DOI"}]},
                {
                    "number": "2.2",
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
        self.m3 = {
            "title": "Test scheme 3",
            "slug": "test-scheme-3",
            "description": "This is only here to test paging."}
        self.m4 = {
            "title": "Test scheme 4",
            "slug": "test-scheme-4",
            "description": "This is also only here to test paging."}
        self.t1 = {
            "title": "Test tool 1",
            "slug": "test-tool-1",
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
            "slug": "test-tool-2",
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
            "slug": "test-crosswalk-1",
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
            "slug": "test-scheme-1_TO_test-scheme-2",
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
            "slug": "organization-1",
            "description": "<p>Paragraph 1.</p><p>Paragraph 2.</p>",
            "types": ["standards body"],
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
                    "scheme": "DOI"},
                {
                    "id": "https://ror.org/002h8g185",
                    "scheme": "ROR"}]}
        self.e1 = {
            "title": "Test endorsement 1",
            "slug": "test-endorsement-1",
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
                    "id": "10001.1234/e1",
                    "scheme": "Handle"}]}
        self.rel1 = {
            "@id": "msc:e1",
            "endorsed schemes": ["msc:m1", "msc:m2"],
            "originators": ["msc:g1"]}
        self.rel2 = {
            "@id": "msc:c2",
            "input schemes": ["msc:m1"],
            "output schemes": ["msc:m2"],
            "maintainers": ["msc:g1"]}
        self.rel3 = {
            "@id": "msc:m1",
            "funders": ["msc:g1"]}
        self.rel4 = {
            "@id": "msc:m2",
            "parent schemes": ["msc:m1"],
            "users": ["msc:g1"]}
        self.rel5 = {
            "@id": "msc:t1",
            "supported schemes": ["msc:m3"]}
        self.rel6 = {
            "@id": "msc:m3",
            "funders": ["msc:g1"]}
        self.datatype1 = {
            "id": "https://www.w3.org/TR/vocab-dcat/#class-dataset",
            "label": "Dataset"}
        self.datatype2 = {
            "id": "https://www.w3.org/TR/vocab-dcat/#class-catalog",
            "label": "Catalog"}

        self.fw_tags = {
            "parent schemes": "parent_schemes",
            "supported schemes": "supported_schemes",
            "input schemes": "input_schemes",
            "output schemes": "output_schemes",
            "endorsed schemes": "endorsed_schemes",
            "maintainers": "maintainers",
            "funders": "funders",
            "users": "users",
            "originators": "originators"}
        self.rv_tags = {
            "parent schemes": "child_schemes",
            "supported schemes": "tools",
            "input schemes": "input_to_mappings",
            "output schemes": "output_from_mappings",
            "endorsed schemes": "endorsements",
            "maintainers": "maintained_{}s",
            "funders": "funded_{}s",
            "users": "used_schemes",
            "originators": "endorsements"}
        self.rc_cls = {'m': 'scheme', 't': 'tool', 'c': 'mapping'}
        rels = dict()
        i = 1
        while hasattr(self, f'rel{i}'):
            fw_rel = dict()
            id = getattr(self, f'rel{i}').get('@id').replace('msc:', '')
            for k, v in getattr(self, f'rel{i}').items():
                if k not in self.fw_tags:
                    continue

                # Forward relations
                fw_rel[self.fw_tags[k]] = v

                # Inverse relations
                tag = self.rv_tags[k]
                for mscid in v:
                    v_id = mscid.replace('msc:', '')
                    if v_id not in rels:
                        rels[v_id] = dict()
                    if '{}' in tag:
                        tag = tag.format(self.rc_cls.get(id[0:1]))
                    if tag not in rels[v_id]:
                        rels[v_id][tag] = list()
                    rels[v_id][tag].append(f"msc:{id}")
            if id not in rels:
                rels[id] = dict()
            rels[id].update(fw_rel)
            i += 1
        self.rels = rels

    def count(self, table: str):
        '''Returns number of records in table.'''
        i = 1
        while hasattr(self, f'{table}{i}'):
            i += 1
        return i - 1

    def get_formdata(self, record: str, with_relations=False, version=None):
        '''Returns record in the form that WTForms would produce.'''
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
                                (f'{key}-{index}-{subsubkey}',
                                 subvalue[subsubkey]))
                    elif isinstance(subvalue, list):
                        for subsubvalue in subvalue:
                            multi_dict_items.append(
                                (f'{key}-{index}', subsubvalue))
                    elif key in ['keywords']:
                        multi_dict_items.append(
                            (f'{key}-{index}', kw_map[subvalue]))
                    else:
                        multi_dict_items.append((key, subvalue))
            elif isinstance(value, dict):
                for subkey, subvalue in value.items():
                    multi_dict_items.append(
                        (f'{key}-{subkey}', subvalue))
            else:
                multi_dict_items.append((key, value))
        if with_relations:
            for rel, mscids in self.rels.get(record, dict()).items():
                for index, mscid in enumerate(mscids):
                    multi_dict_items.append((rel, mscid))
        formdata = MultiDict(multi_dict_items)
        return formdata

    def get_apidata(self, record: str, with_embedded=True):
        '''Returns record in form that API would respond with.'''
        dbdata = getattr(self, record)
        apidata = dict()
        apidata['mscid'] = f'msc:{record}'
        apidata['uri'] = f'http://localhost/api2/{record}'
        for key, value in dbdata.items():
            apidata[key] = value
        related_entities = list()
        for k, vs in self.rels.get(record, dict()).items():
            for v in vs:
                related_entity = {
                    'id': v,
                    'role': k.replace('_', ' ')[:-1],
                }
                if with_embedded:
                    related_entity['data'] = self.get_apidata(
                        v.replace('msc:', ''), with_embedded=False)
                related_entities.append(related_entity)
        if related_entities:
            n = 5
            related_entities.sort(
                key=lambda k: k['role'] + k['id'][:n] + k['id'][n:].zfill(5))
            apidata['relatedEntities'] = related_entities
        return json.loads(json.dumps(apidata))

    def get_api1data(self, record: str, with_embedded=True):
        '''Returns record in form that API 1 would respond with.'''
        kw_map = {
            'http://rdamsc.bath.ac.uk/thesaurus/subdomain235':
                "Earth sciences",
            'http://vocabularies.unesco.org/thesaurus/concept4011':
                "Biological diversity"}

        dbdata = getattr(self, record)
        apidata = dict()
        apidata['identifiers'] = [
            {'id': f'msc:{record}', 'scheme': 'RDA-MSCWG'}]
        for key, value in dbdata.items():
            if key == 'identifiers':
                apidata[key] += value
            elif key == 'dataTypes':
                apidata[key] = list()
                for v in value:
                    dt = getattr(self, v[4:])
                    dt['url'] = dt['id']
                    del dt['id']
                    apidata[key].append(dt)
            elif key == 'keywords':
                apidata[key] = list()
                for v in value:
                    apidata[key].append(kw_map[v])
                apidata[key].sort()
            elif key == 'versions':
                apidata[key] = list()
                for v in value:
                    if 'valid' in v:
                        start = v['valid']['start']
                        end = v['valid'].get('end')
                        if end:
                            v['valid'] = f"{start}/{end}"
                        else:
                            v['valid'] = start
                    apidata[key].append(v)
            else:
                apidata[key] = value
        related_entities = list()
        for k, vs in self.rels.get(record, dict()).items():
            for v in vs:
                related_entity = {
                    'id': v,
                    'role': k.replace('_', ' ')[:-1],
                }
                if k in self.fw_tags.values():
                    related_entities.append(related_entity)
        if related_entities:
            n = 5
            related_entities.sort(
                key=lambda k: k['id'][:n] + k['id'][n:].zfill(5))
            apidata['relatedEntities'] = related_entities
        return json.loads(json.dumps(apidata))

    def get_apidataset(self, table: str):
        '''Returns table in form that API would respond with.'''
        apidataset = list()
        i = 1
        while hasattr(self, f'{table}{i}'):
            apidataset.append(self.get_apidata(
                f'{table}{i}', with_embedded=False))
            i += 1
        return apidataset

    def get_apirel(self, record: str, inverse=False):
        '''Returns relation in form that API would respond with.'''
        rel_id = f'msc:{record}'
        if inverse:
            apirel = {
                "@id": rel_id,
                "uri": f'http://localhost/api2/invrel/{record}'}
            i = 1
            while hasattr(self, f'rel{i}'):
                rel = getattr(self, f'rel{i}')
                id = rel['@id']
                for predicate, objects in rel.items():
                    if predicate in ['@id', 'uri']:
                        continue
                    tag = self.rv_tags[predicate].replace('_', ' ')
                    if '{}' in tag:
                        tag = tag.format(self.rc_cls.get(id[4:5]))
                    for object in objects:
                        if object != apirel['@id']:
                            continue
                        apirel.setdefault(tag, list()).append(id)
                i += 1
        else:
            rel = dict()
            if record.startswith("rel"):
                rel = getattr(self, record)
                rel_id = rel["@id"]
            else:
                i = 1
                while hasattr(self, f'rel{i}'):
                    test_rel = getattr(self, f'rel{i}')
                    if test_rel['@id'] == rel_id:
                        rel = test_rel
                        break
                    i += 1
            apirel = {
                "@id": rel_id,
                "uri": f'http://localhost/api2/rel/{rel_id[4:]}'}
            apirel.update(rel)

        table_order = {'m': 0, 't': 10, 'c': 20, 'g': 30, 'e': 40}
        n = 5
        for predicate in apirel.keys():
            if isinstance(apirel[predicate], list):
                apirel[predicate].sort(
                    key=lambda k: table_order[k[n - 1:n]] + int(k[n:]))
        return apirel

    def get_apirelset(self, inverse=False):
        '''Returns table of relations in form that API would respond with.'''
        table_order = {'m': 0, 't': 10, 'c': 20, 'g': 30, 'e': 40}
        apidataset = list()
        i = 1
        n = 5
        if inverse:
            reldict = dict()
            while hasattr(self, f'rel{i}'):
                record = getattr(self, f'rel{i}')
                id = record['@id']
                for predicate, objects in record.items():
                    if predicate in ['@id', 'uri']:
                        continue
                    tag = self.rv_tags[predicate].replace('_', ' ')
                    if '{}' in tag:
                        tag = tag.format(self.rc_cls.get(id[4:5]))
                    for object in objects:
                        reldict.setdefault(object, dict()).setdefault(
                            tag, list()
                        ).append(id)
                i += 1

            for id in sorted(reldict.keys(),
                             key=lambda k: k[:n] + k[n:].zfill(5)):
                item = {
                    "@id": id,
                    "uri": f'http://localhost/api2/invrel/{id[4:]}'}
                item.update(reldict[id])
                apidataset.append(item)

            for item in apidataset:
                for predicate in item.keys():
                    if isinstance(item[predicate], list):
                        item[predicate].sort(
                            key=lambda k: table_order[k[n - 1:n]] + int(k[n:]))
        else:
            while hasattr(self, f'rel{i}'):
                apidataset.append(self.get_apirel(f'rel{i}'))
                i += 1

        apidataset.sort(
            key=lambda k: table_order[k['@id'][n - 1:n]] + int(k['@id'][n:]))
        return apidataset

    def get_apiterm(self, table: str, number: int):
        '''Returns term record in form that API would respond with.'''
        apidataset = self.get_apitermset(table)
        if number < 1 or number > len(apidataset):
            return None

        return apidataset[number - 1]

    def get_apitermset(self, table: str):
        '''Returns term table in form that API would respond with.'''
        apidataset = list()
        db_file = self._app.config['TERM_DATABASE_PATH']

        if not os.path.isfile(db_file):
            return apidataset

        with open(db_file, 'r') as f:
            db = json.load(f)

        if table not in db:
            return apidataset

        i = 1
        while f"{i}" in db[table]:
            record = db[table][f"{i}"]
            record['mscid'] = f'msc:{table}{i}'
            record['uri'] = f'http://localhost/api2/{table}{i}'
            apidataset.append(record)
            i += 1

        return apidataset

    def _tables_to_file(self, tables: list, db_file: str):
        '''Writes a set of tables to a given DB file.'''
        if os.path.isfile(db_file):
            try:
                with open(db_file, 'r') as f:
                    db = json.load(f)
            except json.decoder.JSONDecodeError:
                db = {"_default": {}}
        else:
            db = {"_default": {}}

        for table in tables:
            db[table] = dict()
            i = 1
            while hasattr(self, f'{table}{i}'):
                db[table][i] = getattr(self, f'{table}{i}')
                i += 1

            # Write a deleted entry to ensure it doesn't mess things up.
            # Relation records retain `@id` so are never left entirely blank.
            if table != 'rel':
                db[table][i] = dict()

        with open(db_file, 'w') as f:
            json.dump(db, f, indent=1, ensure_ascii=False)

    def write_bad_db(self):
        '''Writes main database file.'''
        self.rel4["parent schemes"] += ["msc:m3"]
        self.rel6["parent schemes"] = ["msc:m2"]
        self._tables_to_file(
            ["m", "t", "c", "g", "e", "rel"],
            self._app.config['MAIN_DATABASE_PATH'])

    def write_db(self):
        '''Writes main database file.'''
        self._tables_to_file(
            ["m", "t", "c", "g", "e", "rel"],
            self._app.config['MAIN_DATABASE_PATH'])

    def write_terms(self):
        '''Writes term database file.'''
        self._tables_to_file(
            ["datatype"],
            self._app.config['TERM_DATABASE_PATH'])


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

    def get_csrf(self, html=None) -> str:
        '''Extracts CSRF token from page's form controls.'''
        if html is not None:
            self.read(html)
        m = re.search(
            r'<input id="csrf_token" name="csrf_token" type="hidden"'
            r' value="([^"]+)">', self.html)
        if not m:
            return None
        return m.group(1)

    def get_all_hidden(self, html=None) -> MultiDict:
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


class UserDBActions(object):
    def __init__(self, app):
        self._app = app
        self.pwd1 = 'Not a great password'
        self.api_users1 = {
            'userid': 'backdoor',
            'password_hash': pwd_context.hash(self.pwd1),
        }
        self.pwd2 = 'An even worse password'
        self.api_users2 = {
            'userid': 'compromised',
            'password_hash': pwd_context.hash(self.pwd2),
            'blocked': True,
        }

    def _tables_to_file(self, tables: list, db_file: str):
        '''Writes a set of tables to a given DB file.'''
        if os.path.isfile(db_file):
            try:
                with open(db_file, 'r') as f:
                    db = json.load(f)
            except json.decoder.JSONDecodeError:
                db = {"_default": {}}
        else:
            db = {"_default": {}}

        for table in tables:
            db[table] = dict()
            i = 1
            while hasattr(self, f'{table}{i}'):
                db[table][i] = getattr(self, f'{table}{i}')
                i += 1

        with open(db_file, 'w') as f:
            json.dump(db, f, indent=1, ensure_ascii=False)

    def write_db(self):
        '''Writes main database file.'''
        self._tables_to_file(
            ["api_users"],
            self._app.config['USER_DATABASE_PATH'])


@pytest.fixture
def app():
    with tempfile.TemporaryDirectory() as inst_path:
        app = create_app({
            'TESTING': True,
            'MAIN_DATABASE_PATH': os.path.join(
                inst_path, 'data', 'db.json'),
            'VOCAB_DATABASE_PATH': os.path.join(
                inst_path, 'data', 'vocab.json'),
            'TERM_DATABASE_PATH': os.path.join(
                inst_path, 'data', 'terms.json'),
            'USER_DATABASE_PATH': os.path.join(
                inst_path, 'users', 'db.json'),
            'OAUTH_DATABASE_PATH': os.path.join(
                inst_path, 'oauth', 'db.json'),
            'OPENID_FS_STORE_PATH': os.path.join(
                inst_path, 'open-id'),
            'OAUTH_CREDENTIALS': {
                'test': {
                    'id': 'test-oauth-app-id',
                    'secret': 'test-oauth-app-secret'}}
        })

        yield app


class AuthAPIActions(object):
    def __init__(self, client, user_db):
        self._client = client
        self._username = user_db.api_users1.get('userid')
        self._password = user_db.pwd1
        self._token = ''
        self._expiry = 0
        user_db.write_db()

    def get_token(self):
        if time.time() > self._expiry:
            credentials = _basic_auth_str(self._username, self._password)
            self._expiry = time.time() + 595
            response = self._client.get(
                '/api2/user/token',
                headers={"Authorization": credentials},
                follow_redirects=True)
            test_data = response.get_json()
            self._token = test_data.get("token")
        return self._token


@pytest.fixture
def client(app):
    with app.test_client() as client:
        yield client


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def auth(client, page):
    return AuthActions(client, page)


@pytest.fixture
def auth_api(client, user_db):
    return AuthAPIActions(client, user_db)


@pytest.fixture
def data_db(app):
    return DataDBActions(app)


@pytest.fixture
def user_db(app):
    return UserDBActions(app)


@pytest.fixture
def page():
    return PageActions()
