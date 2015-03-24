## repo-deploy

Polls a central application configuration repository for application
configuration and code updates.

The result of this polling is a directory of arbitrary application files,
which the application container installed on the server image is
expected to monitor for updates.

The directory to monitor is located at `${deployDir}/current`. By
default, this resolves to `/var/deploy/current`. Alternate
locations can be specified in `/etc/repo-deploy/repo-deploy.cfg`.

You can install repo-deploy from PyPI:

```
pip install repo-deploy
```

### Command line parameters

```
usage: repo-deploy [-h] [-c CONFIG] [--pre-hooks PRE_HOOKS]
                [--post-hooks POST_HOOKS] [-i ID] [-d DIRECTORY] [-f] [-v]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Configuration file
  --cache DIRECTORY     The local cache/work directory
  --pre-hooks PRE_HOOKS
                        Pre-update script hooks directory
  --post-hooks POST_HOOKS
                        Post-update script hooks directory
  -r DIRECTORY, --remote REPOSITORY
                        Remote repository
  -l DIRECTORY, --local DIRECTORY
                        Local directory
  -f, --fetch           Fetch config once and exit
  -v, --verbose         Verbose logging for debugging
```

### /etc/repo-deploy/repo-deploy.cfg options:

Option | Value
-------|-------
*remote* | The configuration repository URL. Currently supports `s3`, `http(s)`, and `git` (see below for details)
*local* | The local repository directory
*schedule* | A cron-like schedule string that configures when the deployer will check for updates (ignored if run with `-f`)

### Repository formats

#### HTTP/S repositories

HTTP repositories should provide the URL to a ZIP file, whose contents will be extracted to the local
repository directory.

#### S3 repositories

S3 repositories have the same structure of HTTP repositories, but the URL should be of the
form `s3://bucket/path/to/app.zip`. For non-public buckets, you can specify credentials in several
different ways:

1. Use IAM instance roles to automatically provide credentials (preferred)

2. Save the credentials to `~deploy/.amazon/account-key`, with the following format:

```
accessKey=XXX
secretKey=XXX
```

3. Specify the access key and secret key in `/etc/repo-deploy/repo-deploy.cfg`

```
aws-access-key=XXX
aws-secret-key=XXX
```

#### Git repositories

Git repositories use standard Git URLs, with the added ability to specify a specfic
directory and branch to clone.

URL structure:
```
user@github.com:barchart/app.git/path#branch
```

If `/path` or `#branch` are omitted, repo-deploy defaults to cloning the root of the
`master` branch.

### Pre/Post update hooks

For application-specific update processes, you can bundle pre-and-post-update hook scripts
in the deployer machine image. These scripts go in `/etc/repo-deploy/pre-update.d` and
`/etc/repo-deploy/post-update.d`. Any executable file in these directories will be run before or
after a code update happens.

#### Environment variables

Two environment variables are passed to script hooks to allow hooks to intelligently compare
configuration changes:

* `CURRENT_CONFIG` The current (new) configuration directory
* `PREVIOUS_CONFIG` The previous (existing) configuration directory

#### Return values

A non-zero return value indicates that the current update should be blocked (for pre-update
hooks) or reverted (for post-update hooks). The update will be tried again on the next
scheduled check (default 60 seconds.)  This behavior should only be used in exceptional cases
(i.e. the app is in an unstable state) rather than as a scheduling mechanism. Scheduling
should be handled by cron (with `-f` command line parameter) or the "schedule" configuration
 variable.

#### Use cases 

Pre-update hooks can be used to:

* block updates until the application is in an updatable state
* acquire a distributed update lock to facilitate rolling updates in a cluster

Post-update hooks can be used to:

* move files to the correct locations
* reload/restart the application
* verify service health
* release a distributed rolling update lock
