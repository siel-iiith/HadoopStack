import hadoopstack
import simplejson
    
from hadoopstack.dbOperations.db import get_node_objects
from hadoopstack.dbOperations.db import flush_data_to_mongo

from hadoopstack.services.configuration import configure_cluster
from hadoopstack.services.configuration import configure_slave
from hadoopstack.services import ec2

from bson import objectid

def spawn(data, cloud):
    """
    Generates the keypair and creates security groups specific to the
    cluster and boots the instances.

    @param data: The job document stored in mongo database.
    @type data: dict

    @param cloud: Cloud object containing information of a specific
    cloud provider.
    @type cloud: dict
    """

    image_id = cloud['default_image_id']

    data['job']['nodes'] = []
    data['job']['status'] = 'spawning'
    flush_data_to_mongo('job', data)

    job_name = data['job']['name']
    keypair_name, sec_master, sec_slave = ec2.ec2_entities(job_name)

    conn = ec2.make_connection(cloud['auth'])
    ec2.create_keypair(conn, keypair_name)
    ec2.create_security_groups(conn, sec_master, sec_slave)

    master = data['job']['master']

    res_master = ec2.boot_instances(
        conn,
        1,
        keypair_name,
        [sec_master],
        flavor = master['flavor'],
		image_id = image_id
        )

    data['job']['nodes'] += get_node_objects(conn, "master", res_master.id)
    flush_data_to_mongo('job', data)

    ec2.associate_public_ip(conn, res_master.instances[0].id)

    for slave in data['job']['slaves']:
        res_slave = ec2.boot_instances(
            conn,
            slave['instances'],
            keypair_name,
            [sec_slave],
            flavor = slave['flavor'],
			image_id = image_id
            )
        data['job']['nodes'] += get_node_objects(conn, "slave", res_slave.id)
        flush_data_to_mongo('job', data)

    return

def create(data, cloud, general_config):
    """
    Creates the cluster - provisioning and configuration

    @param data: The job document stored in mongo database.
    @type data: dict

    @param cloud: Cloud object containing information of a specific
    cloud provider.
    @type cloud: dict

    @param general_config: General configuration parameters from hadoopstack.configure_slave
    @type general_config: dict
    """

    # TODO: We need to create an request-check/validation filter before inserting

    spawn(data, cloud)
    configure_cluster(data, cloud['user'], general_config)
    
    return

def delete(cid, cloud):
    """
    Deletes the cluster

    @param cid: Cluster ID
    @type data: string

    @param cloud: Cloud object containing information of a specific
    cloud provider.
    @type cloud: dict
    """

    job_info = hadoopstack.main.mongo.db.job.find({"_id": objectid.ObjectId(cid)})[0]['job']
    job_name = job_info['name']

    conn = ec2.make_connection(cloud['auth'])

    keypair = 'hadoopstack-' + job_name
    security_groups = ['hadoopstack-' + job_name + '-master', 
        'hadoopstack-' + job_name + '-slave']

    '''
    
    Instances take a while to terminate, till then their status is
    'shutting-down'. Complete termination is required for deletion  of
    Security Groups. Hence, we use a loop to verify complete termination.

    '''
    
    flag = True
    public_ips = []

    while flag:
        flag = False
        for res in conn.get_all_instances():
            for instance in res.instances:
                for node in job_info['nodes']:
                    if instance.id == str(node['id']):
                        try:
                            if instance.ip_address != instance.private_ip_address:
                                if instance.ip_address not in public_ips:
                                    public_ips.append(str(instance.ip_address))
                            instance.terminate()
                        except:
                            pass
                        flag = True
                        continue

    print "Terminated Instances"

    try:
        for kp in conn.get_all_key_pairs(keynames = [keypair]):
            kp.delete()

        print "Terminated keypairs"

    except:
        print "Error while deleting Keypair"

    try:
        for sg in conn.get_all_security_groups(groupnames = security_groups):
            print sg.delete() 
        
        print "Terminated Security Groups"

    except:
        print "Error while deleting Security Groups"

    ec2.release_public_ips(conn, public_ips)

    return True


def list_clusters():
    clusters_dict = {"clusters": []}
    for i in list(hadoopstack.main.mongo.db.job.find()):
        clusters_dict["clusters"].append(i['cluster'])
    return clusters_dict

def add_nodes(data, cloud, job_id, general_config):
    """
    Add nodes to a cluster and updates the job object

    @param data: The job document stored in mongo database.
    @type data: dict

    @param cloud: Cloud object containing information of a specific
    cloud provider.
    @type cloud: dict

    @param job_id: Job ID
    @type job_id: string

    @param general_config: General config parameters of hadoopstack
    @type general_config: dict
    """

    conn = ec2.make_connection(cloud['auth'])

    job_db_item = hadoopstack.main.mongo.db.job.find_one({"_id": objectid.ObjectId(job_id)})
    job_obj = job_db_item['job']
    job_name = job_obj['name']
    new_node_obj_list = list()

    keypair_name, sec_master, sec_slave = ec2.ec2_entities(job_name)
    key_location = '/tmp/'  + keypair_name + '.pem'

    for slave in data['slaves']:
        res_slave = ec2.boot_instances(
                conn,
                slave['instances'],
                keypair_name,
                [sec_master],
                slave['flavor'],
                cloud['default_image_id']
                )

        # Incrementing the number of slaves in job object
        for count in range (0, len(job_obj['slaves'])):
            if slave['flavor'] == job_obj['slaves'][count]['flavor']:
                job_obj['slaves'][count]['instances'] += 1

        node_obj = get_node_objects(conn, "slave", res_slave.id)
        job_obj['nodes'] += node_obj
        new_node_obj_list += node_obj
        job_db_item['job'] = job_obj
        flush_data_to_mongo('job', job_db_item)

    for new_node_obj in new_node_obj_list:
        configure_slave(new_node_obj['private_ip_address'],
                        key_location, job_name, cloud['user'],
                        general_config['chef_server_hostname'],
                        general_config['chef_server_ip'])

def remove_nodes(data, cloud, job_id):
    """
    Removes Nodes from a running cluster and updates the Job object.

    @param data: The job document stored in mongo database.
    @type data: dict

    @param cloud: Cloud object containing information of a specific
    cloud provider.
    @type cloud: dict

    @param job_id: Job ID
    @type job_id: string
    """

    conn = ec2.make_connection(cloud['auth'])

    job_db_item = hadoopstack.main.mongo.db.job.find_one({"_id": objectid.ObjectId(job_id)})
    job_obj = job_db_item['job']

    for slave in data['slaves']:
        for node in job_obj['nodes']:
            if slave['flavor'] == node['flavor'] and node['role'] != 'master':
                conn.terminate_instances(node['id'].split())
                slave['instances'] -=1
                job_obj['nodes'].remove(node)
            if slave['instances'] == 0:
                break

    # Decrementing the number of slaves in job object
    for count in range (0, len(job_obj['slaves'])):
        if slave['flavor'] == job_obj['slaves'][count]['flavor']:
            job_obj['slaves'][count]['instances'] -= 1

    job_db_item['job'] = job_obj
    flush_data_to_mongo('job', job_db_item)
