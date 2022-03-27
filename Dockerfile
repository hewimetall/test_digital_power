FROM python:3.10 As pre_build
RUN pip install --no-cache-dir poetry

FROM pre_build
WORKDIR /code
COPY poetry.lock pyproject.toml ./
RUN poetry install

COPY ./ /code/app
