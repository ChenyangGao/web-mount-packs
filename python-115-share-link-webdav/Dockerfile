# Dockerfile for https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-share-link-webdav
# Build:
#   docker build --rm -t chenyanggao/python-115-share-link-webdav .
# Run (for the first time to scan qrcode):
#   docker run --rm -it -p <PORT>:8080 -v <WORKDIR_FOLDER>:/etc/python-115-share-link-webdav chenyanggao/python-115-share-link-webdav
# Run (runing in the background):
#   docker run -d -p <PORT>:8080 -v <WORKDIR_FOLDER>:/etc/python-115-share-link-webdav --restart=always chenyanggao/python-115-share-link-webdav
# for example
#   docker run --rm -it -p 8080:8080 -v ~/python-115-share-link-webdav:/etc/python-115-share-link-webdav chenyanggao/python-115-share-link-webdav
# Then open (or enter) this URL in web browser or Windows File Explorer or any other WebDAV client:
#   http://localhost:8080/
# and edit configuration files in the directory:
#   ~/python-115-share-link-webdav

FROM python:3-alpine

COPY . /app

#dependencies
RUN apk add --no-cache --virtual .build-deps gcc libxml2-dev libxslt-dev musl-dev py3-pip \
    && pip3 install --no-cache-dir lxml \
    && pip3 install --no-cache-dir -r /app/requirements.txt \
    && apk del .build-deps gcc musl-dev

RUN mkdir -p /etc/python-115-share-link-webdav
WORKDIR /etc/python-115-share-link-webdav

EXPOSE 8080

ENTRYPOINT ["python3"]
CMD ["/app/__main__.py", "-w"]
