ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip py3-flask py3-requests

WORKDIR /app

COPY poller.py app.py run.sh ./
COPY static/ ./static/

RUN chmod +x run.sh
RUN mkdir -p /data

CMD ["/app/run.sh"]
