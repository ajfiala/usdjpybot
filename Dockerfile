# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

WORKDIR /app

RUN pip3 install pandas
RUN pip3 install numpy
RUN pip3 install ta
RUN apt-get update
RUN apt-get install git -y
RUN pip3 install --upgrade git+https://github.com/yhilpisch/tpqoa.git

COPY . .

CMD [ "python3", "-u" , "MACD_bot.py"]