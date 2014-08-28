import sys
import os
import time
import datetime
import sched
import sh
import shutil
import logging
import subprocess
from croniter import croniter
from repodeploy import repo


class Deployer:

	def __init__(self, config):

		self.log = logging.getLogger(__name__)

		self.config = config
		self.version = None

		self.identity = config['identity'] if 'identity' in config else None
		self.directory = os.path.abspath(config['directory']) if 'directory' in config else os.getcwd()
		self.action = config['action'] if 'action' in config else None

		self.versionfile = '%s/current.version' % self.directory
		self.currentdir = '%s/current' % self.directory
		self.workdir = '%s/work' % self.directory

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
			self.repository = repo.repository(config['repository'], self.workdir, self.config)
		except Exception as e:
			self.log.error('unable to initialize configuration repository: %s (%s)' % (config['repository'], e))
			sys.exit(1)

		if self.identity is None:
			self.log.error('no identity set, exiting')
			sys.exit(1)

		self.log.info('identity=%s' % self.identity)
		self.log.info('repository=%s' % self.repository.url)

	def run(self):

		scheduler = sched.scheduler(time.time, time.sleep)
		cron = croniter(self.config['schedule']) if 'schedule' in self.config else croniter('* * * * *')

		self.check_config()

		while True:
			try:
				scheduler.enterabs(cron.get_next(float), 1, self.check_config, ())
				scheduler.run()
			except KeyboardInterrupt as k:
				break
			except Exception as e:
				self.log.error("exception during update: %s" % e)
	
	def check_config(self):

		self.log.debug('checking for config updates')
		version = self.repository.current(self.identity)
		if version is not None:
			if version != self.version:
				self.log.info('updating to version %s' % version)
				self.update_config()
				self.log.info('update complete')
			else:
				self.log.debug('on latest version %s' % version)
			return True
		else:
			self.log.warn('no configuration found for identity: %s' % self.identity)
			return False

	def update_config(self):

		try:

			(version, directory) = self.repository.fetch(self.identity)

			if not directory:
				self.log.warn('update failed to properly unpack, skipping')
				return False

			# Pre-update scripts
			if not self.run_hooks(self.config['pre_hooks'], current=directory, previous=self.currentdir):
				self.log.warn('pre-update hooks failed, update blocked')
				return False

			save = None

			# Repository is link-safe, target directory does not change location
			if self.repository.link:
				# Repository probably changed, full reset
				if not os.path.islink(self.currentdir):
					shutil.rmtree(self.currentdir)
				else:
					save = os.path.realpath(self.currentdir)
				if save == directory:
					save = None
				else:
					sh.ln('-sfT', directory, self.currentdir)

			# Unpacked directories may move, need to copy instead of link
			else:
				save = '%s/config.save' % self.workdir
				# Repository probably changed, full reset
				if os.path.islink(self.currentdir):
					os.unlink(self.currentdir)
				elif os.path.exists(self.currentdir):
					self.move_contents(self.currentdir, save)
				self.move_contents(directory, self.currentdir)
				shutil.rmtree(directory)

			self.log.debug('activated configuration version: %s' % version)

			# Post-update scripts
			if not self.run_hooks(self.config['post_hooks'], current=self.currentdir, previous=save):
				if save and os.path.exists(save):
					self.log.warn('post-update hooks failed, reverting to previous configuration')
					if self.repository.link:
						target = os.path.realpath(self.currentdir)
						sh.ln('-sf', save, self.currentdir)
						# Should always be true at this point
						if target != save:
							shutil.rmtree(target)
					else:
						self.move_contents(save, self.currentdir)
						shutil.rmtree(save)
					# Re-run post-update hooks after revert
					if not self.run_hooks(self.config['post_hooks'], current=self.currentdir):
						self.log.error('post-update hooks failed after revert, application may be unstable')
				else:
					self.log.error('post-update hooks failed, application may be unstable')
				return False
			else:
				if save is not None and os.path.exists(save):
					shutil.rmtree(save)
				self.version = version
				with open(self.versionfile, 'w') as f:
					f.write(self.version)
				return True

		except Exception as e:
			self.log.error('could not update configuration: %s' % unicode(e))

		return False

	def move_contents(self, src, dest):
		"""
		Some apps resolve the final link when monitoring directories, so we
		can't just change symlinks, we need to move files.
		"""

		if not os.path.exists(dest):
			os.makedirs(dest)
		else:
			# Remove files in dest (if exists)
			destfiles = os.listdir(dest)
			if len(destfiles):
				sh.rm('-rf', *destfiles, _cwd=dest)

		# Move src files to dest
		srcfiles = os.listdir(src)
		if len(srcfiles):
			srcfiles.append(dest)
			sh.mv(*srcfiles, _cwd=src)

		return True

	def run_hooks(self, hook_dir, current=None, previous=None):
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
