FROM apache/superset:4.1.2
USER root
RUN sed -i "s|http://deb.debian.org|https://deb.debian.org|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir 'pydoris==1.1.0' 'SQLAlchemy==1.4.52' 'PyMySQL==1.1.1' 'mysqlclient==2.2.7'
COPY superset_config.py start.sh init_admin.py /app/course/
USER superset
ENV SUPERSET_CONFIG_PATH=/app/course/superset_config.py
CMD ["/bin/sh", "/app/course/start.sh"]
