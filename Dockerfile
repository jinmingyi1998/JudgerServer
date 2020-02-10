FROM ubuntu:18.04

RUN chmod -R 777 /tmp && \
    rm -rf /etc/apt/sources.list.d/* && \
    rm -rf /var/lib/apt/lists/*
COPY requirement.txt /root/requirement.txt
COPY Server /root/JudgerServer
COPY supervisord.conf /etc/supervisord.conf
COPY Judger /root/Judger

RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y vim cmake supervisor sudo htop python3 python3-pip python3-dev \
    python openjdk-8-jdk gccgo libseccomp-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && pip3 install  --no-cache-dir -r /root/requirement.txt \
    && cd /root/Judger && mkdir build \
    && cd build && cmake .. && make && make install \
    && cd ../bindings/Python && python3 setup.py install \
    && rm -rf /root/Judger

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en

CMD supervisord