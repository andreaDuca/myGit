import argparse
import collections
import configparser
from datetime import datetime
import grp, pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

argparser = argparse.ArgumentParser(description="The stupidest content tracker")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
#  required to write the command name
argsubparsers.required = True

#  an subparser for init command args
argsp = argsubparsers.add_parser("init", help = "Inizialize a new empty myGit repository.")
argsp.add_argument("path", metavar = "directory", nargs = "?", default = ".", help = "where to create the repository.")

def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        case "add"          : cmd_add(args)
        case "cat-file"     : cmd_cat_file(args)
        case "check-ignore" : cmd_check_ignore(args)
        case "checkout"     : cmd_checkout(args)
        case "commit"       : cmd_commit(args)
        case "hash-object"  : cmd_hash_object(args)
        case "init"         : cmd_init(args)
        case "log"          : cmd_log(args)
        case "ls-files"     : cmd_ls_files(args)
        case "ls-tree"      : cmd_ls_tree(args)
        case "rev-parse"    : cmd_rev_parse(args)
        case "rm"           : cmd_rm(args)
        case "show-ref"     : cmd_show_ref(args)
        case "status"       : cmd_status(args)
        case "tag"          : cmd_tag(args)
        case _              : print("Bad command.")

class GitRepository(object):
    worktree = None
    gitdir = None
    conf = None


    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception("Not a Git repository %s" % path)

        # Read configuration file in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception("Unsupported repositoryformatversion %s" % vers)

class GitObject (object):

    def __init__(self, data=None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self, repo):
        """This function MUST be implemented by subclasses.

It must read the object's contents from self.data, a byte string, and do
whatever it takes to convert it into a meaningful representation.  What exactly that means depend on each subclass."""
        raise Exception("Unimplemented!")

    def deserialize(self, data):
        raise Exception("Unimplemented!")

    def init(self):
        pass


def object_read(repo, sha):
    """Read object sha from Git repository repo.  Return a
    GitObject whose exact type depends on the object."""

    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    if not os.path.isfile(path):
        return None

    # open and read binary
    with open (path, "rb") as f:
        raw = zlib.decompress(f.read())

        # Read object type (es. commit), from 0 to index of first withe space
        spaceIndex = raw.find(b' ')
        bType = raw[0:spaceIndex]

        # Read and validate object size, from withe space to null
        nullIndex = raw.find(b'\x00', spaceIndex)
        size = int(raw[spaceIndex:nullIndex].decode("ascii"))
        if size != len(raw)-nullIndex-1:
            raise Exception("Malformed object {0}: bad length".format(sha))

        # Pick constructor
        match bType:
            case b'commit' : type=GitCommit
            case b'tree'   : type=GitTree
            case b'tag'    : type=GitTag
            case b'blob'   : type=GitBlob
            case _:
                raise Exception("Unknown type {0} for object {1}".format(bType.decode("ascii"), sha))

        # Call constructor and return object, without file header
        return type(raw[nullIndex+1:])

def object_write(obj, repo=None):
    # Serialize object data
    data = obj.serialize()
    # Add header: (binary) type+space+DataSize+null + data
    result = obj.bType + b' ' + str(len(data)).encode() + b'\x00' + data
    # Compute hash
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        # Compute path
        path=repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            with open(path, 'wb') as f:
                # Compress and write
                f.write(zlib.compress(result))
    return sha



class GitBlob(GitObject):
    bType=b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data   


def repo_path(repo, *path):
    """Compute path under repo's gitdir."""
    return os.path.join(repo.gitdir, *path)


def repo_file(repo, *path, mkdir=False):
    """Same as repo_path, but create dirname(*path) if absent.  For
        example, repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\") will create
        .git/refs/remotes/origin."""

    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)


def repo_dir(repo, *path, mkdir=False):
    """Same as repo_path, but mkdir *path if absent if mkdir."""

    path = repo_path(repo, *path)

    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception("Not a directory %s" % path)

    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None

def repo_default_config():
    ret = configparser.ConfigParser()

    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")

    return ret

#create a new repo at path
def repo_create(path):
    repo = GitRepository(path,True)

    # the path must exist and to be empty
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception("Not a directory %s" % path)
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception("is not empty %s" % path)
    else:
        os.makedirs(repo.worktree)

    # must create and init some dir
    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo,"objects", mkdir=True)
    assert repo_dir(repo,"refs", "tags", mkdir=True)
    assert repo_dir(repo,"refs", "heads", mkdir=True)

    #init .git/HEAD
    with open(repo_file(repo, "HEAD"), "w") as file:
        file.write("refs/heads/master\n")

    #.git/description
    with open(repo_file(repo, "descriptio"), "w") as file:
        file.write("Unnamed repository; edit this file 'description' to edit the name")

    with open(repo_file(repo, "config"), "w") as file:
        config = repo_default_config()
        config.write(file)

    return repo

#  bridge function for init
def cmd_init(args):
    repo_create(args.path)

def repo_find(path = ".", required = True):
    path = os.path.relpath(path)

    # if this is a directory with .git file, then it's the repository
    if os.path.isdir(path +  ".git"):
        return GitRepository(path)

    # back to /
    parent = os.path.realpath(os.path.join(path, ".."))
    # if not found
    if parent == path:
        if required:
            raise Exception("No git directory")
        else:
            return None

    return repo_find(parent, required)
