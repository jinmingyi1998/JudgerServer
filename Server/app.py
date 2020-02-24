import json
import multiprocessing
import os
import shutil
import zipfile
from pathlib import Path
from time import sleep

import flask
import psutil
import requests
from flask import request, redirect, session, url_for
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.wsgi import WSGIContainer
from werkzeug.utils import secure_filename

from cleaner import delfile
from exception import CompileError
from judger import Judger, Compiler

app = flask.Flask(__name__)

SERVICE_PORT = int(os.getenv('SERVICE_PORT', "5001"))
BASE_DIR = '/ojdata'
TMP_DIR = "/tmp/judger"
PASSWORD = os.getenv('PASSWORD', 'iAMaPASSWORD')
OJ_BACKEND_CALLBACK = os.getenv('OJ_BACKEND_CALLBACK', None)
assert OJ_BACKEND_CALLBACK is not None, "ENV: OJ_BACKEND_CALLBACK must be set!"

app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB
app.config['SESSION_TYPE'] = 'memcached'
app.config['SECRET_KEY'] = PASSWORD

'''
test json:
{
    "submit_id": 3,
    "problem_id": 1,
    "max_cpu_time": 1000,
    "max_memory": 11111960,
    "src": "main.cpp",
    "seccomp_rule": "c_cpp",
    "run_command": "./main",
    "compile_command": "/usr/bin/g++ main.cpp -o main",
    "source": "#include<stdio.h>\nint main()\n{\n\tint a,b;\n\tscanf(\"%d %d\",&a,&b);\n\tprintf(\"%d\\n\",a+b);\n}\n"
}
'''


def start_up():
    if not os.path.exists(BASE_DIR):
        print("mkdir", BASE_DIR)
        os.mkdir(BASE_DIR)
    if not os.path.exists(TMP_DIR):
        print("mkdir", TMP_DIR)
        os.makedirs(TMP_DIR)
    p = multiprocessing.Process(target=delfile, args=(TMP_DIR,))
    p.start()


def run(judger, compiler):
    try:
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
            print(str(e))
            res['err'] = "ERR"
            res['info'] = "System Broken"
        return res
    except KeyboardInterrupt:
        pass


def send_callback(run_result):
    try:
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
                sleep(10)
    except KeyboardInterrupt:
        pass


def callback(run_result):
    print(run_result)
    network_pool.apply_async(send_callback, (run_result,))


@app.route('/favicon.ico')
@app.route('/ping')
def ping():
    return "pong"


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == PASSWORD:
            session['is_login'] = True
            return redirect(url_for('upload_home'))
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
    print("run problem id:", problem_id)
    source = data['source']
    judge_dir = os.path.join(TMP_DIR, str(submit_id))  # temp directory for running
    data_dir = os.path.join(BASE_DIR, str(problem_id))  # standard input output file, read only
    if os.path.exists(judge_dir):
        shutil.rmtree(judge_dir)
    os.makedirs(judge_dir)
    with open(os.path.join(judge_dir, data['src']), mode='w+', encoding='utf-8') as f:
        f.write(source)
    compiler = Compiler(data['compile_command'], judge_dir)
    spj = False
    if os.path.exists(os.path.join(data_dir, "spj")) or \
            os.path.exists(os.path.join(data_dir, "spj.py")):
        spj = True
    judger = Judger(data['max_cpu_time'],
                    data['max_memory'],
                    data['run_command'],
                    data.get('seccomp_rule'),
                    judge_dir,
                    1 if data.get('memory_limit_check_only') else 0
                    , data_dir, submit_id, spj)
    judge_pool.apply_async(run, (judger, compiler), callback=callback)
    return "success"


def allowed_file(filename):
    return '.' in filename and \
           filename.split('.')[-1] in ['zip']


def unzip_file(zip_src, dst_dir):
    if zipfile.is_zipfile(zip_src):
        fz = zipfile.ZipFile(zip_src, 'r')
        for file in fz.namelist():
            fz.extract(file, dst_dir)
    else:
        print('This is not zip')


@app.route('/upload')
def upload_home():
    if session.get('is_login', False) == False:
        return redirect('/login')
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <p>change the url to  /upload/{id}.</p>
    <p>for example:  /upload/1   will upload to directory 1</p>
    <p>请直接修改url为 /upload/{id}， 比如/upload/1 将会上传至目录 1</p>
    <p>上传的文件必须为zip，zip内深度必须为0</p>
    <p>标准输入文件后缀为 .in  标准输出文件后缀为 .out </p>
    <p>Special Judge程序必须为 spj.* , 推荐上传源代码,支持 spj.c spj.cpp spj.py（为Python3）</p>
    <p>目录下如果有spj则启用Special Judge，程序输出将作为标准输入输入到spj,spj标准输出0 为AC，其他为WA</p> 
    '''


def check_spj(upload_dir):
    dir = Path(upload_dir)
    for filename in dir.glob("spj.*"):
        if filename.suffix not in ['.c', '.cpp', '.py']:
            continue
        compile_command = {
            ".c": "/usr/bin/g++ -fno-tree-ch -O2 -Wall -std=c++14 spj.c -lm -o spj",
            ".cpp": "/usr/bin/g++ -fno-tree-ch -O2 -Wall -std=c++14 spj.cpp -lm -o spj",
            ".py": "/usr/bin/python3 -m py_compile spj.py"
        }
        compiler = Compiler(compile_command.get(filename.suffix),
                            upload_dir)
        try:
            compiler()
        except CompileError as ce:
            return ce.message
        break
    return "ok"


@app.route('/upload/<int:post_id>', methods=['GET', 'POST'])
def upload_view(post_id):
    if session.get('is_login', False) == False:
        return redirect('/login')
    if request.method == 'POST':
        # 获取post过来的文件名称，从name=file参数中获取
        file = request.files['file']
        print(file.filename)
        suffix = file.filename.split('.')[-1]
        if file and suffix in ['zip']:
            upload_dir = os.path.join(BASE_DIR, str(post_id))
            file_name = os.path.join(upload_dir, secure_filename(file.filename))
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir)
            os.makedirs(upload_dir)
            file.save(file_name)
            unzip_file(file_name, upload_dir)
            os.remove(file_name)
            compile_out = check_spj(upload_dir)
            if compile_out != 'ok':
                return "compile error:" + compile_out
            return redirect('/upload')
        else:
            return "文件格式错误"
    return '''
     <!doctype html>
     <title>Upload new File</title>
     <h3>Upload new File</h1>
     <p>上传的文件必须为zip，zip内深度必须为0</p>
    <p>标准输入文件后缀为 .in  标准输出文件后缀为 .out </p>
    <p>Special Judge程序必须为 spj.* , 推荐上传源代码,支持 spj.c spj.cpp spj.py（为Python3）</p>
    <p>目录下如果有spj则启用Special Judge，程序输出将作为标准输入输入到spj,spj标准输出0 为AC，其他为WA</p>
     <form action="" method=post enctype=multipart/form-data>
     <p><input type="file" name="file" required="required" >
     <input type=submit value=Upload>
     </form>
     '''


if __name__ == "__main__":
    judge_pool = multiprocessing.Pool(psutil.cpu_count() + 1)
    network_pool = multiprocessing.Pool(100)
    try:
        start_up()
        http_server = HTTPServer(WSGIContainer(app))
        http_server.listen(SERVICE_PORT)
        IOLoop.instance().start()
    except KeyboardInterrupt as e:
        pass
    finally:
        IOLoop.instance().stop()
        judge_pool.close()
        judge_pool.join()
        network_pool.close()
        network_pool.join()
