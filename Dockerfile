FROM pytradfri:latest

COPY ./tradfri-telegraf.py /usr/src/app/
COPY ./requirements.txt /usr/src/app/

RUN /usr/bin/pip3 install -r /usr/src/app/requirements.txt
RUN pip3 install pytradfri[async]

WORKDIR /data
ENV PYTHONPATH $PYTHONPATH:/usr/local/lib/python3.7/dist-packages
CMD python3 /usr/src/app/tradfri-telegraf.py
