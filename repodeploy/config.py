import requests
import socket
import logging


def parse(filename):

	config = {}

	with open(filename, 'r') as f:

		for line in f:
			if line[:1] == '#':
				continue
			(key, value) = line.split('=')
			config[key.strip()] = value.strip()

	return config

def instance_config(config):

	# Update with local instance data
	for update in (ec2_config, host_config):
		config = update(config)

	return config

def ec2_config(config):
	try:
		# Raises exception if non-existent, means we're not in EC2
		socket.gethostbyname('instance-data.ec2.internal')
		resp = requests.get('http://instance-data.ec2.internal/latest/user-data')
		try:
			json = resp.json()
			# Always override if user-data exists
			if u'identity' in json:
				config['identity'] = json[u'identity']
			if u'repository' in json:
				config['repository'] = json[u'repository']
		except Exception as e:
			logging.getLogger(__name__).error('Could not parse user-data: %s' % e)
	except Exception as e:
		pass
	return config

def host_config(config):
	# Fallback, only set if no ID is defined yet
	if 'identity' not in config:
		try:
			host = socket.getfqdn().split('.')
			host.reverse()
			config['identity'] = '.'.join(host)
		except:
			pass
	return config
