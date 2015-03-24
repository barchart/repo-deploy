import boto
import os
import sh
import shutil
import logging
import requests
import hashlib
from urlparse import urlparse
from repodeploy import config


def repository(url, work_dir, *args):

    repositories = {
        's3': S3Repository,
        'http': HttpRepository,
        'https': HttpRepository,
        'git+ssh': GitRepository,
        'git+http': GitRepository,
        'git+https': GitRepository
    }

    try:
        parsed = urlparse(url)
        if parsed.scheme in repositories:
            return repositories[parsed.scheme](url, work_dir, *args)
        elif parsed.path.find('.git') > -1:
            return GitRepository(url, work_dir, *args)
    except Exception as e:
        raise Exception('Unable to create repository: %s (%s)' % (url, e))

    return None


class Repository(object):
    
    def __init__(self, url, work_dir, cfg):
        self.url = url
        self.work_dir = work_dir
        self.config = cfg
        self.log = logging.getLogger(__name__)
        self.link = False

    def current(self, path):
        """
        Check the current configuration version from the repository to see if we need to update
        """
        raise NotImplemented()

    def fetch(self, path):
        """
        Fetch the resource at the specified path and return the local file or directory
        representing it in the working directory.
        """
        raise NotImplemented()

    def workdir(self, name, remove=False):
        d = '%s/%s' % (self.work_dir, name)
        if os.path.exists(d) and remove:
            shutil.rmtree(d)
        if not os.path.exists(d):
            os.makedirs(d)
        return d
    
class S3Repository(Repository):

    def __init__(self, url, work_dir, cfg):

        super(S3Repository, self).__init__(url, work_dir, cfg)

        parsed = urlparse(url)
        self.bucket = parsed.hostname
        self.path = parsed.path

        if 'aws-access-key' in cfg:
            self.s3 = boto.connect_s3(cfg['aws-access-key'], cfg['aws-secret-key'])
        elif os.path.exists(os.path.expanduser('~/.amazon/account-key')):
            credentials = config.parse(os.path.expanduser('~/.amazon/account-key'))
            self.s3 = boto.connect_s3(credentials['accessKey'], credentials['secretKey'])
        else:
            self.s3 = boto.connect_s3()

    def current(self):

        key = self.key(self.path)

        if key is not None:
            return key.etag.strip('"')

        return None

    def fetch(self):

        cache = self.workdir('cache', True)
        key = self.key(self.path)

        if key is not None:

            outfile = '%s/%s' % (cache, os.path.basename(key.name))

            with open(outfile, 'w') as f:
                key.get_file(f)

            unpack_dir = self.workdir('unpacked', True)
            sh.unzip(outfile, _cwd=unpack_dir)
            return (key.etag.strip('"'), unpack_dir)

            raise Exception("Unable to unpack archive format '%s'" % ext)

        return (None, cache)

    def key(self, path):

        bucket = self.s3.get_bucket(self.bucket, validate=False)

        try:
            return bucket.get_key(path)
        except:
            return None

class HttpRepository(Repository):

    def __init__(self, url, work_dir, cfg):
        super(HttpRepository, self).__init__(url, work_dir, cfg)

    def current(self):
        return self.key(requests.head(self.url))

    def key(self, response):
        if 'etag' in response.headers:
            return response.headers['etag'].strip('"')
        else:
            m = hashlib.md5()
            m.update(response.headers['content-length'])
            if 'last-modified' in response.headers:
                m.update('/')
                m.update(response.headers['last-modified'])
            return m.hexdigest()

    def fetch(self):

        cache = self.workdir('cache', True)
        r = requests.get(self.url, stream=True)

        if r.status_code == 200:

            outfile = '%s/latest.zip' % cache

            with open(outfile, 'w') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)

            unpack_dir = self.workdir('unpacked', True)
            sh.unzip(outfile, _cwd=unpack_dir)
            return (self.key(r), unpack_dir)

            raise Exception("Unable to unpack archive format '%s'" % ext)

        return (None, cache)

class GitRepository(Repository):

    def __init__(self, url, work_dir, cfg):
        super(GitRepository, self).__init__(url, work_dir, cfg)

        # Should use symlinks instead of moving since directory location isn't change
        self.link = True

        self.remote = url
        self.prefix = ''
        self.branch = 'master'

        if not url.endswith('.git'):
            pos = url.rfind('.git') + 4
            self.remote = url[:pos]
            self.prefix = url[pos:]

        if '#' in self.prefix:
            prefix = self.prefix
            pos = prefix.rfind('#') + 1
            self.prefix = prefix[:pos]
            self.branch = prefix[pos:]

        self.staging = self.workdir('git-work')
        self.local = self.workdir('git')

    def pull(self, directory):

        # Check for repository location change
        if os.path.exists('%s/%s' % (directory, '.git')):
            # Oh this will probably explode horribly at some point
            remote = str(sh.git('remote', '-v')).split('\n')[0].split('\t')[1].split(' ')[0]
            if remote != self.remote:
                # Location changed, wipe out and start again
                shutil.rmtree(directory)

        if not os.path.exists('%s/%s' % (directory, '.git')):
            # Fresh clone
            out = sh.git('clone', '-b', self.branch, '--single-branch', self.remote, directory, _cwd=os.path.dirname(directory))
            if out.exit_code != 0:
                raise Exception(str(out))
        else:
            # Ensure we revert to last good state (in case of moved files)
            out = sh.git('checkout', self.branch, _cwd=directory)
            if out.exit_code != 0:
                raise Exception(str(out))
            out = sh.git('checkout', '.', _cwd=directory)
            if out.exit_code != 0:
                raise Exception(str(out))
            # Update from remote
            out = sh.git('pull', _cwd=directory)
            if out.exit_code != 0:
                raise Exception(str(out))

        # Update any submodules
        out = sh.git('submodule', 'update', '--init', '--recursive', _cwd=directory)
        if out.exit_code != 0:
            raise Exception(str(out))

        # Parse latest revision from git
        return str(sh.git('rev-parse', 'HEAD', _cwd=directory)).strip()

    def current(self):
        version = self.pull(self.staging)
        path = '%s%s' % (self.staging, self.prefix)
        if os.path.exists(path):
            return version
        return None

    def fetch(self):
        version = self.pull(self.local)
        path = '%s%s' % (self.local, self.prefix)
        if os.path.exists(path):
            return (version, path)
        return (None, None)
