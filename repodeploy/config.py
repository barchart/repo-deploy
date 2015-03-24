import requests
import socket
import logging
import os


def parse(filename):

    config = {}

    if os.path.exists(filename):

        with open(filename, 'r') as f:

            for line in f:
                if line[:1] == '#':
                    continue
                (key, value) = line.split('=')
                config[key.strip()] = value.strip()

    return config

def value(cfg, name, envvar=None, arg=None, default=None):
    if arg:
        return arg
    if name in cfg and cfg[name]:
        return cfg[name]
    if envvar in os.environ and os.environ[envvar]:
        return os.environ[envvar]
    return default
