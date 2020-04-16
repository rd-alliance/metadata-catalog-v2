# Installing and running the Metadata Standards Catalog

## Development

Use `git clone` as normal to get a copy of this code folder where you want it on your file system, then enter the folder on the command line.

Set up a virtual environment:

```bash
# *nix
python3 -m venv venv
# Windows
py -3 -m venv venv
```

Activate it:

```bash
# *nux
. venv/bin/activate
# Windows
venv\Scripts\activate
```


## Pre-requisite software

The Metadata Standards Catalog is written in [Python 3], so as a first step
this will need to be installed on your machine. You will also need quite a few
non-standard packages, but all of them are easily available via the `pip`
utility:

  - For the actual rendering of the pages you will need [Flask], [Flask-WTF]
    (and hence [WTForms]), and [Flask-Login].
  - For Open ID v2.x login support, you will need [Flask-OpenID].
  - For Open ID Connect (OAuth) support, you will need [RAuth] (and hence
    [Requests]), and Google's [oauth2client].
  - For API authentication, you will need [Flask-HTTPAuth] and [PassLib]
  - For database capability, you will need [TinyDB] v3.6.0+, [tinyrecord],
    and [RDFLib].
  - For version control of the databases, you will need [Dulwich].
  - To allow requests from JavaScript, you will need [Flask-CORS].

[Python 3]: https://www.python.org/
[Flask]: http://flask.pocoo.org/
[Flask-WTF]: https://flask-wtf.readthedocs.io/
[WTForms]: https://wtforms.readthedocs.io/
[Flask-Login]: https://flask-login.readthedocs.io/
[Flask-OpenID]: https://pythonhosted.org/Flask-OpenID/
[RAuth]: https://rauth.readthedocs.io/
[Requests]: http://docs.python-requests.org/
[oauth2client]: https://developers.google.com/api-client-library/python/guide/aaa_oauth
[Flask-HTTPAuth]: https://flask-httpauth.readthedocs.io/
[PassLib]: https://passlib.readthedocs.io/
[TinyDB]: http://tinydb.readthedocs.io/
[tinyrecord]: https://github.com/eugene-eeo/tinyrecord
[RDFLib]: http://rdflib.readthedocs.io/
[Dulwich]: https://www.dulwich.io/
[Flask-CORS]: http://flask-cors.readthedocs.io/

The Catalog is compatible with Flask 0.10 (this is what `python3-flask` gives
you in Ubuntu 16.04 LTS), but can be used with later versions.

## Installing the Catalog

If you are testing the Catalog on your own machine, you can run it directly
from the working directory (see below).

If you are setting up an instance of the Catalog on a live Web server, please
refer to the [deployment options] documented by the Flask developers.

[deployment options]: http://flask.pocoo.org/docs/0.12/deploying/

The key files and folders you need are these:

  - the application itself, `serve.py`;
  - the base configuration folder `config`;
  - the `static` and `templates` folders;
  - the vocabulary RDF file, `simple-unesco-thesaurus.ttl`.

If you do not set an instance folder for yourself, one will be created for you.

## Configuring the Catalog

### Configuration files

The Catalog will look in the following places for configuration options, in the
following order:

 1. The `config` folder, in the file `for.py`.
 2. The `instance` folder (in the same directory as the `serve.py` script), in
    the file `keys.cfg`.
 3. A file specified by the environment variable MSC_SETTINGS.

Settings are applied in the order they are discovered, so later ones override
earlier ones.

To set an environment variable on UNIX-like systems, you will need to include
the following line in your shell profile (or issue the command from the
command line):

 ```bash
 export MSC_SETTINGS=/path/to/settings.cfg
 ```

On Windows, you can run the following from the command prompt.

 ```batchfile
 set MSC_SETTINGS=\path\to\settings.cfg
 ```

### Database files

The Catalog uses three NoSQL databases, which are saved to disk in the form of
JSON files. You can either supply pre-populated versions of these files, or let
the Catalog create them for you:

 1. The Main database holds the records for schemes, tools, mappings, etc.
 2. The User database holds the user profiles.
 3. The OAuth database holds OAuth URLs discovered dynamically.

The Catalog also uses an Open ID folder for holding temporary files while
authenticating users using the Open ID v2 protocol.

You can configure the names and locations of these files and the folder by
putting the respective paths in one of your configuration files:

```python
MAIN_DATABASE_PATH = os.path.join('path', 'to', 'file.json')  # default: instance/data/db.json
USER_DATABASE_PATH = os.path.join('path', 'to', 'file.json')  # default: instance/data/users.json
OAUTH_DATABASE_PATH = os.path.join('path', 'to', 'file.json') # default: instance/oauth-urls.json
OPENID_PATH = os.path.join('path', 'to', 'folder')            # default: instance/open-id
```

One way of pre-populating the Main database is to generate the JSON file from
the YAML files in the `db` folder using the `dbctl.py` script. See the
[Administrator's Guide] for more information on this.

[Administrator's Guide]: ADMINISTRATION.md

### Security

To secure the installation, you should choose your own secret key and add it
to one of your configuration files, overriding the one in `for.py`:

```python
SECRET_KEY = 'secret string'
```

To be able to use Open ID Connect (OAuth), you will need to include IDs and
secret codes from the Open ID providers in your configuration like this:

```python
OAUTH_CREDENTIALS = {
    'google': {
        'id': 'id string',
        'secret': 'secret string'},
    'linkedin': {
        'id': 'id string',
        'secret': 'secret string'},
    'twitter': {
        'id': 'id string',
        'secret': 'secret string'}}
```

I have registered a set of these for use in the official instance at
<https://rdamsc.bath.ac.uk>, should there be demand.

## Running the Catalog

### Local testing

Open up a fresh terminal/command prompt (as it will block the command line for
as long as the script is running) and run the script `serve.py`. Depending on
your operating system you might be able to run the script directly:

```bash
./serve.py
```

Otherwise you might need to invoke `python` or `python3`:

```bash
python3 serve.py
```

You should then be able to access the Catalog in your Web browser using the URL
the script shows you, e.g. <http://127.0.0.1:5000/>.

### Production

Again, please refer to the [deployment options] documented by the Flask
developers for how to run the Catalog in production. Here is one way of doing
it, as a WSGI application on Apache, on an Ubuntu server.

Install the requisite packages:

```bash
sudo apt install apache2 openssl-blacklist libapache2-mod-wsgi-py3 python3-venv build-essential python3-dev
```

Create a user as whom to run the app:

```bash
sudo adduser --system --group rdamsc
```

If you are behind a web proxy, you can save some typing by setting some
variables. In the user's `$HOME/.profile`:

```bash
export http_proxy=http://proxy.example.com:99999/
export https_proxy=http://proxy.example.com:99999/
```

For Git:
```bash
sudo -Hu rdamsc git config --global http.proxy http://proxy.example.com:99999/
sudo -Hu rdamsc git config --global https.proxy http://proxy.example.com:99999/
```

The app will be split across three locations: the source code folder, the data
folder, and the WSGI app folder.

Set up the source code folder in, say, `/opt/rdamsc`:

```bash
sudo mkdir /opt/rdamsc
sudo chown rdamsc /opt/rdamsc
sudo -Hu rdamsc git clone https://github.com/rd-alliance/metadata-catalog-dev.git /opt/rdamsc
```

Set up the data folder in, say, `/var/rdamsc`:

```bash
sudo mkdir /var/rdamsc
sudo chown rdamsc /var/rdamsc
cd /opt/rdamsc
sudo ln -s /var/rdamsc instance
```

Create a file `/var/rdamsc/keys.cfg` with content such as the following:

```config
SECRET_KEY = 'your secret string'
```

Set up the WSGI app folder in, say, `/var/www/rdamsc`:

```bash
sudo mkdir /var/www/rdamsc
sudo chown rdamsc /var/www/rdamsc
```

While still in the source code (`opt`) folder, set up the Python dependencies:

```bash
sudo -Hsu rdamsc
python3 -m venv venv
. venv/bin/activate
pip3 install Flask Flask-WTF flask-login Flask-OpenID rauth oauth2client Flask-HTTPAuth passlib tinydb tinyrecord rdflib dulwich flask-cors pyyaml
```

Copy the `activate_this.py` script from the [virtualenv] repository to
`venv/bin/activate_this.py`.

[virtualenv]: https://github.com/pypa/virtualenv/blob/master/virtualenv_embedded/activate_this.py

You now have the libraries you need to restore the database from the backup in
the Git repo:

```bash
rdamsc python3 dbctl.py compile
```

(You will see a warning about IDs missing from the sequence. These are gaps left
behind from erroneously added records that have since been deleted. Continue
anyway to preserve the current internal IDs.)

Install the WSGI app by creating a file `/var/www/rdamsc/rdamsc.wsgi`:

```python
activate_this = '/opt/rdamsc/venv/bin/activate_this.py'
with open(activate_this) as file_:
    exec(file_.read(), dict(__file__=activate_this))

import os
import sys
sys.path.insert(0, '/opt/rdamsc')
os.environ['http_proxy'] = 'http://proxy.example.com:99999/'
os.environ['https_proxy'] = 'http://proxy.example.com:99999/'

from serve import app as application
```

To enable automatic reloading of the application, add the path of the WSGI file
to your application configuration:

```python
WSGI_PATH = '/var/www/rdamsc/rdamsc.wsgi'
```

Exit the app user account:

```bash
exit
```

As root, create a site configuration file at
`/etc/apache2/sites-available/rdamsc.conf`, remembering to give the actual
domain name you'll be using:

```apache
WSGIPassAuthorization On

<VirtualHost *:80>
    ServerName (whatever it is)

    WSGIDaemonProcess rdamsc user=rdamsc group=rdamsc threads=5
    WSGIScriptAlias / /var/www/rdamsc/rdamsc.wsgi

    <Directory /var/www/rdamsc>
        WSGIProcessGroup rdamsc
        WSGIApplicationGroup %{GLOBAL}
        WSGIScriptReloading On
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/error.log
    CustomLog ${APACHE_LOG_DIR}/access.log combined

</VirtualHost>

<IfModule mod_ssl.c>
    <VirtualHost *:443>
        ServerName (whatever it is)

        WSGIScriptAlias / /var/www/rdamsc/rdamsc.wsgi

        <Directory /var/www/rdamsc>
            WSGIProcessGroup rdamsc
            WSGIApplicationGroup %{GLOBAL}
            WSGIScriptReloading On
            Require all granted
        </Directory>

        ErrorLog ${APACHE_LOG_DIR}/error.log
        CustomLog ${APACHE_LOG_DIR}/access.log combined

        SSLEngine on
        SSLCertificateFile /path/to/fullchain.pem
        SSLCertificateKeyFile /path/to/privkey.pem

    </VirtualHost>
</IfModule>
```

Activate the regular HTTP virtual host:

```bash
sudo a2ensite rdamsc
# If replacing the default site:
sudo a2dissite 000-default
sudo service apache2 graceful
```

Once you have that working, install your SSL certificates and activate the
HTTPS virtual host:

```bash
sudo a2enmod ssl
sudo service apache2 graceful
```

## Things to watch out for

The Dulwich library for working with Git is quite sensitive, and will not stage
any commits if a `gitignore` file (local or global) contains lines consisting
solely of space characters.

If you have problems with authenticating through a proxy, you may need to
install the `pycurl` library as well.
