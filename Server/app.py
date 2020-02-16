import shutil
import zipfile
from time import sleep
import flask
from flask import request, redirect, session
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
BASE_DIR = '/ojdata'
TMP_DIR = "/tmp/judger"
PASSWORD = os.getenv('PASSWORD', '1234')
OJ_BACKEND_CALLBACK = os.getenv('OJ_BACKEND_CALLBACK', None)
assert OJ_BACKEND_CALLBACK is not None, "ENV: OJ_BACKEND_CALLBACK must be set!"
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB


def start_up():
    if not os.path.exists(BASE_DIR):
        print("mkdir",BASE_DIR)
        os.mkdir(BASE_DIR)
    if not os.path.exists(TMP_DIR):
        print("mkdir",TMP_DIR)
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
        if len(res['results']) == 0:
            res["err"] = "ERR"
            res['info'] = "No Data"
            print(res, "No data ERROR")
    except Exception as e:
        res['err'] = "ERR"
        res['info'] = "System Broken"
    return res


def callback(run_result):
    for i in range(5):
        try:
            if i > 0:
                print("retry ...")
            headers = {'Content-Type': 'application/json'}
            with requests.post(OJ_BACKEND_CALLBACK, headers=headers, data=json.dumps(run_result)) as r:
                print(json.dumps(run_result))
                assert r.content.decode('utf-8') == 'success'
                return
        except Exception as e:
            print("callback failed", str(e))
            sleep(5)


@app.route('/favicon.ico')
@app.route('/ping')
def ping():
    return "pong"


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == PASSWORD:
            session['isLogin'] = True
            return redirect('/ping')
    return '''
        <form action="" method="post">
            <p><input type=text name=password>
            <p><input type=submit value=Login>
        </form>
    '''


@app.route('/judge', methods=['POST'])
def judge():
    data = request.json
    print(data)
    submit_id = data['submit_id']
    problem_id = data['problem_id']
    print("run problem id:",problem_id)
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
                    data.get('seccomp_rule'),
                    judge_dir,
                    1 if data.get('memory_limit_check_only') else 0
                    , data_dir, submit_id, False)
    judge_pool.apply_async(run, (judger, compiler), callback=callback)
    return "success"


def allowed_file(filename):
    return '.' in filename and \
           filename.split('.')[-1] in ['zip']


def unzip_file(zip_src, dst_dir):
    r = zipfile.is_zipfile(zip_src)
    if r:
        fz = zipfile.ZipFile(zip_src, 'r')
        for file in fz.namelist():
            fz.extract(file, dst_dir)
    else:
        print('This is not zip')


@app.route('/upload')
def upload_home():
    return '''
    <!doctype html>
    <title>Upload new File</title>
    change the url to  /upload/{id}.
    for example:  /upload/1   will upload to directory 1    
    '''


@app.route('/upload/<int:post_id>', methods=['GET', 'POST'])
def upload_view(post_id):
    if request.method == 'POST':
        # 获取post过来的文件名称，从name=file参数中获取
        file = request.files['file']
        print(file.filename)
        suffix = file.filename.split('.')[-1]
        if file and suffix in ['zip']:
            upload_dir = os.path.join(BASE_DIR, str(post_id))
            file_name = os.path.join(upload_dir, file.filename)
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir)
            else:
                os.makedirs(upload_dir)
            file.save(file_name)
            unzip_file(file_name, upload_dir)
            return redirect('/upload')
    return '''
     <!doctype html>
     <title>Upload new File</title>
     <h1>Upload new File</h1>
     <form action="" method=post enctype=multipart/form-data>
     <p><input type=file name=file>
     <input type=submit value=Upload>
     </form>
     '''


if __name__ == "__main__":
    judge_pool = multiprocessing.Pool(psutil.cpu_count())
    start_up()
    try:
        http_server = HTTPServer(WSGIContainer(app))
        http_server.listen(SERVICE_PORT)
        IOLoop.instance().start()
    except KeyboardInterrupt as e:
        print("keyboard interrupt")
    judge_pool.close()
    judge_pool.join()
