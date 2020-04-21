# Dependencies
# ============
# Standard
# --------
import re
import unicodedata
import urllib.parse


# General data handling
# =====================
class Pluralizer:
    """Class for pluralizing nouns. Example uses:

        '{:N corp/us/era}'.format(Pluralizer(0))
        '{:N scheme/s}'.format(Pluralizer(1))
        '{:N sheep}'.format(Pluralizer(2))

    From http://stackoverflow.com/a/27642538
    """
    def __init__(self, value):
        self.value = value

    def __format__(self, formatter):
        formatter = formatter.replace("N", str(self.value))
        start, _, suffixes = formatter.partition("/")
        singular, _, plural = suffixes.rpartition("/")

        return "{}{}".format(start, singular if self.value == 1 else plural)


# Utilities used in templates
# ===========================
def to_url_slug(string):
    """Transforms string into URL-safe slug."""
    slug = urllib.parse.quote_plus(string)
    return slug


def from_url_slug(slug):
    """Transforms URL-safe slug back into regular string."""
    string = urllib.parse.unquote_plus(slug)
    return string


def abbrev_url(url):
    """Extracts last component of URL path. Useful for datatype URLs."""
    url_tuple = urllib.parse.urlparse(url)
    path = url_tuple.path
    if not path:
        return url
    path_fragments = path.split("/")
    if not path_fragments[-1] and len(path_fragments) > 1:
        return path_fragments[-2]
    return path_fragments[-1]


def parse_date_range(string):
    date_split = string.partition('/')
    if date_split[2]:
        return (date_split[0], date_split[2])
    return (string, None)


# Utilities used in data
# ======================
def to_file_slug(string):
    """Transforms string into slug for use when decomposing the database to
    individual files.
    """
    # Put to lower case, turn spaces to hyphens
    slug = string.strip().lower().replace(' ', '-')
    # Fixes for problem entries
    slug = unicodedata.normalize('NFD', slug)
    slug = slug.encode('ascii', 'ignore')
    slug = slug.decode('utf-8')
    # Strip out non-alphanumeric ASCII characters
    slug = re.sub(r'[^-A-Za-z0-9_]+', '', slug)
    # Remove duplicate hyphens
    slug = re.sub(r'-+', '-', slug)
    # Truncate
    slug = slug[:71]
    return slug
