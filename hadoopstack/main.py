import os
from flask import Flask
from hadoopstack.api.v1 import app_v1

app = Flask(__name__)
app.register_blueprint(app_v1)

@app.route('/')
def default():
    return "Current API is v1 accessible on url prefix /v1"

if __name__ == '__main__':
    app.run(host='0.0.0.0')

if not app.debug:
    import logging
    from logging import FileHandler
    file_handler = FileHandler("error.txt")
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)