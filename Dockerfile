FROM ubuntu:18.04
COPY requirement.txt /root/requirement.txt
COPY Server /root/JudgerServer
COPY supervisord.conf /etc/supervisord.conf
COPY Judger /root/Judger

RUN chmod -R 777 /tmp && \
    rm -rf /etc/apt/sources.list.d/* && \
    rm -rf /var/lib/apt/lists/* && apt-get update \
    && apt-get install -y cmake supervisor python3 python3-pip python3-dev \
    python openjdk-8-jdk gccgo libseccomp-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir -r /root/requirement.txt \
    && cd /root/Judger && mkdir build \
    && cd build && cmake .. && make && make install \
    && cd ../bindings/Python && python3 setup.py install \
    && rm -rf /root/Judger

ENV LANG=en_US.UTF-8 \
    TZ=Asia/Shanghai \
    LC_ALL=C \
    LANGUAGE=en_US:en \
    JAVA_HOME=/usr/lib/jvm/java-1.8-openjdk \
    PATH=$JAVA_HOME/bin:${PATH} \
    CLASSPATH=$JAVA_HOME/lib \
    OJ_BACKEND_CALLBACK=http://localhost:8080/callback
VOLUME /ojdata
EXPOSE 8000

CMD supervisord