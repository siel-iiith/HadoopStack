from flask import Blueprint, request, jsonify

from hadoopstack.services.cluster import make_connection
from hadoopstack.services.cluster import spawn_instances

app_v1 = Blueprint('v1', __name__, url_prefix='/v1')

@app_v1.route('/')
def version():
    return "v1 API. Jobs and clusters API are accessible at /jobs and \
    /clusters respectively"

@app_v1.route('/clusters/', methods = ['GET','POST'])
def clusters():
    if request.method == 'POST':
        data = request.json
        num_tt = int(data['cluster']['node-recipes']['tasktracker'])
        num_jt = int(data['cluster']['node-recipes']['jobtracker'])        
        num_vms = num_jt + num_tt
        conn=make_connection()
        spawn_instances(conn,num_vms)
            
        return jsonify(**request.json)    
        
    return "To be implemented"

