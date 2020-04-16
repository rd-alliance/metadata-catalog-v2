# Dependencies
# ============
# Standard
# --------
import os

# Non-standard
# ------------
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import g
# See https://flask-login.readthedocs.io/
from flask_login import current_user
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query, where
from tinydb.database import Document
from tinydb.operations import delete
from tinydb.storages import Storage, touch
# See https://www.dulwich.io/
from dulwich.repo import Repo
from dulwich.errors import NotGitRepository
import dulwich.porcelain as git


class JSONStorageWithGit(Storage):
    """Store the data in a JSON file and log the change in a Git repo.
    """

    def __init__(self, path, create_dirs=False, encoding='utf8', **kwargs):
        """Create a new instance.
        Also creates the storage file, if it doesn't exist.

        Arguments:
            path (str): Path/filename of the JSON data.
        """

        super(JSONStorageWithGit, self).__init__()
        # Create file if not exists
        touch(path, create_dirs=create_dirs)
        self.kwargs = kwargs
        self._handle = open(path, 'r+', encoding=encoding)
        # Ensure Git is configured properly
        git_repo = os.path.dirname(path)
        try:
            self.repo = Repo(git_repo)
        except NotGitRepository:
            self.repo = Repo.init(git_repo)
        self.filename = path
        basename = os.path.basename(path)
        self.name = os.path.splitext(basename)[0]

    @property
    def _refname(self):
        return b'refs/heads/master'

    def close(self):
        self._handle.close()

    def read(self):
        # Get the file size
        self._handle.seek(0, os.SEEK_END)
        size = self._handle.tell()

        if not size:
            # File is empty
            return None
        else:
            self._handle.seek(0)
            return json.load(self._handle)

    def write(self, data):
        # Write the json file
        self._handle.seek(0)
        serialized = json.dumps(data, **self.kwargs)
        self._handle.write(serialized)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.truncate()

        # Add file to Git staging area
        added, ignored = git.add(repo=self.repo, paths=[self.filename])

        # Avoid empty commits
        if not added:
            print("WARNING: Failed to stage changes to {}."
                  .format(self.filename))
            if ignored:
                print("DEBUG: Operation blocked by gitignore pattern.")
            return
        changes = 0
        for groupname, group in git.status(repo=self.repo)[0].items():
            changes += len(group)
        if not changes:
            return

        # Prepare commit information
        committer = 'MSCWG <{}>'.format(mscwg_email).encode('utf8')
        user = None
        if g:
            # This will either catch an API user or return None
            user = g.get('user', None)
        if current_user and current_user.is_authenticated:
            # If human user is logged in, use their record instead
            user = current_user
        if user:
            author = ('{} <{}>'.format(
                user['name'], user['email']).encode('utf8'))
            message = ('Update to {} from {}\n\nUser ID:\n{}'.format(
                self.name, user['name'], user['userid'])
                .encode('utf8'))
        else:
            author = committer
            message = ('Update to {}'.format(self.name).encode('utf8'))

        # Execute commit
        git.commit(self.repo, message=message, author=author,
                   committer=committer)
