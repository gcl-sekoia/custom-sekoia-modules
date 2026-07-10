FROM python:3.11

WORKDIR /app

RUN pip install poetry

COPY poetry.lock pyproject.toml /app/
RUN poetry config virtualenvs.create false && poetry install --only main

COPY . .

RUN useradd -ms /bin/bash sekoiaio-runtime
USER sekoiaio-runtime

ENTRYPOINT [ "python", "./main.py" ]
