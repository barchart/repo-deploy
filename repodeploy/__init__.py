import sys
import os
import time
import datetime
import sched
import sh
import shutil
import logging
import subprocess
import re
from croniter import croniter
from repodeploy import repo
from dirsync import sync


class Deployer:

    def __init__(self, config):

        self.log = logging.getLogger(__name__)

        self.config = config
        self.version = None

        self.versionfile = '%s/current.version' % self.config['cache']
        self.currentdir = os.path.abspath(config['local'])
        self.workdir = '%s/work' % self.config['cache']

        # Create work dir
        if not os.path.exists(self.workdir):
            os.makedirs(self.workdir)

        # Create current config if nonexistent
        if not os.path.lexists(self.currentdir):
            os.makedirs(self.currentdir)
        elif os.path.exists(self.versionfile):
            with open(self.versionfile, 'r') as f:
                version = f.readline().strip()
                if version is not None:
                    self.version = version

        try:
            self.repository = repo.repository(config['remote'], self.workdir, self.config)
        except Exception as e:
            self.log.error('unable to initialize remote repository: %s (%s)' % (config['remote'], e))
            sys.exit(1)

        self.log.info('remote=%s' % re.sub(r'//[^:]*:[^@]*@', '//*****:*****@', self.repository.url))

    def run(self):

        scheduler = sched.scheduler(time.time, time.sleep)
        cron = croniter(self.config['schedule']) if 'schedule' in self.config else croniter('* * * * *')

        try:
            self.check_repo()
        except Exception as e:
            self.log.error("exception during update: %s" % e)

        while True:
            try:
                scheduler.enterabs(cron.get_next(float), 1, self.check_repo, ())
                scheduler.run()
            except KeyboardInterrupt as k:
                break
            except Exception as e:
                self.log.error("exception during update: %s" % e)
    
    def check_repo(self):

        self.log.debug('checking for repository updates')
        version = self.repository.current()
        if version is not None:
            if version != self.version:
                self.log.info('updating to version %s' % version)
                self.update_repo()
                self.log.info('update complete')
            else:
                self.log.debug('on latest version %s' % version)
            return True
        else:
            self.log.warn('no repository found')
            return False

    def update_repo(self):

        try:

            (version, directory) = self.repository.fetch()

            if not directory:
                self.log.warn('update failed to properly unpack, skipping')
                return False

            # Pre-update scripts
            if not self.run_hooks(self.config['pre_hooks'], current=directory, previous=self.currentdir):
                self.log.warn('pre-update hooks failed, update blocked')
                return False

            save = '%s/repository.save' % self.workdir
            if os.path.exists(self.currentdir):
                self.log.debug('saving rollback to %s' % save)
                self.sync_dirs(self.currentdir, save)
            self.log.debug('syncing %s to %s' % (directory, self.currentdir))
            self.sync_dirs(directory, self.currentdir)

            self.log.debug('activated repository version: %s' % version)

            # Post-update scripts
            if not self.run_hooks(self.config['post_hooks'], current=self.currentdir, previous=save):
                if save and os.path.exists(save):
                    self.log.warn('post-update hooks failed, rollback to previous version')
                    self.sync_dirs(save, self.currentdir)
                    # Re-run post-update hooks after rollback
                    if not self.run_hooks(self.config['post_hooks'], current=self.currentdir):
                        self.log.error('post-update hooks failed after rollback, application may be unstable')
                else:
                    self.log.error('post-update hooks failed, application may be unstable')
                return False
            else:
                self.version = version
                with open(self.versionfile, 'w') as f:
                    f.write(self.version)
                return True

        except Exception as e:
            self.log.error('could not update repository: %s' % unicode(e))

        return False

    def sync_dirs(self, src, dest):
        sync(src, dest, 'sync', exclude=['^\.git$', '^\.git/.*'], logger=logging.getLogger('%s.dirsync' % __name__), create=True, purge=True)

    def run_hooks(self, hook_dir, current=None, previous=None):
        if os.path.exists(hook_dir):
            for script in os.listdir(hook_dir):
                full = '%s/%s' % (hook_dir, script)
                if os.access(full, os.X_OK):
                    self.log.info('running update hook: %s' % full)
                    # Pass in current/previous config directories
                    env = os.environ.copy()
                    env['CURRENT_CONFIG'] = current if current else ''
                    env['PREVIOUS_CONFIG'] = previous if previous else ''
                    p = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
                    (out, err) = p.communicate()
                    if p.returncode > 0:
                        for line in out.split('\n'):
                            if line:
                                self.log.warn(line)
                        return False
        return True
