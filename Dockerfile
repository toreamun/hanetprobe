FROM python:3-alpine

WORKDIR /app

COPY src .
COPY LICENSE .
COPY requirements.txt requirements.txt
RUN pip install --trusted-host pypi.python.org -r requirements.txt

CMD [ "python", "probe_app.py", "config/probe.yaml" ]