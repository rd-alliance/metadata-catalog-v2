# Dependencies
# ============
# Standard
# --------
import re
import typing as t
import unicodedata
import urllib.parse

# Non-standard
# ------------
from flask import url_for
from tinydb import Query
from wtforms import Field


# General data handling
# =====================
class Pluralizer:
    """Class for pluralizing nouns. Example uses:

        '{:N corp/us/era}'.format(Pluralizer(0))
        '{:N scheme/s}'.format(Pluralizer(1))
        '{:N sheep}'.format(Pluralizer(2))

    From http://stackoverflow.com/a/27642538
    """

    def __init__(self, value: int):
        self.value = value

    def __format__(self, formatter: str) -> str:
        formatter = formatter.replace("N", str(self.value))
        start, _, suffixes = formatter.partition("/")
        singular, _, plural = suffixes.rpartition("/")

        return "{}{}".format(start, singular if self.value == 1 else plural)


# Utilities used in templates
# ===========================
def to_url_slug(string: str) -> str:
    """Transforms string into URL-safe slug."""
    slug = urllib.parse.quote_plus(string)
    return slug


def from_url_slug(slug: str) -> str:
    """Transforms URL-safe slug back into regular string."""
    string = urllib.parse.unquote_plus(slug)
    return string


def url_for_subject(subject: str) -> str:
    """Wrapper around flask.url_for that additionally escapes slashes in
    the subject name. The escaping has no effect on the routing in Flask,
    but is a visual clue that the slash is not intended as a path segment
    separator.
    """
    return url_for("search.subject", subject=subject.replace("/", "%2F")).replace(
        "%252F", "%2F"
    )


def has_day(isodate: str) -> bool:
    """Returns true if ISO date has a day component."""
    return isodate.count("-") == 2


def is_list(obj: object) -> bool:
    """Returns true if object is a list. Principle use is to determine if a
    field has undergone validation: unvalidated field.errors is a tuple,
    validated field.errors is a list."""
    return isinstance(obj, list)


# Utilities used in data
# ======================
def clean_error_list(field: Field) -> t.List[str]:
    """Extracts all errors from a Field as a flat list."""
    seen_errors = set()
    for error in field.errors:
        if isinstance(error, list):
            for sub_error in error:
                seen_errors.add(sub_error)
        else:
            seen_errors.add(error)
    return list(seen_errors)


def to_file_slug(string: str, callback: t.Callable[[Query], list]) -> str:
    """Transforms string into a new slug for use when decomposing the
    database to individual files. The callback should be the search
    method of a TinyDB table, and will be used to ensure that the
    returned slug does not already exist in that table.
    """
    # Put to lower case, turn spaces to hyphens
    slug = string.strip().lower().replace(" ", "-")
    # Fixes for problem entries
    slug = unicodedata.normalize("NFD", slug)
    slug = slug.encode("ascii", "ignore")
    slug = slug.decode("utf-8")
    # Strip out non-alphanumeric ASCII characters
    slug = re.sub(r"[^-A-Za-z0-9_]+", "", slug)
    # Remove duplicate hyphens
    slug = re.sub(r"-+", "-", slug)
    # Truncate
    slug = slug[:71]

    # Ensure uniqueness within table
    i = ""
    while callback(Query().slug == (slug + str(i))):
        if i == "":
            i = 1
        else:
            i += 1
    else:
        return slug


def wild_to_regex(string: str) -> str:
    """Transforms wildcard syntax into regular expression syntax."""
    regex = re.escape(string)
    regex = regex.replace(r"\*", ".*")
    regex = regex.replace(r"\?", ".")
    return regex
