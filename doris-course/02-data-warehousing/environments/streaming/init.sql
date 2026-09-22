-- Local disposable course fixture only. Never reuse these credentials elsewhere.
CREATE DATABASE course_cdc;
CREATE USER 'course_cdc'@'%' IDENTIFIED BY 'course_cdc_local_only';
GRANT SELECT, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'course_cdc'@'%';
CREATE TABLE course_cdc.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    order_amount DECIMAL(18,2) NOT NULL
);
