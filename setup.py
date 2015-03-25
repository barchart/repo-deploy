from distutils.core import setup

setup(name='repo-deploy',
	description='Automatic code and configuration updates for continuous deployment environments',
	long_description="""
	Automates code and configuration deployment for continuous deployment environments by periodically
	polling a source repository for configuration changes (http, git, s3, etc). When changes are
	detected, the new files are retrieved and any locally configured update triggers are executed
	(in /etc/repo-deploy/*.d). This is intentionally separate from configuration management systems
	like Puppet in order to provide more flexible packaging and build process integration. The
	deployer can be configured to run as a daemon (with supervisord) or under cron (or Puppet
	agent.)
	""",
	author='Jeremy Jongsma',
	author_email='jeremy@barchart.com',
	url='https://github.com/barchart/repo-deploy',
	version='1.0.7',
	packages=['repodeploy'],
	scripts=['bin/repo-deploy'],
	data_files=[
		('/etc/repo-deploy', ['etc/repo-deploy.cfg']),
		('/etc/repo-deploy/pre-update.d', ['etc/pre-update.d/README']),
		('/etc/repo-deploy/post-update.d', ['etc/post-update.d/README'])
	],
	install_requires=['requests>=2.2.0', 'boto>=2.20.0', 'sh>=1.0', 'croniter>=0.3.5', 'dirsync>=2.1'])
