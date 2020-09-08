# Installing and running the Metadata Standards Catalog

## Pre-requisite software

The Metadata Standards Catalog is written in [Python 3.6+], so as a first step
this will need to be installed on your machine.

You will also need quite a few non-standard packages; the instructions below
will install these for you in an isolated virtual environment, but here they
are if you want to look up the documentation:

  - [Flask], [Flask-WTF] (and hence [WTForms]), and [Flask-Login] are needed for
    the actual rendering of the pages.
  - [Email validator] is used for email address validation in forms.
  - [Flask-OpenID] provides Open ID v2.x login support.
  - [RAuth] (which depends on [Requests]), and Google's [oauth2client] are used
    for Open ID Connect (OAuth) support.
  - [Flask-HTTPAuth] and [PassLib] are used for API authentication.
  - The database is implemented using [TinyDB] v4+ and [tinyrecord].
  - The subject thesaurus is converted from RDF to JSON via [RDFLib].
  - [Dulwich] is used to apply version control to the database.
  - [GitHub-Webhook] allows the Catalog to update itself.
  - [Flask-CORS] is used to allow requests from JavaScript.

[Python 3]: https://www.python.org/
[Flask]: http://flask.pocoo.org/
[Flask-WTF]: https://flask-wtf.readthedocs.io/
[WTForms]: https://wtforms.readthedocs.io/
[Flask-Login]: https://flask-login.readthedocs.io/
[Email validator]: https://pypi.org/project/email-validator/
[Flask-OpenID]: https://pythonhosted.org/Flask-OpenID/
[RAuth]: https://rauth.readthedocs.io/
[Requests]: http://docs.python-requests.org/
[oauth2client]: https://developers.google.com/api-client-library/python/guide/aaa_oauth
[Flask-HTTPAuth]: https://flask-httpauth.readthedocs.io/
[PassLib]: https://passlib.readthedocs.io/
[TinyDB]: http://tinydb.readthedocs.io/
[tinyrecord]: https://pypi.org/project/tinyrecord/
[RDFLib]: http://rdflib.readthedocs.io/
[Dulwich]: https://www.dulwich.io/
[GitHub-Webhook]: https://bloomberg.github.io/python-github-webhook/
[Flask-CORS]: http://flask-cors.readthedocs.io/


## Installation

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
# *nix
. venv/bin/activate
# Windows
venv\Scripts\activate
```

Optionally, upgrade your sandboxed copy of `pip`:

```bash
pip install --upgrade pip
```

Install the Catalog and its dependencies to your virtual environment:

```bash
pip install -e .
```


### Running unit tests

See the [Guide for Contributors](CONTRIBUTING.md) for how to run the unit tests.


### Running a development version

Run the application like this to get development mode:

```bash
# *nix
export FLASK_APP=rdamsc; export FLASK_ENV=development; flask run
# Windows
set FLASK_APP=rdamsc
set FLASK_ENV=development
flask run
# Windows Powershell
$env:FLASK_APP = "rdamsc"
$env:FLASK_ENV = "development"
flask run
```

You will get feedback on the command line about what URL to use to access the
application.


### Running in production using mod_wsgi on Apache

These instructions are one way to go about using the Catalog in production.
For other options, please refer to the [deployment options] documented by the
Flask developers.

[deployment options]: https://flask.palletsprojects.com/en/1.1.x/deploying/

On the Web server, let's assume for example that you have installed the
application using the above instructions in `/opt/rdamsc`.

These instructions are for mod_wsgi on Apache, so these need to be installed. On
Debian or a derivative like Ubuntu, you'd do this:

```bash
sudo apt install apache2 libapache2-mod-wsgi-py3
```

It is recommended that you set up a non-privileged system user to run the
Catalog (say, `rdamsc`) and that this user and the Apache user (`www-data` on
Debian-based Linux distros) are in each other's groups. Be sure to assign
ownership of the source code directory to this user. Example:

```bash
sudo adduser --system --group rdamsc
sudo usermod -aG www-data rdamsc
sudo usermod -aG rdamsc www-data
sudo chown rdamsc:www-data /opt/rdamsc
```

You should create an instance folder where the Catalog can keep its data. You
could put it in `/var/rdamsc`:

```bash
sudo mkdir /var/rdamsc
sudo chown rdamsc:www-data /var/rdamsc
```

Configure the Catalog to use this folder explicitly by changing the `app`
assignment line to include the information:

```python
# Create the app:
app = Flask(__name__, instance_relative_config=True, instance_path='/var/rdamsc')
```

Commit this change so Git can reapply it over any other code changes.

Inside your virtual environment, you need the `activate_this.py` script so you
can activate it with the system's Python installation. The latest copy is
available from the GitHub repository for [virtualenv]. Install it to
`venv/bin/activate_this.py`.

[virtualenv]: https://github.com/pypa/virtualenv/blob/master/src/virtualenv/activation/python/activate_this.py

Now you need to create the WSGI file that will run the application for you.
Let's say you want to run your website content from `/srv/` and have set this up
in your Apache configuration (`/etc/apache2/apache2.conf`). Create the site
directory:

```bash
sudo mkdir /srv/rdamsc
sudo chown rdamsc:www-data /srv/rdamsc
```

Create a file `/srv/rdamsc/rdamsc.wsgi` with this content:

```python
activate_this = '/opt/rdamsc/venv/bin/activate_this.py'
with open(activate_this) as file_:
    exec(file_.read(), dict(__file__=activate_this))

from rdamsc import create_app
application = create_app()
```

If you are behind an HTTP proxy, you may need these lines as well:

```python
import os

os.environ['http_proxy'] = 'http://proxyURL'
os.environ['https_proxy'] = 'https://proxyURL'
```

Now create an Apache site (e.g. `/etc/apache2/sites-available/rdamsc.conf`) that
points to this file:

```apache
WSGIPassAuthorization On

<VirtualHost *:80>
    ServerName rdamsc.example.com

    WSGIDaemonProcess rdamsc user=rdamsc group=rdamsc threads=5
    WSGIScriptAlias / /srv/rdamsc/rdamsc.wsgi

    <Directory /srv/rdamsc>
        WSGIProcessGroup rdamsc
        WSGIApplicationGroup %{GLOBAL}
        Require all granted
    </Directory>
</VirtualHost>
```

If your system Python is not able to run the Catalog and you have to use the
version in your virtual environment, you will need an extra couple of lines at
the top (check the path for your environment):

```apache
LoadModule wsgi_module "/opt/rdamsc/venv/path/to/mod_wsgi...so"
WSGIPythonHome "/opt/rdamsc/venv"
```

You may also want extra lines to configure logging or SSL.

You should then configure the Catalog (see below, it deserves its own section)
before activating the site:

```bash
sudo a2ensite rdamsc
sudo a2dissite 000-default
sudo service apache2 graceful
```


## Configuring the Catalog

### Configuration files

The Catalog will look in the following places for configuration options, in the
following order:

 1. the default dictionary hard-coded into the `create_app` function;
 2. the file `instance/config.py`, unless a configuration dictionary is passed
    to the `create_app` function, in which case that is used instead.
 3. A file specified by the environment variable MSC_SETTINGS.

Settings are applied in the order they are discovered, so later ones override
earlier ones.

To set an environment variable on UNIX-like systems, you will need to include
the following line in your shell profile (or issue the command from the
command line):

 ```bash
 export MSC_SETTINGS=/path/to/config.py
 ```

On Windows, you can run the following from the command prompt.

 ```batchfile
 set MSC_SETTINGS=\path\to\config.py
 ```


### Security

To secure the installation, you must choose your own secret key and add it
to one of your configuration files, overriding the default one:

```python
SECRET_KEY = 'secret string'
```

To enable automatic updating from GitHub, you will also need to set up a
webhook key and record the path to the WSGI file (so it can be reloaded):

```python
WSGI_PATH = '/srv/rdamsc/rdamsc.wsgi'
WEBHOOK_SECRET = 'another secret string'
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
<https://rdamsc.bath.ac.uk>.


### Database files

The Catalog uses multiple NoSQL databases, which are saved to disk in the form
of JSON files. You can either supply pre-populated versions of these files, or
let the Catalog create them for you:

- **Main database** contains the tables for the schemes, tools, organisations,
  mappings, endorsements and the relationships between them.

  *Configuration key:* `MAIN_DATABASE_PATH`

  *Default location:* `instance/data/db.json`

- **Thesaurus database** contains the controlled vocabulary used for subject
  areas.

  *Configuration key:* `VOCAB_DATABASE_PATH`

  *Default location:* `instance/data/vocab.json`

- **Terms database** contains the controlled vocabulary used for data
  types, URL location types, ID schemes, and organisation and tool types.

  *Configuration key:* `TERM_DATABASE_PATH`

  *Default location:* `instance/data/terms.json`

- **User database** contains the users registered with the application.

  *Configuration key:* `USER_DATABASE_PATH`

  *Default location:* `instance/users/db.json`

- **Open ID Connect database** contains cached details for Open ID Connect
  providers.

  *Configuration key:* `OAUTH_DATABASE_PATH`

  *Default location:* `instance/oauth/db.json`

- **Open ID v2 folder** contains cached files for Open ID v2 authentication.

  *Configuration key:* `OPENID_FS_STORE_PATH`

  *Default location:* `instance/open-id/`

You can configure the names and locations of these files and the folder by
putting the respective paths in one of your configuration files:

```python
MAIN_DATABASE_PATH = os.path.join('path', 'to', 'file.json')
```

## Things to watch out for

The Dulwich library for working with Git is quite sensitive, and will not stage
any commits if a `gitignore` file (local or global) contains lines consisting
solely of space characters.

If you have problems with authenticating through a proxy, you may need to
install the `pycurl` library as well.


## Implementing maintenance mode in Apache (Debian-based style)

### Configuration

Place a standalone holding HTML page at, say, `/srv/rdamsc/maintenance.html`.

Add a file at, say, `/srv/rdamsc/exceptions.map` with a list of IP addresses
that should be allowed to see (i.e. test) the site during maintenance, putting
each one on its own line followed by `OK`:

```apache
192.168.0.1 OK
```

In `/etc/apache2/envvars`, add a definition to `APACHE_ARGUMENTS`. This is
normally commented out. If you are already using this for something, you'll
probably want two lines (one with the definition and one without) and toggle
between them:

```ini
    #export APACHE_ARGUMENTS='-D Maintenance'
```

Amend your site configuration to include the `Alias` line for the maintenance
page (so it bypasses WSGI) and the `IfDefine` blocks:

```apache
WSGIPassAuthorization On

<VirtualHost *:80>
    ServerName rdamsc.example.com

    Alias /maintenance.html /srv/rdamsc/maintenance.html

    WSGIDaemonProcess rdamsc user=rdamsc group=rdamsc threads=5
    WSGIScriptAlias / /srv/rdamsc/rdamsc.wsgi

    <Directory /srv/rdamsc>
        WSGIProcessGroup rdamsc
        WSGIApplicationGroup %{GLOBAL}
        Require all granted
    </Directory>/maintenance.html

    <IfDefine Maintenance>
        ErrorDocument 503 /maintenance.html

        # Set Retry-After on error pages:
        Header always set Retry-After 7200
        Header onsuccess unset Retry-After

        RewriteEngine on
        RewriteMap exceptions txt:/srv/rdamsc/exceptions.map

        # Allow individual IP addresses through:
        RewriteCond ${exceptions:%{REMOTE_ADDR}} =OK
        RewriteRule ^ - [L]

        # Otherwise redirect all traffic to the maintenance page:
        RewriteCond %{REQUEST_URI} !=/maintenance.html
        RewriteRule ^ - [R=503,L]
    </IfDefine>

    <IfDefine !Maintenance>
        # Redirect requests for maintenance page to home page:
        RewriteEngine on
        RewriteRule ^/maintenance/index.html$ / [R,L]
    </IfDefine>
</VirtualHost>
```


### Switching into Maintenance Mode

 1. Edit the file `/etc/apache2/envvars` so that the Maintenance line is active:

    ```ini
    export APACHE_ARGUMENTS='-D Maintenance'
    ```

 2. Stop and start the server (restarting it won't work properly):

    ```bash
    sudo apachectl graceful-stop
    sudo apachectl start
    ```


### Switching out of Maintenance Mode

 1. Edit the file `/etc/apache2/envvars` so that the Maintenance line is
    commented out:

    ```ini
    #export APACHE_ARGUMENTS='-D Maintenance'
    ```

 2. Stop and start the server:

    ```bash
    sudo apachectl graceful-stop
    sudo apachectl start
    ```
