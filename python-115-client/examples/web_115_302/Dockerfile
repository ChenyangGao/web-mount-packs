# Dockerfile for https://github.com/ChenyangGao/web-mount-packs/tree/main/python-115-client/examples/web_115_302
# Build:
#   docker build --rm -t chenyanggao/web_115_302 .
# Run (for the first time to scan qrcode):
#   docker run --rm -it -p <PORT>:80 -v <WORKDIR_FOLDER>:/etc/web_115_302 chenyanggao/web_115_302
# Run (runing in the background):
#   docker run -d -p <PORT>:80 -v <WORKDIR_FOLDER>:/etc/web_115_302 --restart=always chenyanggao/web_115_302
# for example
#   docker run --rm -it -p 8000:80 -v ~/web_115_302:/etc/web_115_302 chenyanggao/web_115_302
# Then open (or enter) this URL in web browser or Windows File Explorer or any other WebDAV client:
#   http://localhost:8000/
# and edit configuration files in the directory:
#   ~/web_115_302

FROM python:3-alpine

COPY . /app

#dependencies
RUN apk add --no-cache --virtual .build-deps gcc libxml2-dev libxslt-dev musl-dev py3-pip \
    && pip3 install --no-cache-dir lxml \
    && pip3 install --no-cache-dir -r /app/requirements.txt \
    && apk del .build-deps gcc musl-dev

RUN mkdir -p /etc/web_115_302
WORKDIR /etc/web_115_302

EXPOSE 80

ENTRYPOINT ["python3"]
CMD ["/app/__main__.py", "--cookies-path", "115-cookies.txt"]
