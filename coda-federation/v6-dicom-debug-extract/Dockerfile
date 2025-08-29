
FROM harbor2.vantage6.ai/infrastructure/algorithm-base:4.2
ARG PKG_NAME="v6_dicom_query"
COPY . /app
RUN pip install /app
ENV PKG_NAME=${PKG_NAME}
CMD python -c "from vantage6.algorithm.tools.wrap import wrap_algorithm; wrap_algorithm()"
