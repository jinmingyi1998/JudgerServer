import logging
import os
import shutil
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(filename)s %(lineno)d %(levelname)s : %(message)s')


def delfile(file_url):
    while True:
        logging.info("delete temp files...")
        for f in os.listdir(file_url):
            filedate = os.path.getmtime(os.path.join(file_url, f))
            date1 = time.time()
            delta = (date1 - filedate) / 60 / 60 / 24
            if delta >= 7:  # 删除7天以上的目录
                try:
                    shutil.rmtree(os.path.join(file_url, f))
                except Exception as e:
                    logging.error(str(e))
        time.sleep(60 * 60 * 24)
