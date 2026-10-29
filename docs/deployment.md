# Deployment

For a production deployment, the following are required:

+ WSGI server, e.g. Gunicorn, mod_wsgi (httpd),
+ [PostgreSQL](https://www.postgresql.org/) database
+ Celery and celery beat servers running,
+ Access to a RabbitMQ server,

## Configuration

Configuration of PolarRouteServer works with environment variables, these are covered in [Configuration](configuration.md) in detail.

It is up to you how you choose to set these environment variables in your deployment.

## Setting up the database

Assuming you have a running PostgreSQL database and that the environment variables are set, particularly all of the database connection settings and `DJANGO_SETTINGS_MODULE` run:

```shell
$ django-admin migrate
```

to build the database.

When running this for the first time, you may need to point to your `DJANGO_SETTINGS_MODULE`:

```shell
export DJANGO_SETTINGS_MODULE=polarrouteserver.settings.development
```

## Create a superuser in the database

Run the following and follow the prompts.

```shell
$ django-admin createsuperuser
```

## Management of a deployment

All of the commands used for administration of a Django project are available post-installation via the `django-admin` command. Note that the envrionment variables used will need to be set in the session which you're running these commands.

Note that the same commands can be run by running `python manage.py` where `manage.py` is the file contained in the top level of the repository.

Of particular interest in production are:

```shell
$ django-admin makemigrations # create new migrations files based on changes to models
$ django-admin migrate # apply new migrations files to alter the database
$ django-admin dbshell # open the database's command line interface
```

To see more commands, run `django-admin --help`.

In addition a custom command is available to manually insert new meshes into the database from file:

```shell
$ django-admin insert_mesh <Mesh file or list of files>
```

`insert_mesh` takes a filename or list of filepaths containing environment or vehicle meshes, as `.json` files or gzipped `.json.gz` files.

Only meshes which are not present in the database will be inserted. Uniqueness is based on the md5 hash of the mesh json.

## Configuring a web server

PolarRoute-server can be served similarly to any other Django application, see [Django docs for more information](https://docs.djangoproject.com/en/5.1/howto/deployment/). Or see the instructions for httpd/mod_wsgi below.

## Configuring mod_wsgi

If you are using mod_wsgi to serve PolarRoute-server under httpd, a typical `.conf` file may look something like:

```
<VirtualHost *:443>
ServerName polarroute.myserver.com
DocumentRoot /path/to/my/polarrouteserver/
LogLevel info
SSLEngine on
SSLCertificateFile /local/certs/myserver.com.pem

    PassEnv DJANGO_SETTINGS_MODULE
    PassEnv POLARROUTE_MESH_DIR
    PassEnv POLARROUTE_MESH_METADATA_DIR
    PassEnv POLARROUTE_ALLOWED_HOSTS
    PassEnv POLARROUTE_CORS_ALLOWED_ORIGINS
    PassEnv POLARROUTE_STATIC_ROOT
    PassEnv CELERY_BROKER_URL
    PassEnv CELERYD_CHDIR
    PassEnv POLARROUTE_DEBUG
    PassEnv POLARROUTE_LOG_DIR
    PassEnv POLARROUTE_BASE_DIR
    PassEnv POLARROUTE_LOG_LEVEL

    PassEnv POLARROUTE_DB_NAME
    PassEnv POLARROUTE_DB_USER
    PassEnv POLARROUTE_DB_PASSWORD
    PassEnv POLARROUTE_DB_HOST

WSGIDaemonProcess polarroute.myserver.com user=wsgi group=wsgi threads=5 python-home=/path/to/my/python/home python-path=/path/to/my/python/path
WSGIProcessGroup polarroute.myserver.com
WSGIApplicationGroup %{GLOBAL}
WSGIScriptAlias / /path/to/my/polarrouteserver//wsgi.py
Alias /static /var/www/polarroute.myserver.com/static
CustomLog /var/log/httpd/access_log.polarroute.myserver.com combined
ErrorLog /var/log/httpd/error_log.polarroute.myserver.com

<Location />
Require all granted
</Location>
</VirtualHost>

<Directory "/path/to/my/polarrouteserver/">
AllowOverride All
Options -Indexes
Require all granted
WSGIScriptReloading On
WSGIProcessGroup polarroute.myserver.com
WSGIApplicationGroup %{GLOBAL}

</Directory>

<Directory /var/www/polarroute.myserver.com/static/>
Order allow,deny
Allow from all
</Directory>

```

## Collecting static files

PolarRoute-server itself has no static files since it is a headless server, however it does make use of Django's `/admin` endpoint as a database management dashboard. For this to work, we need to create a static file location, e.g. `/var/www/polarroute.{{ hostname }}/static` and run the following commands (noting to use the correct path to your static file location):

```shell
export DJANGO_SETTINGS_MODULE=polarrouteserver.settings.production
export POLARROUTE_STATIC_ROOT=/var/www/polarroute.myserver.com/static/
django-admin collecstatic
```

This only needs to be run once.

## Other recommendations

It is also recommended to do the following in a deployment:

+ Add polarrouteserver and celery logs to logrotate - logfiles are written from polarrouteserver and celery to files in `POLARROUTE_LOG_DIR`, it is prudent to add these to a log rotation utility such as logrotate.
+ Manage Celery, Celerybeat and rabbitmq under systemd.
