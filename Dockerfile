FROM ubuntu:18.04

MAINTAINER MingyiJin

RUN chmod -R 777 /tmp && \
    rm -rf /etc/apt/sources.list.d/* && \
    rm -rf /var/lib/apt/lists/*

COPY sources.list /etc/apt/sources.list

COPY pip.conf /root/.pip/pip.conf

COPY requirement.txt /root/requirement.txt

COPY Server /root/JudgerServer

COPY Judger /root/Judger

RUN apt-get update && apt-get upgrade -y

RUN apt-get install -y vim cmake supervisor sudo htop python3 python3-pip python3-dev python openjdk-8-jdk

COPY supervisord.conf /etc/supervisord.conf

RUN pip3 install -r /root/requirement.txt

RUN apt-get install -y libseccomp-dev

RUN cd /root/Judger && mkdir build && cd build && cmake .. && make && make install && cd ../bindings/Python && python3 setup.py install

ENV TZ=Asia/Shanghai \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en

CMD supervisord