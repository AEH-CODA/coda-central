# Use the official Vantage6 base image for algorithms
FROM harbor2.vantage6.ai/infrastructure/algorithm-base:4.2

# Name of your Python package (must match your setup.py name)
ARG PKG_NAME="v6_logistic_regression_py"

# Copy all code into the image
COPY . /app

# Install your algorithm as a Python package
RUN pip install /app

# Set the environment variable and define default run command
ENV PKG_NAME=${PKG_NAME}
CMD python -c "from vantage6.algorithm.tools.wrap import wrap_algorithm; wrap_algorithm()"
