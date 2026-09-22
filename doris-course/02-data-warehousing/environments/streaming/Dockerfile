FROM flink:1.20.1-scala_2.12-java11
USER root
RUN mkdir -p /opt/flink/state && chown flink:flink /opt/flink/state
ADD --chown=flink:flink https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-mysql-cdc/3.4.0/flink-sql-connector-mysql-cdc-3.4.0.jar /opt/flink/lib/
ADD --chown=flink:flink https://repo.maven.apache.org/maven2/org/apache/doris/flink-doris-connector-1.20/25.0.0/flink-doris-connector-1.20-25.0.0.jar /opt/flink/lib/
ADD --chown=flink:flink https://repo.maven.apache.org/maven2/mysql/mysql-connector-java/8.0.27/mysql-connector-java-8.0.27.jar /opt/flink/lib/
USER flink
