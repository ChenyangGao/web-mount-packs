# Dockerfile for https://github.com/ChenyangGao/web-mount-packs/tree/main/webdav-115-share-link
# Build:
#   docker build --rm -t chenyanggao/webdav-115-share-link .
# Run (for the first time to scan qrcode):
#   docker run --rm -it -p <PORT>:80 -v <WORKDIR_FOLDER>:/etc/webdav-115-share-link chenyanggao/webdav-115-share-link
# Run (runing in the background):
#   docker run -d -p <PORT>:80 -v <WORKDIR_FOLDER>:/etc/webdav-115-share-link --restart=always chenyanggao/webdav-115-share-link
# for example
#   docker run --rm -it -p 8000:80 -v ~/webdav-115-share-link:/etc/webdav-115-share-link chenyanggao/webdav-115-share-link
# Then open (or enter) this URL in web browser or Windows File Explorer or any other WebDAV client:
#   http://localhost:8000/
# and edit configuration files in the directory:
#   ~/webdav-115-share-link

FROM python:3-alpine

COPY . /app

#dependencies
RUN apk add --no-cache --virtual .build-deps gcc libxml2-dev libxslt-dev musl-dev py3-pip \
    && pip3 install --no-cache-dir lxml \
    && pip3 install --no-cache-dir -r /app/requirements.txt \
    && apk del .build-deps gcc musl-dev

RUN mkdir -p /etc/webdav-115-share-link
WORKDIR /etc/webdav-115-share-link

EXPOSE 80

ENTRYPOINT ["python3"]
CMD ["/app/__main__.py", "-w"]
