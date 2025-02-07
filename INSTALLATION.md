# Installing and running the Metadata Standards Catalog

## Pre-requisite software

The Metadata Standards Catalog is written in [Python 3], requiring version 3.10
or newer, so as a first step this will need to be installed on your machine.

You will also need quite a few additional packages from PyPI, so it is strongly
recommended that you install the Catalog into an isolated virtual environment.
The methods below make this especially quick and easy.

[Python 3]: https://www.python.org/

## Installation

### Installing in a container using cloud-init

A [YAML configuration] is provided to automate the process of initializing the
Catalog in a Linux container. This is especially useful if you want to test how
the code runs under a version of Python different from the one you have
installed. These instructions use [LXD] but the equivalent steps should work
with [Incus].

[YAML configuration]: rdamsc-init.yaml
[LXD]: https://canonical.com/lxd
[Incus]: https://linuxcontainers.org/incus/
[linuxcontainers public image server]: https://images.linuxcontainers.org
[hosts file]: https://en.wikipedia.org/wiki/Hosts_(file)
[backup of the live data]: https://github.com/rd-alliance/metadata-catalog-data/tree/master/backup

 1. By default with these instructions, the Web GUI will be served from the
    domain `rdamsc.internal`. If you want to use a different domain name, copy
    `rdamsc-init.yaml` to `my-rdamsc-init.yaml` (this will be ignored by Git)
    and change the `Server Name` directive at around line 14 to use your chosen
    domain.

 2. Create a new container using an image that is Debian-based and supports
    `cloud-init`. (The Ubuntu images provided by Canonical are suitable. If you
    are choosing from the [linuxcontainers public image server], the ‘cloud’
    variants support `cloud-init`.) An Ubuntu one is given here as an example:

    ```bash
    lxc init ubuntu:24.04 rdamsc
    ```

 3. Configure the container using the YAML configuration, either
    `rdamsc-init.yaml` or `my-rdamsc-init.yaml` depending on what you decided in
    step 1:

    ```bash
    cat rdamsc-init.yaml | lxc config set rdamsc user.user-data -
    ```

 4. Start the image, then log into it:

    ```bash
    lxc start rdamsc
    lxc shell rdamsc
    ```

    (If using Incus, try `incus shell` as `incus console` is different.)

 5. In the container's shell, check that the setup completed successfully:

    ```bash
    cloud-init status --wait
    # Should end up saying "status: done"
    ```

    The automated installation simulates a production instance, including
    the steps given below for running in production and implementing
    maintenance mode.

 6. If you want to view the Web GUI, add its domain (`rdamsc.internal` by
    default) and the container's IP address to your computer's
    [hosts file].

 7. The testing apparatus is not automatically installed. To install it,
    you will need to do a few final steps in the container's shell:

    ```bash
    cd ~rdamsc
    sudo -su rdamsc
    . venv/bin/activate
    pip install -r requirements.txt -e ".[dev]"
    # This would be a good point to run the test suite. When finished...
    deactivate
    exit
    ```

 8. Take a snapshot so you can revert to a clean state after trying a
    few things out:

    ```bash
    lxc snapshot rdamsc clean
    ```

    Depending on your use case, you may want to copy over the latest
    [backup of the live data] and take another snapshot.

 9. To remove the container, run these commands outside the container:

    ```bash
    lxc stop rdamsc
    lxc delete rdamsc
    ```


### Installing manually

Use `git clone` as normal to get a copy of this code folder where you want it on
your file system, then enter the folder on the command line.

Set up a virtual environment (you might need an additional package for this on a
*nix system):

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

Optionally, upgrade your sandboxed copy of `pip` and install `wheel`:

```bash
pip install --upgrade pip
pip install wheel
```

Install the Catalog and its dependencies to your virtual environment. In a
development context:

```bash
pip install -r requirements.txt -e ".[dev]"
```

In production, you don't need the unit testing apparatus:

```bash
pip install -r requirements.txt -e .
```


### Running unit tests

See the [Guide for Contributors](CONTRIBUTING.md) for how to run the unit tests.


### Running a development version

Run the application like this to get development mode:

```bash
# *nix
export FLASK_APP=rdamsc; flask --debug run
# Windows
set FLASK_APP=rdamsc
flask --debug run
# Windows Powershell
$env:FLASK_APP = "rdamsc"
flask --debug run
```

(You may need to give the path to the executable in the virtual environment,
e.g. `venv/bin/flask`).

You will get feedback on the command line about what URL to use to access the
application.


### Running in production using mod_wsgi on Apache

These instructions are one way to go about using the Catalog in production.
For other options, please refer to the [deployment options] documented by the
Flask developers.

[deployment options]: https://flask.palletsprojects.com/en/stable/deploying/

On the Web server, let's assume for example that you have installed the
application using the above instructions in `/opt/rdamsc`.

These instructions are for `mod_wsgi` on Apache, so these need to be installed.
On Debian or a derivative like Ubuntu, you'd do this:

```bash
sudo apt install apache2 libapache2-mod-wsgi-py3
```

If you need to use a version of Python that is not the system default, and a
pre-compiled `mod_wsgi` is not available for it, then as well as the `python3.x`
and `python3.x-venv` you'd need to get this far, you will also need to install
`python3.x-dev` and `apache2-dev`.

It is recommended that you set up a non-privileged system user to run the
Catalog (say, `rdamsc`) and that this user and the Apache user (`www-data` on
Debian-based Linux distros) are in each other's groups. Be sure to assign
ownership of the source code directory to this user. Example:

```bash
sudo adduser --system --group rdamsc
sudo usermod -aG www-data rdamsc
sudo usermod -aG rdamsc www-data
sudo chown -R rdamsc:www-data /opt/rdamsc
```

You should create an instance folder where the Catalog can keep its data. The
canonical location would be `/var/opt/rdamsc` but you can choose another one:

```bash
sudo mkdir /var/opt/rdamsc
sudo chown rdamsc:www-data /var/opt/rdamsc
```

You can now switch to the `rdamsc` user:

```bash
sudo -Hsu rdamsc
```

Configure the Catalog to use this folder explicitly by changing the `app`
assignment line in `rdamsc/__init__.py` to include the information:

```python
# Create the app:
app = Flask(__name__, instance_relative_config=True, instance_path='/var/opt/rdamsc')
```

Commit this change so Git can reapply it over any other code changes. Doing
this as your newly created user, you will need to configure Git at the same
time:

```bash
git config --global user.name "RDA MSCWG"
git config --global user.email "rdamsc@localhost"
git add rdamsc/__init__.py
git commit -m "Update production instance path"
```

If a pre-compiled WSGI mod is not available for the Python you used in the
virtual environment, then you can compile a matching version in your virtual
environment at this point:

```bash
. venv/bin/activate
pip install mod_wsgi
deactivate
```

Now you need to create the WSGI file that will run the application for you.
Let's say you want to run your website content from `/srv/` and have set this up
in your Apache configuration (`/etc/apache2/apache2.conf`). Create the site
directory:

```bash
exit
sudo mkdir /srv/rdamsc
sudo chown rdamsc:www-data /srv/rdamsc
```

The `srv` folder in this repository has a ready-made `rdamsc.wsgi` file you can
copy to the directory you just created. Ensure that it is writeable by the
`rdamsc` user. Alternatively, as the `rdamsc` user, create the file
`/srv/rdamsc/rdamsc.wsgi` with this content:

```python
from rdamsc import create_app
application = create_app()
```

If you are behind an HTTP proxy, you may need to add (or uncomment) these lines
as well, remembering to provide the actual proxy URLs:

```python
import os

os.environ['http_proxy'] = 'http://proxyURL'
os.environ['https_proxy'] = 'https://proxyURL'
```

Now create an Apache site (e.g. `/etc/apache2/sites-available/rdamsc.conf`) that
points to this file. If your system Python and WSGI Apache plugin can run the
application use something like this (check the path for your virtual
environment):

```apache
WSGIPassAuthorization On

<VirtualHost *:80>
    ServerName rdamsc.example.com

    WSGIDaemonProcess rdamsc user=rdamsc group=rdamsc threads=5 python-home=/opt/rdamsc/venv
    WSGIScriptAlias / /srv/rdamsc/rdamsc.wsgi

    AllowEncodedSlashes NoDecode

    <Directory /srv/rdamsc>
        WSGIProcessGroup rdamsc
        WSGIApplicationGroup %{GLOBAL}
        Require all granted
    </Directory>
</VirtualHost>
```

If you compiled a custom WSGI module in your virtual environment, you will need
an extra line at the top of this file to use it:

```apache
LoadModule wsgi_module "/opt/rdamsc/venv/path/to/mod_wsgi...so"
```

You may also want extra lines to configure logging, SSL or proxies.

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
    to the `create_app` function, in which case that is used instead. (The
    `instance` folder may be overridden as well, as in the instructions for
    production use above.)
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
<https://rdamsc.bath.ac.uk>. If you want to be able to log into an instance
hosted elsewhere, you will have to register that instance separately with one
of the supported providers. You should be able to register instances running
on localhost (127.0.0.1) for testing purposes.


### Database files

The Catalog uses multiple NoSQL databases, which are saved to disk in the form
of JSON files. You can either supply pre-populated versions of these files,
(for example, using the latest [backup of the live data]) or let the
Catalog create them for you:

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


## Updating the installation

To update the installed code, navigate to the working directory and pull in the
changes:

```bash
sudo -Hsu rdamsc
git pull --rebase
```

It is a good idea to update dependencies periodically as well:

```bash
. venv/bin/activate
pip install -U --upgrade-strategy eager -r requirements.txt
deactivate
```

Finally, reload the site:

```bash
touch /srv/rdamsc/rdamsc.wsgi
exit
```


## Implementing maintenance mode in Apache (Debian-based style)

### Configuration

Place a standalone holding HTML page at, say, `/srv/rdamsc/maintenance.html`.

Add a file at, say, `/srv/rdamsc/exceptions.map` with a list of IP addresses
that should be allowed to see (i.e. test) the site during maintenance, putting
each one on its own line followed by `OK`:

```apache
192.168.0.1 OK
```

Examples of both these files are provided in the `srv` folder in this
repository.

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

    WSGIDaemonProcess rdamsc user=rdamsc group=rdamsc threads=5 python-home=/opt/rdamsc/venv
    WSGIScriptAlias / /srv/rdamsc/rdamsc.wsgi

    AllowEncodedSlashes NoDecode

    <Directory /srv/rdamsc>
        WSGIProcessGroup rdamsc
        WSGIApplicationGroup %{GLOBAL}
        Require all granted
    </Directory>

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
        RewriteRule ^/maintenance.html$ / [R,L]
    </IfDefine>
</VirtualHost>
```

### Warning about future maintenance

To add a warning message about an upcoming period of downtime, add the start
date and time of the downtime to your instance configuration file:

```python
MAINTENANCE_START = "2020-02-02T20:20:20"
```

The value must be a valid ISO 8601 date that can be parsed by Python's
[`datetime.fromisoformat()`][fromiso] method; note that more patterns are
supported in Python 3.11+ than in 3.7–3.10 so check the documentation for the
version of Python you are using. The date will be converted to UTC, thus it is
a good idea to specify the timezone so this works correctly.

[fromiso]: https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat

It is also a good idea to set an end date and time as well:

```python
MAINTENANCE_END = "2020-02-02T22:20:20"
```

This will add some detail to the warning message and remove it once the
specified time has passed.

Force a reload of the application for these settings to take effect by doing
*one* of the following:

```bash
sudo systemctl restart apache2
sudo apachectl restart
sudo -u rdamsc touch /srv/rdamsc/rdamsc.wsgi
```

These settings do not currently affect the behaviour of the Catalog beyond the
warning message, but might do in future.

### Switching into Maintenance Mode

 1. Edit the file `/etc/apache2/envvars` so that the Maintenance line is active:

    ```ini
    export APACHE_ARGUMENTS='-D Maintenance'
    ```

 2. Stop and start the server:

    ```bash
    sudo systemctl restart apache2
    ```

    or if not running systemd:

    ```bash
    sudo apachectl graceful-stop
    sudo apachectl start
    ```

    (The reason for doing a stop and start here is that an `apachectl restart`
    does not shut down the parent `apache` process. A fresh start is needed to
    pick up the change in arguments.)

### Switching out of Maintenance Mode

 1. Edit the file `/etc/apache2/envvars` so that the Maintenance line is
    commented out:

    ```ini
    #export APACHE_ARGUMENTS='-D Maintenance'
    ```

 2. Stop and start the server:

    ```bash
    sudo systemctl restart apache2
    ```

    or if not running systemd:

    ```bash
    sudo apachectl graceful-stop
    sudo apachectl start
    ```
