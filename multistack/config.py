from os import listdir
from os.path import isfile
from os.path import join
from os.path import basename
import ConfigParser
import uuid

from multistack.dbOperations.db import flush_data_to_mongo
import multistack

def config_parser(filename = "/etc/multistack/multistack.conf"):

    config = ConfigParser.ConfigParser()
    config.read(filename)
    return config

def parse_cloud_conf(filename):

    cloud = dict()
    config = config_parser(filename)

    cloud['id'] = str(uuid.uuid4())
    cloud['name'] = basename(filename)

    for item in config.items('DEFAULT'):
        cloud[item[0]] = item[1]

    if config.has_section('auth'):
        cloud['auth'] = dict()
        for item in config.items('auth'):
            if item not in config.items('DEFAULT'):
                cloud['auth'][item[0]] = item[1]

    if config.has_section('quota'):
        cloud['quota'] = dict()
        cloud['quota']['total'] = dict()
        cloud['quota']['total']['instances'] = int(config.get('quota', 'instances'))
        cloud['quota']['total']['vcpus'] = int(config.get('quota', 'vcpus'))
        cloud['quota']['total']['ram'] = int(config.get('quota', 'ram'))

        cloud['quota']['available'] = dict()
        cloud['quota']['available'] = cloud['quota']['total']

    if config.has_section('flavors'):
        cloud['flavors'] = dict()
        for item in config.items('flavors'):
            if item not in config.items('DEFAULT'):
                flavor_name = item[0].replace('.', '_')
                cloud['flavors'][flavor_name] = dict()
                cloud['flavors'][flavor_name]['vcpus'] = int(item[1].split(',')[0])
                cloud['flavors'][flavor_name]['ram'] = int(item[1].split(',')[1])

    return cloud

def parse_multistack_conf(filename):
    conf = dict()
    conf['general'] = dict()

    config = config_parser(filename)

    for item in config.items('DEFAULT'):
        conf['general'][item[0]] = item[1]

    if config.has_section('flask'):
        conf['flask'] = dict()
        for item in config.items('flask'):
            if item not in config.items('DEFAULT'):
                conf['flask'][item[0]] = item[1]

    return conf

def set_conf(conf_dir = "/etc/multistack"):

    conf = parse_multistack_conf(join(conf_dir, 'multistack.conf'))

    cloud_dir = join(conf_dir, 'clouds')
    clouds = list()

    for cloud_file in listdir(cloud_dir):
        if cloud_file.split('.')[-1] == 'conf':
            clouds.append(parse_cloud_conf(join(cloud_dir, cloud_file)))

    conf['clouds'] = clouds
    print conf['clouds']

    multistack.main.mongo.db.conf.remove()
    flush_data_to_mongo('conf', conf)

def read_conf():
    return multistack.main.mongo.db.conf.find()[0]
