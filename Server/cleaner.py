import os
import shutil
import time


def delfile(file_url):
    while True:
        print("delete temp files...")
        for f in os.listdir(file_url):
            filedate = os.path.getmtime(os.path.join(file_url, f))
            date1 = time.time()
            delta = (date1 - filedate) / 60 / 60 / 24
            if delta >= 7:  # 删除7天以上的目录
                try:
                    shutil.rmtree(os.path.join(file_url, f))
                except Exception as e:
                    print(e)
        time.sleep(60 * 60 * 24)
