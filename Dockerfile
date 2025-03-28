FROM 3.13.2-alpine3.21

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


COPY ./src .

EXPOSE 8080

CMD [ "python", "main.py" ]