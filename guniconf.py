import multiprocessing
from os import environ

proc_name = 'cloudControl'
bind = '0.0.0.0:' + environ.get('PORT','5000')
workers = multiprocessing.cpu_count()*2 + 1
worker_class = 'eventlet'
accesslog = '/var/log/cloudControl/access.log'
access_log_format = '%(t)s %(l)s %(h)s %(u)s "%(r)s" %(s)s %(b)s "%(a)s" %(L)s secs %(message)s'
errorlog = '/var/log/cloudControl/error.log'
reload = True