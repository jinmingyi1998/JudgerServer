# JudgerServer
Base On Judger(https://github.com/QingdaoU/Judger)

## docker
https://hub.docker.com/repository/docker/jinmingyi1998/judgerserver

## How to start
enviroment need to set:
- OJ_BACKEND_CALLBACK : the http address to send callback
- SERVICE_PORT : server port (default 5001)
- DATA_DIR : the path where the test case data is (default /ojdata) (it better be an absolute path)

for example:
```
docker pull jinmingyi1998/judgerserver:1.3
docker run -d --name judgerserver \
    -p 12345:12345 -v $OJDATA:/ojdata \
    -e OJ_BACKEND_CALLBACK=127.0.0.1:8080/callback \
    -e SERVICE_PORT=12345 jinmingyi1998/judgerserver:1.3 
```
