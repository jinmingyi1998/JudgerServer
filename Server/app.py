import shutil

import flask
from flask import request
import os
import multiprocessing
import requests
import psutil
import json
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.wsgi import WSGIContainer

from exception import CompileError
from judger import Judger, Compiler

app = flask.Flask(__name__)

SERVICE_PORT = int(os.getenv('SERVICE_PORT', "5001"))
BASE_DIR = os.getenv('DATA_DIR', '/ojdata')
TMP_DIR = "/tmp/judger"

OJ_BACKEND_CALLBACK = os.getenv('OJ_BACKEND_CALLBACK', None)
assert OJ_BACKEND_CALLBACK is not None, "ENV: OJ_BACKEND must be set!"


def start_up():
    if not os.path.exists(BASE_DIR):
        os.mkdir(BASE_DIR)
    if not os.path.exists(TMP_DIR):
        os.makedirs(TMP_DIR)


def run(judger, compiler):
    res = {"submit_id": judger.submit_id}
    try:
        compiler()
    except CompileError as ce:
        res['err'] = "CE"
        res['info'] = ce.message
        return res
    try:
        res['results'] = judger()
        if len(res['results'])==0:
            res["err" ] = "ERR"
            res['info']="No Data"
            print(res,"No data ERROR")
    except Exception as e:
        res['err'] = "ERR"
        res['info'] = "System Broken"
    return res


def callback(run_result):
    try:
        headers = {'Content-Type': 'application/json'}
        with requests.post(OJ_BACKEND_CALLBACK, headers=headers, data=json.dumps(run_result)) as r:
            print(json.dumps(run_result))
            assert r.content.decode('utf-8')=='success'
    except Exception as e:
        print("callback failed", str(e))


@app.route('/favicon.ico')
@app.route('/ping')
def ping():
    return "pong"


@app.route('/judge', methods=['POST'])
def judge():
    data = request.json
    submit_id = data['submit_id']
    problem_id = data['problem_id']
    source = data['source']
    judge_dir = os.path.join(TMP_DIR, str(submit_id))
    data_dir = os.path.join(BASE_DIR, str(problem_id))
    if os.path.exists(judge_dir):
        shutil.rmtree(judge_dir)
    os.makedirs(judge_dir)
    with open(os.path.join(judge_dir, data['src']), mode='w+', encoding='utf-8') as f:
        f.write(source)
    compiler = Compiler(data['compile_command'], judge_dir)
    judger = Judger(data['max_cpu_time'],
                    data['max_memory'],
                    data['run_command'],
                    data['seccomp_rule'],
                    judge_dir,
                    1 if data.get('memory_limit_check_only') else 0
                    , data_dir, submit_id, False)
    judge_pool.apply_async(run, (judger, compiler), callback=callback)
    return "success"


if __name__ == "__main__":
    judge_pool = multiprocessing.Pool(psutil.cpu_count())
    start_up()
    try:
        http_server = HTTPServer(WSGIContainer(app))
        http_server.listen(SERVICE_PORT)
        IOLoop.instance().start()
    except KeyboardInterrupt as e:
        pass
    judge_pool.close()
    judge_pool.join()
